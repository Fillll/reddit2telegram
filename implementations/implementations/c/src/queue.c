#include "app.h"
#include "channels.h"
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
void context_free(ErrorContext *c) {
    free(c->channel);
    free(c->link);
    c->channel = c->link = NULL;
}
static bool run_body(const App *app, const json_t *task, const json_t *filter, Metrics *metrics,
                     Error *error) {
    json_auto_t *started = JO(P("$set", JO(P("status", ji(2)), P("updated_at", jf(now()))))).p;
    int64_t modified = 0;
    TRY(db_update(app->db, "tasks", filter, started, false, false, &modified, error), false);
    STR(message) = strf("Modified %lld docs", (long long)modified);
    log_info(message, false);
    REQUIRE(!strcmp(field(task, "name"), "supply"), E_UNKNOWN_TASK, false);
    json_t *args = get(task, "args");
    const char *module = field(args, "submodule_name");
    Config *owned_config __attribute__((cleanup(auto_config_free))) = NULL;
    const Config *config = app->config;
    if (json_is_object(get(args, "config"))) {
        owned_config = config_copy(config, get(args, "config"));
        config = owned_config;
    } else if (json_is_string(get(args, "config_filename"))) {
        owned_config = config_load(field(args, "config_filename"), error);
        TRY(owned_config, false);
        config = owned_config;
    }
    Database *owned_db __attribute__((cleanup(auto_db_free))) = NULL;
    Database *db = app->db;
    if (!json_equal(get(config->values, "db"), get(app->config->values, "db"))) {
        owned_db = db_new(config, error);
        TRY(owned_db, false);
        db = owned_db;
    }
    App job = {config, db, app->videos, app->reporter};
    ErrorContext context __attribute__((cleanup(context_free))) = {0};
    if (app_supply(&job, module, metrics, &context, error))
        return true;
    if (!error->kind)
        error_set(error, E_IO, 0);
    reporter_capture(app->reporter, *error, module);
    Error ignored = {0};
    if (!report_developer(&job, module, &context, *error, metrics, &ignored)) {
        STR(log) = strf("developer reporting failed for %s", module);
        log_info(log, true);
    }
    return false;
}
void app_run_job(const App *app, const json_t *task) {
    json_t *args = get(task, "args");
    STR(id) = id_string(get(task, "_id"));
    Metrics *metrics = metrics_begin(app->config->root, id, field(args, "submodule_name"),
                                     get(task, "created_at"));
    Error outcome = {0};
    json_auto_t *filter = JO(P("_id", jr(get(task, "_id")))).p;
    bool ok = run_body(app, task, filter, metrics, &outcome);
    if (ok) {
        json_auto_t *update = JO(P("$set", JO(P("status", ji(3)), P("updated_at", jf(now()))))).p;
        int64_t modified = 0;
        ok = db_update(app->db, "tasks", filter, update, false, false, &modified, &outcome);
        if (ok) {
            STR(log) = strf("Modified %lld docs", (long long)modified);
            log_info(log, false);
            log_info("Task supply successfully executed.", false);
        }
    }
    if (!ok) {
        if (!outcome.kind)
            outcome.kind = E_IO;
        STR(log) = strf("Task supply failed: %s", error_name(outcome));
        log_info(log, true);
        Error status_error = {0};
        json_auto_t *update = JO(P("$set", JO(P("status", ji(4)), P("updated_at", jf(now()))))).p;
        int64_t modified = 0;
        if (!db_update(app->db, "tasks", filter, update, false, false, &modified, &status_error))
            outcome = status_error;
        else {
            STR(line) = strf("Modified %lld docs", (long long)modified);
            log_info(line, false);
        }
    }
    metrics_finish(metrics, outcome);
    metrics_free(metrics);
}
bool app_supply(const App *app, const char *module, Metrics *metrics, ErrorContext *context,
                Error *error) {
    long_sleep(.2);
    CHANNEL(channel) = channel_resolve(app, module, error);
    TRY(channel, false);
    free(context->channel);
    context->channel = json_is_string(channel->destination) ? xstrdup(text(channel->destination))
                                                            : dump_json(channel->destination);
    if (!channel->requires_submission) {
        SENDER(sender) =
            sender_new(app->config, app->db, channel->destination, metrics, app->videos);
        Supply result;
        return channel_maintenance(app, module, sender, &result, error);
    }
    const char *ranks[] = {"hot", "new", "top"};
    size_t rankings = channel->ranking ? 1 : 3;
    for (size_t rank = 0; rank < rankings; rank++) {
        free(context->link);
        context->link = NULL;
        REDDIT(reddit) = reddit_new(app->config, metrics);
        SENDER(sender) =
            sender_new(app->config, app->db, channel->destination, metrics, app->videos);
        STR(after) = NULL;
        size_t scanned = 0;
        bool reached = false, stop = false;
        while (scanned < channel->limit && !stop) {
            json_auto_t *page = NULL;
            for (int attempt = 0; attempt < 10; attempt++) {
                Error retry = {0};
                page = reddit_listing(reddit, channel->subreddit,
                                      channel->ranking ? channel->ranking : ranks[rank],
                                      channel->limit, after, &retry);
                if (page)
                    break;
                if (attempt == 9) {
                    *error = retry;
                    return false;
                }
                metrics_count(metrics, "reddit_listing_retries", 1);
                long_sleep(2.818281828 * M_PI / 2);
            }
            json_t *items = get(get(page, "data"), "children");
            REQUIRE(json_is_array(items), E_REDDIT, false);
            if (!json_array_size(items))
                break;
            size_t index;
            json_t *item;
            json_array_foreach(items, index, item) {
                if (scanned >= channel->limit)
                    break;
                scanned++;
                json_t *submission = get(item, "data");
                STR(link) = strf("https://redd.it/%s", field(submission, "id"));
                free(context->link);
                context->link = xstrdup(link);
                bool seen = false, blocked = false;
                TRY(sender_seen(sender, link, &seen, error), false);
                if (seen)
                    continue;
                TRY(sender_error_limit(sender, link, &blocked, error), false);
                if (blocked)
                    continue;
                Supply result;
                TRY(channel_post(app, module, channel, submission, sender, reddit, &result, error),
                    false);
                reached = true;
                switch (result) {
                case SUPPLY_SENT:
                    TRY(sender_mark(sender, link, true, error), false);
                    stop = true;
                    break;
                case SUPPLY_REJECT:
                    TRY(sender_mark(sender, link, false, error), false);
                    break;
                case SUPPLY_SKIP:
                    break;
                case SUPPLY_STOP:
                    stop = true;
                    break;
                }
                if (stop)
                    break;
            }
            free(after);
            after = json_is_string(get(get(page, "data"), "after"))
                        ? xstrdup(field(get(page, "data"), "after"))
                        : NULL;
            if (!after)
                break;
        }
        if (reached)
            break;
    }
    free(context->link);
    context->link = NULL;
    return clean_files(app->config,
                       json_is_string(channel->destination) ? text(channel->destination) : "", NULL,
                       error);
}
typedef struct Job {
    App app;
    json_t *task;
    struct Job *next;
} Job;
typedef struct {
    pthread_mutex_t lock;
    pthread_cond_t ready;
    pthread_t *threads;
    size_t started, pending;
    bool closing;
    Job *first, *last;
} Workers;
static void *worker_main(void *data) {
    Workers *w = data;
    for (;;) {
        pthread_mutex_lock(&w->lock);
        while (!w->first && !w->closing)
            pthread_cond_wait(&w->ready, &w->lock);
        if (!w->first && w->closing) {
            pthread_mutex_unlock(&w->lock);
            return NULL;
        }
        Job *job = w->first;
        w->first = job->next;
        if (!w->first)
            w->last = NULL;
        pthread_mutex_unlock(&w->lock);
        app_run_job(&job->app, job->task);
        json_decref(job->task);
        free(job);
        pthread_mutex_lock(&w->lock);
        w->pending--;
        pthread_mutex_unlock(&w->lock);
    }
}
static size_t worker_count(Workers *w) {
    pthread_mutex_lock(&w->lock);
    size_t count = w->pending;
    pthread_mutex_unlock(&w->lock);
    return count;
}
static void workers_free(Workers *w) {
    if (!w)
        return;
    STR(message) = strf("Stopped claiming tasks; draining %zu pending jobs", worker_count(w));
    log_info(message, false);
    pthread_mutex_lock(&w->lock);
    w->closing = true;
    pthread_mutex_unlock(&w->lock);
    pthread_cond_broadcast(&w->ready);
    for (size_t i = 0; i < w->started; i++)
        pthread_join(w->threads[i], NULL);
    free(w->threads);
    pthread_cond_destroy(&w->ready);
    pthread_mutex_destroy(&w->lock);
    free(w);
}
static void auto_workers_free(Workers **w) {
    workers_free(*w);
}
static Workers *workers_new(size_t count, Error *error) {
    Workers *w = xcalloc(1, sizeof(*w));
    if (pthread_mutex_init(&w->lock, NULL)) {
        free(w);
        error_set(error, E_IO, 0);
        return NULL;
    }
    if (pthread_cond_init(&w->ready, NULL)) {
        pthread_mutex_destroy(&w->lock);
        free(w);
        error_set(error, E_IO, 0);
        return NULL;
    }
    w->threads = xcalloc(count, sizeof(pthread_t));
    for (size_t i = 0; i < count; i++) {
        if (pthread_create(&w->threads[i], NULL, worker_main, w)) {
            workers_free(w);
            error_set(error, E_IO, 0);
            return NULL;
        }
        w->started++;
    }
    return w;
}
static void workers_submit(Workers *w, const App *app, const json_t *task) {
    Job *job = xcalloc(1, sizeof(*job));
    job->app = *app;
    job->task = json_incref((json_t *)task);
    pthread_mutex_lock(&w->lock);
    if (w->last)
        w->last->next = job;
    else
        w->first = job;
    w->last = job;
    w->pending++;
    pthread_mutex_unlock(&w->lock);
    pthread_cond_signal(&w->ready);
}
bool consumer_run(const App *app, Error *error) {
    size_t size = config_workers(app->config), maximum = config_pending(app->config),
           batch_size = config_batch(app->config);
    REQUIRE(size && size <= INT_MAX && maximum && maximum <= INT_MAX && batch_size &&
                batch_size <= INT_MAX,
            E_CONFIG, false);
    r2t_install_signals();
    json_auto_t *recover_filter = JO(P("status", JO(P("$in", JA(ji(2), ji(5))))),
                                     P("updated_at", JO(P("$lt", jf(now() - 60)))))
                                      .p;
    json_auto_t *recover_update =
        JO(P("$set", JO(P("status", ji(1)), P("updated_at", jf(now()))))).p;
    int64_t recovered = 0;
    TRY(db_update(app->db, "tasks", recover_filter, recover_update, true, false, &recovered, error),
        false);
    if (recovered) {
        STR(log) = strf("Recovered %lld abandoned tasks", (long long)recovered);
        log_info(log, true);
    }
    STR(log) = strf("Starting consumer C with %zu workers", size);
    log_info(log, false);
    Workers *workers __attribute__((cleanup(auto_workers_free))) = workers_new(size, error);
    TRY(workers, false);
    double next_memory = 0;
    while (!r2t_stopping()) {
        if (now() >= next_memory) {
            next_memory = now() + 60;
            Error ignored = {0};
            STR(status) = read_file("/proc/self/status", NULL, &ignored);
            if (status) {
                const char *rss = strstr(status, "VmRSS:");
                if (rss && strtoull(rss + 6, NULL, 10) >= 256 * 1024)
                    r2t_allocator(0, 1);
            }
        }
        json_auto_t *expired_filter =
            JO(P("status", ji(1)), P("created_at", JO(P("$lt", jf(now() - 25 * 60))))).p;
        json_auto_t *expired_update =
            JO(P("$set", JO(P("status", ji(4)), P("updated_at", jf(now()))))).p;
        int64_t expired = 0;
        TRY(db_update(app->db, "tasks", expired_filter, expired_update, true, false, &expired,
                      error),
            false);
        if (expired) {
            STR(message) = strf("Failed %lld expired new tasks", (long long)expired);
            log_info(message, true);
        }
        size_t pending = worker_count(workers),
               available = maximum > pending ? maximum - pending : 0;
        size_t take = available < batch_size ? available : batch_size;
        double cutoff = now() - 25 * 60;
        json_auto_t *batch = json_array();
        for (size_t i = 0; i < take; i++) {
            json_auto_t *filter =
                JO(P("status", ji(1)), P("created_at", JO(P("$gte", jf(cutoff))))).p;
            json_auto_t *update =
                JO(P("$set", JO(P("status", ji(5)), P("updated_at", jf(now()))))).p;
            json_auto_t *sort = JO(P("created_at", ji(1))).p;
            json_auto_t *projection =
                JO(P("name", ji(1)), P("args", ji(1)), P("created_at", ji(1))).p;
            json_auto_t *task =
                db_claim(app->db, "tasks", filter, update, sort, projection, false, error);
            if (!task) {
                TRY(!error->kind, false);
                break;
            }
            jappend(batch, task);
        }
        STR(message) = strf("Claimed %zu new tasks", json_array_size(batch));
        log_info(message, false);
        size_t i;
        json_t *task;
        json_array_foreach(batch, i, task) workers_submit(workers, app, task);
        r2t_wait_stop(5000);
    }
    return true;
}
json_t *schedules(const Config *config, Error *error) {
    STR(path) = config_cron_path(config);
    STR(raw) = read_file(path, NULL, error);
    TRY(raw, NULL);
    json_auto_t *lines = split_text(raw, "\n");
    json_auto_t *out = json_array();
    for (size_t i = 1; i < json_array_size(lines); i++) {
        const char *line = text(json_array_get(lines, i));
        STR(stripped) = trim(line, NULL);
        if (!*stripped)
            continue;
        json_auto_t *parts = split_text(line, "\t");
        REQUIRE(json_array_size(parts) >= 2, E_CONFIG, NULL);
        json_array_append_new(out,
                              JA(jr(json_array_get(parts, 0)), jr(json_array_get(parts, 1))).p);
    }
    return jrelease(&out);
}
static bool cron_number(const char *s, int *value, Error *error) {
    const char *days[] = {"sun", "mon", "tue", "wed", "thu", "fri", "sat"};
    STR(low) = lower(s);
    for (int i = 0; i < 7; i++)
        if (!strcmp(low, days[i])) {
            *value = i;
            return true;
        }
    char *end = NULL;
    long n = strtol(s, &end, 10);
    REQUIRE(end != s && !*end && n >= 0 && n <= INT_MAX, E_CONFIG, false);
    *value = (int)n;
    return true;
}
static bool cron_field(const char *expression, int current, int minimum, int maximum, bool *match,
                       Error *error) {
    *match = false;
    json_auto_t *items = split_text(expression, ",");
    size_t i;
    json_t *item;
    json_array_foreach(items, i, item) {
        json_auto_t *parts = split_text(text(item), "/");
        REQUIRE(json_array_size(parts) <= 2, E_CONFIG, false);
        const char *range = text(json_array_get(parts, 0));
        int step = 1;
        if (json_array_size(parts) == 2)
            TRY(cron_number(text(json_array_get(parts, 1)), &step, error), false);
        REQUIRE(step > 0, E_CONFIG, false);
        int first, last;
        if (!strcmp(range, "*")) {
            first = minimum;
            last = maximum;
        } else {
            json_auto_t *bounds = split_text(range, "-");
            REQUIRE(json_array_size(bounds) <= 2, E_CONFIG, false);
            TRY(cron_number(text(json_array_get(bounds, 0)), &first, error), false);
            last = first;
            if (json_array_size(bounds) == 2)
                TRY(cron_number(text(json_array_get(bounds, 1)), &last, error), false);
            else if (json_array_size(parts) == 2)
                last = maximum;
        }
        REQUIRE(first >= minimum && last <= maximum && first <= last, E_CONFIG, false);
        for (int n = first; n <= last; n += step)
            if (n == current || (maximum == 7 && n == 7 && current == 0))
                *match = true;
    }
    return true;
}
bool cron_matches(const char *mask, double timestamp, bool *matches, Error *error) {
    json_auto_t *parts = words(mask);
    REQUIRE(json_array_size(parts) == 5, E_CONFIG, false);
    struct tm tm = time_parts(timestamp, false);
    bool minute, hour, day, month, weekday;
    TRY(cron_field(text(json_array_get(parts, 0)), tm.tm_min, 0, 59, &minute, error), false);
    TRY(cron_field(text(json_array_get(parts, 1)), tm.tm_hour, 0, 23, &hour, error), false);
    TRY(cron_field(text(json_array_get(parts, 2)), tm.tm_mday, 1, 31, &day, error), false);
    TRY(cron_field(text(json_array_get(parts, 3)), tm.tm_mon + 1, 1, 12, &month, error), false);
    TRY(cron_field(text(json_array_get(parts, 4)), tm.tm_wday, 0, 7, &weekday, error), false);
    bool both =
        strcmp(text(json_array_get(parts, 2)), "*") && strcmp(text(json_array_get(parts, 4)), "*");
    *matches = minute && hour && month && (both ? (day || weekday) : (day && weekday));
    return true;
}
bool scheduler_run(const App *app, Error *error) {
    double current = now();
    json_auto_t *rows = schedules(app->config, error);
    TRY(rows, false);
    json_auto_t *modules = json_array();
    size_t i;
    json_t *row;
    json_array_foreach(rows, i, row) {
        bool match = false;
        TRY(cron_matches(text(json_array_get(row, 0)), current, &match, error), false);
        if (match)
            jappend(modules, json_array_get(row, 1));
    }
    size_t n = json_array_size(modules);
    if (!n)
        return true;
    for (size_t index = n; index > 1; index--) {
        uint64_t random = 0;
        STR(value) = uuid_text();
        for (size_t b = 0; b < 16; b++)
            random = random * 33 + (unsigned char)value[b];
        size_t target = random % index;
        json_t *a = json_incref(json_array_get(modules, index - 1)),
               *b = json_incref(json_array_get(modules, target));
        json_array_set_new(modules, index - 1, b);
        json_array_set_new(modules, target, a);
    }
    double created = now();
    json_auto_t *docs = json_array();
    json_t *module;
    json_array_foreach(modules, i, module) json_array_append_new(
        docs, JO(P("name", js("supply")),
                 P("args", JO(P("submodule_name", jr(module)),
                              P("config_filename", js(app->config->path)))),
                 P("status", ji(1)), P("created_at", jf(created)), P("updated_at", jf(created)))
                  .p);
    TRY(db_insert(app->db, "tasks", docs, error), false);
    json_auto_t *run = active_run(app->config->root);
    json_auto_t *event = JO(P("submitted_jobs", ji((int64_t)n))).p;
    emit(run, "scheduler_submitted", event);
    STR(log) = strf("Inserted %zu tasks", n);
    log_info(log, false);
    return true;
}
