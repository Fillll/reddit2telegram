#ifndef R2T_C_APP_H
#define R2T_C_APP_H
#include "sender.h"
typedef struct Reporter Reporter;
typedef struct {
    const Config *config;
    Database *db;
    sem_t *videos;
    Reporter *reporter;
} App;
typedef struct {
    char *channel, *link;
} ErrorContext;
void context_free(ErrorContext *context);
bool app_supply(const App *app, const char *module, Metrics *metrics, ErrorContext *context,
                Error *error);
void app_run_job(const App *app, const json_t *task);
bool consumer_run(const App *app, Error *error);
bool scheduler_run(const App *app, Error *error);
json_t *schedules(const Config *config, Error *error);
bool cron_matches(const char *mask, double timestamp, bool *matches, Error *error);
Reporter *reporter_new(const Config *config, Error *error);
void reporter_free(Reporter *reporter);
void reporter_capture(Reporter *reporter, Error error, const char *module);
bool report_developer(const App *app, const char *module, const ErrorContext *context, Error fault,
                      Metrics *metrics, Error *error);
#endif
