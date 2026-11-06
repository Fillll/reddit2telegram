#ifndef R2T_C_REDDIT_H
#define R2T_C_REDDIT_H
#include "http.h"
typedef struct {
    const Config *config;
    Http *http;
    char *token;
    double expiry, next;
} Reddit;
Reddit *reddit_new(const Config *config, Metrics *metrics);
void reddit_free(Reddit *reddit);
void auto_reddit_free(Reddit **reddit);
#define REDDIT(name) Reddit *name __attribute__((cleanup(auto_reddit_free)))
json_t *reddit_get(Reddit *reddit, const char *path, json_t *params, Error *error);
json_t *reddit_listing(Reddit *reddit, const char *subreddit, const char *ranking, size_t limit,
                       const char *after, Error *error);
json_t *reddit_hydrate(Reddit *reddit, const json_t *submission, Error *error);
#endif
