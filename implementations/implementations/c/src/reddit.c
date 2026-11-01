#include "reddit.h"
#include <math.h>
#include <openssl/evp.h>
#include <stdlib.h>
#include <string.h>
Reddit *reddit_new(const Config *config, Metrics *metrics) {
    Reddit *r = xcalloc(1, sizeof(*r));
    r->config = config;
    r->http = http_new(metrics, false);
    return r;
}
void reddit_free(Reddit *r) {
    if (r) {
        http_free(r->http);
        free(r->token);
        free(r);
    }
}
void auto_reddit_free(Reddit **r) {
    reddit_free(*r);
}
static char *base64(const char *s) {
    size_t n = strlen(s);
    char *out = xcalloc(4 * ((n + 2) / 3) + 1, 1);
    int length = EVP_EncodeBlock((unsigned char *)out, (const unsigned char *)s, (int)n);
    if (length < 0)
        abort();
    out[length] = 0;
    return out;
}
static bool authorize(Reddit *r, Error *error) {
    if (r->token && now() < r->expiry)
        return true;
    json_t *c = get(r->config->values, "reddit");
    STR(credentials) = strf("%s:%s", field(c, "client_id"), field(c, "client_secret"));
    STR(encoded) = base64(credentials);
    STR(auth) = strf("Basic %s", encoded);
    json_auto_t *headers =
        JO(P("User-Agent", js(field(c, "user_agent"))), P("Authorization", js(auth)),
           P("Content-Type", js("application/x-www-form-urlencoded")))
            .p;
    json_auto_t *params =
        JO(P("grant_type", js("password")), P("username", js(field(c, "username"))),
           P("password", js(field(c, "password"))))
            .p;
    STR(body) = form_body(params);
    RESPONSE(response) =
        http_request(r->http, "POST", "https://www.reddit.com/api/v1/access_token", headers, body,
                     strlen(body), NULL, NULL, 0, NULL, false, error);
    TRY(response, false);
    REQUIRE(response_ok(response), E_REDDIT, false);
    json_auto_t *data = response_json(response, error);
    TRY(data, false);
    REQUIRE(json_is_string(get(data, "access_token")), E_REDDIT, false);
    free(r->token);
    r->token = xstrdup(field(data, "access_token"));
    r->expiry = now() + number(get(data, "expires_in"), 3600) - 10;
    return true;
}
static void feedback(Reddit *r, const Response *response) {
    const char *keys[] = {"x-ratelimit-remaining", "x-ratelimit-reset", "x-ratelimit-used"};
    double values[3];
    for (size_t i = 0; i < 3; i++) {
        const char *s = response_header(response, keys[i]);
        char *end = NULL;
        values[i] = strtod(s, &end);
        if (end == s || *end)
            return;
    }
    double remaining = values[0], reset = values[1], used = values[2];
    r->next =
        now() +
        (remaining <= 0
             ? reset
             : fmin(reset, fmin(10, fmax(0, reset - (600 - 600 / (remaining + used) * used)))));
}
json_t *reddit_get(Reddit *r, const char *path, json_t *params, Error *error) {
    json_auto_t *query = params ? json_deep_copy(params) : json_object();
    json_object_set_new(query, "raw_json", js("1").p);
    STR(encoded) = form_body(query);
    STR(url) = strf("https://oauth.reddit.com%s?%s", path, encoded);
    for (int attempt = 0; attempt < 3; attempt++) {
        if (attempt)
            pause_between(attempt == 1 ? 0 : 2, attempt == 1 ? 2 : 4);
        double delay = r->next - now();
        if (delay > 0)
            pause_between(delay, delay);
        TRY(authorize(r, error), NULL);
        STR(auth) = strf("Bearer %s", r->token);
        json_auto_t *headers =
            JO(P("User-Agent", js(field(get(r->config->values, "reddit"), "user_agent"))),
               P("Authorization", js(auth)))
                .p;
        Error transient = {0};
        RESPONSE(response) = http_request(r->http, "GET", url, headers, NULL, 0, NULL, NULL, 0,
                                          NULL, false, &transient);
        if (!response) {
            if (attempt == 2) {
                *error = transient;
                return NULL;
            }
            continue;
        }
        feedback(r, response);
        long code = response->raw->status;
        if (code == 401) {
            free(r->token);
            r->token = NULL;
            r->expiry = 0;
            if (attempt < 2)
                continue;
        }
        if ((code == 408 || code == 500 || code == 502 || code == 503 || code == 504 ||
             code == 520 || code == 522) &&
            attempt < 2)
            continue;
        REQUIRE(code < 400, E_REDDIT, NULL);
        return response_json(response, error);
    }
    error_set(error, E_REDDIT, 0);
    return NULL;
}
json_t *reddit_listing(Reddit *r, const char *subreddit, const char *ranking, size_t limit,
                       const char *after, Error *error) {
    STR(count) = strf("%zu", limit < 25 ? limit : 25);
    json_auto_t *params = JO(P("limit", js(count))).p;
    if (after)
        json_object_set_new(params, "after", js(after).p);
    if (!strcmp(ranking, "top"))
        json_object_set_new(params, "t", js("all").p);
    STR(path) = strf("/r/%s/%s", subreddit, ranking);
    return reddit_get(r, path, params, error);
}
json_t *reddit_hydrate(Reddit *r, const json_t *submission, Error *error) {
    const char *id = field(submission, "id");
    REQUIRE(*id, E_REDDIT, NULL);
    STR(path) = strf("/comments/%s", id);
    json_auto_t *params = JO(P("limit", js("2048")), P("sort", js("confidence"))).p;
    json_auto_t *response = reddit_get(r, path, params, error);
    TRY(response, NULL);
    json_t *first = json_array_get(response, 0);
    json_t *children = get(get(first, "data"), "children");
    json_t *data = get(json_array_get(children, 0), "data");
    REQUIRE(json_is_object(data), E_REDDIT, NULL);
    return json_incref(data);
}
