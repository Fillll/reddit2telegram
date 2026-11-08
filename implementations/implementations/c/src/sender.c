#include "sender.h"
#include <dirent.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
Sender *sender_new(const Config *c, Database *db, const json_t *destination, Metrics *m,
                   sem_t *videos) {
    Sender *s = xcalloc(1, sizeof(*s));
    s->config = c;
    s->db = db;
    s->destination = json_incref((json_t *)destination);
    s->metrics = m;
    s->http = http_new(m, true);
    s->media = http_new(m, false);
    s->videos = videos;
    s->owns_clients = true;
    short_sleep(1);
    return s;
}
Sender *sender_clone(const Sender *source, const json_t *destination) {
    Sender *s = xcalloc(1, sizeof(*s));
    *s = *source;
    s->destination = json_incref((json_t *)destination);
    s->owns_clients = false;
    return s;
}
void sender_free(Sender *s) {
    if (s) {
        json_decref(s->destination);
        if (s->owns_clients) {
            http_free(s->http);
            http_free(s->media);
        }
        free(s);
    }
}
void auto_sender_free(Sender **s) {
    sender_free(*s);
}
char *sender_channel(const Sender *s) {
    return json_is_string(s->destination) ? xstrdup(text(s->destination))
                                          : dump_json(s->destination);
}
static bool ack(Sender *s, const json_t *result, Error *error) {
    if (!s->ack)
        return true;
    json_auto_t *messages =
        json_is_array(result) ? json_incref((json_t *)result) : JA(jr(result)).p;
    json_auto_t *ids = json_array();
    size_t i;
    json_t *message;
    json_array_foreach(messages, i, message) if (json_is_integer(get(message, "message_id")))
        jappend(ids, get(message, "message_id"));
    return s->ack(s->ack_data, ids, error);
}
json_t *sender_api(Sender *s, const char *method, const json_t *input, Error *error) {
    json_auto_t *params = input ? json_deep_copy(input) : json_object();
    bool sending = !strncmp(method, "send", 4) || !strcmp(method, "forwardMessage");
    if (json_is_null(get(params, "chat_id")) &&
        (!strncmp(method, "send", 4) || !strcmp(method, "getChatMemberCount") ||
         !strcmp(method, "getChatAdministrators")))
        jset(params, "chat_id", s->destination);
    json_auto_t *result = http_api(s->http, field(get(s->config->values, "telegram"), "token"),
                                   method, params, NULL, error);
    TRY(result, NULL);
    if (sending)
        TRY(ack(s, result, error), NULL);
    return jrelease(&result);
}
static void split_message(const char *body, char **part, char **tail) {
    json_auto_t *items = split_text(body, " ");
    if (codepoints(text(json_array_get(items, 0))) > 4096) {
        size_t offset = unicode_offset(body, 4096);
        *part = strndup(body, offset);
        *tail = xstrdup(body + offset);
        return;
    }
    size_t size = 0, take = 0, n = json_array_size(items);
    for (size_t i = 0; i < n; i++) {
        size_t count = codepoints(text(json_array_get(items, i)));
        if (size + take + count > 4096)
            break;
        size += count;
        take++;
    }
    json_auto_t *a = json_array();
    json_auto_t *b = json_array();
    for (size_t i = 0; i < n; i++)
        jappend(i < take ? a : b, json_array_get(items, i));
    *part = join(a, " ");
    *tail = join(b, " ");
}
static void split_caption(const char *body, char **caption, char **tail) {
    if (codepoints(body) <= 1024) {
        *caption = xstrdup(body);
        *tail = xstrdup("");
        return;
    }
    STR(flat) = replace(body, "\n", " ");
    json_auto_t *items = split_text(flat, " ");
    BUF(a);
    BUF(b);
    bool switched = false;
    size_t i;
    json_t *v;
    json_array_foreach(items, i, v) {
        const char *word = text(v);
        if (!switched && codepoints(a.data ? a.data : "") + codepoints(word) + 1 < 1020) {
            buffer_text(&a, word);
            buffer_text(&a, " ");
        } else {
            switched = true;
            buffer_text(&b, " ");
            buffer_text(&b, word);
        }
    }
    buffer_text(&a, " ...");
    *caption = buffer_take(&a);
    *tail = strf("... %s", b.data ? b.data : "");
}
bool sender_text(Sender *s, const char *body, bool preview, const char *mode, Supply *result,
                 Error *error) {
    bool split = codepoints(body) >= 4096;
    STR(remaining) = xstrdup(body);
    for (;;) {
        STR(part) = NULL;
        STR(next) = NULL;
        if (split)
            split_message(remaining, &part, &next);
        else {
            part = xstrdup(remaining);
            next = xstrdup("");
        }
        json_auto_t *params = JO(P("text", js(part)), P("disable_web_page_preview", jb(preview))).p;
        if (mode)
            json_object_set_new(params, "parse_mode", js(mode).p);
        json_auto_t *sent = sender_api(s, "sendMessage", params, error);
        TRY(sent, false);
        if (split)
            short_sleep(1);
        if (!*next)
            break;
        free(remaining);
        remaining = xstrdup(next);
    }
    return supply_result(result, SUPPLY_SENT);
}
bool sender_image(Sender *s, const char *url, const char *body, Supply *result, Error *error) {
    if (codepoints(body) > 1024) {
        STR(channel) = sender_channel(s);
        STR(log) = strf("Long pic in %s.", channel);
        log_info(log, false);
        STR(message) = strf("<a href=\"%s\">&#160;</a>%s", url, body);
        return sender_text(s, message, false, "HTML", result, error);
    }
    json_auto_t *params = JO(P("photo", js(url)), P("caption", js(body))).p;
    Error transient = {0};
    json_auto_t *sent = sender_api(s, "sendPhoto", params, &transient);
    if (sent)
        return supply_result(result, SUPPLY_SENT);
    switch (transient.kind) {
    case E_REJECTED:
    case E_TELEGRAM:
    case E_NETWORK:
    case E_TIMEOUT:
    case E_FORBIDDEN:
    case E_RATE_LIMIT:
        return supply_result(result, SUPPLY_SKIP);
    default:
        *error = transient;
        return false;
    }
}
static uint64_t url_size(Sender *s, const char *url) {
    Error ignored = {0};
    RESPONSE(r) =
        http_request(s->media, "HEAD", url, NULL, NULL, 0, NULL, NULL, 0, NULL, false, &ignored);
    if (!r)
        return 0;
    return strtoull(response_header(r, "content-length"), NULL, 10);
}
bool sender_gif(Sender *s, const char *url, const char *body, Supply *result, Error *error) {
    if (url_size(s, url) > MEDIA_LIMIT) {
        log_info("Too big.", false);
        return supply_result(result, SUPPLY_REJECT);
    }
    STR(caption) = NULL;
    STR(tail) = NULL;
    split_caption(body, &caption, &tail);
    json_auto_t *params = JO(P("document", js(url)), P("caption", js(caption))).p;
    Error transient = {0};
    json_auto_t *sent = sender_api(s, "sendDocument", params, &transient);
    if (!sent) {
        if (transient.kind == E_REJECTED)
            return supply_result(result, SUPPLY_SKIP);
        *error = transient;
        return false;
    }
    if (codepoints(tail) > 1) {
        short_sleep(1);
        TRY(sender_text(s, tail, true, NULL, NULL, error), false);
    }
    return supply_result(result, SUPPLY_SENT);
}
bool sender_gallery(Sender *s, const json_t *groups, const char *body, Supply *result,
                    Error *error) {
    TRY(sender_text(s, body, false, NULL, NULL, error), false);
    long_sleep(1);
    size_t i;
    json_t *group;
    json_array_foreach(groups, i, group) {
        json_auto_t *params = JO(P("media", jr(group))).p;
        Error ignored = {0};
        json_auto_t *sent = sender_api(s, "sendMediaGroup", params, &ignored);
        if (sent)
            log_info("Successful gallery sent.", false);
        else {
            STR(message) = strf("Gallery sent failed: %s", error_name(ignored));
            log_info(message, true);
        }
        long_sleep((double)i + 2);
    }
    return supply_result(result, SUPPLY_SENT);
}
static char *dash_audio(Sender *s, const char *url) {
    Error error = {0};
    STR(body) = http_metadata(s->media, url, &error);
    if (!body)
        return NULL;
    STR(audio) = NULL;
    const char *p = body;
    while ((p = strstr(p, "<BaseURL>"))) {
        p += 9;
        const char *end = strstr(p, "</BaseURL>");
        if (!end)
            break;
        STR(value) = strndup(p, (size_t)(end - p));
        STR(low) = lower(value);
        if (strstr(low, "audio")) {
            free(audio);
            audio = xstrdup(value);
        }
        p = end + 10;
    }
    const char *playlist = strstr(url, "DASHPlaylist.mpd");
    if (!audio || !playlist)
        return NULL;
    STR(base) = strndup(url, (size_t)(playlist - url));
    const char *query = strchr(url, '?');
    return strf("%s%s%s", base, audio, query ? query : "");
}
static void temp_free(char **dir) {
    if (!*dir)
        return;
    const char *names[] = {"media.mp4", "media.mp4.aac", "media.1.mp4"};
    for (size_t i = 0; i < 3; i++) {
        STR(path) = strf("%s/%s", *dir, names[i]);
        unlink(path);
    }
    rmdir(*dir);
    free(*dir);
}
static void video_release(sem_t **slot) {
    if (*slot)
        sem_post(*slot);
}
bool sender_video(Sender *s, const char *url, const char *body, const char *dash, Supply *result,
                  Error *error) {
    int lock;
    do {
        lock = sem_wait(s->videos);
    } while (lock < 0 && errno == EINTR);
    REQUIRE(!lock, E_MEDIA, false);
    sem_t *slot __attribute__((cleanup(video_release))) = s->videos;
    STR(parent) = strf("%s/tmp", s->config->app);
    REQUIRE(!mkdir(parent, 0755) || errno == EEXIST, E_IO, false);
    STR(pattern) = strf("%s/r2t-XXXXXX", parent);
    REQUIRE(mkdtemp(pattern), E_IO, false);
    char *folder __attribute__((cleanup(temp_free))) = pattern;
    pattern = NULL;
    STR(video) = strf("%s/media.mp4", folder);
    if (!http_download(s->media, url, video, MEDIA_LIMIT))
        return supply_result(result, SUPPLY_REJECT);
    STR(audio) = strf("%s/media.mp4.aac", folder);
    STR(muxed) = strf("%s/media.1.mp4", folder);
    STR(audio_url) = dash ? dash_audio(s, dash) : NULL;
    if (!audio_url) {
        const char *slash = strrchr(url, '/');
        STR(base) = slash ? strndup(url, (size_t)(slash - url)) : xstrdup(url);
        audio_url = strf("%s/DASH_AUDIO_128.mp4", base);
    }
    const char *send = video;
    if (http_download(s->media, audio_url, audio, MEDIA_LIMIT) && mux_video(video, audio, muxed))
        send = muxed;
    struct stat st;
    REQUIRE(!stat(send, &st), E_IO, false);
    if (st.st_size <= 0 || (uint64_t)st.st_size > MEDIA_LIMIT)
        return supply_result(result, SUPPLY_REJECT);
    STR(caption) = NULL;
    STR(tail) = NULL;
    split_caption(body, &caption, &tail);
    json_auto_t *params = JO(P("chat_id", jr(s->destination)), P("caption", js(caption))).p;
    json_auto_t *sent = http_api(s->http, field(get(s->config->values, "telegram"), "token"),
                                 "sendVideo", params, send, error);
    TRY(sent, false);
    TRY(ack(s, sent, error), false);
    if (codepoints(tail) > 1) {
        short_sleep(1);
        TRY(sender_text(s, tail, true, NULL, NULL, error), false);
    }
    return supply_result(result, SUPPLY_SENT);
}
static char *regex_escape(const char *s) {
    BUF(out);
    for (; *s; s++) {
        if (strchr("\\.^$|()[]{}*+?", *s))
            buffer_text(&out, "\\");
        buffer_add(&out, s, 1);
    }
    return buffer_take(&out);
}
bool sender_seen(Sender *s, const char *url, bool *seen, Error *error) {
    STR(channel) = sender_channel(s);
    STR(c) = lower(channel);
    STR(u) = lower(url);
    const char *slash = strrchr(url, '/');
    const char *id = slash ? slash + 1 : url;
    STR(escaped) = regex_escape(id);
    json_auto_t *filters =
        JA(JO(P("channel", js(c)), P("url_id", js(id))), JO(P("channel", js(c)), P("url", js(u))),
           JO(P("channel", js(c)), P("url", JO(P("$regex", js(escaped))))))
            .p;
    json_auto_t *projection = JO(P("_id", ji(1))).p;
    *seen = false;
    size_t i;
    json_t *filter;
    json_array_foreach(filters, i, filter) {
        json_auto_t *found = db_find(s->db, "urls", filter, NULL, 1, projection, error);
        TRY(found, false);
        if (json_array_size(found)) {
            metrics_count(s->metrics, "previously_seen_candidates", 1);
            *seen = true;
            break;
        }
    }
    return true;
}
bool sender_error_limit(Sender *s, const char *url, bool *blocked, Error *error) {
    STR(channel) = sender_channel(s);
    STR(c) = lower(channel);
    STR(u) = lower(url);
    json_auto_t *filter = JO(P("channel", js(c)), P("url", js(u))).p;
    json_auto_t *record = db_one(s->db, "errors", filter, NULL, error);
    TRY(!error->kind, false);
    *blocked = record && number(get(record, "cnt"), 0) >= 2;
    return true;
}
bool sender_mark(Sender *s, const char *url, bool sent, Error *error) {
    STR(channel) = sender_channel(s);
    STR(c) = lower(channel);
    STR(u) = lower(url);
    const char *slash = strrchr(url, '/');
    json_auto_t *docs = JA(JO(P("url_id", js(slash ? slash + 1 : url)), P("url", js(u)),
                              P("ts", jdate(now())), P("channel", js(c)), P("sent", jb(sent))))
                            .p;
    TRY(db_insert(s->db, "urls", docs, error), false);
    metrics_post(s->metrics, channel, url, sent);
    return true;
}
bool sender_duplicate(Sender *s, const char *url, bool *duplicate, Error *error) {
    *duplicate = false;
    RESPONSE(r) = http_request(s->media, "GET", url, NULL, NULL, 0, NULL, NULL, MEDIA_LIMIT, "MD5",
                               true, error);
    TRY(r, false);
    if (!response_ok(r) || r->raw->too_large || !r->raw->body_digest)
        return true;
    STR(channel) = sender_channel(s);
    STR(c) = lower(channel);
    json_auto_t *fields =
        JO(P("query", JO(P("channel", js(c)), P("md5_sum", js(r->raw->body_digest)))),
           P("update",
             JO(P("$setOnInsert", JO(P("channel", js(c)), P("md5_sum", js(r->raw->body_digest)),
                                     P("ts", jdate(now())))))),
           P("upsert", jb(true)), P("new", jb(false)))
            .p;
    json_auto_t *collection = js("contents").p;
    json_auto_t *response = db_command(s->db, "findAndModify", collection, fields, error);
    TRY(response, false);
    *duplicate = json_is_object(get(response, "value"));
    if (*duplicate) {
        log_info("Duplicated found!", false);
        metrics_count(s->metrics, "duplicate_media_candidates", 1);
    }
    return true;
}
bool clean_files(const Config *config, const char *channel, uint64_t *deleted, Error *error) {
    long_sleep(1 / (M_PI * M_E));
    STR(path) = strf("%s/tmp", config->app);
    DIR *dir = opendir(path);
    REQUIRE(dir, E_IO, false);
    uint64_t total = 0;
    struct dirent *entry;
    while ((entry = readdir(dir))) {
        if (!strcmp(entry->d_name, "empty.md") || !strcmp(entry->d_name, ".") ||
            !strcmp(entry->d_name, ".."))
            continue;
        if (channel && !strstr(entry->d_name, *channel ? channel + 1 : ""))
            continue;
        STR(file) = strf("%s/%s", path, entry->d_name);
        struct stat st;
        if (stat(file, &st) || !S_ISREG(st.st_mode))
            continue;
        if (!unlink(file))
            total += (uint64_t)st.st_size;
    }
    closedir(dir);
    if (deleted)
        *deleted = total;
    return true;
}
