#include "maintenance.hpp"
#include <iomanip>
#include <regex>
#include <set>
#include <sstream>
#include <sys/statvfs.h>
namespace r2t {
static std::string fixed(double n, int digits = 3) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(digits) << n;
    return out.str();
}
Supply cleaner(const App &app, Sender &sender) {
    std::optional<double> free;
    for (auto &line : split(read_file("/proc/meminfo"), "\n"))
        if (line.starts_with("MemFree:")) {
            auto v = words(line);
            if (v.size() > 1)
                free = std::stod(v[1]) / 1024.;
        }
    if (!free)
        throw Error(Kind::Io);
    auto removed_bytes = clean(*app.config);
    struct statvfs disk{};
    if (statvfs("/", &disk))
        throw Error(Kind::Io);
    double available = double(disk.f_bavail) * double(disk.f_frsize) / std::pow(1024., 3);
    auto output = command_output({"vnstat", "-m"});
    auto lines = split(output, "\n");
    if (lines.size() < 4)
        throw Error(Kind::Io);
    auto traffic_fields = split(lines[lines.size() - 4], " | ");
    auto estimate_fields = split(lines[lines.size() - 2], "|");
    if (traffic_fields.size() < 2 || estimate_fields.size() < 2)
        throw Error(Kind::Io);
    auto traffic = trim(traffic_fields[traffic_fields.size() - 2]);
    auto estimate = trim(estimate_fields[estimate_fields.size() - 2]);
    auto response = app.db.command(
        "aggregate", "tasks",
        {{"pipeline", Json::array({{{"$group", {{"_id", "$status"}, {"count", {{"$sum", 1}}}}}}})},
         {"cursor", Json::object()}});
    std::map<int, int64_t> counts;
    for (auto &record : get(get(response, "cursor"), "firstBatch"))
        counts[int(number(get(record, "_id")))] = int64_t(number(get(record, "count")));
    auto previous = app.db.one("settings", {{"setting", "tasks-stati"}});
    auto data = previous ? get(*previous, "data") : Json::object();
    if (!data.is_object())
        data = Json::object();
    int64_t cycles = 0;
    for (auto &v : data)
        cycles = std::max(cycles, int64_t(number(get(v, "cycles_cnt"))));
    cycles++;
    auto body = "Free memory: " + fixed(*free) +
                "MB.\nDeleted files: " + fixed(double(removed_bytes) / std::pow(1024., 3)) +
                "GB.\nAvailable disk space: " + fixed(available) +
                "GB.\nCurrent month traffic: " + traffic +
                ".\nCurrent month estimate: " + estimate + ".\nTasks' stati:\n";
    int64_t removed = 0;
    for (auto [status, name] : std::vector<std::pair<int, std::string>>{
             {1, "NEW"}, {2, "IN_PROGRESS"}, {3, "SUCCESS"}, {4, "FAILED"}, {5, "SCHEDULED"}}) {
        auto old = get(data, name);
        auto count = counts[status];
        auto total = int64_t(number(get(old, "amt"))) + count;
        data[name] = {{"amt", total}, {"cycles_cnt", int64_t(number(get(old, "cycles_cnt"))) + 1}};
        body += "  →  " + name + ": " + std::to_string(count) +
                " (avg: " + fixed(double(total) / cycles) + ")\n";
        removed += app.db.remove("tasks", {{"status", status}});
    }
    body += "Deleted tasks: " + std::to_string(removed) +
            ".\nTotal cycles: " + std::to_string(cycles) + ".\n";
    app.db.update("settings", {{"setting", "tasks-stati"}}, {{"$set", {{"data", data}}}}, false,
                  true);
    sender.send_text(body);
    return Supply::Stop;
}
std::vector<std::string> public_channels(const App &app, const Sender &sender) {
    std::map<std::string, double> unique;
    for (auto &module : public_modules(app)) {
        auto [value, subreddit] = identity(app, module);
        if (!value.is_string())
            throw Error(Kind::Config);
        auto channel = text(value);
        if (channel.find('@') == std::string::npos || channel == "@r_channels_test" ||
            channel == "@r_channels")
            continue;
        auto first = sender.db.one("urls", {{"channel", lower(channel)}}, {{"ts", 1}});
        if (!first)
            throw Error(Kind::Config);
        auto date = bson_timestamp(get(*first, "ts"));
        if (!date)
            throw Error(Kind::Config);
        unique[channel] = *date;
    }
    std::vector<std::string> ordered;
    for (auto &[channel, date] : unique)
        ordered.push_back(channel);
    std::stable_sort(ordered.begin(), ordered.end(),
                     [&](auto &a, auto &b) { return unique[a] < unique[b]; });
    return ordered;
}
static double first_members(const App &app, const Json &filter, const Json &sort) {
    for (auto &record : app.db.find("stats", filter, sort, 100))
        if (get(record, "members_cnt").is_number())
            return number(get(record, "members_cnt"));
    throw Error(Kind::Config);
}
Supply weekly(const App &app, Sender &sender) {
    auto channels = public_channels(app, sender);
    std::vector<std::string> newly;
    std::vector<std::pair<double, std::string>> growers;
    auto cutoff = bson_date(now() - 7 * 86400);
    for (auto &channel : channels) {
        Json filter = {{"channel", lower(channel)}};
        auto first = app.db.one("stats", filter, {{"ts", 1}});
        auto latest = app.db.one("stats", filter, {{"ts", -1}});
        if (!first || !latest)
            throw Error(Kind::Config);
        auto a = bson_timestamp(get(*first, "ts")), b = bson_timestamp(get(*latest, "ts"));
        if (!a || !b)
            throw Error(Kind::Config);
        if (std::floor((*b - *a) / 86400) <= 31)
            newly.push_back(channel);
        auto previous = first_members(
            app, {{"channel", lower(channel)}, {"ts", {{"$gte", cutoff}}}}, {{"ts", 1}});
        auto current = first_members(app, filter, {{"ts", -1}});
        if (current - previous >= 10)
            growers.emplace_back(current - previous, channel);
    }
    if (channels.empty())
        throw Error(Kind::Config);
    std::stable_sort(growers.begin(), growers.end(),
                     [](auto &a, auto &b) { return a.first > b.first; });
    auto featured =
        channels[std::uniform_int_distribution<size_t>(0, channels.size() - 1)(random())];
    std::string body = "<b>Weekend news</b>\n\n";
    if (!newly.empty())
        body += "🎉 Welcome to newly active channels: " + join(newly, ", ") + ". 🎈🎈\n\n";
    body += "🏆 Channel of the week: " + featured + ". Join and enjoy!\n\n";
    if (!growers.empty()) {
        std::vector<std::string> top;
        for (size_t i = 0; i < std::min(size_t(3), growers.size()); i++)
            top.push_back(growers[i].second);
        body += "🔥 Hottest channels of the week: " + join(top, ", ") + ".\n\n";
    }
    body += "🙋\nQ: How can I help?\nA: Support us on Patreon and promote your favorite "
            "channels!\n\nQ: How to make similar channels?\nA: Ask at @r_channels or use manual at "
            "https://github.com/Fillll/reddit2telegram.\n\nQ: Where to donate?\nA: Patreon: "
            "https://www.patreon.com/reddit2telegram.";
    sender.send_text(body, false, "HTML");
    pause(2, 2.000001);
    for (size_t i = 0; i < channels.size(); i += 100) {
        std::string page = i ? "" : "⬇️ All active channels:\n";
        std::vector<std::string> entries;
        for (size_t n = i; n < std::min(i + 100, channels.size()); n++) {
            std::ostringstream line;
            line << std::setfill('0') << std::setw(2) << n + 1 << ". " << channels[n];
            entries.push_back(line.str());
        }
        sender.send_text(page + join(entries, "\n"));
        pause(2, 2.000001);
    }
    return Supply::Stop;
}
static const std::string help =
    "Send channel data in one message:\nsubreddit: https://reddit.com/r/example\nchannel: "
    "@example_channel\ntags: #tag1 #tag2 #tag3\n\nOr send it step by step:\n1. subreddit\n2. "
    "channel\n3. tags\n\nCommands:\n/newchannel to restart\n/cancel to clear the current draft";
