#include "anniversaries.hpp"
#include "build_info.hpp"
#include "durable.hpp"
#include <regex>
#include <set>
namespace r2t {
static const std::string date_kind = "r2t_anniversary_date",
                         event_kind = "r2t_anniversary_delivery", run_kind = "r2t_anniversary_run",
                         main_channel = "@reddit2telegram", community = "@r_channels";
static double midnight(const Json &value) {
    if (auto stamp = bson_timestamp(value)) {
        auto tm = time_parts(*stamp, true);
        tm.tm_hour = tm.tm_min = tm.tm_sec = 0;
        return timegm(&tm);
    }
    if (value.is_string()) {
        auto s = text(value);
        std::tm tm{};
        char *end = strptime(s.c_str(), "%Y-%m-%d", &tm);
        if (end && !*end) {
            double stamp = timegm(&tm);
            if (time_format(stamp, "%Y-%m-%d", true) == s)
                return stamp;
        }
    }
    throw Error(Kind::Config);
}
static std::string chat_key(const Json &value) {
    return value.is_string() ? lower(text(value)) : value.dump();
}
static void bump(Json &record, const std::string &key) {
    record[key] = int64_t(number(get(record, key))) + 1;
}
static void push_error(Json &record, Json error) {
    if (get(record, "errors").is_array())
        record["errors"].push_back(std::move(error));
}
static size_t utf16_count(const std::string &s) {
    size_t n = 0;
    for (unsigned char c : s)
        if ((c & 0xc0) != 0x80)
            n += c >= 0xf0 ? 2 : 1;
    return n;
}
static std::vector<std::string> messages(const std::string &channel, int years,
                                         const std::vector<std::string> &channels, double today) {
    auto plural = years == 1 ? "" : "s";
    std::string intro = "🌍 <b>Discover the Reddit2Telegram family</b>\n\n📣 @reddit2telegram — "
                        "our main channel for discovering posts and channels from across the "
                        "network.\n\n💬 @r_channels — join the community, find new channels, ask "
                        "questions, and suggest your next favorite.\n\n🎂 <b>Celebrating " +
                        html_escape(channel) + ": " + std::to_string(years) + " year" + plural +
                        " together!</b>\n📅 " + time_format(today, "%d %B %Y", true) +
                        "\nThank you for reading, sharing, and being part of the community. Here’s "
                        "to another year of great discoveries!";
    std::set<std::string> others;
    for (auto &value : channels) {
        auto c = lower(value);
        if (c != lower(channel) && c != main_channel && c != community && c != "@r_channels_test")
            others.insert(c);
    }
    if (others.empty())
        return {intro};
    intro += "\n\n🧭 Explore more of our channels in the directory below.";
    std::vector<std::string> pages, lines;
    size_t n = 0;
    for (auto &c : others) {
        auto line = std::to_string(++n) + ". " + html_escape(c);
        auto candidate = lines.empty() ? line : join(lines, "\n") + "\n" + line;
        if (!lines.empty() && (lines.size() == 100 || utf16_count(candidate) > 3400)) {
            pages.push_back(join(lines, "\n"));
            lines.clear();
        }
        lines.push_back(line);
    }
    if (!lines.empty())
        pages.push_back(join(lines, "\n"));
    std::vector<std::string> result = {intro};
    for (size_t i = 0; i < pages.size(); i++)
        result.push_back("🧭 <b>More channels · " + std::to_string(i + 1) + "/" +
                         std::to_string(pages.size()) + "</b>\n\n" + pages[i]);
    return result;
}
class Anniversary {
    const App &app;
    Sender &sender;
    std::optional<double> birthday(const std::string &channel, const std::optional<Json> &record) {
        auto id = date_kind + ":" + channel;
        auto cached = app.db.one("settings", {{"_id", id}});
        auto explicit_date = record ? get(*record, "anniversary_date") : Json(nullptr);
        double birthday;
        std::string source;
        if (!explicit_date.is_null()) {
            birthday = midnight(explicit_date);
            source = "explicit";
        } else if (cached)
            return midnight(get(*cached, "date"));
        else {
            auto docs = app.db.find(
                "urls", {{"channel", channel}, {"sent", true}, {"ts", {{"$type", "date"}}}},
                {{"ts", 1}}, 1, {{"ts", 1}});
            if (docs.empty())
                return {};
            birthday = midnight(get(docs[0], "ts"));
            source = "first_sent_post";
        }
        Json values = {{"setting", id},
                       {"kind", date_kind},
                       {"channel", channel},
                       {"date", bson_date(birthday)},
                       {"source", source}};
        app.db.update("settings", {{"_id", id}},
                      {{explicit_date.is_null() ? "$setOnInsert" : "$set", values}}, false, true);
        return birthday;
    }
    struct Inventory {
        std::vector<std::pair<std::string, double>> channels;
        std::vector<std::string> skipped;
        std::vector<Json> errors;
    };
    Inventory inventory() {
        Inventory result;
        auto local = parse(build::local_channels);
        static const std::regex handles("^@[a-zA-Z][a-zA-Z0-9_]{4,31}$");
        std::set<std::string> seen;
        for (auto &module : public_modules(app)) {
            lease.renew();
            try {
                auto record = app.db.one("channels", {{"submodule", module}});
                auto value =
                    record ? get(*record, "channel") : get(get(local, module), "t_channel");
                if (!value.is_string()) {
                    if (!record)
                        throw Error(Kind::Config);
                    continue;
                }
                auto channel = text(value);
                if (!std::regex_match(channel, handles))
                    continue;
                channel = lower(channel);
                if (channel == community || channel == "@r_channels_test" || seen.contains(channel))
                    continue;
                auto date = birthday(channel, record);
                if (date) {
                    seen.insert(channel);
                    result.channels.emplace_back(channel, *date);
                } else {
                    log("Anniversary skipped: " + channel + " has no successful posting history",
                        true);
                    result.skipped.push_back(channel);
                }
            } catch (...) {
                result.errors.push_back(
                    {{"submodule", module}, {"error_type", safe_error().what()}});
            }
        }
        return result;
    }
    void queue(const std::string &channel, int years, double today,
               const std::vector<std::string> &channels) {
        auto year = time_parts(today, true).tm_year + 1900;
        auto id = event_kind + ":" + channel + ":" + std::to_string(year);
        auto plural = years == 1 ? "" : "s";
        auto notice = "🎂 <b>Celebrating " + html_escape(channel) + ": " + std::to_string(years) +
                      " year" + plural + " together!</b>\n📅 " +
                      time_format(today, "%d %B %Y", true) +
                      "\n\nDiscover this channel and more in our main feed @reddit2telegram.\nJoin "
                      "@r_channels to explore the network and meet the community.";
        Json deliveries = Json::array();
        for (auto &body : messages(channel, years, channels, today))
            deliveries.push_back({{"destination", channel}, {"text", body}, {"state", "pending"}});
        std::set<std::string> destinations = {lower(channel)};
        for (auto &destination : std::vector<Json>{
                 main_channel, community, get(get(app.config->values, "telegram"), "dev_chat")})
            if (destinations.insert(chat_key(destination)).second)
                deliveries.push_back(
                    {{"destination", destination}, {"text", notice}, {"state", "pending"}});
        app.db.update("settings", {{"_id", id}},
                      {{"$setOnInsert",
                        {{"setting", id},
                         {"kind", event_kind},
                         {"channel", channel},
                         {"year", year},
                         {"years", years},
                         {"anniversary", time_format(today, "%Y-%m-%d", true)},
                         {"created_at", bson_date()},
                         {"complete", false},
                         {"deliveries", deliveries}}}},
                      false, true);
    }
    bool deliver(const Json &event) {
        if (!event.contains("_id") || !get(event, "deliveries").is_array())
            throw Error(Kind::Config);
        auto id = get(event, "_id");
        std::set<std::string> blocked;
        const auto &deliveries = get(event, "deliveries");
        for (size_t index = 0; index < deliveries.size(); index++) {
            lease.renew();
            auto &delivery = deliveries[index];
            if (!delivery.contains("destination") || !get(delivery, "state").is_string())
                throw Error(Kind::Config);
            auto destination = get(delivery, "destination");
            auto blocked_key = destination.dump(), state = text(delivery, "state"),
                 path = "deliveries." + std::to_string(index);
            if (state == "sent" || blocked.contains(blocked_key))
                continue;
            if (state == "sending" || state == "uncertain") {
                app.db.update("settings", {{"_id", id}, {path + ".state", "sending"}},
                              {{"$set", {{path + ".state", "uncertain"}}}});
                blocked.insert(blocked_key);
                continue;
            }
            auto attempt = uuid();
            auto response = app.db.command(
                "update", "settings",
                {{"updates", Json::array({{{"q", {{"_id", id}, {path + ".state", "pending"}}},
                                           {"u",
                                            {{"$set",
                                              {{path + ".state", "sending"},
                                               {path + ".attempt", attempt},
                                               {path + ".attempted_at", bson_date()}}},
                                             {"$inc", {{path + ".attempts", 1}}}}},
                                           {"multi", false},
                                           {"upsert", false}}})}});
            if (!number(get(response, "n"))) {
                blocked.insert(blocked_key);
                continue;
            }
            Json selector = {{"_id", id}, {path + ".attempt", attempt}};
            auto checkpoint =
                std::make_shared<Checkpoint>(app.db, selector, path, std::vector<int64_t>{});
            auto target = sender;
            target.destination = destination;
            target.acknowledgement = checkpoint;
            try {
                if (!get(delivery, "text").is_string())
                    throw Error(Kind::Config);
                if (target.send_text(text(delivery, "text"), true, "HTML") != Supply::Sent ||
                    checkpoint->ids().empty())
                    throw Error(Kind::Announcement);
            } catch (...) {
                auto error = safe_error();
                if (!checkpoint->ids().empty())
                    checkpoint->record({});
                else {
                    bool retryable = error.kind == Kind::Rejected ||
                                     error.kind == Kind::Forbidden || error.kind == Kind::RateLimit;
                    app.db.update("settings", selector,
                                  {{"$set",
                                    {{path + ".state", retryable ? "pending" : "uncertain"},
                                     {path + ".last_error_type", error.what()}}}});
                }
                blocked.insert(blocked_key);
            }
            short_sleep();
        }
        auto current = app.db.one("settings", {{"_id", id}});
        if (!current || !get(*current, "deliveries").is_array())
            throw Error(Kind::Database);
        auto &parts = get(*current, "deliveries");
        bool complete = std::all_of(parts.begin(), parts.end(),
                                    [](auto &part) { return text(part, "state") == "sent"; });
        app.db.update("settings", {{"_id", id}},
                      {{"$set", {{"complete", complete}, {"updated_at", bson_date()}}}});
        return complete;
    }

