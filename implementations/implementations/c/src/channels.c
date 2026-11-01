#include "channels.h"
#include "build_info.h"
#include "maintenance.h"
#include <math.h>
#include <openssl/rand.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static pthread_mutex_t cache_lock = PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP;
static char *cached_weighted = NULL, *cached_promotion = NULL;
static void unlock(pthread_mutex_t **p) {
    pthread_mutex_unlock(*p);
}
static uint64_t random_bits(void) {
    uint64_t n;
    if (RAND_bytes((unsigned char *)&n, sizeof(n)) != 1)
        abort();
    return n;
}
static int string_compare(const void *a, const void *b) {
    return strcmp(text(*(json_t *const *)a), text(*(json_t *const *)b));
}
json_t *public_modules(const App *app, Error *error) {
    json_auto_t *rows = schedules(app->config, error);
    TRY(rows, NULL);
    json_auto_t *unique = json_object();
    size_t i;
    json_t *row;
    json_array_foreach(rows, i, row) {
        const char *name = text(json_array_get(row, 1));
        if (strncmp(name, "tech_", 5))
            json_object_set_new(unique, name, json_true());
    }
    size_t count = json_object_size(unique);
    json_t **values = xcalloc(count ? count : 1, sizeof(json_t *));
    const char *key;
    json_t *value;
    size_t at = 0;
    JOBJECT_FOREACH(unique, key, value) values[at++] = js(key).p;
    qsort(values, count, sizeof(json_t *), string_compare);
    json_t *out = json_array();
    for (i = 0; i < count; i++)
        json_array_append_new(out, values[i]);
    free(values);
    return out;
}
static char *weighted(Error *error) {
    pthread_mutex_lock(&cache_lock);
    pthread_mutex_t *lock __attribute__((cleanup(unlock))) = &cache_lock;
    if (cached_weighted)
        return xstrdup(cached_weighted);
    json_auto_t *data = parse_json(R2T_WEIGHTED_CHANNEL, strlen(R2T_WEIGHTED_CHANNEL), error);
    TRY(data, NULL);
    json_t *weights = get(data, "weights");
    double total = 0;
    const char *name;
    json_t *weight;
    JOBJECT_FOREACH(weights, name, weight) total += number(weight, 0);
    REQUIRE(total > 0, E_CONFIG, NULL);
    double draw = (double)(random_bits() >> 11) / 9007199254740992.0 * total;
    JOBJECT_FOREACH(weights, name, weight) {
        if (draw < number(weight, 0)) {
            cached_weighted = xstrdup(name);
            return xstrdup(name);
        }
        draw -= number(weight, 0);
    }
    error_set(error, E_CONFIG, 0);
    return NULL;
}
bool channel_identity(const App *app, const char *module, json_t **destination, char **subreddit,
                      Error *error) {
    if (!strcmp(module, "r_porn")) {
        *destination = js("@r_porn").p;
        *subreddit = weighted(error);
        return *subreddit != NULL;
    }
    if (!strcmp(module, "reddit2telegram")) {
        *destination = js("@reddit2telegram").p;
        *subreddit = xstrdup("");
        return true;
    }
    STR(low) = lower(module);
    json_auto_t *filter = JO(P("submodule", js(low))).p;
    json_auto_t *record = db_one(app->db, "channels", filter, NULL, error);
    TRY(!error->kind, false);
    if (record) {
        *destination = json_incref(get(record, "channel"));
        *subreddit = xstrdup(field(record, "subreddit"));
        return true;
    }
    json_auto_t *local = parse_json(R2T_LOCAL_CHANNELS, strlen(R2T_LOCAL_CHANNELS), error);
    TRY(local, false);
    json_t *v = get(local, module);
    REQUIRE(json_is_object(v), E_CONFIG, false);
    *destination = json_incref(get(v, "t_channel"));
    *subreddit = xstrdup(field(v, "subreddit"));
    return true;
}
void channel_free(Channel *c) {
    if (c) {
        json_decref(c->destination);
        json_decref(c->options);
        free(c->subreddit);
        free(c->ranking);
        free(c);
    }
}
void auto_channel_free(Channel **c) {
    channel_free(*c);
}
static Channel *channel_new(const json_t *destination, const char *subreddit, const char *ranking,
                            size_t limit, bool requires, const json_t *options) {
    Channel *c = xcalloc(1, sizeof(*c));
    c->destination = json_incref((json_t *)destination);
    c->subreddit = xstrdup(subreddit);
    c->ranking = ranking ? xstrdup(ranking) : NULL;
    c->limit = limit;
    c->requires_submission = requires;
    c->options = options ? json_incref((json_t *)options) : json_object();
    return c;
}
static bool update_order(const App *app, Error *error) {
    json_auto_t *modules = public_modules(app, error);
    TRY(modules, false);
    json_auto_t *order = json_object();
    size_t i;
    json_t *name;
    json_array_foreach(modules, i, name) {
        const char *module = text(name);
        if (!strcmp(module, "reddit2telegram"))
            continue;
        json_auto_t *destination = NULL;
        STR(subreddit) = NULL;
        TRY(channel_identity(app, module, &destination, &subreddit, error), false);
        REQUIRE(json_is_string(destination), E_CONFIG, false);
        STR(channel) = lower(text(destination));
        json_auto_t *filter = JO(P("_id", js(channel))).p;
        json_auto_t *first = db_one(app->db, "view_with_first_dates", filter, NULL, error);
        TRY(!error->kind, false);
        if (first && !json_is_null(get(first, "first_date")))
            jset(order, module, get(first, "first_date"));
    }
    json_auto_t *filter = JO(P("setting", js("r2t_promotion_queue"))).p;
    json_auto_t *update =
        JO(P("$setOnInsert", JO(P("already_promoted", JA0()), P("counter", ji(0)))),
           P("$set", JO(P("promotion_order", jr(order)))))
            .p;
    return db_update(app->db, "settings", filter, update, false, true, NULL, error);
}
typedef struct {
    const char *name;
    double date;
} Ordered;
static int order_compare(const void *a, const void *b) {
    const Ordered *x = a, *y = b;
    return (y->date > x->date) - (y->date < x->date);
}
static char *promotion_target(const App *app, Error *error) {
    pthread_mutex_lock(&cache_lock);
    pthread_mutex_t *lock __attribute__((cleanup(unlock))) = &cache_lock;
    if (cached_promotion)
        return xstrdup(cached_promotion);
    json_auto_t *modules = public_modules(app, error);
    TRY(modules, NULL);
    json_auto_t *all = json_array();
    size_t i;
    json_t *v;
    json_array_foreach(modules, i, v) if (strcmp(text(v), "reddit2telegram")) jappend(all, v);
    REQUIRE(json_array_size(all), E_CONFIG, NULL);
    if (time_parts(now(), false).tm_wday == 0) {
        cached_promotion = xstrdup(text(json_array_get(all, random_bits() % json_array_size(all))));
        return xstrdup(cached_promotion);
    }
    json_auto_t *filter = JO(P("setting", js("r2t_promotion_queue"))).p;
    json_auto_t *record = db_one(app->db, "settings", filter, NULL, error);
    TRY(!error->kind, NULL);
    if (!record) {
        TRY(update_order(app, error), NULL);
        record = db_one(app->db, "settings", filter, NULL, error);
        TRY(record, NULL);
    }
    json_t *promoted = get(record, "already_promoted"), *order = get(record, "promotion_order");
    REQUIRE(json_is_array(promoted) && json_is_object(order), E_CONFIG, NULL);
    size_t n = json_object_size(order);
    Ordered *values = xcalloc(n ? n : 1, sizeof(Ordered));
    const char *key;
    size_t count = 0;
    JOBJECT_FOREACH(order, key, v) {
        double stamp = 0;
        bson_timestamp(v, &stamp);
        values[count++] = (Ordered){key, stamp};
    }
    qsort(values, n, sizeof(Ordered), order_compare);
    char *chosen = NULL;
    for (i = 0; i < n; i++) {
        const char *name = values[i].name;
        bool active = false, done = false;
        size_t j;
        json_t *value;
        json_array_foreach(all, j, value) if (!strcmp(text(value), name)) active = true;
        json_array_foreach(promoted, j, value) if (!strcmp(text(value), name)) done = true;
        if (active && !done) {
            chosen = xstrdup(name);
            break;
        }
    }
    free(values);
    if (chosen) {
        cached_promotion = chosen;
        return xstrdup(chosen);
    }
    json_auto_t *update =
        JO(P("$inc", JO(P("counter", ji(1)))), P("$set", JO(P("already_promoted", JA0())))).p;
    TRY(db_update(app->db, "settings", filter, update, false, false, NULL, error), NULL);
    error_set(error, E_CONFIG, 0);
    return NULL;
}
Channel *channel_resolve(const App *app, const char *module, Error *error) {
    if (!strcmp(module, "r_porn")) {
        STR(subreddit) = weighted(error);
        TRY(subreddit, NULL);
        json_auto_t *data = parse_json(R2T_WEIGHTED_CHANNEL, strlen(R2T_WEIGHTED_CHANNEL), error);
        TRY(data, NULL);
        json_auto_t *options = JO(P("check_dups", jb(true)),
                                  P("min_upvotes_limit", jr(get(get(data, "limits"), subreddit))))
                                   .p;
        const char *types[] = {"text", "other", "album", "gif", "img", "video", "gallery"};
        for (size_t i = 0; i < 7; i++) {
            const char *kind = types[i];
            const char *prefix = !strcmp(kind, "text") ? "{title}\n\n{self_text}"
                                 : (!strcmp(kind, "other") || !strcmp(kind, "album"))
                                     ? "{title}\n{link}"
                                     : "{title}";
            STR(pattern) = strf("%s\n\n{upvotes} upvotes\n/r/{subreddit_name} → "
                                "#{subreddit_name}\n{short_link}\n{channel}",
                                prefix);
            json_object_set_new(options, kind, js(pattern).p);
        }
        json_auto_t *destination = js("@r_porn").p;
        return channel_new(destination, subreddit, NULL, 100, true, options);
    }
    if (!strcmp(module, "reddit2telegram")) {
        STR(target) = promotion_target(app, error);
        TRY(target, NULL);
        json_auto_t *handle = NULL;
        STR(subreddit) = NULL;
        TRY(channel_identity(app, target, &handle, &subreddit, error), NULL);
        json_auto_t *destination = js("@reddit2telegram").p;
        return channel_new(destination, subreddit, "top", 1000, true, NULL);
    }
    if (!strncmp(module, "tech_", 5)) {
        json_auto_t *destination = NULL;
        if (!strcmp(module, "tech_receiver"))
            destination = js("@r_channels").p;
        else if (!strcmp(module, "tech_weekly_radar"))
            destination = js("@reddit2telegram").p;
        else if (!strcmp(module, "tech_cleaner") || !strcmp(module, "tech_anniversary") ||
                 !strcmp(module, "tech_store_stat"))
            destination = json_incref(get(get(app->config->values, "telegram"), "dev_chat"));
        else {
            error_set(error, E_CONFIG, 0);
            return NULL;
        }
        return channel_new(destination, "all", NULL, 100,
                           strcmp(module, "tech_anniversary") && strcmp(module, "tech_store_stat"),
                           NULL);
    }
    STR(low) = lower(module);
    json_auto_t *filter = JO(P("submodule", js(low))).p;
    json_auto_t *record = db_one(app->db, "channels", filter, NULL, error);
    TRY(!error->kind, NULL);
    if (!record) {
        json_auto_t *local = parse_json(R2T_LOCAL_CHANNELS, strlen(R2T_LOCAL_CHANNELS), error);
        TRY(local, NULL);
        json_t *v = get(local, module);
        REQUIRE(json_is_object(v), E_CONFIG, NULL);
        record = JO(P("channel", jr(get(v, "t_channel"))), P("subreddit", jr(get(v, "subreddit"))),
                    P("submissions_ranking", jr(get(v, "submissions_ranking"))),
                    P("submissions_limit", json_object_get(v, "submissions_limit")
                                               ? jr(get(v, "submissions_limit"))
                                               : ji(100)))
                     .p;
    }
    json_auto_t *options = JO(P("min_upvotes_limit", jr(get(record, "min_upvotes_limit")))).p;
    const char *kinds[] = {"text", "gif", "video", "img", "album", "gallery", "other"};
    json_t *content = get(record, "content");
    for (size_t i = 0; i < 7; i++)
        json_object_set_new(options, kinds[i],
                            json_is_null(content)                ? jb(true).p
                            : json_object_get(content, kinds[i]) ? jr(get(content, kinds[i])).p
                                                                 : jb(false).p);
    const char *ranking = json_is_string(get(record, "submissions_ranking"))
                              ? field(record, "submissions_ranking")
                              : NULL;
    if (ranking && strcmp(ranking, "hot") && strcmp(ranking, "new") && strcmp(ranking, "top"))
        ranking = "hot";
    int64_t limit = 0;
    size_t count =
        integer(get(record, "submissions_limit"), &limit) && limit >= 0 ? (size_t)limit : SIZE_MAX;
    return channel_new(get(record, "channel"), field(record, "subreddit"), ranking, count, true,
                       options);
}
char *channel_tags(const App *app, const char *module, Error *error) {
    STR(low) = lower(module);
    json_auto_t *filter = JO(P("submodule", js(low))).p;
    json_auto_t *record = db_one(app->db, "channels", filter, NULL, error);
    TRY(!error->kind, NULL);
    if (record && *field(record, "tags"))
        return xstrdup(field(record, "tags"));
    STR(path) = strf("%s/channels/%s/tags.txt", app->config->app, module);
    Error local = {0};
    char *value = read_file(path, NULL, &local);
    if (!value) {
        if (access(path, F_OK) == 0) {
            *error = local;
            return NULL;
        }
        return xstrdup("");
    }
    return value;
}
bool channel_nice(const App *app, const char *module, const json_t *submission, Sender *sender,
                  Reddit *reddit, const char *heading, const char *ending, const char *channel,
                  Supply *result, Error *error) {
    json_auto_t *destination = NULL;
    STR(source) = NULL;
    if (channel)
        destination = js(channel).p;
    else
        TRY(channel_identity(app, module, &destination, &source, error), false);
    REQUIRE(json_is_string(destination) && json_is_number(get(submission, "created_utc")), E_CONFIG,
            false);
    STR(raw_tags) = channel_tags(app, module, error);
    TRY(raw_tags, false);
    json_auto_t *tag_words = words(raw_tags);
    STR(tags) = join(tag_words, " ");
    STR(date) = time_format(number(get(submission, "created_utc"), 0), "%Y %b %d", true);
    json_auto_t *options = JO(P("channel_to_promote", jr(destination)), P("date", js(date)),
                              P("tags", js(tags)), P("extra_ending", js(ending ? ending : "")),
                              P("announcement_heading", js(heading ? heading : "")))
                               .p;
    const char *types[] = {"text", "other", "album", "gif", "img", "video", "gallery"};
    for (size_t i = 0; i < 7; i++) {
        const char *kind = types[i];
        const char *prefix = !strcmp(kind, "text") ? "{announcement_heading}{title}\n\n{self_text}"
                             : (!strcmp(kind, "other") || !strcmp(kind, "album"))
                                 ? "{announcement_heading}{title}\n{link}"
                                 : "{announcement_heading}{title}";
        STR(pattern) =
            strf("%s\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby "
                 "{channel_to_promote}\n{tags}\n\n{extra_ending}",
                 prefix);
        json_object_set_new(options, kind, js(pattern).p);
    }
    return sender_simple(sender, submission, options, reddit, result, error);
}
static bool promotion(const App *app, const json_t *submission, Sender *sender, Reddit *reddit,
                      Supply *result, Error *error) {
    double current = now();
    struct tm tm = time_parts(current, false);
    int weekday = (tm.tm_wday + 6) % 7;
    if (weekday == 5 && (tm.tm_hour == 0 || tm.tm_hour == 23) && tm.tm_min == 1) {
        TRY(update_order(app, error), false);
        return supply_result(result, SUPPLY_STOP);
    }
    if (weekday == 5)
        return supply_result(result, SUPPLY_STOP);
    STR(date) = time_format(current, "%Y %b %d", false);
    STR(hash) = digest_text(date, "SHA1");
    int hour = 0;
    for (size_t i = 0; i < strlen(hash); i += 2) {
        char byte[] = {hash[i], hash[i + 1], 0};
        hour = (hour * 256 + (int)strtol(byte, NULL, 16)) % 24;
    }
    if (tm.tm_hour != hour)
        return supply_result(result, SUPPLY_STOP);
    STR(target) = promotion_target(app, error);
    TRY(target, false);
    TRY(channel_nice(app, target, submission, sender, reddit, "", "", NULL, result, error), false);
    if (*result == SUPPLY_SENT && weekday < 5) {
        json_auto_t *filter = JO(P("setting", js("r2t_promotion_queue"))).p;
        json_auto_t *update = JO(P("$push", JO(P("already_promoted", js(target))))).p;
        TRY(db_update(app->db, "settings", filter, update, false, false, NULL, error), false);
    }
    return true;
}
bool channel_maintenance(const App *app, const char *module, Sender *sender, Supply *result,
                         Error *error) {
    if (!strcmp(module, "tech_cleaner"))
        return maintenance_cleaner(app, sender, result, error);
    if (!strcmp(module, "tech_receiver"))
        return maintenance_receiver(app, sender, result, error);
    if (!strcmp(module, "tech_weekly_radar"))
        return maintenance_weekly(app, sender, result, error);
    (void)app;
    (void)module;
    (void)sender;
    (void)result;
    return error_set(error, E_INCOMPLETE_PORT, 0);
}
bool channel_post(const App *app, const char *module, const Channel *channel,
                  const json_t *submission, Sender *sender, Reddit *reddit, Supply *result,
                  Error *error) {
    if (!strcmp(module, "reddit2telegram"))
        return promotion(app, submission, sender, reddit, result, error);
    if (!strncmp(module, "tech_", 5))
        return channel_maintenance(app, module, sender, result, error);
    return sender_simple(sender, submission, channel->options, reddit, result, error);
}
