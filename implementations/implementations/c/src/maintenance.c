#include "maintenance.h"
#include <ctype.h>
#include <math.h>
#include <regex.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/statvfs.h>
bool maintenance_cleaner(const App *app, Sender *sender, Supply *result, Error *error) {
    STR(memory) = read_file("/proc/meminfo", NULL, error);
    TRY(memory, false);
    const char *free_value = strstr(memory, "MemFree:");
    REQUIRE(free_value, E_IO, false);
    double free_mb = strtod(free_value + 8, NULL) / 1024.;
    uint64_t deleted = 0;
    TRY(clean_files(app->config, NULL, &deleted, error), false);
    struct statvfs disk;
    REQUIRE(!statvfs("/", &disk), E_IO, false);
    double available = (double)disk.f_bavail * (double)disk.f_frsize / pow(1024, 3);
    const char *args[] = {"vnstat", "-m", NULL};
    STR(output) = command_output(args, error);
    TRY(output, false);
    json_auto_t *lines = split_text(output, "\n");
    size_t count = json_array_size(lines);
    REQUIRE(count >= 4, E_IO, false);
    json_auto_t *traffic_parts = split_text(text(json_array_get(lines, count - 4)), " | ");
    json_auto_t *estimate_parts = split_text(text(json_array_get(lines, count - 2)), "|");
    REQUIRE(json_array_size(traffic_parts) >= 2 && json_array_size(estimate_parts) >= 2, E_IO,
            false);
    STR(traffic) =
        trim(text(json_array_get(traffic_parts, json_array_size(traffic_parts) - 2)), NULL);
    STR(estimate) =
        trim(text(json_array_get(estimate_parts, json_array_size(estimate_parts) - 2)), NULL);
    json_auto_t *command =
        JO(P("pipeline",
             JA(JO(P("$group", JO(P("_id", js("$status")), P("count", JO(P("$sum", ji(1))))))))),
           P("cursor", JO0()))
            .p;
    json_auto_t *tasks = js("tasks").p;
    json_auto_t *aggregate = db_command(app->db, "aggregate", tasks, command, error);
    TRY(aggregate, false);
    int64_t counts[6] = {0};
    size_t i;
    json_t *record;
    json_array_foreach(get(get(aggregate, "cursor"), "firstBatch"), i, record) {
        int64_t id;
        if (integer(get(record, "_id"), &id) && id >= 1 && id <= 5)
            counts[id] = (int64_t)number(get(record, "count"), 0);
    }
    json_auto_t *filter = JO(P("setting", js("tasks-stati"))).p;
    json_auto_t *previous = db_one(app->db, "settings", filter, NULL, error);
    TRY(!error->kind, false);
    json_auto_t *data = previous && json_is_object(get(previous, "data"))
                            ? json_deep_copy(get(previous, "data"))
                            : json_object();
    const char *key;
    json_t *v;
    int64_t cycles = 0;
    JOBJECT_FOREACH(data, key, v) {
        int64_t n = (int64_t)number(get(v, "cycles_cnt"), 0);
        if (n > cycles)
            cycles = n;
    }
    cycles++;
    BUF(body);
    STR(intro) =
        strf("Free memory: %.3fMB.\nDeleted files: %.3fGB.\nAvailable disk space: %.3fGB.\nCurrent "
             "month traffic: %s.\nCurrent month estimate: %s.\nTasks' stati:\n",
             free_mb, (double)deleted / pow(1024, 3), available, traffic, estimate);
    buffer_text(&body, intro);
    const char *names[] = {"", "NEW", "IN_PROGRESS", "SUCCESS", "FAILED", "SCHEDULED"};
    int64_t removed = 0;
    for (int status = 1; status <= 5; status++) {
        json_t *old = get(data, names[status]);
        int64_t total = (int64_t)number(get(old, "amt"), 0) + counts[status];
        json_auto_t *item = JO(P("amt", ji(total)),
                               P("cycles_cnt", ji((int64_t)number(get(old, "cycles_cnt"), 0) + 1)))
                                .p;
        STR(line) = strf("  →  %s: %lld (avg: %.3f)\n", names[status], (long long)counts[status],
                         (double)total / cycles);
        buffer_text(&body, line);
        jset(data, names[status], item);
        json_auto_t *selection = JO(P("status", ji(status))).p;
        int64_t deleted_tasks = 0;
        TRY(db_delete(app->db, "tasks", selection, false, &deleted_tasks, error), false);
        removed += deleted_tasks;
    }
    STR(ending) =
        strf("Deleted tasks: %lld.\nTotal cycles: %lld.\n", (long long)removed, (long long)cycles);
    buffer_text(&body, ending);
    json_auto_t *update = JO(P("$set", JO(P("data", jr(data))))).p;
    TRY(db_update(app->db, "settings", filter, update, false, true, NULL, error), false);
    TRY(sender_text(sender, body.data, false, NULL, NULL, error), false);
    return supply_result(result, SUPPLY_STOP);
}
typedef struct {
    json_t *channel;
    double date;
} ChannelDate;
static int date_compare(const void *a, const void *b) {
    const ChannelDate *x = a, *y = b;
    return (x->date > y->date) - (x->date < y->date);
}
json_t *public_channels(const App *app, Sender *sender, Error *error) {
    json_auto_t *modules = public_modules(app, error);
    TRY(modules, NULL);
    json_auto_t *unique = json_object();
    size_t i;
    json_t *module;
    json_array_foreach(modules, i, module) {
        json_auto_t *channel = NULL;
        STR(subreddit) = NULL;
        TRY(channel_identity(app, text(module), &channel, &subreddit, error), NULL);
        REQUIRE(json_is_string(channel), E_CONFIG, NULL);
        const char *handle = text(channel);
        if (!strchr(handle, '@') || !strcmp(handle, "@r_channels_test") ||
            !strcmp(handle, "@r_channels"))
            continue;
        STR(low) = lower(handle);
        json_auto_t *filter = JO(P("channel", js(low))).p;
        json_auto_t *sort = JO(P("ts", ji(1))).p;
        json_auto_t *first = db_one(sender->db, "urls", filter, sort, error);
        TRY(first, NULL);
        double date;
        REQUIRE(bson_timestamp(get(first, "ts"), &date), E_CONFIG, NULL);
        json_object_set_new(unique, handle, jf(date).p);
    }
    size_t count = json_object_size(unique);
    ChannelDate *values = xcalloc(count ? count : 1, sizeof(ChannelDate));
    const char *key;
    json_t *date;
    size_t at = 0;
    JOBJECT_FOREACH(unique, key, date) values[at++] = (ChannelDate){js(key).p, number(date, 0)};
    qsort(values, count, sizeof(ChannelDate), date_compare);
    json_t *out = json_array();
    for (i = 0; i < count; i++)
        json_array_append_new(out, values[i].channel);
    free(values);
    return out;
}
static bool first_members(const App *app, const json_t *filter, const json_t *sort, double *members,
                          Error *error) {
    json_auto_t *records = db_find(app->db, "stats", filter, sort, 100, NULL, error);
    TRY(records, false);
    size_t i;
    json_t *record;
    json_array_foreach(records, i, record) if (json_is_number(get(record, "members_cnt"))) {
        *members = number(get(record, "members_cnt"), 0);
        return true;
    }
    return error_set(error, E_CONFIG, 0);
}
typedef struct {
    double growth;
    json_t *channel;
} Growth;
static int growth_compare(const void *a, const void *b) {
    const Growth *x = a, *y = b;
    return (y->growth > x->growth) - (y->growth < x->growth);
}
static void growth_free(Growth **p) {
    free(*p);
}
bool maintenance_weekly(const App *app, Sender *sender, Supply *result, Error *error) {
    json_auto_t *channels = public_channels(app, sender, error);
    TRY(channels, false);
    json_auto_t *newly = json_array();
    size_t n = json_array_size(channels);
    Growth *growing __attribute__((cleanup(growth_free))) = xcalloc(n ? n : 1, sizeof(Growth));
    size_t growth_count = 0;
    json_auto_t *cutoff = jdate(now() - 7 * 86400).p;
    size_t i;
    json_t *channel;
    json_array_foreach(channels, i, channel) {
        STR(low) = lower(text(channel));
        json_auto_t *filter = JO(P("channel", js(low))).p;
        json_auto_t *ascending = JO(P("ts", ji(1))).p;
        json_auto_t *descending = JO(P("ts", ji(-1))).p;
        json_auto_t *first = db_one(app->db, "stats", filter, ascending, error);
        TRY(first, false);
        json_auto_t *latest = db_one(app->db, "stats", filter, descending, error);
        TRY(latest, false);
        double a, b;
        REQUIRE(bson_timestamp(get(first, "ts"), &a) && bson_timestamp(get(latest, "ts"), &b),
                E_CONFIG, false);
        if (floor((b - a) / 86400) <= 31)
            jappend(newly, channel);
        json_auto_t *recent = JO(P("channel", js(low)), P("ts", JO(P("$gte", jr(cutoff))))).p;
        double previous, current;
        TRY(first_members(app, recent, ascending, &previous, error), false);
        TRY(first_members(app, filter, descending, &current, error), false);
        if (current - previous >= 10)
            growing[growth_count++] = (Growth){current - previous, channel};
    }
    REQUIRE(n, E_CONFIG, false);
    qsort(growing, growth_count, sizeof(Growth), growth_compare);
    STR(draw) = uuid_text();
    uint64_t selected = strtoull(draw, NULL, 16) % n;
    BUF(body);
    buffer_text(&body, "<b>Weekend news</b>\n\n");
    if (json_array_size(newly)) {
        STR(list) = join(newly, ", ");
        STR(line) = strf("🎉 Welcome to newly active channels: %s. 🎈🎈\n\n", list);
        buffer_text(&body, line);
    }
    STR(feature) = strf("🏆 Channel of the week: %s. Join and enjoy!\n\n",
                        text(json_array_get(channels, selected)));
    buffer_text(&body, feature);
    if (growth_count) {
        json_auto_t *top = json_array();
        for (i = 0; i < growth_count && i < 3; i++)
            jappend(top, growing[i].channel);
        STR(list) = join(top, ", ");
        STR(line) = strf("🔥 Hottest channels of the week: %s.\n\n", list);
        buffer_text(&body, line);
    }
    buffer_text(&body, "🙋\nQ: How can I help?\nA: Support us on Patreon and promote your favorite "
                       "channels!\n\nQ: How to make similar channels?\nA: Ask at @r_channels or "
                       "use manual at https://github.com/Fillll/reddit2telegram.\n\nQ: Where to "
                       "donate?\nA: Patreon: https://www.patreon.com/reddit2telegram.");
    TRY(sender_text(sender, body.data, false, "HTML", NULL, error), false);
    pause_between(2, 2);
    for (size_t index = 0; index < n; index += 100) {
        BUF(page);
        if (!index)
            buffer_text(&page, "⬇️ All active channels:\n");
        for (i = index; i < index + 100 && i < n; i++) {
            if (i > index)
                buffer_text(&page, "\n");
            STR(line) = strf("%02zu. %s", i + 1, text(json_array_get(channels, i)));
            buffer_text(&page, line);
        }
        TRY(sender_text(sender, page.data, false, NULL, NULL, error), false);
        pause_between(2, 2);
    }
    return supply_result(result, SUPPLY_STOP);
}
static const char *help =
    "Send channel data in one message:\nsubreddit: https://reddit.com/r/example\nchannel: "
    "@example_channel\ntags: #tag1 #tag2 #tag3\n\nOr send it step by step:\n1. subreddit\n2. "
    "channel\n3. tags\n\nCommands:\n/newchannel to restart\n/cancel to clear the current draft";
