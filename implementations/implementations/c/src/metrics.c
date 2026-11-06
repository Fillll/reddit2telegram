#include "metrics.h"
#include <fcntl.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
json_t *active_run(const char *root) {
    STR(path) = strf("%s/implementations/benchmarks/state/active.json", root);
    Error error = {0};
    size_t n = 0;
    STR(raw) = read_file(path, &n, &error);
    if (!raw)
        return NULL;
    json_auto_t *run = parse_json(raw, n, &error);
    if (!run || now() < number(get(run, "started_at"), INFINITY) ||
        now() >= number(get(run, "deadline"), 0))
        return NULL;
    return jrelease(&run);
}
void emit(const json_t *run, const char *event, json_t *fields) {
    if (!run || now() < number(get(run, "started_at"), INFINITY) ||
        now() >= number(get(run, "deadline"), 0))
        return;
    const char *path = field(run, "events_path");
    if (!*path)
        return;
    json_object_set_new(fields, "schema", ji(1).p);
    jset(fields, "run_id", get(run, "run_id"));
    json_object_set_new(fields, "ts", jf(now()).p);
    json_object_set_new(fields, "event", js(event).p);
    STR(json) = dump_json(fields);
    BUF(line);
    buffer_text(&line, json);
    buffer_text(&line, "\n");
    int fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
    if (fd < 0)
        return;
    ssize_t n = write(fd, line.data, line.length);
    close(fd);
    if (n != (ssize_t)line.length)
        log_info("benchmark event write failed", true);
}
Metrics *metrics_begin(const char *root, const char *task, const char *module,
                       const json_t *created) {
    json_auto_t *run = active_run(root);
    if (!run)
        return NULL;
    Metrics *m = xcalloc(1, sizeof(*m));
    m->run = json_incref(run);
    m->counters = json_object();
    m->wait = json_is_number(created) ? jf(fmax(0, now() - number(created, 0))).p : json_null();
    m->task_id = xstrdup(task);
    m->module = xstrdup(module);
    m->started = monotonic_now();
    pthread_mutex_init(&m->lock, NULL);
    json_auto_t *fields =
        JO(P("task_id", js(task)), P("module", js(module)), P("queue_wait_seconds", jr(m->wait))).p;
    emit(run, "job_start", fields);
    return m;
}
void metrics_free(Metrics *m) {
    if (m) {
        json_decref(m->run);
        json_decref(m->counters);
        json_decref(m->wait);
        free(m->task_id);
        free(m->module);
        pthread_mutex_destroy(&m->lock);
        free(m);
    }
}
void metrics_count(Metrics *m, const char *key, uint64_t n) {
    if (!m)
        return;
    pthread_mutex_lock(&m->lock);
    int64_t before = 0;
    integer(get(m->counters, key), &before);
    json_object_set_new(m->counters, key, ji(before + (int64_t)n).p);
    pthread_mutex_unlock(&m->lock);
}
void metrics_finish(Metrics *m, Error error) {
    if (!m)
        return;
    pthread_mutex_lock(&m->lock);
    json_auto_t *fields = JO(P("task_id", js(m->task_id)), P("module", js(m->module)),
                             P("status", js(error.kind == E_NONE ? "success" : "failed")),
                             P("error_type", error.kind == E_NONE ? JN() : js(error_name(error))),
                             P("duration_seconds", jf(monotonic_now() - m->started)),
                             P("queue_wait_seconds", jr(m->wait)), P("counters", jr(m->counters)))
                              .p;
    emit(m->run, "job_end", fields);
    pthread_mutex_unlock(&m->lock);
}
void metrics_post(Metrics *m, const char *channel, const char *url, bool sent) {
    metrics_count(m, sent ? "posts_recorded_sent" : "candidates_rejected", 1);
    if (!m || !sent)
        return;
    STR(c) = lower(channel);
    STR(u) = lower(url);
    BUF(bytes);
    buffer_text(&bytes, c);
    buffer_add(&bytes, "\0", 1);
    buffer_text(&bytes, u);
    Error error = {0};
    STR(hash) = digest(bytes.data, bytes.length, "SHA256", &error);
    if (!hash)
        return;
    json_auto_t *fields = JO(P("task_id", js(m->task_id)), P("post_key", js(hash))).p;
    emit(m->run, "post_record", fields);
}
void metrics_delivery(Metrics *m, const json_t *result) {
    json_auto_t *messages =
        json_is_array(result) ? json_incref((json_t *)result) : JA(jr(result)).p;
    size_t i;
    json_t *message;
    json_array_foreach(messages, i, message) {
        if (json_is_null(get(message, "message_id")))
            continue;
        metrics_count(m, "telegram_messages", 1);
        const char *kind = "text_or_other";
        const char *types[] = {"video", "animation", "photo", "document", "audio"};
        for (size_t n = 0; n < 5; n++)
            if (!json_is_null(get(message, types[n]))) {
                kind = types[n];
                break;
            }
        STR(key) = strf("telegram_messages_%s", kind);
        metrics_count(m, key, 1);
    }
}
