#ifndef R2T_C_MODEL_H
#define R2T_C_MODEL_H
#define _GNU_SOURCE
#include "CR2T.h"
#include <jansson.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <time.h>

typedef enum {
    E_NONE,
    E_CONFIG,
    E_IO,
    E_DATABASE,
    E_NETWORK,
    E_TIMEOUT,
    E_REDDIT,
    E_TELEGRAM,
    E_REJECTED,
    E_FORBIDDEN,
    E_RATE_LIMIT,
    E_LEASE,
    E_ANNOUNCEMENT,
    E_MEDIA,
    E_TEMPLATE,
    E_UNKNOWN_TASK,
    E_INCOMPLETE_PORT
} ErrorKind;
typedef struct {
    ErrorKind kind;
    int code;
} Error;
const char *error_name(Error e);
bool error_set(Error *error, ErrorKind kind, int code);
#define REQUIRE(condition, which, result)                                                          \
    do {                                                                                           \
        if (!(condition)) {                                                                        \
            error_set(error, (which), 0);                                                          \
            return (result);                                                                       \
        }                                                                                          \
    } while (0)
#define TRY(condition, result)                                                                     \
    do {                                                                                           \
        if (!(condition))                                                                          \
            return (result);                                                                       \
    } while (0)
void *xcalloc(size_t count, size_t size);
char *xstrdup(const char *s);
char *strf(const char *format, ...) __attribute__((format(printf, 1, 2)));
void auto_free(char **pointer);
void auto_bson_free(char **pointer);
#define STR(name) char *name __attribute__((cleanup(auto_free)))
#define BSONSTR(name) char *name __attribute__((cleanup(auto_bson_free)))

/* Builders consume typed owned values. JR retains a borrowed node explicitly;
 * raw borrowed pointers cannot accidentally be passed to a consuming builder.
 * Jansson's json_auto_t releases locals on normal returns and scope exits. */
typedef struct {
    json_t *p;
} JOwned;
typedef struct {
    const char *key;
    JOwned value;
} JField;
JOwned jo_fields(size_t count, const JField *fields);
JOwned ja_values(size_t count, const JOwned *values);
JOwned js(const char *s);
JOwned ji(int64_t n);
JOwned jf(double n);
JOwned jb(bool b);
JOwned jr(const json_t *v);
JOwned jdate(double seconds);
#define P(key, value) ((JField){(key), (value)})
#define JO(...) jo_fields(sizeof((JField[]){__VA_ARGS__}) / sizeof(JField), (JField[]){__VA_ARGS__})
#define JA(...) ja_values(sizeof((JOwned[]){__VA_ARGS__}) / sizeof(JOwned), (JOwned[]){__VA_ARGS__})
#define JO0() ((JOwned){json_object()})
#define JA0() ((JOwned){json_array()})
#define JN() ((JOwned){json_null()})
json_t *jrelease(json_t **p);
json_t *get(const json_t *v, const char *key);
const char *text(const json_t *v);
const char *field(const json_t *v, const char *key);
double number(const json_t *v, double fallback);
bool integer(const json_t *v, int64_t *out);
bool truth(const json_t *v);
bool jset(json_t *object, const char *key, const json_t *value);
bool jappend(json_t *array, const json_t *value);
json_t *parse_json(const char *bytes, size_t length, Error *error);
char *dump_json(const json_t *value);
char *id_string(const json_t *v);

typedef struct {
    char *data;
    size_t length, capacity;
} Buffer;
void buffer_free(Buffer *b);
void buffer_add(Buffer *b, const void *data, size_t length);
void buffer_text(Buffer *b, const char *text);
char *buffer_take(Buffer *b);
#define BUF(name) Buffer name __attribute__((cleanup(buffer_free))) = {0}
double now(void);
double monotonic_now(void);
char *read_file(const char *path, size_t *length, Error *error);
char *lower(const char *value);
char *trim(const char *value, const char *characters);
json_t *words(const char *value);
char *replace(const char *value, const char *from, const char *to);
char *join(const json_t *values, const char *delimiter);
char *time_format(double timestamp, const char *format, bool utc);
struct tm time_parts(double timestamp, bool utc);
bool bson_timestamp(const json_t *value, double *timestamp);
char *digest(const void *bytes, size_t length, const char *algorithm, Error *error);
char *digest_text(const char *value, const char *algorithm);
char *uuid_text(void);
void log_info(const char *message, bool warning);
void pause_between(double low, double high);
void short_sleep(double coefficient);
void long_sleep(double coefficient);
size_t codepoints(const char *value);
size_t utf16_count(const char *value);
size_t unicode_offset(const char *value, size_t points);
char *render(const char *pattern, const json_t *fields, Error *error);
char *human(int64_t value);

typedef struct {
    json_t *values;
    char *path, *app, *root;
} Config;
Config *config_load(const char *filename, Error *error);
Config *config_copy(const Config *source, const json_t *values);
void config_free(Config *config);
void auto_config_free(Config **config);
size_t config_workers(const Config *config);
size_t config_pending(const Config *config);
size_t config_batch(const Config *config);
char *config_cron_path(const Config *config);
typedef enum { SUPPLY_SENT, SUPPLY_REJECT, SUPPLY_SKIP, SUPPLY_STOP } Supply;
#endif
