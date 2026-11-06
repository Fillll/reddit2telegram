#ifndef R2T_C_METRICS_H
#define R2T_C_METRICS_H
#include "model.h"
typedef struct {
    json_t *run, *counters, *wait;
    char *task_id, *module;
    double started;
    pthread_mutex_t lock;
} Metrics;
json_t *active_run(const char *root);
void emit(const json_t *run, const char *event, json_t *fields);
Metrics *metrics_begin(const char *root, const char *task, const char *module,
                       const json_t *created);
void metrics_free(Metrics *metrics);
void metrics_count(Metrics *metrics, const char *key, uint64_t n);
void metrics_finish(Metrics *metrics, Error error);
void metrics_post(Metrics *metrics, const char *channel, const char *url, bool sent);
void metrics_delivery(Metrics *metrics, const json_t *result);
#endif