static char *normalize(const char *input, const char *kind) {
    STR(value) = trim(input, NULL);
    char *colon = strchr(value, ':');
    if (colon) {
        STR(prefix) = strndup(value, (size_t)(colon - value));
        STR(clean) = trim(prefix, NULL);
        STR(low) = lower(clean);
        if (!strcmp(low, kind)) {
            char *next = trim(colon + 1, NULL);
            free(value);
            value = next;
        }
    }
    const char *pattern = !strcmp(kind, "subreddit")
                              ? "(https?://)?(www\\.)?reddit\\.com/r/([^/?#[:space:]]+)"
                              : "(https?://)?t(elegram)?\\.me/([^/?#[:space:]]+)";
    regex_t regex;
    regmatch_t match[4];
    if (!regcomp(&regex, pattern, REG_EXTENDED | REG_ICASE)) {
        bool found = regexec(&regex, value, 4, match, 0) == 0;
        if (found && match[3].rm_so >= 0) {
            char *next = strndup(value + match[3].rm_so, (size_t)(match[3].rm_eo - match[3].rm_so));
            free(value);
            value = next;
        } else {
            STR(stripped) = trim(value, "/");
            free(value);
            value = xstrdup(stripped);
        }
        regfree(&regex);
    }
    if (!strcmp(kind, "subreddit") && tolower((unsigned char)value[0]) == 'r' && value[1] == '/') {
        char *next = xstrdup(value + 2);
        free(value);
        value = next;
    }
    if (!strcmp(kind, "channel") && *value == '@') {
        char *next = xstrdup(value + 1);
        free(value);
        value = next;
    }
    json_auto_t *tokens = words(value);
    if (!*value || json_array_size(tokens) != 1)
        return xstrdup("");
    STR(trimmed) = trim(value, NULL);
    return trim(trimmed, "/");
}
static char *normalize_tags(const char *input) {
    STR(flat) = replace(input, ",", " ");
    json_auto_t *parts = words(flat);
    json_auto_t *seen = json_object();
    json_auto_t *tags = json_array();
    size_t i;
    json_t *v;
    json_array_foreach(parts, i, v) {
        const char *part = text(v);
        STR(tag) = *part == '#' ? xstrdup(part) : strf("#%s", part);
        if (!json_object_get(seen, tag)) {
            json_object_set_new(seen, tag, json_true());
            json_array_append_new(tags, js(tag).p);
        }
    }
    return join(tags, " ");
}
static bool complete_data(const json_t *data) {
    return *field(data, "subreddit") && *field(data, "channel") && *field(data, "tags");
}
static json_t *complete_request(const char *input) {
    json_auto_t *raw = split_text(input, "\n");
    json_auto_t *lines = json_array();
    size_t i;
    json_t *v;
    json_array_foreach(raw, i, v) {
        STR(line) = trim(text(v), NULL);
        if (*line)
            json_array_append_new(lines, js(line).p);
    }
    if (json_array_size(lines)) {
        STR(first) = lower(text(json_array_get(lines, 0)));
        if (!strcmp(first, "/newchannel") || !strcmp(first, "/start"))
            json_array_remove(lines, 0);
    }
    json_auto_t *data = json_object();
    json_array_foreach(lines, i, v) {
        const char *line = text(v);
        STR(low) = lower(line);
        if (!strncmp(low, "subreddit", 9)) {
            STR(value) = normalize(line, "subreddit");
            json_object_set_new(data, "subreddit", js(value).p);
        } else if (!strncmp(low, "channel", 7)) {
            STR(value) = normalize(line, "channel");
            json_object_set_new(data, "channel", js(value).p);
        } else if (!strncmp(low, "tags", 4)) {
            STR(value) = normalize_tags(line);
            json_object_set_new(data, "tags", js(value).p);
        }
    }
    if (complete_data(data))
        return jrelease(&data);
    if (json_array_size(lines) == 3) {
        STR(subreddit) = normalize(text(json_array_get(lines, 0)), "subreddit");
        STR(channel) = normalize(text(json_array_get(lines, 1)), "channel");
        STR(tags) = normalize_tags(text(json_array_get(lines, 2)));
        json_t *next =
            JO(P("subreddit", js(subreddit)), P("channel", js(channel)), P("tags", js(tags))).p;
        json_decref(data);
        data = next;
        if (complete_data(data))
            return jrelease(&data);
    }
    return NULL;
}
static bool reply(const App *app, Sender *source, int64_t user, const char *body, Error *error) {
    json_auto_t *destination = ji(user).p;
    SENDER(sender) = sender_new(app->config, app->db, destination, source->metrics, app->videos);
    return sender_text(sender, body, false, NULL, NULL, error);
}
static bool save_channel(const App *app, Sender *source, int64_t user, const json_t *data,
                         Error *error) {
    const char *channel = field(data, "channel"), *subreddit = field(data, "subreddit"),
               *tags = field(data, "tags");
    STR(low) = lower(channel);
    STR(handle) = strf("@%s", channel);
    json_auto_t *filter = JO(P("submodule", js(low))).p;
    json_auto_t *existing = db_one(app->db, "channels", filter, NULL, error);
    TRY(!error->kind, false);
    json_auto_t *update =
        JO(P("$set",
             JO(P("submodule", js(low)), P("channel", js(handle)), P("subreddit", js(subreddit)),
                P("tags", js(tags)), P("min_upvotes_limit", JN()),
                P("submissions_ranking", js("hot")), P("submissions_limit", ji(100)))))
            .p;
    TRY(db_update(app->db, "channels", filter, update, false, true, NULL, error), false);
    STR(setting) = strf("tech_receiver_state:%lld", (long long)user);
    json_auto_t *state = JO(P("setting", js(setting))).p;
    TRY(db_delete(app->db, "settings", state, true, NULL, error), false);
    STR(body) = strf("%s channel:\nsubreddit: r/%s\nchannel: @%s\ntags: %s",
                     existing ? "Updated" : "Saved", subreddit, channel, tags);
    return reply(app, source, user, body, error);
}
static bool process_message(const App *app, Sender *sender, int64_t user, const char *input,
                            Error *error) {
    STR(setting) = strf("tech_receiver_state:%lld", (long long)user);
    json_auto_t *filter = JO(P("setting", js(setting))).p;
    STR(trimmed) = trim(input, NULL);
    STR(low) = lower(trimmed);
    if (!strcmp(low, "/help") || !strcmp(low, "help"))
        return reply(app, sender, user, help, error);
    if (!strcmp(low, "/cancel") || !strcmp(low, "cancel")) {
        TRY(db_delete(app->db, "settings", filter, true, NULL, error), false);
        return reply(app, sender, user, "Draft cleared.", error);
    }
    if (!strcmp(low, "/newchannel") || !strcmp(low, "/start")) {
        TRY(db_delete(app->db, "settings", filter, true, NULL, error), false);
        json_auto_t *update = JO(P("$set", JO(P("data", JO(P("step", js("await_subreddit"))))))).p;
        TRY(db_update(app->db, "settings", filter, update, false, true, NULL, error), false);
        return reply(app, sender, user, "Send subreddit name or Reddit URL.", error);
    }
    json_auto_t *complete = complete_request(input);
    if (complete)
        return save_channel(app, sender, user, complete, error);
    json_auto_t *previous = db_one(app->db, "settings", filter, NULL, error);
    TRY(!error->kind, false);
    json_auto_t *state =
        previous ? json_deep_copy(get(previous, "data")) : JO(P("step", js("await_subreddit"))).p;
    const char *step = field(state, "step");
    STR(response) = NULL;
    if (!strcmp(step, "await_subreddit")) {
        STR(subreddit) = normalize(input, "subreddit");
        if (!*subreddit)
            return reply(app, sender, user, help, error);
        json_t *next = JO(P("step", js("await_channel")), P("subreddit", js(subreddit))).p;
        json_decref(state);
        state = next;
        response = strf("Saved subreddit: r/%s\nNow send channel (@name or t.me link).", subreddit);
    } else if (!strcmp(step, "await_channel")) {
        STR(channel) = normalize(input, "channel");
        if (!*channel)
            return reply(app, sender, user,
                         "Channel is invalid. Send @channel_name or https://t.me/channel_name",
                         error);
        json_object_set_new(state, "step", js("await_tags").p);
        json_object_set_new(state, "channel", js(channel).p);
        response = strf("Saved channel: @%s\nNow send tags like #tag1 #tag2 #tag3", channel);
    } else if (!strcmp(step, "await_tags")) {
        STR(tags) = normalize_tags(input);
        if (!*tags)
            return reply(app, sender, user, "Tags are invalid. Send tags like #tag1 #tag2 #tag3",
                         error);
        REQUIRE(json_is_string(get(state, "channel")) && json_is_string(get(state, "subreddit")),
                E_CONFIG, false);
        json_auto_t *data = JO(P("channel", jr(get(state, "channel"))),
                               P("subreddit", jr(get(state, "subreddit"))), P("tags", js(tags)))
                                .p;
        return save_channel(app, sender, user, data, error);
    } else {
        TRY(db_delete(app->db, "settings", filter, true, NULL, error), false);
        return reply(app, sender, user, help, error);
    }
    json_auto_t *update = JO(P("$set", JO(P("data", jr(state))))).p;
    TRY(db_update(app->db, "settings", filter, update, false, true, NULL, error), false);
    return reply(app, sender, user, response, error);
}
bool maintenance_receiver(const App *app, Sender *sender, Supply *result, Error *error) {
    json_auto_t *collection = js("settings").p;
    json_auto_t *index = JO(P("indexes", JA(JO(P("key", JO(P("setting", ji(1)))),
                                               P("name", js("setting_1")), P("unique", jb(true))))))
                             .p;
    json_auto_t *indexed = db_command(app->db, "createIndexes", collection, index, error);
    TRY(indexed, false);
    json_auto_t *filter = JO(P("setting", ji(1))).p;
    json_auto_t *record = db_one(app->db, "settings", filter, NULL, error);
    TRY(!error->kind, false);
    int64_t last = record ? (int64_t)number(get(record, "last_update"), 0) : 0;
    if (!record) {
        json_auto_t *docs = JA(JO(P("setting", ji(1)), P("last_update", ji(0)))).p;
        TRY(db_insert(app->db, "settings", docs, error), false);
    }
    json_auto_t *params = JO(P("offset", ji(last + 1))).p;
    json_auto_t *updates = sender_api(sender, "getUpdates", params, error);
    TRY(updates, false);
    json_t *configured = get(get(app->config->values, "telegram"), "papa");
    int64_t papa;
    REQUIRE(integer(configured, &papa) ||
                (json_is_string(configured) && (papa = strtoll(text(configured), NULL, 10), true)),
            E_CONFIG, false);
    REQUIRE(json_is_array(updates), E_TELEGRAM, false);
    size_t i;
    json_t *update;
    json_array_foreach(updates, i, update) {
        int64_t id;
        REQUIRE(integer(get(update, "update_id"), &id), E_TELEGRAM, false);
        if (id > last)
            last = id;
        json_t *message = get(update, "message");
        int64_t user;
        if (!integer(get(get(message, "chat"), "id"), &user) ||
            !json_is_string(get(message, "text")) || user < 0)
            continue;
        json_auto_t *forward =
            JO(P("chat_id", jr(get(get(app->config->values, "telegram"), "dev_chat"))),
               P("from_chat_id", ji(user)), P("message_id", jr(get(message, "message_id"))))
                .p;
        json_auto_t *sent = sender_api(sender, "forwardMessage", forward, error);
        TRY(sent, false);
        if (user == papa)
            TRY(process_message(app, sender, user, field(message, "text"), error), false);
    }
    json_auto_t *saved = JO(P("$set", JO(P("last_update", ji(last))))).p;
    TRY(db_update(app->db, "settings", filter, saved, false, false, NULL, error), false);
    return supply_result(result, SUPPLY_STOP);
}
