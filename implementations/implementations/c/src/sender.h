#ifndef R2T_C_SENDER_H
#define R2T_C_SENDER_H
#include "database.h"
#include "reddit.h"
#include <semaphore.h>
#define MEDIA_LIMIT (50u * 1024u * 1024u)
typedef bool (*AckFn)(void *data, const json_t *ids, Error *error);
typedef struct {
    const Config *config;
    Database *db;
    json_t *destination;
    Metrics *metrics;
    Http *http, *media;
    sem_t *videos;
    bool owns_clients;
    AckFn ack;
    void *ack_data;
} Sender;
typedef struct {
    const char *kind;
    char *url;
    json_t *groups;
} Media;
Sender *sender_new(const Config *config, Database *db, const json_t *destination, Metrics *metrics,
                   sem_t *videos);
Sender *sender_clone(const Sender *source, const json_t *destination);
void sender_free(Sender *sender);
void auto_sender_free(Sender **sender);
#define SENDER(name) Sender *name __attribute__((cleanup(auto_sender_free)))
char *sender_channel(const Sender *sender);
json_t *sender_api(Sender *sender, const char *method, const json_t *params, Error *error);
bool sender_text(Sender *sender, const char *body, bool preview, const char *parse, Supply *result,
                 Error *error);
bool sender_image(Sender *sender, const char *url, const char *body, Supply *result, Error *error);
bool sender_gif(Sender *sender, const char *url, const char *body, Supply *result, Error *error);
bool sender_gallery(Sender *sender, const json_t *groups, const char *body, Supply *result,
                    Error *error);
bool sender_video(Sender *sender, const char *url, const char *body, const char *dash,
                  Supply *result, Error *error);
bool sender_seen(Sender *sender, const char *url, bool *seen, Error *error);
bool sender_error_limit(Sender *sender, const char *url, bool *blocked, Error *error);
bool sender_mark(Sender *sender, const char *url, bool sent, Error *error);
bool sender_duplicate(Sender *sender, const char *url, bool *duplicate, Error *error);
Media *sender_classify(Sender *sender, const json_t *submission, Error *error);
void media_free(Media *media);
void auto_media_free(Media **media);
#define MEDIA(name) Media *name __attribute__((cleanup(auto_media_free)))
bool sender_simple(Sender *sender, const json_t *submission, const json_t *options, Reddit *reddit,
                   Supply *result, Error *error);
char *html_escape(const char *value);
char *html_decode(const char *value);
bool clean_files(const Config *config, const char *channel, uint64_t *deleted, Error *error);
bool mux_video(const char *video, const char *audio, const char *output);
char *command_output(const char *const *args, Error *error);
#endif
