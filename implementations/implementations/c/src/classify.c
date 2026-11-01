#include "sender.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void utf8_add(Buffer *out, uint32_t n) {
    unsigned char bytes[4];
    size_t size;
    if (n < 128) {
        bytes[0] = n;
        size = 1;
    } else if (n < 2048) {
        bytes[0] = 192 | (n >> 6);
        bytes[1] = 128 | (n & 63);
        size = 2;
    } else if (n < 65536) {
        bytes[0] = 224 | (n >> 12);
        bytes[1] = 128 | ((n >> 6) & 63);
        bytes[2] = 128 | (n & 63);
        size = 3;
    } else {
        bytes[0] = 240 | (n >> 18);
        bytes[1] = 128 | ((n >> 12) & 63);
        bytes[2] = 128 | ((n >> 6) & 63);
        bytes[3] = 128 | (n & 63);
        size = 4;
    }
    buffer_add(out, bytes, size);
}
char *html_decode(const char *value) {
    BUF(out);
    const char *p = value;
    const char *entities[] = {"amp;", "quot;", "apos;", "lt;", "gt;", "nbsp;"};
    const char *decoded[] = {"&", "\"", "'", "<", ">", "\xc2\xa0"};
    while (*p) {
        bool found = false;
        if (*p == '&') {
            for (size_t i = 0; i < 6; i++) {
                size_t n = strlen(entities[i]);
                if (!strncmp(p + 1, entities[i], n)) {
                    buffer_text(&out, decoded[i]);
                    p += n + 1;
                    found = true;
                    break;
                }
            }
            if (found)
                continue;
            if (p[1] == '#') {
                const char *start = p + 2;
                bool hex = *start == 'x' || *start == 'X';
                if (hex)
                    start++;
                char *end = NULL;
                unsigned long n = strtoul(start, &end, hex ? 16 : 10);
                if (end != start && *end == ';' && n > 0 && n <= 0x10ffff &&
                    !(n >= 0xd800 && n <= 0xdfff)) {
                    utf8_add(&out, (uint32_t)n);
                    p = end + 1;
                    continue;
                }
            }
        }
        buffer_add(&out, p++, 1);
    }
    return buffer_take(&out);
}
char *html_escape(const char *value) {
    BUF(out);
    for (const char *p = value; *p; p++) {
        const char *s = *p == '&'    ? "&amp;"
                        : *p == '<'  ? "&lt;"
                        : *p == '>'  ? "&gt;"
                        : *p == '\"' ? "&quot;"
                        : *p == '\'' ? "&#x27;"
                                     : NULL;
        if (s)
            buffer_text(&out, s);
        else
            buffer_add(&out, p, 1);
    }
    return buffer_take(&out);
}
static Media *media_new(const char *kind, const char *url, const json_t *groups) {
    Media *m = xcalloc(1, sizeof(*m));
    m->kind = kind;
    m->url = xstrdup(url);
    m->groups = groups ? json_incref((json_t *)groups) : json_array();
    return m;
}
void media_free(Media *m) {
    if (m) {
        free(m->url);
        json_decref(m->groups);
        free(m);
    }
}
void auto_media_free(Media **m) {
    media_free(*m);
}
static json_t *groups_of(const json_t *items) {
    json_t *groups = json_array();
    if (!groups)
        abort();
    for (size_t i = 0; i < json_array_size(items); i += 10) {
        json_t *group = json_array();
        if (!group)
            abort();
        for (size_t j = i; j < i + 10 && j < json_array_size(items); j++)
            jappend(group, json_array_get(items, j));
        json_array_append_new(groups, group);
    }
    return groups;
}
typedef struct {
    json_t *value;
} Item;
static void items_free(Item **p) {
    free(*p);
}
static int compare_items(const void *a, const void *b, void *context) {
    const Item *x = a, *y = b;
    if (*(bool *)context) {
        int64_t n = 0, m = 0;
        integer(get(x->value, "id"), &n);
        integer(get(y->value, "id"), &m);
        return (n > m) - (n < m);
    }
    return strcmp(field(x->value, "id"), field(y->value, "id"));
}
static bool suffix(const char *value, const char *ending) {
    size_t n = strlen(value), m = strlen(ending);
    return n >= m && !strcmp(value + n - m, ending);
}
static char *mime_type(Sender *s, const char *url) {
    Error ignored = {0};
    RESPONSE(r) =
        http_request(s->media, "HEAD", url, NULL, NULL, 0, NULL, NULL, 0, NULL, false, &ignored);
    return xstrdup(response_header(r, "content-type"));
}
static json_t *imgur_image(const json_t *v) {
    bool animated = json_is_true(get(v, "animated"));
    const char *link = field(v, "link");
    if (animated) {
        if (*field(v, "mp4"))
            link = field(v, "mp4");
        else if (*field(v, "gifv"))
            link = field(v, "gifv");
    }
    STR(normalized) = suffix(link, ".gifv") ? strndup(link, strlen(link) - 1) : xstrdup(link);
    return JO(P("type", js(animated ? "video" : "photo")), P("media", js(normalized))).p;
}
static Media *imgur(Sender *s, const char *url, const ParsedURL *parsed) {
    json_auto_t *cfg = json_incref(get(s->config->values, "imgur"));
    if (json_is_null(cfg)) {
        STR(path) = strf("%s/configs/imgur.yml", s->config->app);
        Error ignored = {0};
        Config *config __attribute__((cleanup(auto_config_free))) = config_load(path, &ignored);
        if (config) {
            json_decref(cfg);
            cfg = json_incref(config->values);
        }
    }
    if (json_is_null(cfg))
        return media_new("other", url, NULL);
    STR(path) = trim(parsed->path, "/");
    json_auto_t *parts = split_text(path, "/");
    const char *first = text(json_array_get(parts, 0));
    if (!*first || !strcmp(first, "topic"))
        return media_new("other", url, NULL);
    bool album = !strcmp(first, "a") || !strcmp(first, "gallery");
    const char *identifier = text(json_array_get(parts, album ? 1 : json_array_size(parts) - 1));
    const char *dot = strchr(identifier, '.');
    STR(id) = dot ? strndup(identifier, (size_t)(dot - identifier)) : xstrdup(identifier);
    const char *endpoints[] = {album ? "album" : "image", "image"};
    for (size_t i = 0; i < (album ? 2u : 1u); i++) {
        const char *endpoint = endpoints[i];
        if (!strcmp(endpoint, "image") && !strcmp(first, "a"))
            break;
        STR(api) = strf("https://api.imgur.com/3/%s/%s", endpoint, id);
        STR(auth) = strf("Client-ID %s", field(cfg, "client_id"));
        json_auto_t *headers = JO(P("Authorization", js(auth))).p;
        Error ignored = {0};
        RESPONSE(response) = http_request(s->media, "GET", api, headers, NULL, 0, NULL, NULL, 0,
                                          NULL, false, &ignored);
        if (!response)
            continue;
        json_auto_t *body = response_json(response, &ignored);
        if (!body || !json_is_true(get(body, "success")))
            continue;
        json_t *data = get(body, "data");
        json_t *images = get(data, "images");
        if (json_is_array(images)) {
            json_auto_t *items = json_array();
            size_t n;
            json_t *image;
            json_array_foreach(images, n, image) json_array_append_new(items, imgur_image(image));
            json_auto_t *groups = groups_of(items);
            return media_new("album", url, groups);
        }
        json_auto_t *item = imgur_image(data);
        return media_new(json_is_true(get(data, "animated")) ? "gif" : "img", field(item, "media"),
                         NULL);
    }
    return media_new("other", url, NULL);
}
Media *sender_classify(Sender *s, const json_t *submission, Error *error) {
    const char *url = field(submission, "url");
    URL(parsed) = url_parse(url, error);
    TRY(parsed, NULL);
    STR(low) = lower(url);
    json_t *items = get(get(submission, "gallery_data"), "items");
    if (json_is_array(items)) {
        bool numeric = true, strings = true;
        size_t i;
        json_t *item;
        json_array_foreach(items, i, item) {
            numeric &= json_is_integer(get(item, "id"));
            strings &= json_is_string(get(item, "id"));
        }
        REQUIRE(numeric || strings, E_MEDIA, NULL);
        json_auto_t *last = json_object();
        json_array_foreach(items, i, item) {
            STR(id) = id_string(get(item, "id"));
            jset(last, id, item);
        }
        size_t n = json_object_size(last);
        Item *ordered __attribute__((cleanup(items_free))) = xcalloc(n ? n : 1, sizeof(Item));
        const char *key;
        size_t at = 0;
        json_object_foreach(last, key, item) ordered[at++] = (Item){item};
        qsort_r(ordered, n, sizeof(Item), compare_items, &numeric);
        json_auto_t *media = json_array();
        for (i = 0; i < n; i++) {
            item = ordered[i].value;
            json_t *source =
                get(get(get(submission, "media_metadata"), field(item, "media_id")), "s");
            bool photo = json_is_string(get(source, "u"));
            json_t *link = get(source, photo ? "u" : "mp4");
            REQUIRE(json_is_string(link), E_MEDIA, NULL);
            STR(decoded) = html_decode(text(link));
            Error ignored = {0};
            URL(u) = url_parse(decoded, &ignored);
            STR(normalized) = u && !strcmp(u->host, "preview.redd.it")
                                  ? strf("https://i.redd.it%s", u->path)
                                  : replace(decoded, "auto=webp", "auto=jpg");
            json_array_append_new(
                media, JO(P("type", js(photo ? "photo" : "video")), P("media", js(normalized))).p);
        }
        json_auto_t *groups = groups_of(media);
        return media_new("gallery", "", groups);
    }
    json_t *video = json_is_true(get(submission, "is_video"))
                        ? get(get(submission, "media"), "reddit_video")
                        : json_null();
    if (json_is_null(video)) {
        json_t *first = json_array_get(get(submission, "crosspost_parent_list"), 0);
        if (json_is_true(get(first, "is_video")))
            video = get(get(first, "media"), "reddit_video");
    }
    if (!json_is_null(video))
        return media_new(json_is_true(get(video, "is_gif")) ? "gif" : "video",
                         field(video, "fallback_url"), NULL);
    if (json_is_true(get(submission, "is_self")))
        return media_new("text", "", NULL);
    bool image = suffix(low, ".jpg") || suffix(low, ".jpeg") || suffix(low, ".png");
    if (!strcmp(parsed->host, "i.redd.it") && image)
        return media_new("img", url, NULL);
    if (!strcmp(parsed->host, "i.imgur.com") || !strcmp(parsed->host, "i.stack.imgur.com")) {
        if (suffix(low, ".gifv")) {
            STR(base) = strndup(url, strlen(url) - 5);
            STR(mp4) = strf("%s.mp4", base);
            return media_new("gif", mp4, NULL);
        }
        if (suffix(low, ".gif") || suffix(low, ".mp4"))
            return media_new("gif", url, NULL);
        if (image)
            return media_new("img", url, NULL);
    }
    STR(mime) = mime_type(s, url);
    if (!strcmp(mime, "image/jpeg") || !strcmp(mime, "image/png"))
        return media_new("img", url, NULL);
    if (strstr(mime, "image/gif")) {
        if (suffix(url, ".gif")) {
            STR(base) = strndup(url, strlen(url) - 4);
            STR(mp4) = strf("%s.mp4", base);
            STR(type) = mime_type(s, mp4);
            if (!strcmp(type, "video/mp4"))
                return media_new("gif", mp4, NULL);
        }
        return media_new("gif", url, NULL);
    }
    if (suffix(url, ".gifv")) {
        STR(base) = strndup(url, strlen(url) - 5);
        STR(mp4) = strf("%s.mp4", base);
        STR(type) = mime_type(s, mp4);
        if (!strcmp(type, "video/mp4"))
            return media_new("gif", mp4, NULL);
        STR(gif) = strndup(url, strlen(url) - 1);
        STR(gif_type) = mime_type(s, gif);
        if (!strcmp(gif_type, "image/gif"))
            return media_new("gif", gif, NULL);
    }
    if (!strcmp(parsed->host, "imgur.com") || !strcmp(parsed->host, "www.imgur.com") ||
        !strcmp(parsed->host, "m.imgur.com"))
        return imgur(s, url, parsed);
    if (strstr(parsed->host, "gfycat.com")) {
        STR(path) = trim(parsed->path, "/");
        json_auto_t *parts = split_text(path, "/");
        const char *name =
            text(json_array_get(parts, !strcmp(text(json_array_get(parts, 0)), "detail") ? 1 : 0));
        STR(api) = strf("https://api.gfycat.com/v1/gfycats/%s", name);
        Error ignored = {0};
        STR(content) = http_metadata(s->media, api, &ignored);
        if (content) {
            json_auto_t *data = parse_json(content, strlen(content), &ignored);
            json_t *link = get(get(data, "gfyItem"), "mp4Url");
            if (json_is_string(link))
                return media_new("gif", text(link), NULL);
        }
    }
    return media_new("other", url, NULL);
}
bool sender_simple(Sender *s, const json_t *initial, const json_t *options, Reddit *reddit,
                   Supply *result, Error *error) {
    json_auto_t *submission = json_incref((json_t *)initial);
    if (json_is_number(get(options, "min_upvotes_limit")) &&
        json_is_null(get(submission, "score"))) {
        json_t *hydrated = reddit_hydrate(reddit, submission, error);
        TRY(hydrated, false);
        json_decref(submission);
        submission = hydrated;
    }
    if (json_is_number(get(options, "min_upvotes_limit")) &&
        number(get(submission, "score"), 0) < number(get(options, "min_upvotes_limit"), 0))
        return supply_result(result, SUPPLY_SKIP);
    bool missing =
        !json_object_get(submission, "url") || !json_object_get(submission, "is_self") ||
        (json_is_true(get(submission, "is_gallery")) &&
         !json_object_get(submission, "gallery_data")) ||
        (json_is_array(get(get(submission, "gallery_data"), "items")) &&
         !json_object_get(submission, "media_metadata")) ||
        (json_is_true(get(submission, "is_video")) && !json_object_get(submission, "media"));
    Error classify_error = {0};
    if (missing) {
        json_t *hydrated = reddit_hydrate(reddit, submission, &classify_error);
        if (!hydrated) {
            STR(channel) = sender_channel(s);
            STR(message) = strf("HTTP fail prevented at %s", channel);
            log_info(message, false);
            return supply_result(result, SUPPLY_SKIP);
        }
        json_decref(submission);
        submission = hydrated;
    }
    MEDIA(media) = sender_classify(s, submission, &classify_error);
    if (!media) {
        STR(channel) = sender_channel(s);
        STR(message) = strf("HTTP fail prevented at %s", channel);
        log_info(message, false);
        return supply_result(result, SUPPLY_SKIP);
    }
    const char *required[] = {"title", "selftext", "score", "subreddit", "over_18"};
    for (size_t i = 0; i < 5; i++)
        if (!json_object_get(submission, required[i])) {
            json_t *hydrated = reddit_hydrate(reddit, submission, error);
            TRY(hydrated, false);
            json_decref(submission);
            submission = hydrated;
            break;
        }
    int64_t score = (int64_t)number(get(submission, "score"), 0);
    if ((!json_object_get(options, "nsfw_filter_out") || truth(get(options, "nsfw_filter_out"))) &&
        json_is_true(get(submission, "over_18")))
        return supply_result(result, SUPPLY_REJECT);
    if (json_is_true(get(options, "check_dups")) && *media->url) {
        bool duplicate = false;
        TRY(sender_duplicate(s, media->url, &duplicate, error), false);
        if (duplicate)
            return supply_result(result, SUPPLY_REJECT);
    }
    json_t *rule = json_object_get(options, media->kind);
    if (!rule)
        rule = json_true();
    if (!truth(rule))
        return supply_result(result, SUPPLY_REJECT);
    STR(channel) = sender_channel(s);
    STR(score_text) = strf("%lld", (long long)score);
    STR(upvotes) = human(score);
    STR(short_link) = strf("https://redd.it/%s", field(submission, "id"));
    json_auto_t *fields =
        JO(P("what", js(media->kind)), P("url", js(media->url)),
           P("title", js(field(submission, "title"))),
           P("self_text", js(field(submission, "selftext"))),
           P("link", js(field(submission, "url"))), P("short_link", js(short_link)),
           P("subreddit_name", js(field(submission, "subreddit"))), P("score", js(score_text)),
           P("upvotes", js(upvotes)), P("channel", js(channel)))
            .p;
    const char *key;
    json_t *v;
    json_object_foreach(options, key, v) {
        STR(value) = json_is_string(v) ? xstrdup(text(v)) : dump_json(v);
        json_object_set_new(fields, key, js(value).p);
    }
    const char *fallback = !strcmp(media->kind, "text")
                               ? "{title}\n\n{self_text}\n\n{short_link}\n{channel}"
                           : (!strcmp(media->kind, "video") || !strcmp(media->kind, "gallery"))
                               ? "{title}\n\n{short_link}\n{channel}"
                           : (!strcmp(media->kind, "album") || !strcmp(media->kind, "other"))
                               ? "{title}\n{link}\n\n{short_link}\n{channel}"
                               : "{title}\n{short_link}\n{channel}";
    const char *pattern = json_is_string(rule) ? text(rule) : fallback;
    if (!strcmp(media->kind, "text")) {
        int64_t limit;
        if (integer(get(options, "max_selftext_len"), &limit)) {
            const char *source = field(submission, "selftext");
            size_t count = codepoints(source),
                   take = limit < 0 ? (size_t)(-limit) > count ? 0 : count - (size_t)(-limit)
                                    : (size_t)limit;
            STR(prefix) = strndup(source, unicode_offset(source, take));
            STR(body) = strf("%s...", prefix);
            json_object_set_new(fields, "self_text", js(body).p);
        }
        bool preview = truth(get(options, "disable_web_page_preview"));
        STR(a) = replace(pattern, "{short_link}", "[{short_link}]({short_link})");
        STR(markdown) = replace(a, "{channel}", "[{channel}]({channel})");
        STR(body) = render(markdown, fields, error);
        TRY(body, false);
        Error transient = {0};
        if (sender_text(s, body, preview, "Markdown", result, &transient))
            return true;
        if (transient.kind != E_REJECTED) {
            *error = transient;
            return false;
        }
        STR(message) = strf("Markdown fail in %s; sending as plain text.", channel);
        log_info(message, false);
        STR(plain) = render(pattern, fields, error);
        TRY(plain, false);
        return sender_text(s, plain, preview, NULL, result, error);
    }
    STR(body) = render(pattern, fields, error);
    TRY(body, false);
    if (!strcmp(media->kind, "img"))
        return sender_image(s, media->url, body, result, error);
    if (!strcmp(media->kind, "gif"))
        return sender_gif(s, media->url, body, result, error);
    if (!strcmp(media->kind, "video")) {
        json_t *dash = get(get(get(submission, "media"), "reddit_video"), "dash_url");
        return sender_video(s, media->url, body, json_is_string(dash) ? text(dash) : NULL, result,
                            error);
    }
    if (!strcmp(media->kind, "gallery") || !strcmp(media->kind, "album"))
        return sender_gallery(s, media->groups, body, result, error);
    return sender_text(s, body, false, NULL, result, error);
}
