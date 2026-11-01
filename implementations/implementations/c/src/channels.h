#ifndef R2T_C_CHANNELS_H
#define R2T_C_CHANNELS_H
#include "app.h"
typedef struct {
    json_t *destination, *options;
    char *subreddit, *ranking;
    size_t limit;
    bool requires_submission;
} Channel;
void channel_free(Channel *channel);
void auto_channel_free(Channel **channel);
#define CHANNEL(name) Channel *name __attribute__((cleanup(auto_channel_free)))
json_t *public_modules(const App *app, Error *error);
bool channel_identity(const App *app, const char *module, json_t **destination, char **subreddit,
                      Error *error);
Channel *channel_resolve(const App *app, const char *module, Error *error);
bool channel_maintenance(const App *app, const char *module, Sender *sender, Supply *result,
                         Error *error);
bool channel_post(const App *app, const char *module, const Channel *channel,
                  const json_t *submission, Sender *sender, Reddit *reddit, Supply *result,
                  Error *error);
char *channel_tags(const App *app, const char *module, Error *error);
bool channel_nice(const App *app, const char *module, const json_t *submission, Sender *sender,
                  Reddit *reddit, const char *heading, const char *ending, const char *channel,
                  Supply *result, Error *error);
#endif
