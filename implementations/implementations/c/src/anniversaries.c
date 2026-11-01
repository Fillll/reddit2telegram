#include "anniversaries.h"
#include "build_info.h"
#include "durable.h"
#include <regex.h>
#include <stdlib.h>
#include <string.h>
static const char *date_kind = "r2t_anniversary_date", *event_kind = "r2t_anniversary_delivery",
                  *run_kind = "r2t_anniversary_run";
typedef struct {
    const App *app;
    Sender *sender;
    Lease lease;
} Anniversary;
static bool midnight(const json_t *value, double *timestamp, Error *error) {
    double stamp;
    if (bson_timestamp(value, &stamp)) {
        struct tm parts = time_parts(stamp, true);
        parts.tm_hour = parts.tm_min = parts.tm_sec = 0;
        *timestamp = timegm(&parts);
        return true;
    }
    if (json_is_string(value)) {
        struct tm parts = {0};
        const char *raw = text(value);
        char *end = strptime(raw, "%Y-%m-%d", &parts);
        if (end && !*end) {
            stamp = timegm(&parts);
            STR(check) = time_format(stamp, "%Y-%m-%d", true);
            if (!strcmp(check, raw)) {
                *timestamp = stamp;
                return true;
            }
        }
    }
    return error_set(error, E_CONFIG, 0);
}
static char *chat_key(const json_t *value) {
    return json_is_string(value) ? lower(text(value)) : dump_json(value);
}
static void bump(json_t *record, const char *key) {
    json_object_set_new(record, key, ji((int64_t)number(get(record, key), 0) + 1).p);
}
static void push_error(json_t *record, JOwned value) {
    json_array_append_new(get(record, "errors"), value.p);
}
static int string_compare(const void *a, const void *b) {
    return strcmp(text(*(json_t *const *)a), text(*(json_t *const *)b));
}
static json_t *messages(const char *channel, int years, const json_t *channels, double today) {
    STR(escaped) = html_escape(channel);
    STR(date) = time_format(today, "%d %B %Y", true);
    STR(intro) =
        strf("🌍 <b>Discover the Reddit2Telegram family</b>\n\n📣 @reddit2telegram — "
             "our main channel for discovering posts and channels from across the network.\n\n"
             "💬 @r_channels — join the community, find new channels, ask questions, and suggest "
             "your next favorite.\n\n🎂 <b>Celebrating %s: %d year%s together!</b>\n📅 %s\n"
             "Thank you for reading, sharing, and being part of the community. Here’s to another "
             "year of great discoveries!",
             escaped, years, years == 1 ? "" : "s", date);
    json_auto_t *unique = json_object();
    size_t i;
    json_t *value;
    STR(self) = lower(channel);
    json_array_foreach(channels, i, value) {
        STR(c) = lower(text(value));
        if (strcmp(c, self) && strcmp(c, "@reddit2telegram") && strcmp(c, "@r_channels") &&
            strcmp(c, "@r_channels_test"))
            json_object_set_new(unique, c, json_true());
    }
    size_t count = json_object_size(unique);
    json_t **sorted = xcalloc(count ? count : 1, sizeof(*sorted));
    size_t at = 0;
    const char *key;
    JOBJECT_FOREACH(unique, key, value) sorted[at++] = js(key).p;
    qsort(sorted, count, sizeof(*sorted), string_compare);
    json_auto_t *others = json_array();
    for (i = 0; i < count; i++)
        json_array_append_new(others, sorted[i]);
    free(sorted);
    json_auto_t *out = json_array();
    if (!count) {
        json_array_append_new(out, js(intro).p);
        return jrelease(&out);
    }
    STR(intro_directory) =
        strf("%s\n\n🧭 Explore more of our channels in the directory below.", intro);
    json_array_append_new(out, js(intro_directory).p);
    json_auto_t *pages = json_array();
    json_auto_t *lines = json_array();
    json_array_foreach(others, i, value) {
        STR(escaped_line) = html_escape(text(value));
        STR(line) = strf("%zu. %s", i + 1, escaped_line);
        STR(previous) = join(lines, "\n");
        STR(candidate) = *previous ? strf("%s\n%s", previous, line) : xstrdup(line);
        if (json_array_size(lines) &&
            (json_array_size(lines) == 100 || utf16_count(candidate) > 3400)) {
            json_array_append_new(pages, js(previous).p);
            json_array_clear(lines);
        }
        json_array_append_new(lines, js(line).p);
    }
    if (json_array_size(lines)) {
        STR(page) = join(lines, "\n");
        json_array_append_new(pages, js(page).p);
    }
    json_array_foreach(pages, i, value) {
        STR(page) = strf("🧭 <b>More channels · %zu/%zu</b>\n\n%s", i + 1, json_array_size(pages),
                         text(value));
        json_array_append_new(out, js(page).p);
    }
    return jrelease(&out);
}
static bool birthday(Anniversary *service, const char *channel, const json_t *record, double *date,
                     bool *found, Error *error) {
    STR(id) = strf("%s:%s", date_kind, channel);
    json_auto_t *filter = JO(P("_id", js(id))).p;
    json_auto_t *cached = db_one(service->app->db, "settings", filter, NULL, error);
    TRY(!error->kind, false);
    json_t *explicit_date = get(record, "anniversary_date");
    const char *source;
    *found = true;
    if (!json_is_null(explicit_date)) {
        TRY(midnight(explicit_date, date, error), false);
        source = "explicit";
    } else if (cached)
        return midnight(get(cached, "date"), date, error);
    else {
        json_auto_t *query =
            JO(P("channel", js(channel)), P("sent", jb(true)), P("ts", JO(P("$type", js("date")))))
                .p;
        json_auto_t *sort = JO(P("ts", ji(1))).p;
        json_auto_t *projection = JO(P("ts", ji(1))).p;
        json_auto_t *docs = db_find(service->app->db, "urls", query, sort, 1, projection, error);
        TRY(docs, false);
        if (!json_array_size(docs)) {
            *found = false;
            return true;
        }
        TRY(midnight(get(json_array_get(docs, 0), "ts"), date, error), false);
        source = "first_sent_post";
    }
    json_auto_t *update =
        JO(P(json_is_null(explicit_date) ? "$setOnInsert" : "$set",
             JO(P("setting", js(id)), P("kind", js(date_kind)), P("channel", js(channel)),
                P("date", jdate(*date)), P("source", js(source)))))
            .p;
    return db_update(service->app->db, "settings", filter, update, false, true, NULL, error);
}
static bool inventory(Anniversary *service, json_t *run, json_t *names, json_t *birthdays,
                      Error *error) {
    json_auto_t *local = parse_json(R2T_LOCAL_CHANNELS, strlen(R2T_LOCAL_CHANNELS), error);
    TRY(local, false);
    json_auto_t *modules = public_modules(service->app, error);
    TRY(modules, false);
    json_auto_t *seen = json_object();
    regex_t handles;
    REQUIRE(!regcomp(&handles, "^@[a-zA-Z][a-zA-Z0-9_]{4,31}$", REG_EXTENDED), E_CONFIG, false);
    size_t i;
    json_t *module;
    bool okay = true;
    json_array_foreach(modules, i, module) {
        if (!lease_renew(&service->lease, error)) {
            okay = false;
            break;
        }
        Error fault = {0};
        json_auto_t *filter = JO(P("submodule", jr(module))).p;
        json_auto_t *record = db_one(service->app->db, "channels", filter, NULL, &fault);
        json_t *value =
            record ? get(record, "channel") : get(get(local, text(module)), "t_channel");
        if (!fault.kind && !json_is_string(value)) {
            if (record)
                continue;
            error_set(&fault, E_CONFIG, 0);
        }
        STR(channel) = lower(text(value));
        if (!fault.kind &&
            (regexec(&handles, channel, 0, NULL, 0) || !strcmp(channel, "@r_channels") ||
             !strcmp(channel, "@r_channels_test") || json_object_get(seen, channel)))
            continue;
        double date;
        bool found = false;
        if (!fault.kind)
            birthday(service, channel, record, &date, &found, &fault);
        if (fault.kind) {
            push_error(run, JO(P("submodule", jr(module)), P("error_type", js(error_name(fault)))));
        } else if (found) {
            json_object_set_new(seen, channel, json_true());
            json_array_append_new(names, js(channel).p);
            json_array_append_new(birthdays, jf(date).p);
        } else {
            STR(message) =
                strf("Anniversary skipped: %s has no successful posting history", channel);
            log_info(message, true);
            json_array_append_new(get(run, "skipped_no_history"), js(channel).p);
        }
    }
    regfree(&handles);
    return okay;
}
static bool queue_anniversary(Anniversary *service, const char *channel, int years, double today,
                              const json_t *channels, Error *error) {
    int year = time_parts(today, true).tm_year + 1900;
    STR(id) = strf("%s:%s:%d", event_kind, channel, year);
    STR(escaped) = html_escape(channel);
    STR(date) = time_format(today, "%d %B %Y", true);
    STR(notice) =
        strf("🎂 <b>Celebrating %s: %d year%s together!</b>\n📅 %s\n\n"
             "Discover this channel and more in our main feed @reddit2telegram.\nJoin @r_channels "
             "to explore the network and meet the community.",
             escaped, years, years == 1 ? "" : "s", date);
    json_auto_t *deliveries = json_array();
    json_auto_t *bodies = messages(channel, years, channels, today);
    size_t i;
    json_t *body;
    json_array_foreach(bodies, i, body) json_array_append_new(
        deliveries,
        JO(P("destination", js(channel)), P("text", jr(body)), P("state", js("pending"))).p);
    json_auto_t *destinations = json_object();
    STR(low) = lower(channel);
    json_object_set_new(destinations, low, json_true());
    json_auto_t *targets = JA(js("@reddit2telegram"), js("@r_channels"),
                              jr(get(get(service->app->config->values, "telegram"), "dev_chat")))
                               .p;
    json_t *target;
    json_array_foreach(targets, i, target) {
        STR(key) = chat_key(target);
        if (json_object_get(destinations, key))
            continue;
        json_object_set_new(destinations, key, json_true());
        json_array_append_new(
            deliveries,
            JO(P("destination", jr(target)), P("text", js(notice)), P("state", js("pending"))).p);
    }
    STR(anniversary) = time_format(today, "%Y-%m-%d", true);
    json_auto_t *filter = JO(P("_id", js(id))).p;
    json_auto_t *update =
        JO(P("$setOnInsert",
             JO(P("setting", js(id)), P("kind", js(event_kind)), P("channel", js(channel)),
                P("year", ji(year)), P("years", ji(years)), P("anniversary", js(anniversary)),
                P("created_at", jdate(now())), P("complete", jb(false)),
                P("deliveries", jr(deliveries)))))
            .p;
    return db_update(service->app->db, "settings", filter, update, false, true, NULL, error);
}
static bool deliver(Anniversary *service, const json_t *event, bool *complete, Error *error) {
    REQUIRE(json_object_get(event, "_id") && json_is_array(get(event, "deliveries")), E_CONFIG,
            false);
    json_t *id = get(event, "_id");
    json_auto_t *blocked = json_object();
    size_t index;
    json_t *delivery;
    json_array_foreach(get(event, "deliveries"), index, delivery) {
        TRY(lease_renew(&service->lease, error), false);
        REQUIRE(json_object_get(delivery, "destination") && json_is_string(get(delivery, "state")),
                E_CONFIG, false);
        json_t *destination = get(delivery, "destination");
        STR(blocked_key) = dump_json(destination);
        const char *state = field(delivery, "state");
        STR(path) = strf("deliveries.%zu", index);
        STR(state_path) = strf("%s.state", path);
        STR(attempt_path) = strf("%s.attempt", path);
        if (!strcmp(state, "sent") || json_object_get(blocked, blocked_key))
            continue;
        if (!strcmp(state, "sending") || !strcmp(state, "uncertain")) {
            json_auto_t *filter = JO(P("_id", jr(id)), P(state_path, js("sending"))).p;
            json_auto_t *update = JO(P("$set", JO(P(state_path, js("uncertain"))))).p;
            TRY(db_update(service->app->db, "settings", filter, update, false, false, NULL, error),
                false);
            json_object_set_new(blocked, blocked_key, json_true());
            continue;
        }
        STR(attempt) = uuid_text();
        STR(attempted_path) = strf("%s.attempted_at", path);
        STR(attempts_path) = strf("%s.attempts", path);
        json_auto_t *pending = JO(P("_id", jr(id)), P(state_path, js("pending"))).p;
        json_auto_t *sending =
            JO(P("$set", JO(P(state_path, js("sending")), P(attempt_path, js(attempt)),
                            P(attempted_path, jdate(now())))),
               P("$inc", JO(P(attempts_path, ji(1)))))
                .p;
        bool matched;
        TRY(update_matched(service->app->db, pending, sending, &matched, error), false);
        if (!matched) {
            json_object_set_new(blocked, blocked_key, json_true());
            continue;
        }
        json_auto_t *selector = JO(P("_id", jr(id)), P(attempt_path, js(attempt))).p;
        CHECKPOINT(checkpoint) = checkpoint_new(service->app->db, selector, path, NULL);
        SENDER(target) = sender_clone(service->sender, destination);
        target->ack = checkpoint_record;
        target->ack_data = checkpoint;
        Error fault = {0};
        Supply result = SUPPLY_REJECT;
        if (!json_is_string(get(delivery, "text")))
            error_set(&fault, E_CONFIG, 0);
        else
            sender_text(target, field(delivery, "text"), true, "HTML", &result, &fault);
        json_auto_t *ids = checkpoint_ids(checkpoint);
        if (!fault.kind && (result != SUPPLY_SENT || !json_array_size(ids)))
            error_set(&fault, E_ANNOUNCEMENT, 0);
        if (fault.kind) {
            if (json_array_size(ids)) {
                json_auto_t *empty = json_array();
                TRY(checkpoint_record(checkpoint, empty, error), false);
            } else {
                bool retryable = fault.kind == E_REJECTED || fault.kind == E_FORBIDDEN ||
                                 fault.kind == E_RATE_LIMIT;
                STR(error_path) = strf("%s.last_error_type", path);
                json_auto_t *failed =
                    JO(P("$set", JO(P(state_path, js(retryable ? "pending" : "uncertain")),
                                    P(error_path, js(error_name(fault))))))
                        .p;
                TRY(db_update(service->app->db, "settings", selector, failed, false, false, NULL,
                              error),
                    false);
            }
            json_object_set_new(blocked, blocked_key, json_true());
        }
        short_sleep(1);
    }
    json_auto_t *selector = JO(P("_id", jr(id))).p;
    json_auto_t *current = db_one(service->app->db, "settings", selector, NULL, error);
    TRY(!error->kind, false);
    REQUIRE(current && json_is_array(get(current, "deliveries")), E_DATABASE, false);
    *complete = true;
    json_array_foreach(get(current, "deliveries"), index,
                       delivery) if (strcmp(field(delivery, "state"), "sent")) *complete = false;
    json_auto_t *update =
        JO(P("$set", JO(P("complete", jb(*complete)), P("updated_at", jdate(now()))))).p;
    return db_update(service->app->db, "settings", selector, update, false, false, NULL, error);
}
static bool sweep(Anniversary *service, json_t *run, bool *acquired, Error *error) {
    TRY(lease_acquire(&service->lease, acquired, error), false);
    if (!*acquired) {
        json_object_set_new(run, "status", js("skipped_overlap").p);
        return true;
    }
    if (service->lease.previous_owner) {
        json_auto_t *filter =
            JO(P("kind", js(run_kind)), P("owner", js(service->lease.previous_owner)),
               P("status", js("running")), P("_id", JO(P("$ne", jr(get(run, "_id"))))))
                .p;
        json_auto_t *update =
            JO(P("$set", JO(P("status", js("interrupted")), P("finished_at", jdate(now())),
                            P("errors", JA(JO(P("error_type", js("InterruptedSweep"))))))))
                .p;
        TRY(db_update(service->app->db, "settings", filter, update, true, false, NULL, error),
            false);
    }
    json_auto_t *names = json_array();
    json_auto_t *birthdays = json_array();
    TRY(inventory(service, run, names, birthdays, error), false);
    json_object_set_new(run, "channels", ji((int64_t)json_array_size(names)).p);
    double today;
    TRY(midnight(get(run, "date"), &today, error), false);
    struct tm current = time_parts(today, true);
    int year = current.tm_year + 1900;
    size_t i;
    json_t *channel;
    json_array_foreach(names, i, channel) {
        TRY(lease_renew(&service->lease, error), false);
        struct tm born = time_parts(number(json_array_get(birthdays, i), 0), true);
        int day = born.tm_mday;
        if (born.tm_mon == 1 && day == 29 &&
            !(year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)))
            day = 28;
        int years = current.tm_year - born.tm_year;
        if (years > 0 && current.tm_mon == born.tm_mon && current.tm_mday == day) {
            bump(run, "due");
            TRY(queue_anniversary(service, text(channel), years, today, names, error), false);
        }
    }
    json_auto_t *filter = JO(P("kind", js(event_kind)), P("complete", jb(false))).p;
    json_auto_t *events = db_find(service->app->db, "settings", filter, NULL, 0, NULL, error);
    TRY(events, false);
    json_t *event;
    json_array_foreach(events, i, event) {
        TRY(lease_renew(&service->lease, error), false);
        REQUIRE(json_is_string(get(event, "channel")), E_CONFIG, false);
        bool active = false;
        size_t j;
        json_array_foreach(names, j, channel) if (!strcmp(text(channel), field(event, "channel")))
            active = true;
        if (!active)
            continue;
        Error fault = {0};
        bool complete;
        if (!deliver(service, event, &complete, &fault))
            push_error(
                run, JO(P("event", jr(get(event, "_id"))), P("error_type", js(error_name(fault)))));
        else if (complete)
            bump(run, "completed");
    }
    json_auto_t *pending = db_find(service->app->db, "settings", filter, NULL, 0, NULL, error);
    TRY(pending, false);
    json_array_foreach(pending, i, event) {
        bump(run, "pending");
        REQUIRE(json_is_array(get(event, "deliveries")), E_CONFIG, false);
        size_t j;
        json_t *part;
        json_array_foreach(get(event, "deliveries"), j, part) {
            const char *state = field(part, "state");
            if (!strcmp(state, "sending") || !strcmp(state, "uncertain"))
                bump(run, "uncertain_messages");
        }
    }
    json_object_set_new(run, "status",
                        js(number(get(run, "pending"), 0) > 0 || json_array_size(get(run, "errors"))
                               ? "partial"
                               : "success")
                            .p);
    return true;
}
bool anniversaries(const App *app, Sender *sender, Supply *result, Error *error) {
    Anniversary service = {app, sender, lease_new(app->db, "r2t_anniversary_sweep_lock")};
    STR(unique) = uuid_text();
    STR(id) = strf("%s:%s", run_kind, unique);
    STR(date) = time_format(now(), "%Y-%m-%d", true);
    json_auto_t *run =
        JO(P("_id", js(id)), P("kind", js(run_kind)), P("setting", js(id)),
           P("owner", js(service.lease.owner)), P("date", js(date)), P("started_at", jdate(now())),
           P("status", js("running")), P("channels", ji(0)), P("due", ji(0)), P("completed", ji(0)),
           P("pending", ji(0)), P("uncertain_messages", ji(0)), P("skipped_no_history", JA0()),
           P("errors", JA0()))
            .p;
    json_auto_t *docs = JA(jr(run)).p;
    if (!db_insert(app->db, "settings", docs, error)) {
        lease_free(&service.lease);
        return false;
    }
    bool acquired = false;
    Error outcome = {0};
    if (!sweep(&service, run, &acquired, &outcome)) {
        json_object_set_new(run, "status", js("failed").p);
        push_error(run, JO(P("error_type", js(error_name(outcome)))));
    }
    json_object_set_new(run, "finished_at", jdate(now()).p);
    json_auto_t *values = json_deep_copy(run);
    json_object_del(values, "_id");
    json_auto_t *filter = JO(P("_id", js(id))).p;
    json_auto_t *update = JO(P("$set", jr(values))).p;
    Error local = {0};
    if (!db_update(app->db, "settings", filter, update, false, false, NULL, &local) &&
        !outcome.kind)
        outcome = local;
    local = (Error){0};
    if (acquired && !lease_release(&service.lease, &local) && !outcome.kind)
        outcome = local;
    lease_free(&service.lease);
    if (outcome.kind) {
        *error = outcome;
        return false;
    }
    REQUIRE(strcmp(field(run, "status"), "failed") && strcmp(field(run, "status"), "partial"),
            E_ANNOUNCEMENT, false);
    return supply_result(result, SUPPLY_STOP);
}
