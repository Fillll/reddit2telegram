#ifndef R2T_C_HTTP_H
#define R2T_C_HTTP_H
#include "metrics.h"
typedef struct {
    void *handle;
    Metrics *metrics;
    bool telegram;
} Http;
typedef struct {
    r2t_response *raw;
    json_t *headers;
} Response;
Http *http_new(Metrics *metrics, bool telegram);
void http_free(Http *http);
void auto_http_free(Http **http);
void response_free(Response *response);
void auto_response_free(Response **response);
#define HTTP(name) Http *name __attribute__((cleanup(auto_http_free)))
#define RESPONSE(name) Response *name __attribute__((cleanup(auto_response_free)))
Response *http_request(Http *http, const char *method, const char *url, const json_t *headers,
                       const void *body, size_t body_length, const json_t *multipart,
                       const char *output, uint64_t limit, const char *algorithm,
                       bool allow_initial_failure, Error *error);
bool response_ok(const Response *response);
json_t *response_json(const Response *response, Error *error);
const char *response_header(const Response *response, const char *key);
bool http_download(Http *http, const char *url, const char *output, uint64_t limit);
char *http_metadata(Http *http, const char *url, Error *error);
json_t *http_api(Http *http, const char *token, const char *method, const json_t *params,
                 const char *video, Error *error);
char *percent_encode(const char *value);
char *form_body(const json_t *fields);
typedef struct {
    char *scheme, *host, *path, *query, *user, *password, *port;
} ParsedURL;
ParsedURL *url_parse(const char *value, Error *error);
void url_free(ParsedURL *url);
void auto_url_free(ParsedURL **url);
#define URL(name) ParsedURL *name __attribute__((cleanup(auto_url_free)))
#endif