static std::string normalize(const std::string &input, const std::string &kind) {
    auto value = std::regex_replace(
        trim(input), std::regex("^\\s*" + kind + "\\s*:\\s*", std::regex::icase), "");
    std::regex pattern(kind == "subreddit" ? R"((?:https?://)?(?:www\.)?reddit\.com/r/([^/?#\s]+))"
                                           : R"((?:https?://)?(?:t(?:elegram)?\.me/)([^/?#\s]+))",
                       std::regex::icase);
    std::smatch match;
    if (std::regex_search(value, match, pattern))
        value = match[1].str();
    else
        value = trim(trim(value), "/");
    if (kind == "subreddit" && lower(value).starts_with("r/"))
        value = value.substr(2);
    if (kind == "channel" && value.starts_with("@"))
        value = value.substr(1);
    if (value.empty() || words(value).size() != 1)
        return "";
    return trim(trim(value), "/");
}
static std::string normalize_tags(std::string input) {
    replace_all(input, ",", " ");
    std::set<std::string> seen;
    std::vector<std::string> tags;
    for (auto &part : words(input)) {
        auto tag = part.starts_with("#") ? part : "#" + part;
        if (seen.insert(tag).second)
            tags.push_back(tag);
    }
    return join(tags, " ");
}
static std::optional<Json> complete_request(const std::string &input) {
    std::vector<std::string> lines;
    for (auto &line : split(input, "\n"))
        if (!trim(line).empty())
            lines.push_back(trim(line));
    if (!lines.empty() && (lower(lines[0]) == "/newchannel" || lower(lines[0]) == "/start"))
        lines.erase(lines.begin());
    Json data = Json::object();
    for (auto &line : lines) {
        auto low = lower(line);
        if (low.starts_with("subreddit"))
            data["subreddit"] = normalize(line, "subreddit");
        else if (low.starts_with("channel"))
            data["channel"] = normalize(line, "channel");
        else if (low.starts_with("tags"))
            data["tags"] = normalize_tags(line);
    }
    auto ready = [&] {
        return !text(data, "subreddit").empty() && !text(data, "channel").empty() &&
               !text(data, "tags").empty();
    };
    if (ready())
        return data;
    if (lines.size() == 3) {
        data = {{"subreddit", normalize(lines[0], "subreddit")},
                {"channel", normalize(lines[1], "channel")},
                {"tags", normalize_tags(lines[2])}};
        if (ready())
            return data;
    }
    return {};
}
static void reply(const App &app, const Sender &sender, int64_t user, const std::string &body) {
    app.sender(user, sender.metrics).send_text(body);
}
static void save_channel(const App &app, const Sender &sender, int64_t user, const Json &data) {
    auto channel = text(data, "channel"), subreddit = text(data, "subreddit"),
         tags = text(data, "tags");
    auto existing = app.db.one("channels", {{"submodule", lower(channel)}});
    app.db.update("channels", {{"submodule", lower(channel)}},
                  {{"$set",
                    {{"submodule", lower(channel)},
                     {"channel", "@" + channel},
                     {"subreddit", subreddit},
                     {"tags", tags},
                     {"min_upvotes_limit", nullptr},
                     {"submissions_ranking", "hot"},
                     {"submissions_limit", 100}}}},
                  false, true);
    app.db.remove("settings", {{"setting", "tech_receiver_state:" + std::to_string(user)}}, true);
    reply(app, sender, user,
          std::string(existing ? "Updated" : "Saved") + " channel:\nsubreddit: r/" + subreddit +
              "\nchannel: @" + channel + "\ntags: " + tags);
}
static void process_message(const App &app, const Sender &sender, int64_t user,
                            const std::string &input) {
    Json filter = {{"setting", "tech_receiver_state:" + std::to_string(user)}};
    auto low = lower(trim(input));
    if (low == "/help" || low == "help") {
        reply(app, sender, user, help);
        return;
    }
    if (low == "/cancel" || low == "cancel") {
        app.db.remove("settings", filter, true);
        reply(app, sender, user, "Draft cleared.");
        return;
    }
    if (low == "/newchannel" || low == "/start") {
        app.db.remove("settings", filter, true);
        app.db.update("settings", filter, {{"$set", {{"data", {{"step", "await_subreddit"}}}}}},
                      false, true);
        reply(app, sender, user, "Send subreddit name or Reddit URL.");
        return;
    }
    auto completed = complete_request(input);
    if (completed) {
        save_channel(app, sender, user, *completed);
        return;
    }
    auto previous = app.db.one("settings", filter);
    auto state = previous ? get(*previous, "data") : Json{{"step", "await_subreddit"}};
    auto step = text(state, "step");
    std::string response;
    if (step == "await_subreddit") {
        auto subreddit = normalize(input, "subreddit");
        if (subreddit.empty()) {
            reply(app, sender, user, help);
            return;
        }
        state = {{"step", "await_channel"}, {"subreddit", subreddit}};
        response = "Saved subreddit: r/" + subreddit + "\nNow send channel (@name or t.me link).";
    } else if (step == "await_channel") {
        auto channel = normalize(input, "channel");
        if (channel.empty()) {
            reply(app, sender, user,
                  "Channel is invalid. Send @channel_name or https://t.me/channel_name");
            return;
        }
        state["step"] = "await_tags";
        state["channel"] = channel;
        response = "Saved channel: @" + channel + "\nNow send tags like #tag1 #tag2 #tag3";
    } else if (step == "await_tags") {
        auto tags = normalize_tags(input);
        if (tags.empty()) {
            reply(app, sender, user, "Tags are invalid. Send tags like #tag1 #tag2 #tag3");
            return;
        }
        if (!get(state, "channel").is_string() || !get(state, "subreddit").is_string())
            throw Error(Kind::Config);
        save_channel(app, sender, user,
                     {{"channel", get(state, "channel")},
                      {"subreddit", get(state, "subreddit")},
                      {"tags", tags}});
        return;
    } else {
        app.db.remove("settings", filter, true);
        reply(app, sender, user, help);
        return;
    }
    app.db.update("settings", filter, {{"$set", {{"data", state}}}}, false, true);
    reply(app, sender, user, response);
}
Supply receiver(const App &app, Sender &sender) {
    app.db.command(
        "createIndexes", "settings",
        {{"indexes",
          Json::array({{{"key", {{"setting", 1}}}, {"name", "setting_1"}, {"unique", true}}})}});
    auto record = app.db.one("settings", {{"setting", 1}});
    int64_t last = record ? int64_t(number(get(*record, "last_update"))) : 0;
    if (!record)
        app.db.insert("settings", {{{"setting", 1}, {"last_update", 0}}});
    auto updates = sender.api("getUpdates", {{"offset", last + 1}});
    auto configured = get(get(app.config->values, "telegram"), "papa");
    int64_t papa = configured.is_string() ? std::stoll(text(configured)) : integer(configured);
    if (!updates.is_array())
        throw Error(Kind::Telegram);
    for (auto &update : updates) {
        last = std::max(last, integer(get(update, "update_id")));
        auto &message = get(update, "message");
        auto &id = get(get(message, "chat"), "id");
        auto &body = get(message, "text");
        if (!id.is_number_integer() || !body.is_string())
            continue;
        auto user = integer(id);
        if (user < 0)
            continue;
        sender.api("forwardMessage",
                   {{"chat_id", get(get(app.config->values, "telegram"), "dev_chat")},
                    {"from_chat_id", user},
                    {"message_id", get(message, "message_id")}});
        if (user == papa)
            process_message(app, sender, user, text(body));
    }
    app.db.update("settings", {{"setting", 1}}, {{"$set", {{"last_update", last}}}});
    return Supply::Stop;
}
} // namespace r2t
