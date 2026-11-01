#ifndef R2T_C_PLATFORM_H
#define R2T_C_PLATFORM_H
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
/* Library/platform interop for the plain C application. */
void r2t_init(void);
void r2t_free(void *p);
void r2t_allocator(int arenas, int trim);
void r2t_install_signals(void);
int r2t_stopping(void);
void r2t_wait_stop(int milliseconds);
char *r2t_yaml_json(const char *path);
char *r2t_digest(const char *algorithm, const void *bytes, size_t length);
void *r2t_db_open(const char *uri);
void r2t_db_close(void *pool);
char *r2t_db_command(void *pool, const char *database, const char *command, int *error);
const char *r2t_mongoc_version(void);
const char *r2t_curl_version(void);

typedef struct {
    int error;
    long status;
    unsigned char *body;
    size_t length;
    char *headers;
    uint64_t received;
    uint64_t sent;
    uint64_t requests;
    uint64_t http_errors;
    uint64_t rate_limits;
    int too_large;
    char *body_digest;
} r2t_response;

/* Each handle is owned by one job; reuse retains its connection pool.
 * Headers are newline-separated. Multipart specification is a JSON document:
 * {fields:{name:value},files:{name:{path,filename,content_type}}}. */
void *r2t_http_open(void);
void r2t_http_close(void *client);
r2t_response *r2t_http_request(void *client, const char *method, const char *url,
                               const char *headers, const void *body, size_t body_length,
                               const char *multipart, const char *output_path,
                               uint64_t maximum_bytes, long connect_seconds, long read_seconds,
                               int follow_redirects, const char *digest_algorithm);
void r2t_response_free(r2t_response *response);
#ifdef __cplusplus
}
#endif
#endif
