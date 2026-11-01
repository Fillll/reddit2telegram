#include "app.h"
#include "build_info.h"
#include <errno.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
typedef struct ReportEvent {
    json_t *event;
    struct ReportEvent *next;
} ReportEvent;
typedef struct {
    pthread_mutex_t lock;
    pthread_cond_t ready, done;
    _Atomic unsigned references;
    bool closing, finished;
    size_t pending;
    ReportEvent *first, *last;
    char *dsn, *endpoint;
} ReportState;
struct Reporter {
    ReportState *state;
    pthread_t thread;
};
static void state_release(ReportState *s) {
    if (atomic_fetch_sub_explicit(&s->references, 1, memory_order_acq_rel) == 1) {
        pthread_mutex_destroy(&s->lock);
        pthread_cond_destroy(&s->ready);
        pthread_cond_destroy(&s->done);
        free(s->dsn);
        free(s->endpoint);
        free(s);
    }
}
static void *report_main(void *data) {
    ReportState *s = data;
    for (;;) {
        pthread_mutex_lock(&s->lock);
        while (!s->first && !s->closing)
            pthread_cond_wait(&s->ready, &s->lock);
        if (!s->first && s->closing) {
            s->finished = true;
            pthread_cond_broadcast(&s->done);
            pthread_mutex_unlock(&s->lock);
            state_release(s);
            return NULL;
        }
        ReportEvent *item = s->first;
        s->first = item->next;
        if (!s->first)
            s->last = NULL;
        s->pending--;
        pthread_mutex_unlock(&s->lock);
        json_auto_t *event = item->event;
        free(item);
        STR(body) = dump_json(event);
        json_auto_t *head = JO(P("event_id", jr(get(event, "event_id"))), P("dsn", js(s->dsn))).p;
        json_auto_t *part = JO(P("type", js("event")), P("length", ji((int64_t)strlen(body)))).p;
        STR(head_text) = dump_json(head);
        STR(part_text) = dump_json(part);
        STR(envelope) = strf("%s\n%s\n%s\n", head_text, part_text, body);
        HTTP(http) = http_new(NULL, false);
        json_auto_t *headers = JO(P("Content-Type", js("application/x-sentry-envelope"))).p;
        Error ignored = {0};
        RESPONSE(response) = http_request(http, "POST", s->endpoint, headers, envelope,
                                          strlen(envelope), NULL, NULL, 0, NULL, false, &ignored);
        if (!response) {
            STR(message) = strf("Sentry reporting failed: %s", error_name(ignored));
            log_info(message, true);
        }
    }
}
Reporter *reporter_new(const Config *config, Error *error) {
    Reporter *r = xcalloc(1, sizeof(*r));
    const char *dsn = field(config->values, "sentry");
    if (!*dsn)
        return r;
    URL(url) = url_parse(dsn, error);
    if (!url || !*url->user) {
        free(r);
        error_set(error, E_CONFIG, 0);
        return NULL;
    }
    STR(path) = trim(url->path, "/");
    json_auto_t *parts = split_text(path, "/");
    size_t count = json_array_size(parts);
    const char *project = text(json_array_get(parts, count ? count - 1 : 0));
    if (!count || !*project) {
        free(r);
        error_set(error, E_CONFIG, 0);
        return NULL;
    }
    json_auto_t *prefix = json_array();
    for (size_t i = 0; i + 1 < count; i++)
        jappend(prefix, json_array_get(parts, i));
    STR(base) = join(prefix, "/");
    STR(port) = *url->port ? strf(":%s", url->port) : xstrdup("");
    STR(extra) = *base ? strf("%s/", base) : xstrdup("");
    ReportState *s = xcalloc(1, sizeof(*s));
    s->dsn = xstrdup(dsn);
    s->endpoint =
        strf("%s://%s%s/%sapi/%s/envelope/", url->scheme, url->host, port, extra, project);
    pthread_mutex_init(&s->lock, NULL);
    pthread_cond_init(&s->ready, NULL);
    pthread_cond_init(&s->done, NULL);
    atomic_init(&s->references, 2);
    r->state = s;
    if (pthread_create(&r->thread, NULL, report_main, s)) {
        state_release(s);
        state_release(s);
        free(r);
        error_set(error, E_IO, 0);
        return NULL;
    }
    return r;
}
void reporter_capture(Reporter *r, Error error, const char *module) {
    if (!r || !r->state)
        return;
    ReportState *s = r->state;
    pthread_mutex_lock(&s->lock);
    if (s->closing || s->pending >= 30) {
        pthread_mutex_unlock(&s->lock);
        return;
    }
    STR(id) = uuid_text();
    ReportEvent *item = xcalloc(1, sizeof(*item));
    item->event =
        JO(P("event_id", js(id)), P("timestamp", jf(now())), P("platform", js("other")),
           P("level", js("error")), P("logger", js("r2t-c")), P("release", js(R2T_VERSION)),
           P("exception", JO(P("values", JA(JO(P("type", js(error_name(error))),
                                               P("value", js(error_name(error)))))))),
           P("extra", JO(P("submodule", js(module)))))
            .p;
    if (s->last)
        s->last->next = item;
    else
        s->first = item;
    s->last = item;
    s->pending++;
    pthread_mutex_unlock(&s->lock);
    pthread_cond_signal(&s->ready);
}
void reporter_free(Reporter *r) {
    if (!r)
        return;
    ReportState *s = r->state;
    if (!s) {
        free(r);
        return;
    }
    pthread_mutex_lock(&s->lock);
    s->closing = true;
    pthread_cond_broadcast(&s->ready);
    struct timespec deadline;
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_sec += 2;
    while (!s->finished) {
        int code = pthread_cond_timedwait(&s->done, &s->lock, &deadline);
        if (code == ETIMEDOUT)
            break;
    }
    bool finished = s->finished;
    if (!finished) {
        while (s->first) {
            ReportEvent *item = s->first;
            s->first = item->next;
            json_decref(item->event);
            free(item);
        }
        s->last = NULL;
        s->pending = 0;
    }
    pthread_mutex_unlock(&s->lock);
    if (finished)
        pthread_join(r->thread, NULL);
    else
        pthread_detach(r->thread);
    state_release(s);
    free(r);
}
bool report_developer(const App *app, const char *module, const ErrorContext *context, Error fault,
                      Metrics *metrics, Error *error) {
    SENDER(sender) =
        sender_new(app->config, app->db, get(get(app->config->values, "telegram"), "dev_chat"),
                   metrics, app->videos);
    STR(destination) = sender_channel(sender);
    const char *channel = context->channel ? context->channel : destination;
    STR(c) = lower(channel);
    STR(link_title) = NULL;
    json_auto_t *filter = NULL;
    if (context->link) {
        STR(link) = lower(context->link);
        filter = JO(P("channel", js(c)), P("url", js(link))).p;
        link_title = strf("link: %s\n", context->link);
    } else {
        STR(date) = time_format(now(), "%Y-%m-%d", false);
        filter = JO(P("channel", js(c)), P("link", js("_NO_")), P("date", js(date))).p;
        link_title = xstrdup("");
    }
    json_auto_t *update =
        JO(P("$inc", JO(P("cnt", ji(1)))), P("$set", JO(P("ts", jdate(now()))))).p;
    json_auto_t *projection = JO(P("cnt", ji(1)), P("_id", ji(0))).p;
    json_auto_t *record =
        db_claim(app->db, "errors", filter, update, NULL, projection, true, error);
    TRY(record, false);
    int64_t count;
    REQUIRE(integer(get(record, "cnt"), &count), E_DATABASE, false);
    STR(body) =
        strf("<b>r2t error</b>\nsubmodule: %s\nchannel: %s\n%serror_cnt: %lld\n\n\n<pre>%s</pre>",
             module, channel, link_title, (long long)count, error_name(fault));
    return sender_text(sender, body, false, "HTML", NULL, error);
}
