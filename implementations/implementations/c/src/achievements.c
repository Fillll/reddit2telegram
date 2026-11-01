#include "achievements.h"
#include "build_info.h"
#include "durable.h"
#include <math.h>
#include <openssl/rand.h>
#include <stdlib.h>
#include <string.h>
static const char *main_channel = "@reddit2telegram", *event_kind = "r2t_achievement_delivery",
                  *history = "r2t_achievements";
typedef struct {
    const App *app;
    Sender *sender;
    Lease lease;
} Milestones;
static bool contains_id(const json_t *values, int64_t wanted) {
    size_t i;
    json_t *value;
    json_array_foreach(values, i, value) {
        int64_t id;
        if (integer(value, &id) && id == wanted)
            return true;
    }
    return false;
}
static void report(Milestones *service, const char *body, const char *mode) {
    Error fault = {0};
    if (!sender_text(service->sender, body, false, mode, NULL, &fault))
        log_info("Could not send achievement sweep status", true);
}
static bool queue_milestone(Milestones *service, const char *module, const char *handle,
                            int64_t achievement, Error *error) {
    STR(channel) = lower(handle);
    json_auto_t *filter = JO(P("setting", js(history))).p;
    json_auto_t *legacy = db_one(service->app->db, "settings", filter, NULL, error);
    TRY(!error->kind, false);
    if (legacy && json_object_get(legacy, "channels")) {
        json_t *channels = get(legacy, "channels");
        REQUIRE(json_is_object(channels), E_CONFIG, false);
        if (json_object_get(channels, channel)) {
            json_auto_t *previous = identifiers(channels, channel, error);
            TRY(previous, false);
            if (contains_id(previous, achievement))
                return true;
        }
    }
    STR(id) = strf("%s:%s:%lld", event_kind, channel, (long long)achievement);
    json_auto_t *selector = JO(P("_id", js(id))).p;
    json_auto_t *update =
        JO(P("$setOnInsert",
             JO(P("setting", js(id)), P("kind", js(event_kind)), P("submodule", js(module)),
                P("channel", js(channel)), P("achievement", ji(achievement)),
                P("complete", jb(false)), P("message_ids", JA0()), P("forwarded_ids", JA0()),
                P("created_at", jdate(now())))))
            .p;
    return db_update(service->app->db, "settings", selector, update, false, true, NULL, error);
}
static bool candidate(Milestones *service, const json_t *event, Checkpoint *checkpoint,
                      bool *posting_attempted, Error *error) {
    REQUIRE(json_is_string(get(event, "submodule")) && json_is_string(get(event, "channel")),
            E_CONFIG, false);
    const char *module = field(event, "submodule"), *channel = field(event, "channel");
    CHANNEL(source) = channel_resolve(service->app, module, error);
    TRY(source, false);
    int64_t achievement;
    REQUIRE(integer(get(event, "achievement"), &achievement), E_CONFIG, false);
    STR(heading) = strf("🏆 Great achievement!\n%s\n💪 Milestone of %lld subscribers.\n\n", channel,
                        (long long)achievement);
    REDDIT(reddit) = reddit_new(service->app->config, service->sender->metrics);
    json_auto_t *destination = js(main_channel).p;
    SENDER(target) = sender_new(service->app->config, service->app->db, destination,
                                service->sender->metrics, service->app->videos);
    target->ack = checkpoint_record;
    target->ack_data = checkpoint;
    size_t scanned = 0;
    STR(after) = NULL;
    bool stop = false;
    while (scanned < 1000 && !stop) {
        json_auto_t *page = NULL;
        int retries = 0;
        while (!page) {
            Error fault = {0};
            page = reddit_listing(reddit, source->subreddit, "top", 1000, after, &fault);
            if (!page) {
                if (++retries >= 10) {
                    *error = fault;
                    return false;
                }
                metrics_count(service->sender->metrics, "reddit_listing_retries", 1);
                long_sleep(2.818281828 * M_PI / 2);
            }
        }
        json_t *items = get(get(page, "data"), "children");
        REQUIRE(json_is_array(items), E_REDDIT, false);
        if (!json_array_size(items))
            break;
        size_t i;
        json_t *item;
        json_array_foreach(items, i, item) {
            if (scanned >= 1000)
                break;
            scanned++;
            json_t *submission = get(item, "data");
            STR(link) = strf("https://redd.it/%s", field(submission, "id"));
            bool seen, blocked;
            TRY(sender_seen(target, link, &seen, error), false);
            if (seen)
                continue;
            TRY(sender_error_limit(target, link, &blocked, error), false);
            if (blocked)
                continue;
            *posting_attempted = true;
            Supply result;
            TRY(channel_nice(service->app, module, submission, target, reddit, heading, "", channel,
                             &result, error),
                false);
            json_auto_t *ids = checkpoint_ids(checkpoint);
            if (json_array_size(ids) && result != SUPPLY_SENT)
                result = SUPPLY_STOP;
            if (result == SUPPLY_SENT) {
                TRY(sender_mark(target, link, true, error), false);
                stop = true;
            } else if (result == SUPPLY_REJECT) {
                TRY(sender_mark(target, link, false, error), false);
            } else if (result == SUPPLY_STOP)
                stop = true;
            if (stop)
                break;
        }
        json_t *next = get(get(page, "data"), "after");
        free(after);
        after = json_is_string(next) ? xstrdup(text(next)) : NULL;
        if (!after)
            break;
    }
    return true;
}
static bool deliver(Milestones *service, const json_t *event, Error *error) {
    TRY(lease_renew(&service->lease, error), false);
    REQUIRE(json_object_get(event, "_id") && json_is_string(get(event, "channel")), E_CONFIG,
            false);
    json_auto_t *selector = JO(P("_id", jr(get(event, "_id")))).p;
    const char *channel = field(event, "channel");
    int64_t achievement;
    REQUIRE(integer(get(event, "achievement"), &achievement), E_CONFIG, false);
    json_auto_t *attempt =
        JO(P("$inc", JO(P("attempts", ji(1)))), P("$set", JO(P("last_attempt_at", jdate(now())))))
            .p;
    TRY(db_update(service->app->db, "settings", selector, attempt, false, false, NULL, error),
        false);
    json_auto_t *recorded = identifiers(event, "message_ids", error);
    TRY(recorded, false);
    CHECKPOINT(checkpoint) = checkpoint_new(service->app->db, selector, NULL, recorded);
    if (!json_array_size(recorded)) {
        bool attempted = false;
        Error fault = {0};
        bool posted = candidate(service, event, checkpoint, &attempted, &fault);
        json_auto_t *ids = checkpoint_ids(checkpoint);
        if (!posted && !json_array_size(ids) && attempted) {
            *error = fault;
            return false;
        }
        if (!json_array_size(ids)) {
            json_auto_t *destination = js(main_channel).p;
            SENDER(target) = sender_new(service->app->config, service->app->db, destination,
                                        service->sender->metrics, service->app->videos);
            target->ack = checkpoint_record;
            target->ack_data = checkpoint;
            STR(body) = strf("🏆 Great achievement!\n%s\n💪 Milestone of %lld subscribers.",
                             channel, (long long)achievement);
            Supply result;
            TRY(sender_text(target, body, false, NULL, &result, error), false);
            json_auto_t *sent = checkpoint_ids(checkpoint);
            REQUIRE(result == SUPPLY_SENT && json_array_size(sent), E_ANNOUNCEMENT, false);
        }
    }
    TRY(lease_renew(&service->lease, error), false);
    json_auto_t *ids = checkpoint_ids(checkpoint);
    json_auto_t *remember = JO(P("$addToSet", JO(P("message_ids", JO(P("$each", jr(ids))))))).p;
    TRY(db_update(service->app->db, "settings", selector, remember, false, false, NULL, error),
        false);
    STR(path) = strf("channels.%s", channel);
    json_auto_t *history_filter = JO(P("setting", js(history))).p;
    json_auto_t *update_history = JO(P("$addToSet", JO(P(path, ji(achievement))))).p;
    TRY(db_update(service->app->db, "settings", history_filter, update_history, false, true, NULL,
                  error),
        false);
    if (strcmp(channel, main_channel)) {
        json_auto_t *forwarded = identifiers(event, "forwarded_ids", error);
        TRY(forwarded, false);
        json_auto_t *destination = js(channel).p;
        SENDER(target) = sender_new(service->app->config, service->app->db, destination,
                                    service->sender->metrics, service->app->videos);
        size_t i;
        json_t *value;
        json_array_foreach(ids, i, value) {
            int64_t id;
            REQUIRE(integer(value, &id), E_CONFIG, false);
            if (contains_id(forwarded, id))
                continue;
            TRY(lease_renew(&service->lease, error), false);
            json_auto_t *params = JO(P("chat_id", js(channel)), P("from_chat_id", js(main_channel)),
                                     P("message_id", ji(id)))
                                      .p;
            json_auto_t *sent = sender_api(target, "forwardMessage", params, error);
            TRY(sent, false);
            json_auto_t *saved = JO(P("$addToSet", JO(P("forwarded_ids", ji(id))))).p;
            TRY(db_update(service->app->db, "settings", selector, saved, false, false, NULL, error),
                false);
        }
    }
    json_auto_t *complete =
        JO(P("$set", JO(P("complete", jb(true)), P("completed_at", jdate(now()))))).p;
    return db_update(service->app->db, "settings", selector, complete, false, false, NULL, error);
}
typedef struct {
    int64_t channels, members, admins, errors, previous;
} Totals;
static const char *sign_text(int64_t n) {
    return n < 0 ? "" : n == 0 ? "±" : "+";
}
static char *percentage(int64_t difference, int64_t before) {
    if (!before)
        return xstrdup("0");
    char *out = strf("%.2f", (double)difference / (double)before * 100);
    size_t length = strlen(out);
    while (length && out[length - 1] == '0')
        out[--length] = 0;
    if (length && out[length - 1] == '.')
        out[length++] = '0';
    out[length] = 0;
    return out;
}
static char *leaderboard(const char *heading, const json_t *snapshots, bool gains) {
    size_t count = json_array_size(snapshots);
    json_t **sorted = xcalloc(count ? count : 1, sizeof(*sorted));
    for (size_t i = 0; i < count; i++) {
        json_t *row = json_array_get(snapshots, i);
        double delta = number(get(row, "current"), 0) - number(get(row, "before"), 0);
        size_t j = i;
        while (j) {
            double other =
                number(get(sorted[j - 1], "current"), 0) - number(get(sorted[j - 1], "before"), 0);
            if (gains ? other >= delta : other <= delta)
                break;
            sorted[j] = sorted[j - 1];
            j--;
        }
        sorted[j] = row;
    }
    BUF(body);
    buffer_text(&body, heading);
    for (size_t i = 0; i < count && i < 5; i++) {
        json_t *row = sorted[i];
        int64_t before = (int64_t)number(get(row, "before"), 0),
                current = (int64_t)number(get(row, "current"), 0);
        int64_t delta = current - before;
        STR(percent) = percentage(delta, before);
        STR(line) =
            strf("%s: %lld %s%lld (%s%s%%) → %lld\n", field(row, "channel"), (long long)before,
                 sign_text(delta), (long long)delta, sign_text(delta), percent, (long long)current);
        buffer_text(&body, line);
    }
    free(sorted);
    return buffer_take(&body);
}
static bool collect_admins(Milestones *service, const char *channel, json_t *snapshot,
                           Totals *totals, Error *error) {
    json_auto_t *params = JO(P("chat_id", js(channel))).p;
    json_auto_t *admins = sender_api(service->sender, "getChatAdministrators", params, error);
    TRY(admins, false);
    REQUIRE(json_is_array(admins), E_TELEGRAM, false);
    json_auto_t *names = json_array();
    size_t i;
    json_t *admin;
    json_array_foreach(admins, i, admin) {
        json_t *name = get(get(admin, "user"), "username");
        if (json_is_string(name)) {
            if (strcmp(text(name), "reddit2telegram_bot")) {
                STR(handle) = strf("@%s", text(name));
                json_array_append_new(names, js(handle).p);
            }
        } else
            json_array_append_new(names, js("%NO_USERNAME%").p);
    }
    totals->admins += (int64_t)json_array_size(names);
    jset(snapshot, "admins", names);
    return true;
}
static bool collect_members(Milestones *service, const char *module, const char *channel,
                            json_t *snapshot, Totals *totals, const json_t *thresholds,
                            json_t *snapshots, Error *error) {
    json_auto_t *params = JO(P("chat_id", js(channel))).p;
    json_auto_t *value = sender_api(service->sender, "getChatMemberCount", params, error);
    TRY(value, false);
    int64_t members;
    REQUIRE(integer(value, &members), E_TELEGRAM, false);
    STR(low) = lower(channel);
    json_auto_t *filter = JO(P("channel", js(low)), P("members_cnt", JO(P("$gte", ji(0))))).p;
    json_auto_t *sort = JO(P("ts", ji(-1))).p;
    json_auto_t *previous = db_one(service->app->db, "stats", filter, sort, error);
    TRY(!error->kind, false);
    int64_t before = members;
    REQUIRE(!previous || integer(get(previous, "members_cnt"), &before), E_CONFIG, false);
    size_t i;
    json_t *value_threshold;
    json_array_foreach(thresholds, i, value_threshold) {
        int64_t threshold;
        REQUIRE(integer(value_threshold, &threshold), E_CONFIG, false);
        if (before < threshold && threshold <= members)
            TRY(queue_milestone(service, module, channel, threshold, error), false);
    }
    json_object_set_new(snapshot, "members_cnt", ji(members).p);
    json_auto_t *docs = JA(jr(snapshot)).p;
    TRY(db_insert(service->app->db, "stats", docs, error), false);
    totals->members += members;
    totals->previous += before;
    json_array_append_new(
        snapshots,
        JO(P("channel", js(channel)), P("before", ji(before)), P("current", ji(members))).p);
    return true;
}
static bool sweep(Milestones *service, Error *error) {
    report(service, "Regular bypass started.", NULL);
    json_auto_t *threshold_values = parse_json(R2T_MILESTONES, strlen(R2T_MILESTONES), error);
    TRY(threshold_values, false);
    json_auto_t *wrapped = JO(P("ids", jr(threshold_values))).p;
    json_auto_t *thresholds = identifiers(wrapped, "ids", error);
    TRY(thresholds, false);
    json_auto_t *modules = public_modules(service->app, error);
    TRY(modules, false);
    size_t count = json_array_size(modules);
    double coefficient = 2000.0 / 3 / 2 / (count ? count : 1);
    for (size_t i = count; i > 1; i--) {
        uint64_t bits;
        REQUIRE(RAND_bytes((unsigned char *)&bits, sizeof(bits)) == 1, E_IO, false);
        size_t j = bits % i;
        json_auto_t *a = json_incref(json_array_get(modules, i - 1));
        json_auto_t *b = json_incref(json_array_get(modules, j));
        json_array_set(modules, i - 1, b);
        json_array_set(modules, j, a);
    }
    Totals totals = {0};
    json_auto_t *snapshots = json_array();
    json_auto_t *seen = json_object();
    size_t i;
    json_t *module;
    json_array_foreach(modules, i, module) {
        TRY(lease_renew(&service->lease, error), false);
        short_sleep(coefficient);
        Error fault = {0};
        CHANNEL(resolved) = channel_resolve(service->app, text(module), &fault);
        if (!resolved) {
            totals.errors++;
            continue;
        }
        if (!json_is_string(resolved->destination))
            continue;
        const char *channel = text(resolved->destination);
        STR(low) = lower(channel);
        if (*channel != '@' || json_object_get(seen, low))
            continue;
        json_object_set_new(seen, low, json_true());
        json_auto_t *snapshot =
            JO(P("channel", js(low)), P("ts", jdate(now())), P("submodule", jr(module))).p;
        totals.channels++;
        if (!collect_admins(service, channel, snapshot, &totals, &fault)) {
            totals.errors++;
            STR(body) = strf("Failed to get admins for %s.", channel);
            report(service, body, NULL);
        }
        short_sleep(coefficient);
        fault = (Error){0};
        if (!collect_members(service, text(module), channel, snapshot, &totals, thresholds,
                             snapshots, &fault)) {
            totals.errors++;
            STR(body) = strf("Failed to collect statistics or queue milestones for %s.", channel);
            report(service, body, NULL);
        }
    }
    json_auto_t *filter = JO(P("kind", js(event_kind)), P("complete", jb(false))).p;
    json_auto_t *events = db_find(service->app->db, "settings", filter, NULL, 0, NULL, error);
    TRY(events, false);
    json_t *event;
    json_array_foreach(events, i, event) {
        TRY(lease_renew(&service->lease, error), false);
        Error fault = {0};
        if (!deliver(service, event, &fault)) {
            totals.errors++;
            REQUIRE(json_object_get(event, "_id") && json_is_string(get(event, "channel")),
                    E_CONFIG, false);
            json_auto_t *selector = JO(P("_id", jr(get(event, "_id")))).p;
            json_auto_t *update = JO(P("$set", JO(P("last_error_type", js(error_name(fault))),
                                                  P("last_failure_at", jdate(now())))))
                                      .p;
            TRY(db_update(service->app->db, "settings", selector, update, false, false, NULL,
                          error),
                false);
            int64_t achievement;
            REQUIRE(integer(get(event, "achievement"), &achievement), E_CONFIG, false);
            STR(body) = strf("Milestone delivery pending: %s, %lld subscribers.",
                             field(event, "channel"), (long long)achievement);
            report(service, body, NULL);
        }
    }
    int64_t difference = totals.members - totals.previous;
    STR(percent) = percentage(difference, totals.previous);
    STR(body) =
        strf("Ok, regular bypass results.\n\n<pre>Active channels: %lld.</pre>\n"
             "<pre>Subscribers: %lld.</pre>\n<pre>Cnt diff: %s%lld (%s%s%%).</pre>\n"
             "<pre>Admins: %lld.</pre>\n<pre>Errors during bypass: %lld.</pre>\n\n<i>See you!</i>",
             (long long)totals.channels, (long long)totals.members, sign_text(difference),
             (long long)difference, sign_text(difference), percent, (long long)totals.admins,
             (long long)totals.errors);
    report(service, body, "HTML");
    short_sleep(1);
    STR(gain) = leaderboard("📈 <b>TOP 5 GAIN</b> 📈\n", snapshots, true);
    report(service, gain, "HTML");
    short_sleep(1);
    STR(fall) = leaderboard("📉 <b>TOP 5 FALL</b> 📉\n", snapshots, false);
    report(service, fall, "HTML");
    return true;
}
bool achievements(const App *app, Sender *sender, Supply *result, Error *error) {
    Milestones service = {app, sender, lease_new(app->db, "r2t_achievement_sweep_lock")};
    bool acquired = false;
    if (!lease_acquire(&service.lease, &acquired, error)) {
        lease_free(&service.lease);
        return false;
    }
    if (!acquired) {
        lease_free(&service.lease);
        return supply_result(result, SUPPLY_STOP);
    }
    Error outcome = {0}, local = {0};
    sweep(&service, &outcome);
    if (!lease_release(&service.lease, &local) && !outcome.kind)
        outcome = local;
    lease_free(&service.lease);
    if (outcome.kind) {
        *error = outcome;
        return false;
    }
    return supply_result(result, SUPPLY_STOP);
}