  public:
    Lease lease;
    Anniversary(const App &app, Sender &sender)
        : app(app), sender(sender), lease(app.db, "r2t_anniversary_sweep_lock") {}
    void sweep(Json &run, bool &acquired) {
        acquired = lease.acquire();
        if (!acquired) {
            run["status"] = "skipped_overlap";
            return;
        }
        if (lease.previous_owner)
            app.db.update("settings",
                          {{"kind", run_kind},
                           {"owner", *lease.previous_owner},
                           {"status", "running"},
                           {"_id", {{"$ne", get(run, "_id")}}}},
                          {{"$set",
                            {{"status", "interrupted"},
                             {"finished_at", bson_date()},
                             {"errors", Json::array({{{"error_type", "InterruptedSweep"}}})}}}},
                          true);
        auto inventory = this->inventory();
        std::vector<std::string> names;
        for (auto &[channel, date] : inventory.channels)
            names.push_back(channel);
        run["channels"] = inventory.channels.size();
        run["skipped_no_history"] = inventory.skipped;
        run["errors"] = inventory.errors;
        auto today = midnight(get(run, "date"));
        auto current = time_parts(today, true);
        int year = current.tm_year + 1900;
        for (auto &[channel, date] : inventory.channels) {
            lease.renew();
            auto birthday = time_parts(date, true);
            int month = birthday.tm_mon, day = birthday.tm_mday;
            if (month == 1 && day == 29 && !(year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)))
                day = 28;
            int years = current.tm_year - birthday.tm_year;
            if (years > 0 && current.tm_mon == month && current.tm_mday == day) {
                bump(run, "due");
                queue(channel, years, today, names);
            }
        }
        for (auto &event : app.db.find("settings", {{"kind", event_kind}, {"complete", false}})) {
            lease.renew();
            if (!get(event, "channel").is_string())
                throw Error(Kind::Config);
            if (std::find(names.begin(), names.end(), text(event, "channel")) == names.end())
                continue;
            try {
                if (deliver(event))
                    bump(run, "completed");
            } catch (...) {
                push_error(run,
                           {{"event", get(event, "_id")}, {"error_type", safe_error().what()}});
            }
        }
        for (auto &event : app.db.find("settings", {{"kind", event_kind}, {"complete", false}})) {
            bump(run, "pending");
            if (!get(event, "deliveries").is_array())
                throw Error(Kind::Config);
            for (auto &part : get(event, "deliveries")) {
                auto state = text(part, "state");
                if (state == "sending" || state == "uncertain")
                    bump(run, "uncertain_messages");
            }
        }
        run["status"] =
            number(get(run, "pending")) > 0 || !get(run, "errors").empty() ? "partial" : "success";
    }
};
Supply anniversaries(const App &app, Sender &sender) {
    Anniversary service(app, sender);
    auto id = run_kind + ":" + uuid();
    Json run = {{"_id", id},
                {"kind", run_kind},
                {"setting", id},
                {"owner", service.lease.owner},
                {"date", time_format(now(), "%Y-%m-%d", true)},
                {"started_at", bson_date()},
                {"status", "running"},
                {"channels", 0},
                {"due", 0},
                {"completed", 0},
                {"pending", 0},
                {"uncertain_messages", 0},
                {"skipped_no_history", Json::array()},
                {"errors", Json::array()}};
    app.db.insert("settings", {run});
    bool acquired = false;
    std::optional<Error> outcome;
    try {
        service.sweep(run, acquired);
    } catch (...) {
        outcome = safe_error();
        run["status"] = "failed";
        push_error(run, {{"error_type", outcome->what()}});
    }
    run["finished_at"] = bson_date();
    auto values = run;
    values.erase("_id");
    try {
        app.db.update("settings", {{"_id", id}}, {{"$set", values}});
    } catch (...) {
        if (!outcome)
            outcome = safe_error();
    }
    if (acquired)
        try {
            service.lease.release();
        } catch (...) {
            if (!outcome)
                outcome = safe_error();
        }
    if (outcome)
        throw *outcome;
    if (text(run, "status") == "failed" || text(run, "status") == "partial")
        throw Error(Kind::Announcement);
    return Supply::Stop;
}
} // namespace r2t
