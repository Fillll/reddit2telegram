#include "achievements.hpp"
#include "build_info.hpp"
#include "durable.hpp"
#include <iomanip>
#include <numbers>
#include <set>
#include <sstream>
namespace r2t {
static const std::string main_channel = "@reddit2telegram", event_kind = "r2t_achievement_delivery",
                         history = "r2t_achievements";
struct Snapshot {
    std::string channel;
    int64_t before, current;
};
struct Totals {
    int64_t channels = 0, members = 0, admins = 0, errors = 0, previous = 0;
};
static std::string sign(int64_t n) {
    return n < 0 ? "" : n == 0 ? "±" : "+";
}
static std::string round2(double n) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(2) << n;
    auto s = out.str();
    while (s.ends_with('0'))
        s.pop_back();
    if (s.ends_with('.'))
        s += '0';
    return s;
}
static std::string leaderboard(std::string heading, const std::vector<Snapshot> &snapshots) {
    for (size_t i = 0; i < std::min(size_t(5), snapshots.size()); i++) {
        auto &r = snapshots[i];
        auto difference = r.current - r.before;
        auto symbol = sign(difference);
        auto percentage = r.before ? round2(double(difference) / r.before * 100) : "0";
        heading += r.channel + ": " + std::to_string(r.before) + " " + symbol +
                   std::to_string(difference) + " (" + symbol + percentage + "%) → " +
                   std::to_string(r.current) + "\n";
    }
    return heading;
}
class Milestones {
    const App &app;
    Sender &sender;
    void report(const std::string &body, const std::optional<std::string> &mode = {}) {
        try {
            sender.send_text(body, false, mode);
        } catch (...) {
            log("Could not send achievement sweep status", true);
        }
    }
    void queue(const std::string &module, std::string channel, int64_t achievement) {
        channel = lower(channel);
        auto legacy = app.db.one("settings", {{"setting", history}});
        if (legacy && legacy->contains("channels")) {
            auto &channels = get(*legacy, "channels");
            if (!channels.is_object())
                throw Error(Kind::Config);
            if (channels.contains(channel)) {
                auto previous = identifiers({{"ids", get(channels, channel)}}, "ids");
                if (std::find(previous.begin(), previous.end(), achievement) != previous.end())
                    return;
            }
        }
        auto id = event_kind + ":" + channel + ":" + std::to_string(achievement);
        app.db.update("settings", {{"_id", id}},
                      {{"$setOnInsert",
                        {{"setting", id},
                         {"kind", event_kind},
                         {"submodule", module},
                         {"channel", channel},
                         {"achievement", achievement},
                         {"complete", false},
                         {"message_ids", Json::array()},
                         {"forwarded_ids", Json::array()},
                         {"created_at", bson_date()}}}},
                      false, true);
    }
    void candidate(const Json &event, std::shared_ptr<Checkpoint> checkpoint,
                   bool &posting_attempted) {
        if (!get(event, "submodule").is_string() || !get(event, "channel").is_string())
            throw Error(Kind::Config);
        auto module = text(event, "submodule"), channel = text(event, "channel");
        auto source = resolve(app, module);
        auto number = integer(get(event, "achievement"));
        auto heading = "🏆 Great achievement!\n" + channel + "\n💪 Milestone of " +
                       std::to_string(number) + " subscribers.\n\n";
        Reddit reddit(*app.config, sender.metrics);
        auto target = app.sender(main_channel, sender.metrics);
        target.acknowledgement = checkpoint;
        size_t scanned = 0;
        std::optional<std::string> after;
        bool stop = false;
        while (scanned < 1000 && !stop) {
            Json page;
            int retries = 0;
            while (true)
                try {
                    page = reddit.listing(source.subreddit, "top", 1000, after);
                    break;
                } catch (...) {
                    if (++retries >= 10)
                        throw;
                    sender.metrics.count("reddit_listing_retries");
                    long_sleep(2.818281828 * std::numbers::pi / 2);
                }
            auto &items = get(get(page, "data"), "children");
            if (!items.is_array())
                throw Error(Kind::Reddit);
            if (items.empty())
                break;
            for (auto &item : items) {
                if (scanned >= 1000)
                    break;
                scanned++;
                auto &submission = get(item, "data");
                auto link = "https://redd.it/" + text(submission, "id");
                if (target.was_before(link) || target.too_many_errors(link))
                    continue;
                posting_attempted = true;
                auto result = nice(app, module, submission, target, reddit, heading, "", channel);
                if (!checkpoint->ids().empty() && result != Supply::Sent)
                    result = Supply::Stop;
                switch (result) {
                case Supply::Sent:
                    target.mark(link, true);
                    stop = true;
                    break;
                case Supply::Reject:
                    target.mark(link, false);
                    break;
                case Supply::Skip:
                    break;
                case Supply::Stop:
                    stop = true;
                    break;
                }
                if (stop)
                    break;
            }
            auto &next = get(get(page, "data"), "after");
            after = next.is_string() ? std::optional<std::string>(text(next)) : std::nullopt;
            if (!after)
                break;
        }
    }
    void deliver(const Json &event) {
        lease.renew();
        if (!event.contains("_id") || !get(event, "channel").is_string())
            throw Error(Kind::Config);
        Json selector = {{"_id", get(event, "_id")}};
        auto channel = text(event, "channel");
        auto number = integer(get(event, "achievement"));
        app.db.update("settings", selector,
                      {{"$inc", {{"attempts", 1}}}, {"$set", {{"last_attempt_at", bson_date()}}}});
        auto checkpoint = std::make_shared<Checkpoint>(app.db, selector, std::nullopt,
                                                       identifiers(event, "message_ids"));
        if (checkpoint->ids().empty()) {
            bool attempted = false;
            try {
                candidate(event, checkpoint, attempted);
            } catch (...) {
                if (checkpoint->ids().empty() && attempted)
                    throw;
            }
            if (checkpoint->ids().empty()) {
                auto target = app.sender(main_channel, sender.metrics);
                target.acknowledgement = checkpoint;
                auto result =
                    target.send_text("🏆 Great achievement!\n" + channel + "\n💪 Milestone of " +
                                     std::to_string(number) + " subscribers.");
                if (result != Supply::Sent || checkpoint->ids().empty())
                    throw Error(Kind::Announcement);
            }
        }
        lease.renew();
        auto ids = checkpoint->ids();
        app.db.update("settings", selector, {{"$addToSet", {{"message_ids", {{"$each", ids}}}}}});
        app.db.update("settings", {{"setting", history}},
                      {{"$addToSet", {{"channels." + channel, number}}}}, false, true);
        if (channel != main_channel) {
            auto forwarded = identifiers(event, "forwarded_ids");
            auto target = app.sender(channel, sender.metrics);
            for (auto id : ids) {
                if (std::find(forwarded.begin(), forwarded.end(), id) != forwarded.end())
                    continue;
                lease.renew();
                target.api(
                    "forwardMessage",
                    {{"chat_id", channel}, {"from_chat_id", main_channel}, {"message_id", id}});
                app.db.update("settings", selector, {{"$addToSet", {{"forwarded_ids", id}}}});
            }
        }
        app.db.update("settings", selector,
                      {{"$set", {{"complete", true}, {"completed_at", bson_date()}}}});
    }

