#include "model.h"
#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <openssl/rand.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

const char *error_name(Error e) {
    static const char *names[] = {
        "None",         "Config",   "Io",       "Database",    "Network",       "Timeout",
        "Reddit",       "Telegram", "Rejected", "Forbidden",   "RateLimit",     "Lease",
        "Announcement", "Media",    "Template", "UnknownTask", "IncompletePort"};
    return e.kind >= E_NONE && e.kind <= E_INCOMPLETE_PORT ? names[e.kind] : "NativeError";
}
bool error_set(Error *e, ErrorKind kind, int code) {
    if (e) {
        e->kind = kind;
        e->code = code;
    }
    return false;
}
void *xcalloc(size_t n, size_t s) {
    void *p = calloc(n, s);
    if (!p)
        abort();
    return p;
}
char *xstrdup(const char *s) {
    char *p = strdup(s ? s : "");
    if (!p)
        abort();
    return p;
}
char *strf(const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    char *s = NULL;
    int n = vasprintf(&s, fmt, args);
    va_end(args);
    if (n < 0)
        abort();
    return s;
}
void auto_free(char **p) {
    free(*p);
}
void auto_bson_free(char **p) {
    r2t_free(*p);
}
JOwned jo_fields(size_t n, const JField *fields) {
    json_t *out = json_object();
    if (!out)
        abort();
    for (size_t i = 0; i < n; i++)
        if (!fields[i].value.p || json_object_set_new(out, fields[i].key, fields[i].value.p))
            abort();
    return (JOwned){out};
}
JOwned ja_values(size_t n, const JOwned *values) {
    json_t *out = json_array();
    if (!out)
        abort();
    for (size_t i = 0; i < n; i++)
        if (!values[i].p || json_array_append_new(out, values[i].p))
            abort();
    return (JOwned){out};
}
JOwned js(const char *s) {
    json_t *v = json_string(s ? s : "");
    if (!v)
        abort();
    return (JOwned){v};
}
JOwned ji(int64_t n) {
    json_t *v = json_integer((json_int_t)n);
    if (!v)
        abort();
    return (JOwned){v};
}
JOwned jf(double n) {
    json_t *v = json_real(n);
    if (!v)
        abort();
    return (JOwned){v};
}
JOwned jb(bool b) {
    return (JOwned){json_boolean(b)};
}
JOwned jr(const json_t *v) {
    return (JOwned){json_incref((json_t *)(v ? v : json_null()))};
}
JOwned jdate(double seconds) {
    char ms[32];
    snprintf(ms, sizeof(ms), "%lld", (long long)(seconds * 1000));
    return JO(P("$date", JO(P("$numberLong", js(ms)))));
}
json_t *jrelease(json_t **p) {
    json_t *v = *p;
    *p = NULL;
    return v;
}
json_t *get(const json_t *v, const char *key) {
    json_t *item = json_is_object(v) ? json_object_get(v, key) : NULL;
    return item ? item : json_null();
}
const char *text(const json_t *v) {
    const char *s = json_string_value(v);
    return s ? s : "";
}
const char *field(const json_t *v, const char *key) {
    return text(get(v, key));
}
double number(const json_t *v, double fallback) {
    if (json_is_number(v))
        return json_number_value(v);
    const char *keys[] = {"$numberLong", "$numberInt", "$numberDouble"};
    for (size_t i = 0; i < 3; i++) {
        json_t *n = get(v, keys[i]);
        if (json_is_string(n)) {
            char *end = NULL;
            double x = strtod(text(n), &end);
            if (end != text(n) && !*end)
                return x;
        }
    }
    return fallback;
}
bool integer(const json_t *v, int64_t *out) {
    if (json_is_integer(v)) {
        *out = (int64_t)json_integer_value(v);
        return true;
    }
    if (json_is_real(v)) {
        double n = json_real_value(v);
        if (isfinite(n) && trunc(n) == n && n >= -9223372036854775808.0 &&
            n < 9223372036854775808.0) {
            *out = (int64_t)n;
            return true;
        }
    }
    if (json_is_string(get(v, "$numberLong"))) {
        char *end = NULL;
        errno = 0;
        long long n = strtoll(field(v, "$numberLong"), &end, 10);
        if (!errno && end != field(v, "$numberLong") && !*end) {
            *out = n;
            return true;
        }
    }
    return false;
}
bool truth(const json_t *v) {
    if (!v || json_is_null(v) || json_is_false(v))
        return false;
    if (json_is_number(v))
        return json_number_value(v) != 0;
    if (json_is_string(v))
        return json_string_length(v) != 0;
    if (json_is_array(v))
        return json_array_size(v) != 0;
    if (json_is_object(v))
        return json_object_size(v) != 0;
    return true;
}
bool jset(json_t *object, const char *key, const json_t *v) {
    if (json_object_set(object, key, (json_t *)(v ? v : json_null())))
        abort();
    return true;
}
bool jappend(json_t *array, const json_t *v) {
    if (json_array_append(array, (json_t *)(v ? v : json_null())))
        abort();
    return true;
}
json_t *parse_json(const char *bytes, size_t n, Error *error) {
    json_t *v = json_loadb(bytes, n, JSON_DECODE_ANY, NULL);
    if (!v)
        error_set(error, E_CONFIG, 0);
    return v;
}
char *dump_json(const json_t *v) {
    char *s = json_dumps(v ? v : json_null(), JSON_COMPACT | JSON_ENCODE_ANY);
    if (!s)
        abort();
    return s;
}
char *id_string(const json_t *v) {
    if (json_is_string(v))
        return xstrdup(text(v));
    if (json_is_string(get(v, "$oid")))
        return xstrdup(field(v, "$oid"));
    return dump_json(v);
}
void buffer_free(Buffer *b) {
    free(b->data);
    b->data = NULL;
    b->length = b->capacity = 0;
}
void buffer_add(Buffer *b, const void *data, size_t n) {
    if (n > SIZE_MAX - b->length - 1)
        abort();
    size_t needed = b->length + n + 1;
    if (needed > b->capacity) {
        size_t capacity = b->capacity ? b->capacity : 128;
        while (capacity < needed) {
            if (capacity > SIZE_MAX / 2) {
                capacity = needed;
                break;
            }
            capacity *= 2;
        }
        void *p = realloc(b->data, capacity);
        if (!p)
            abort();
        b->data = p;
        b->capacity = capacity;
    }
    if (n)
        memcpy(b->data + b->length, data, n);
    b->length += n;
    b->data[b->length] = 0;
}
void buffer_text(Buffer *b, const char *s) {
    buffer_add(b, s, strlen(s));
}
char *buffer_take(Buffer *b) {
    char *s = b->data ? b->data : xstrdup("");
    b->data = NULL;
    b->length = b->capacity = 0;
    return s;
}
double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_REALTIME, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}
double monotonic_now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}
char *read_file(const char *path, size_t *length, Error *error) {
    FILE *file = fopen(path, "rb");
    REQUIRE(file, E_IO, NULL);
    BUF(out);
    char bytes[8192];
    size_t n;
    while ((n = fread(bytes, 1, sizeof(bytes), file)))
        buffer_add(&out, bytes, n);
    int failed = ferror(file);
    fclose(file);
    REQUIRE(!failed, E_IO, NULL);
    if (length)
        *length = out.length;
    return buffer_take(&out);
}
char *lower(const char *s) {
    char *out = xstrdup(s);
    for (char *p = out; *p; p++)
        *p = (char)tolower((unsigned char)*p);
    return out;
}
static uint32_t next_unicode(const char *s, size_t n, size_t *index) {
    unsigned char c = s[(*index)++];
    if (c < 128)
        return c;
    int remaining = (c & 224) == 192 ? 1 : (c & 240) == 224 ? 2 : (c & 248) == 240 ? 3 : 0;
    uint32_t value = c & ((1u << (6 - remaining)) - 1);
    for (int i = 0; i < remaining && *index < n; i++) {
        unsigned char b = s[*index];
        if ((b & 192) != 128)
            break;
        value = (value << 6) | (b & 63);
        (*index)++;
    }
    return value;
}
static bool whitespace(uint32_t c) {
    return (c >= 9 && c <= 13) || (c >= 28 && c <= 32) || c == 0x85 || c == 0xa0 || c == 0x1680 ||
           (c >= 0x2000 && c <= 0x200a) || c == 0x2028 || c == 0x2029 || c == 0x202f ||
           c == 0x205f || c == 0x3000;
}
char *trim(const char *s, const char *characters) {
    size_t n = strlen(s), first = n, last = 0;
    if (characters) {
        first = strspn(s, characters);
        last = n;
        while (last > first && strchr(characters, s[last - 1]))
            last--;
    } else
        for (size_t i = 0; i < n;) {
            size_t start = i;
            uint32_t c = next_unicode(s, n, &i);
            if (!whitespace(c)) {
                if (first == n)
                    first = start;
                last = i;
            }
        }
    return first >= last ? xstrdup("") : strndup(s + first, last - first);
}
json_t *words(const char *s) {
    json_t *out = json_array();
    if (!out)
        abort();
    size_t n = strlen(s), start = SIZE_MAX;
    for (size_t i = 0; i < n;) {
        size_t pos = i;
        uint32_t c = next_unicode(s, n, &i);
        if (whitespace(c)) {
            if (start != SIZE_MAX) {
                json_t *word = json_stringn(s + start, pos - start);
                if (!word || json_array_append_new(out, word))
                    abort();
                start = SIZE_MAX;
            }
        } else if (start == SIZE_MAX)
            start = pos;
    }
    if (start != SIZE_MAX) {
        json_t *word = json_string(s + start);
        if (!word || json_array_append_new(out, word))
            abort();
    }
    return out;
}
char *replace(const char *s, const char *from, const char *to) {
    BUF(out);
    size_t n = strlen(from);
    if (!n)
        return xstrdup(s);
    const char *at = s, *next;
    while ((next = strstr(at, from))) {
        buffer_add(&out, at, (size_t)(next - at));
        buffer_text(&out, to);
        at = next + n;
    }
    buffer_text(&out, at);
    return buffer_take(&out);
}
char *join(const json_t *values, const char *delimiter) {
    BUF(out);
    size_t i;
    json_t *v;
    json_array_foreach(values, i, v) {
        if (i)
            buffer_text(&out, delimiter);
        buffer_text(&out, text(v));
    }
    return buffer_take(&out);
}
json_t *split_text(const char *s, const char *delimiter) {
    json_t *out = json_array();
    if (!out)
        abort();
    size_t n = strlen(delimiter);
    if (!n) {
        json_array_append_new(out, js(s).p);
        return out;
    }
    const char *start = s, *end;
    while ((end = strstr(start, delimiter))) {
        json_t *v = json_stringn(start, (size_t)(end - start));
        if (!v || json_array_append_new(out, v))
            abort();
        start = end + n;
    }
    json_array_append_new(out, js(start).p);
    return out;
}
struct tm time_parts(double stamp, bool utc) {
    time_t time = (time_t)stamp;
    struct tm tm = {0};
    if (utc)
        gmtime_r(&time, &tm);
    else
        localtime_r(&time, &tm);
    return tm;
}
char *time_format(double stamp, const char *format, bool utc) {
    struct tm tm = time_parts(stamp, utc);
    char out[160];
    if (!strftime(out, sizeof(out), format, &tm))
        return xstrdup("");
    return xstrdup(out);
}
bool bson_timestamp(const json_t *v, double *stamp) {
    json_t *date = get(v, "$date");
    if (json_is_null(date))
        return false;
    if (json_is_string(date)) {
        struct tm tm = {0};
        const char *s = text(date);
        char *end = strptime(s, "%Y-%m-%dT%H:%M:%S", &tm);
        if (!end)
            return false;
        *stamp = timegm(&tm);
        if (*end == '.')
            *stamp += strtod(end, NULL);
        return true;
    }
    *stamp = number(date, 0) / 1000.;
    return true;
}
char *digest(const void *bytes, size_t n, const char *algorithm, Error *error) {
    BSONSTR(raw) = r2t_digest(algorithm, bytes, n);
    REQUIRE(raw, E_IO, NULL);
    return xstrdup(raw);
}
char *digest_text(const char *value, const char *algorithm) {
    Error error = {0};
    char *hash = digest(value, strlen(value), algorithm, &error);
    if (!hash)
        abort();
    return hash;
}
char *uuid_text(void) {
    unsigned char bytes[16];
    if (RAND_bytes(bytes, 16) != 1)
        abort();
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    char *out = xcalloc(33, 1);
    for (int i = 0; i < 16; i++)
        snprintf(out + i * 2, 3, "%02x", bytes[i]);
    return out;
}
void log_info(const char *message, bool warning) {
    static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
    pthread_mutex_lock(&lock);
    STR(date) = time_format(now(), "%Y-%m-%d %H:%M:%S", false);
    fprintf(stderr, "%s - r2t.c - %s - %s\n", date, warning ? "WARNING" : "INFO", message);
    pthread_mutex_unlock(&lock);
}
void pause_between(double a, double b) {
    uint64_t random;
    if (RAND_bytes((unsigned char *)&random, sizeof(random)) != 1)
        abort();
    double value = a + (b - a) * (double)(random >> 11) / 9007199254740992.0;
    struct timespec t = {.tv_sec = (time_t)value, .tv_nsec = (long)((value - floor(value)) * 1e9)};
    while (nanosleep(&t, &t) && errno == EINTR) {
    }
}
void short_sleep(double c) {
    pause_between(2 * c, 4 * c);
}
void long_sleep(double c) {
    pause_between(8 * c, 20 * c);
}
size_t codepoints(const char *s) {
    size_t n = 0;
    for (; *s; s++)
        if (((unsigned char)*s & 192) != 128)
            n++;
    return n;
}
size_t utf16_count(const char *s) {
    size_t n = 0;
    for (; *s; s++) {
        unsigned char c = *s;
        if ((c & 192) != 128)
            n += c >= 240 ? 2 : 1;
    }
    return n;
}
size_t unicode_offset(const char *s, size_t points) {
    size_t i = 0, n = 0;
    for (; s[i]; i++)
        if (((unsigned char)s[i] & 192) != 128) {
            if (n == points)
                break;
            n++;
        }
    return i;
}
char *render(const char *pattern, const json_t *fields, Error *error) {
    BUF(out);
    for (size_t i = 0; pattern[i];) {
        char c = pattern[i++];
        if (c == '{' || c == '}') {
            if (pattern[i] == c) {
                buffer_add(&out, &c, 1);
                i++;
                continue;
            }
            REQUIRE(c != '}', E_TEMPLATE, NULL);
            const char *end = strchr(pattern + i, '}');
            REQUIRE(end, E_TEMPLATE, NULL);
            STR(key) = strndup(pattern + i, (size_t)(end - pattern - i));
            json_t *v = get(fields, key);
            REQUIRE(json_is_string(v), E_TEMPLATE, NULL);
            buffer_text(&out, text(v));
            i = (size_t)(end - pattern) + 1;
        } else
            buffer_add(&out, &c, 1);
    }
    return buffer_take(&out);
}
char *human(int64_t n) {
    if (n > -1000 && n < 1000)
        return strf("%lld", (long long)n);
    double v = n;
    size_t index = 0;
    const char *suffix[] = {"", "k", "M", "G", "T", "P"};
    while (fabs(v) >= 1000 && index < 5) {
        index++;
        v = nearbyint(v / 100) / 10.;
    }
    return strf("%.1f%s", v, suffix[index]);
}
Config *config_load(const char *filename, Error *error) {
    STR(path) = realpath(filename, NULL);
    REQUIRE(path, E_CONFIG, NULL);
    BSONSTR(raw) = r2t_yaml_json(path);
    REQUIRE(raw, E_CONFIG, NULL);
    json_auto_t *parsed = parse_json(raw, strlen(raw), error);
    TRY(parsed, NULL);
    Config *c = xcalloc(1, sizeof(*c));
    c->values = json_incref(get(parsed, "value"));
    c->path = xstrdup(path);
    c->app = xstrdup(path);
    for (int i = 0; i < 2; i++) {
        char *slash = strrchr(c->app, '/');
        if (!slash) {
            config_free(c);
            error_set(error, E_CONFIG, 0);
            return NULL;
        }
        *slash = 0;
    }
    c->root = xstrdup(c->app);
    char *slash = strrchr(c->root, '/');
    if (!slash) {
        config_free(c);
        error_set(error, E_CONFIG, 0);
        return NULL;
    }
    *slash = 0;
    return c;
}
Config *config_copy(const Config *c, const json_t *values) {
    Config *v = xcalloc(1, sizeof(*v));
    v->path = xstrdup(c->path);
    v->app = xstrdup(c->app);
    v->root = xstrdup(c->root);
    v->values = json_incref((json_t *)values);
    return v;
}
void config_free(Config *c) {
    if (c) {
        json_decref(c->values);
        free(c->path);
        free(c->app);
        free(c->root);
        free(c);
    }
}
void auto_config_free(Config **c) {
    config_free(*c);
}
size_t config_workers(const Config *c) {
    long cpus = sysconf(_SC_NPROCESSORS_ONLN);
    return (size_t)number(get(get(c->values, "pool"), "size"), cpus > 0 ? cpus : 1);
}
size_t config_pending(const Config *c) {
    return (size_t)number(get(get(c->values, "consumer"), "max_pending"), config_workers(c));
}
size_t config_batch(const Config *c) {
    return (size_t)number(get(get(c->values, "consumer"), "batch_size"), config_workers(c) * 2);
}
char *config_cron_path(const Config *c) {
    const char *path = field(c->values, "cron_file");
    return path[0] == '/' ? xstrdup(path) : strf("%s/%s", c->app, path);
}
