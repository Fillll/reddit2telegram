#include "http.h"
#include <curl/curl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
Http *http_new(Metrics *m, bool telegram) {
    Http *http = xcalloc(1, sizeof(*http));
    http->handle = r2t_http_open();
    if (!http->handle)
        abort();
    http->metrics = m;
    http->telegram = telegram;
    return http;
}
void http_free(Http *h) {
    if (h) {
        r2t_http_close(h->handle);
        free(h);
    }
}
void auto_http_free(Http **h) {
    http_free(*h);
}
void response_free(Response *r) {
    if (r) {
        r2t_response_free(r->raw);
        json_decref(r->headers);
        free(r);
    }
}
void auto_response_free(Response **r) {
    response_free(*r);
}
static void count(Http *h, const char *prefix, const char *name, uint64_t n) {
    char key[100];
    snprintf(key, sizeof(key), "%s_%s", prefix, name);
    metrics_count(h->metrics, key, n);
}
Response *http_request(Http *h, const char *method, const char *url, const json_t *headers,
                       const void *body, size_t length, const json_t *multipart, const char *output,
                       uint64_t limit, const char *algorithm, bool allow_initial_failure,
                       Error *error) {
    const char *prefix = h->telegram ? "telegram" : "http";
    BUF(header_lines);
    const char *key;
    json_t *v;
    json_object_foreach(headers, key, v) {
        buffer_text(&header_lines, key);
        buffer_text(&header_lines, ": ");
        buffer_text(&header_lines, text(v));
        buffer_text(&header_lines, "\n");
    }
    STR(spec) = multipart ? dump_json(multipart) : NULL;
    count(h, prefix, "request_attempts", 1);
    r2t_response *raw = r2t_http_request(
        h->handle, method, url, header_lines.data ? header_lines.data : "", body, length, spec,
        output, limit, h->telegram ? 30 : (!strcmp(method, "HEAD") ? 3 : 5),
        h->telegram ? 30 : (!strcmp(method, "HEAD") ? 8 : 20), h->telegram ? 0 : 1, algorithm);
    if (!raw) {
        count(h, prefix, "transport_errors", 1);
        error_set(error, E_NETWORK, 0);
        return NULL;
    }
    Response *r = xcalloc(1, sizeof(*r));
    r->raw = raw;
    r->headers = json_object();
    if (!r->headers)
        abort();
    count(h, prefix, "requests", raw->requests);
    if (raw->requests > 1)
        count(h, prefix, "request_attempts", raw->requests - 1);
    count(h, prefix, "http_errors", raw->http_errors);
    count(h, prefix, "rate_limits", raw->rate_limits);
    count(h, prefix, "response_body_bytes", raw->received);
    if (h->telegram)
        metrics_count(h->metrics, "telegram_request_body_bytes", raw->sent);
    if (raw->error && !raw->too_large) {
        count(h, prefix, "transport_errors", 1);
        if (!allow_initial_failure || (raw->status >= 200 && raw->status < 300)) {
            error_set(error, raw->error == 28 || raw->error == 42 ? E_TIMEOUT : E_NETWORK, 0);
            response_free(r);
            return NULL;
        }
    }
    if (raw->headers) {
        STR(copy) = xstrdup(raw->headers);
        char *save = NULL;
        for (char *line = strtok_r(copy, "\r\n", &save); line;
             line = strtok_r(NULL, "\r\n", &save)) {
            char *colon = strchr(line, ':');
            if (!colon)
                continue;
            *colon = 0;
            STR(name) = lower(line);
            STR(value) = trim(colon + 1, NULL);
            json_object_set_new(r->headers, name, js(value).p);
        }
    }
    return r;
}
bool response_ok(const Response *r) {
    return r && r->raw->status >= 200 && r->raw->status < 300;
}
json_t *response_json(const Response *r, Error *error) {
    json_t *v = parse_json((const char *)(r->raw->body ? r->raw->body : (unsigned char *)""),
                           r->raw->length, error);
    if (!v)
        error_set(error, E_NETWORK, 0);
    return v;
}
const char *response_header(const Response *r, const char *key) {
    return r ? field(r->headers, key) : "";
}
bool http_download(Http *h, const char *url, const char *output, uint64_t limit) {
    Error error = {0};
    RESPONSE(r) =
        http_request(h, "GET", url, NULL, NULL, 0, NULL, output, limit, NULL, false, &error);
    bool success = r && response_ok(r) && !r->raw->too_large;
    if (!success)
        unlink(output);
    return success;
}
char *http_metadata(Http *h, const char *url, Error *error) {
    RESPONSE(r) =
        http_request(h, "GET", url, NULL, NULL, 0, NULL, NULL, 1024 * 1024, NULL, false, error);
    TRY(r, NULL);
    REQUIRE(response_ok(r) && !r->raw->too_large, E_MEDIA, NULL);
    return strndup((const char *)r->raw->body, r->raw->length);
}
json_t *http_api(Http *h, const char *token, const char *method, const json_t *params,
                 const char *video, Error *error) {
    STR(url) = strf("https://api.telegram.org/bot%s/%s", token, method);
    RESPONSE(response) = NULL;
    if (video) {
        json_auto_t *fields = json_object();
        const char *key;
        json_t *v;
        json_object_foreach(params, key, v) {
            STR(value) = json_is_string(v) ? xstrdup(text(v)) : dump_json(v);
            json_object_set_new(fields, key, js(value).p);
        }
        json_auto_t *spec =
            JO(P("fields", jr(fields)),
               P("files", JO(P("video", JO(P("path", js(video)), P("filename", js("video.mp4")),
                                           P("content_type", js("video/mp4")))))))
                .p;
        response = http_request(h, "POST", url, NULL, NULL, 0, spec, NULL, 0, NULL, false, error);
    } else {
        STR(bytes) = dump_json(params);
        json_auto_t *headers = JO(P("Content-Type", js("application/json"))).p;
        response = http_request(h, "POST", url, headers, bytes, strlen(bytes), NULL, NULL, 0, NULL,
                                false, error);
    }
    TRY(response, NULL);
    json_auto_t *body = response_json(response, error);
    TRY(body, NULL);
    if (!response_ok(response) || !json_is_true(get(body, "ok"))) {
        ErrorKind kind = response->raw->status == 400   ? E_REJECTED
                         : response->raw->status == 403 ? E_FORBIDDEN
                         : response->raw->status == 429 ? E_RATE_LIMIT
                                                        : E_TELEGRAM;
        error_set(error, kind, 0);
        return NULL;
    }
    json_t *result = json_incref(get(body, "result"));
    if (!strncmp(method, "send", 4) || !strcmp(method, "forwardMessage"))
        metrics_delivery(h->metrics, result);
    return result;
}
char *percent_encode(const char *value) {
    BUF(out);
    for (const unsigned char *p = (const unsigned char *)value; *p; p++) {
        unsigned char c = *p;
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
            c == '-' || c == '_' || c == '.' || c == '~')
            buffer_add(&out, p, 1);
        else {
            char bytes[] = {'%', "0123456789ABCDEF"[c >> 4], "0123456789ABCDEF"[c & 15]};
            buffer_add(&out, bytes, 3);
        }
    }
    return buffer_take(&out);
}
char *form_body(const json_t *fields) {
    BUF(out);
    bool first = true;
    const char *key;
    json_t *v;
    json_object_foreach(fields, key, v) {
        STR(k) = percent_encode(key);
        STR(value) = percent_encode(text(v));
        if (!first)
            buffer_text(&out, "&");
        first = false;
        buffer_text(&out, k);
        buffer_text(&out, "=");
        buffer_text(&out, value);
    }
    return buffer_take(&out);
}
static char *url_part(CURLU *url, CURLUPart part) {
    char *raw = NULL;
    if (curl_url_get(url, part, &raw, 0) != CURLUE_OK)
        return xstrdup("");
    char *out = xstrdup(raw);
    curl_free(raw);
    return out;
}
ParsedURL *url_parse(const char *value, Error *error) {
    r2t_init();
    CURLU *raw = curl_url();
    REQUIRE(raw, E_MEDIA, NULL);
    if (curl_url_set(raw, CURLUPART_URL, value, 0) != CURLUE_OK) {
        curl_url_cleanup(raw);
        error_set(error, E_MEDIA, 0);
        return NULL;
    }
    ParsedURL *u = xcalloc(1, sizeof(*u));
    u->scheme = url_part(raw, CURLUPART_SCHEME);
    u->host = url_part(raw, CURLUPART_HOST);
    u->path = url_part(raw, CURLUPART_PATH);
    u->query = url_part(raw, CURLUPART_QUERY);
    u->user = url_part(raw, CURLUPART_USER);
    u->password = url_part(raw, CURLUPART_PASSWORD);
    u->port = url_part(raw, CURLUPART_PORT);
    curl_url_cleanup(raw);
    return u;
}
void url_free(ParsedURL *u) {
    if (u) {
        free(u->scheme);
        free(u->host);
        free(u->path);
        free(u->query);
        free(u->user);
        free(u->password);
        free(u->port);
        free(u);
    }
}
void auto_url_free(ParsedURL **u) {
    url_free(*u);
}