  public:
    Lease lease;
    Milestones(const App &app, Sender &sender)
        : app(app), sender(sender), lease(app.db, "r2t_achievement_sweep_lock") {}
    Supply sweep() {
        report("Regular bypass started.");
        auto thresholds = identifiers({{"ids", parse(build::milestones)}}, "ids");
        auto modules = public_modules(app);
        auto coefficient = 2000. / 3 / 2 / std::max(size_t(1), modules.size());
        std::shuffle(modules.begin(), modules.end(), random());
        std::set<std::string> seen;
        Totals totals;
        std::vector<Snapshot> snapshots;
        for (auto &module : modules) {
            lease.renew();
            short_sleep(coefficient);
            std::string channel;
            try {
                auto resolved = resolve(app, module);
                if (!resolved.destination.is_string())
                    continue;
                channel = text(resolved.destination);
                if (!channel.starts_with('@') || !seen.insert(lower(channel)).second)
                    continue;
            } catch (...) {
                totals.errors++;
                continue;
            }
            Json snapshot = {
                {"channel", lower(channel)}, {"ts", bson_date()}, {"submodule", module}};
            totals.channels++;
            try {
                auto admins = sender.api("getChatAdministrators", {{"chat_id", channel}});
                if (!admins.is_array())
                    throw Error(Kind::Telegram);
                std::vector<std::string> names;
                for (auto &admin : admins) {
                    auto &name = get(get(admin, "user"), "username");
                    if (name.is_string()) {
                        if (text(name) != "reddit2telegram_bot")
                            names.push_back("@" + text(name));
                    } else
                        names.push_back("%NO_USERNAME%");
                }
                totals.admins += names.size();
                snapshot["admins"] = names;
            } catch (...) {
                totals.errors++;
                report("Failed to get admins for " + channel + ".");
            }
            short_sleep(coefficient);
            try {
                auto members = integer(sender.api("getChatMemberCount", {{"chat_id", channel}}));
                auto previous = app.db.one(
                    "stats", {{"channel", lower(channel)}, {"members_cnt", {{"$gte", 0}}}},
                    {{"ts", -1}});
                auto before = previous ? integer(get(*previous, "members_cnt")) : members;
                for (auto threshold : thresholds)
                    if (before < threshold && threshold <= members)
                        queue(module, channel, threshold);
                snapshot["members_cnt"] = members;
                app.db.insert("stats", {snapshot});
                totals.members += members;
                totals.previous += before;
                snapshots.push_back({channel, before, members});
            } catch (...) {
                totals.errors++;
                report("Failed to collect statistics or queue milestones for " + channel + ".");
            }
        }
        for (auto &event : app.db.find("settings", {{"kind", event_kind}, {"complete", false}})) {
            lease.renew();
            try {
                deliver(event);
            } catch (...) {
                auto error = safe_error();
                totals.errors++;
                if (!event.contains("_id") || !get(event, "channel").is_string())
                    throw Error(Kind::Config);
                app.db.update(
                    "settings", {{"_id", get(event, "_id")}},
                    {{"$set",
                      {{"last_error_type", error.what()}, {"last_failure_at", bson_date()}}}});
                report("Milestone delivery pending: " + text(event, "channel") + ", " +
                       std::to_string(integer(get(event, "achievement"))) + " subscribers.");
            }
        }
        auto difference = totals.members - totals.previous;
        auto symbol = sign(difference);
        auto percentage =
            totals.previous ? round2(double(difference) / totals.previous * 100) : "0";
        report("Ok, regular bypass results.\n\n<pre>Active channels: " +
                   std::to_string(totals.channels) + ".</pre>\n<pre>Subscribers: " +
                   std::to_string(totals.members) + ".</pre>\n<pre>Cnt diff: " + symbol +
                   std::to_string(difference) + " (" + symbol + percentage +
                   "%).</pre>\n<pre>Admins: " + std::to_string(totals.admins) +
                   ".</pre>\n<pre>Errors during bypass: " + std::to_string(totals.errors) +
                   ".</pre>\n\n<i>See you!</i>",
               "HTML");
        short_sleep();
        std::stable_sort(snapshots.begin(), snapshots.end(), [](auto &a, auto &b) {
            return a.current - a.before > b.current - b.before;
        });
        report(leaderboard("📈 <b>TOP 5 GAIN</b> 📈\n", snapshots), "HTML");
        short_sleep();
        std::stable_sort(snapshots.begin(), snapshots.end(), [](auto &a, auto &b) {
            return a.current - a.before < b.current - b.before;
        });
        report(leaderboard("📉 <b>TOP 5 FALL</b> 📉\n", snapshots), "HTML");
        return Supply::Stop;
    }
};
Supply achievements(const App &app, Sender &sender) {
    Milestones service(app, sender);
    if (!service.lease.acquire())
        return Supply::Stop;
    std::optional<Error> error;
    Supply result;
    try {
        result = service.sweep();
    } catch (...) {
        error = safe_error();
    }
    try {
        service.lease.release();
    } catch (...) {
        if (!error)
            error = safe_error();
    }
    if (error)
        throw *error;
    return result;
}
} // namespace r2t
