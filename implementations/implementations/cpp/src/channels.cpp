#include "channels.hpp"
#include "build_info.hpp"
#include "maintenance.hpp"
#include <set>
namespace r2t {
static std::recursive_mutex cache_lock;
static std::optional<std::string> cached_weighted, cached_promotion;
std::vector<std::string> public_modules(const App &app) {
    std::set<std::string> unique;
    for (auto &[mask, module] : schedules(*app.config))
        if (!module.starts_with("tech_"))
            unique.insert(module);
    return {unique.begin(), unique.end()};
}
static std::string weighted() {
    std::lock_guard guard(cache_lock);
    if (cached_weighted)
        return *cached_weighted;
    auto data = parse(build::weighted_channel);
    auto &weights = get(data, "weights");
    double total = 0;
    for (auto &weight : weights)
        total += number(weight);
    if (total <= 0)
        throw Error(Kind::Config);
    double draw = std::uniform_real_distribution<double>(0, total)(random());
    for (auto &[name, weight] : weights.items()) {
        if (draw < number(weight)) {
            cached_weighted = name;
            return name;
        }
        draw -= number(weight);
    }
    throw Error(Kind::Config);
}
std::pair<Json, std::string> identity(const App &app, const std::string &module) {
    if (module == "r_porn")
        return {"@r_porn", weighted()};
    if (module == "reddit2telegram")
        return {"@reddit2telegram", ""};
    auto record = app.db.one("channels", {{"submodule", lower(module)}});
    if (record)
        return {get(*record, "channel"), text(*record, "subreddit")};
    auto local = parse(build::local_channels);
    auto &channel = get(local, module);
    if (!channel.is_object())
        throw Error(Kind::Config);
    return {get(channel, "t_channel"), text(channel, "subreddit")};
}
static void update_order(const App &app) {
    Json order = Json::object();
    for (auto &module : public_modules(app)) {
        if (module == "reddit2telegram")
            continue;
        auto [handle, subreddit] = identity(app, module);
        if (!handle.is_string())
            throw Error(Kind::Config);
        auto first = app.db.one("view_with_first_dates", {{"_id", lower(text(handle))}});
        if (first && !get(*first, "first_date").is_null())
            order[module] = get(*first, "first_date");
    }
    app.db.update("settings", {{"setting", "r2t_promotion_queue"}},
                  {{"$setOnInsert", {{"already_promoted", Json::array()}, {"counter", 0}}},
                   {"$set", {{"promotion_order", order}}}},
                  false, true);
}
static std::string promotion_target(const App &app) {
    std::lock_guard guard(cache_lock);
    if (cached_promotion)
        return *cached_promotion;
    auto all = public_modules(app);
    std::erase(all, "reddit2telegram");
    if (all.empty())
        throw Error(Kind::Config);
    if (time_parts(now()).tm_wday == 0) {
        cached_promotion = all[std::uniform_int_distribution<size_t>(0, all.size() - 1)(random())];
        return *cached_promotion;
    }
    auto record = app.db.one("settings", {{"setting", "r2t_promotion_queue"}});
    if (!record) {
        update_order(app);
        record = app.db.one("settings", {{"setting", "r2t_promotion_queue"}});
    }
    if (!record)
        throw Error(Kind::Database);
    auto promoted = get(*record, "already_promoted");
    auto order = get(*record, "promotion_order");
    if (!promoted.is_array() || !order.is_object())
        throw Error(Kind::Config);
    std::vector<std::string> candidates;
    for (auto &[module, date] : order.items())
        candidates.push_back(module);
    std::stable_sort(candidates.begin(), candidates.end(), [&](auto &a, auto &b) {
        return bson_timestamp(get(order, a)).value_or(0) >
               bson_timestamp(get(order, b)).value_or(0);
    });
    for (auto &name : candidates)
        if (std::find(all.begin(), all.end(), name) != all.end() &&
            std::find(promoted.begin(), promoted.end(), Json(name)) == promoted.end()) {
            cached_promotion = name;
            return name;
        }
    app.db.update("settings", {{"setting", "r2t_promotion_queue"}},
                  {{"$inc", {{"counter", 1}}}, {"$set", {{"already_promoted", Json::array()}}}});
    throw Error(Kind::Config);
}
Channel resolve(const App &app, const std::string &module) {
    if (module == "r_porn") {
        auto subreddit = weighted();
        auto data = parse(build::weighted_channel);
        Json options = {{"check_dups", true},
                        {"min_upvotes_limit", get(get(data, "limits"), subreddit)}};
        for (auto kind : {"text", "other", "album", "gif", "img", "video", "gallery"}) {
            std::string prefix = std::string(kind) == "text" ? "{title}\n\n{self_text}"
                                 : (std::string(kind) == "other" || std::string(kind) == "album")
                                     ? "{title}\n{link}"
                                     : "{title}";
            options[kind] = prefix + "\n\n{upvotes} upvotes\n/r/{subreddit_name} → "
                                     "#{subreddit_name}\n{short_link}\n{channel}";
        }
        return {"@r_porn", subreddit, {}, 100, true, options};
    }
    if (module == "reddit2telegram") {
        auto [channel, subreddit] = identity(app, promotion_target(app));
        return {"@reddit2telegram", subreddit, "top", 1000, true, Json::object()};
    }
    if (module.starts_with("tech_")) {
        Json destination;
        if (module == "tech_receiver")
            destination = "@r_channels";
        else if (module == "tech_weekly_radar")
            destination = "@reddit2telegram";
        else if (module == "tech_cleaner" || module == "tech_anniversary" ||
                 module == "tech_store_stat")
            destination = get(get(app.config->values, "telegram"), "dev_chat");
        else
            throw Error(Kind::Config);
        return {destination,
                "all",
                {},
                100,
                module != "tech_anniversary" && module != "tech_store_stat",
                Json::object()};
    }
    auto db_record = app.db.one("channels", {{"submodule", lower(module)}});
    Json record;
    if (db_record)
        record = *db_record;
    else {
        auto local = parse(build::local_channels);
        auto &v = get(local, module);
        if (!v.is_object())
            throw Error(Kind::Config);
        record = {{"channel", get(v, "t_channel")},
                  {"subreddit", get(v, "subreddit")},
                  {"submissions_ranking", get(v, "submissions_ranking")},
                  {"submissions_limit",
                   v.contains("submissions_limit") ? get(v, "submissions_limit") : Json(100)}};
    }
    Json options = {{"min_upvotes_limit", get(record, "min_upvotes_limit")}};
    for (auto kind : {"text", "gif", "video", "img", "album", "gallery", "other"})
        options[kind] = get(record, "content").is_null() ? Json(true)
                                                         : (get(record, "content").contains(kind)
                                                                ? get(get(record, "content"), kind)
                                                                : Json(false));
    std::optional<std::string> ranking;
    if (get(record, "submissions_ranking").is_string()) {
        auto r = text(record, "submissions_ranking");
        ranking = r == "hot" || r == "new" || r == "top" ? r : "hot";
    }
    auto limit = get(record, "submissions_limit");
    return {get(record, "channel"),
            text(record, "subreddit"),
            ranking,
            limit.is_number_integer() ? static_cast<size_t>(integer(limit)) : SIZE_MAX,
            true,
            options};
}
std::optional<std::string> tags(const App &app, const std::string &module) {
    auto record = app.db.one("channels", {{"submodule", lower(module)}});
    if (record && !text(*record, "tags").empty())
        return text(*record, "tags");
    auto path = app.config->app / "channels" / module / "tags.txt";
    if (!std::filesystem::exists(path))
        return {};
    return read_file(path);
}
Supply nice(const App &app, const std::string &module, const Json &submission, Sender &sender,
            Reddit &reddit, const std::string &heading, const std::string &ending,
            const std::optional<std::string> &channel) {
    auto destination = channel ? Json(*channel) : identity(app, module).first;
    if (!destination.is_string() || !get(submission, "created_utc").is_number())
        throw Error(Kind::Config);
    Json options = {{"channel_to_promote", destination},
                    {"date", time_format(number(get(submission, "created_utc")), "%Y %b %d", true)},
                    {"tags", join(words(tags(app, module).value_or("")), " ")},
                    {"extra_ending", ending},
                    {"announcement_heading", heading}};
    for (auto kind : {"text", "other", "album", "gif", "img", "video", "gallery"}) {
        std::string prefix = std::string(kind) == "text"
                                 ? "{announcement_heading}{title}\n\n{self_text}"
                             : (std::string(kind) == "other" || std::string(kind) == "album")
                                 ? "{announcement_heading}{title}\n{link}"
                                 : "{announcement_heading}{title}";
        options[kind] = prefix +
                        "\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby "
                        "{channel_to_promote}\n{tags}\n\n{extra_ending}";
    }
    return sender.simple(submission, options, reddit);
}
static Supply promotion(const App &app, const Json &submission, Sender &sender, Reddit &reddit) {
    auto current = now();
    auto tm = time_parts(current);
    int weekday = (tm.tm_wday + 6) % 7;
    if (weekday == 5 && (tm.tm_hour == 0 || tm.tm_hour == 23) && tm.tm_min == 1) {
        update_order(app);
        return Supply::Stop;
    }
    if (weekday == 5)
        return Supply::Stop;
    auto hash = digest(time_format(current, "%Y %b %d"), "SHA1");
    int hour = 0;
    for (size_t i = 0; i < hash.size(); i += 2)
        hour = (hour * 256 + std::stoi(hash.substr(i, 2), nullptr, 16)) % 24;
    if (tm.tm_hour != hour)
        return Supply::Stop;
    auto target = promotion_target(app);
    auto result = nice(app, target, submission, sender, reddit);
    if (result == Supply::Sent && weekday < 5)
        app.db.update("settings", {{"setting", "r2t_promotion_queue"}},
                      {{"$push", {{"already_promoted", target}}}});
    return result;
}
Supply maintenance(const App &app, const std::string &module, Sender &sender) {
    if (module == "tech_cleaner")
        return cleaner(app, sender);
    if (module == "tech_receiver")
        return receiver(app, sender);
    if (module == "tech_weekly_radar")
        return weekly(app, sender);
    throw Error(Kind::IncompletePort);
}
Supply post(const App &app, const std::string &module, const Channel &channel,
            const Json &submission, Sender &sender, Reddit &reddit) {
    if (module == "reddit2telegram")
        return promotion(app, submission, sender, reddit);
    if (module.starts_with("tech_"))
        return maintenance(app, module, sender);
    return sender.simple(submission, channel.options, reddit);
}
} // namespace r2t
