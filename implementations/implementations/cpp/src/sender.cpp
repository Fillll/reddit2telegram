#include "sender.hpp"
#include <numbers>
#include <regex>
namespace r2t {
static std::string regex_escape(const std::string &s) {
    return std::regex_replace(s, std::regex(R"([.^$|()\[\]{}*+?\\])"), R"(\$&)");
}
std::string html_escape(std::string v) {
    replace_all(v, "&", "&amp;");
    replace_all(v, "<", "&lt;");
    replace_all(v, ">", "&gt;");
    replace_all(v, "\"", "&quot;");
    replace_all(v, "'", "&#x27;");
    return v;
}
static std::string utf8(uint32_t n) {
    std::string s;
    if (n < 0x80)
        s += char(n);
    else if (n < 0x800) {
        s += char(0xc0 | (n >> 6));
        s += char(0x80 | (n & 63));
    } else if (n < 0x10000) {
        s += char(0xe0 | (n >> 12));
        s += char(0x80 | ((n >> 6) & 63));
        s += char(0x80 | (n & 63));
    } else if (n <= 0x10ffff) {
        s += char(0xf0 | (n >> 18));
        s += char(0x80 | ((n >> 12) & 63));
        s += char(0x80 | ((n >> 6) & 63));
        s += char(0x80 | (n & 63));
    }
    return s;
}
std::string html_decode(std::string value) {
    static const std::regex numeric("&#(x[0-9a-fA-F]+|[0-9]+);");
    std::vector<std::smatch> matches;
    for (std::sregex_iterator i(value.begin(), value.end(), numeric), end; i != end; ++i)
        matches.push_back(*i);
    for (auto i = matches.rbegin(); i != matches.rend(); ++i) {
        auto s = (*i)[1].str();
        try {
            auto n = std::stoul(s.starts_with("x") ? s.substr(1) : s, nullptr,
                                s.starts_with("x") ? 16 : 10);
            if (n <= 0x10ffff && !(n >= 0xd800 && n <= 0xdfff))
                value.replace(i->position(), i->length(), utf8(n));
        } catch (...) {
        }
    }
    for (auto [a, b] : std::vector<std::pair<std::string, std::string>>{{"&quot;", "\""},
                                                                        {"&apos;", "'"},
                                                                        {"&lt;", "<"},
                                                                        {"&gt;", ">"},
                                                                        {"&nbsp;", "\xc2\xa0"},
                                                                        {"&amp;", "&"}})
        replace_all(value, a, b);
    return value;
}
static std::pair<std::string, std::string> split_message(const std::string &body) {
    auto words = split(body, " ");
    if (codepoints(words[0]) > 4096)
        return unicode_split(body, 4096);
    size_t size = 0, take = 0;
    for (auto &word : words) {
        auto n = codepoints(word);
        if (size + take + n > 4096)
            break;
        size += n;
        take++;
    }
    return {join({words.begin(), words.begin() + take}, " "),
            join({words.begin() + take, words.end()}, " ")};
}
static std::pair<std::string, std::string> split_caption(const std::string &body) {
    if (codepoints(body) <= 1024)
        return {body, ""};
    auto plain = body;
    replace_all(plain, "\n", " ");
    auto words = split(plain, " ");
    std::string caption, tail;
    bool switched = false;
    for (auto &word : words)
        if (!switched && codepoints(caption) + codepoints(word) + 1 < 1020)
            caption += word + " ";
        else {
            switched = true;
            tail += " " + word;
        }
    return {caption + " ...", "... " + tail};
}
Sender::Sender(std::shared_ptr<const Config> c, Database d, Json to, Metrics m,
               std::shared_ptr<std::counting_semaphore<2>> v)
    : config(std::move(c)), db(std::move(d)), destination(std::move(to)), http(m, true), media(m),
      videos(std::move(v)), metrics(std::move(m)) {
    short_sleep();
}
std::string Sender::channel() const {
    return destination.is_string() ? text(destination) : destination.dump();
}
Json Sender::api(const std::string &method, Json params) const {
    if (get(params, "chat_id").is_null() &&
        (method.starts_with("send") || method == "getChatMemberCount" ||
         method == "getChatAdministrators"))
        params["chat_id"] = destination;
    auto result = http.api(text(get(config->values, "telegram"), "token"), method, params);
    if (method.starts_with("send") || method == "forwardMessage")
        ack(result);
    return result;
}
void Sender::ack(const Json &result) const {
    if (!acknowledgement)
        return;
    std::vector<int64_t> ids;
    auto messages = result.is_array() ? result : Json::array({result});
    for (auto &message : messages)
        if (get(message, "message_id").is_number_integer())
            ids.push_back(integer(get(message, "message_id")));
    acknowledgement->record(ids);
}
Supply Sender::send_text(const std::string &body, bool preview,
                         const std::optional<std::string> &mode) const {
    auto remaining = body;
    bool split = codepoints(body) >= 4096;
    while (true) {
        auto [part, next] =
            split ? split_message(remaining) : std::pair<std::string, std::string>(remaining, "");
        Json params = {{"text", part}, {"disable_web_page_preview", preview}};
        if (mode)
            params["parse_mode"] = *mode;
        api("sendMessage", params);
        if (split)
            short_sleep();
        if (next.empty())
            break;
        remaining = next;
    }
    return Supply::Sent;
}
Supply Sender::send_image(const std::string &url, const std::string &body) const {
    if (codepoints(body) > 1024) {
        log("Long pic in " + channel() + ".");
        return send_text("<a href=\"" + url + "\">&#160;</a>" + body, false, "HTML");
    }
    try {
        api("sendPhoto", {{"photo", url}, {"caption", body}});
        return Supply::Sent;
    } catch (const Error &e) {
        switch (e.kind) {
        case Kind::Rejected:
        case Kind::Telegram:
        case Kind::Network:
        case Kind::Timeout:
        case Kind::Forbidden:
        case Kind::RateLimit:
            return Supply::Skip;
        default:
            throw;
        }
    }
}
Supply Sender::send_gif(const std::string &url, const std::string &body) const {
    if (url_size(url) > media_limit) {
        log("Too big.");
        return Supply::Reject;
    }
    auto [caption, tail] = split_caption(body);
    try {
        api("sendDocument", {{"document", url}, {"caption", caption}});
    } catch (const Error &e) {
        if (e.kind == Kind::Rejected)
            return Supply::Skip;
        throw;
    }
    if (codepoints(tail) > 1) {
        short_sleep();
        send_text(tail, true);
    }
    return Supply::Sent;
}
Supply Sender::send_gallery(const std::vector<std::vector<Json>> &groups,
                            const std::string &body) const {
    send_text(body);
    long_sleep();
    for (size_t i = 0; i < groups.size(); i++) {
        try {
            api("sendMediaGroup", {{"media", groups[i]}});
            log("Successful gallery sent.");
        } catch (...) {
            log(std::string("Gallery sent failed: ") + safe_error().what(), true);
        }
        long_sleep(i + 2);
    }
    return Supply::Sent;
}
Supply Sender::send_video(const std::string &url, const std::string &body,
                          const std::optional<std::string> &dash) const {
    videos->acquire();
    ScopeExit release([&] { videos->release(); });
    auto folder = config->app / "tmp" / ("r2t-" + uuid());
    std::filesystem::create_directories(folder);
    ScopeExit cleanup([&] {
        std::error_code e;
        std::filesystem::remove_all(folder, e);
    });
    auto video = folder / "media.mp4";
    if (!media.download(url, video, media_limit))
        return Supply::Reject;
    auto send = video;
    auto audio_url = dash ? dash_audio(*dash) : std::nullopt;
    auto slash = url.rfind('/');
    auto audio = folder / "media.mp4.aac";
    if (media.download(audio_url.value_or(url.substr(0, slash) + "/DASH_AUDIO_128.mp4"), audio,
                       media_limit)) {
        auto muxed = folder / "media.1.mp4";
        if (mux(video, audio, muxed))
            send = muxed;
    }
    auto bytes = std::filesystem::file_size(send);
    if (bytes == 0 || bytes > media_limit)
        return Supply::Reject;
    auto [caption, tail] = split_caption(body);
    auto result = http.api(text(get(config->values, "telegram"), "token"), "sendVideo",
                           {{"chat_id", destination}, {"caption", caption}}, send);
    ack(result);
    if (codepoints(tail) > 1) {
        short_sleep();
        send_text(tail, true);
    }
    return Supply::Sent;
}
std::optional<std::string> Sender::dash_audio(const std::string &url) const {
    try {
        auto body = media.metadata(url);
        static const std::regex base("<BaseURL>([^<]+)</BaseURL>");
        std::string audio;
        for (std::sregex_iterator i(body.begin(), body.end(), base), end; i != end; ++i) {
            auto item = (*i)[1].str();
            if (lower(item).find("audio") != std::string::npos)
                audio = item;
        }
        auto path = url.find("DASHPlaylist.mpd");
        if (audio.empty() || path == std::string::npos)
            return {};
        auto query = url.find('?');
        return url.substr(0, path) + audio + (query == std::string::npos ? "" : url.substr(query));
    } catch (...) {
        return {};
    }
}
uint64_t Sender::url_size(const std::string &url) const {
    try {
        auto r = media.request("HEAD", url);
        return std::stoull(r.headers.at("content-length"));
    } catch (...) {
        return 0;
    }
}
bool Sender::was_before(const std::string &url) const {
    auto id = split(url, "/").back();
    for (auto &filter : std::vector<Json>{
             {{"channel", lower(channel())}, {"url_id", id}},
             {{"channel", lower(channel())}, {"url", lower(url)}},
             {{"channel", lower(channel())}, {"url", {{"$regex", regex_escape(id)}}}}})
        if (!db.find("urls", filter, Json::object(), 1, {{"_id", 1}}).empty()) {
            metrics.count("previously_seen_candidates");
            return true;
        }
    return false;
}
bool Sender::too_many_errors(const std::string &url) const {
    auto error = db.one("errors", {{"channel", lower(channel())}, {"url", lower(url)}});
    return error && number(get(*error, "cnt")) >= 2;
}
void Sender::mark(const std::string &url, bool sent) const {
    db.insert("urls", {{{"url_id", split(url, "/").back()},
                        {"url", lower(url)},
                        {"ts", bson_date()},
                        {"channel", lower(channel())},
                        {"sent", sent}}});
    metrics.post(channel(), url, sent);
}
bool Sender::duplicate(const std::string &url) const {
    auto r = media.request("GET", url, {}, "", nullptr, {}, media_limit, "MD5", true);
    if (!r.ok() || r.too_large || r.hash.empty())
        return false;
    auto result =
        db.command("findAndModify", "contents",
                   {{"query", {{"channel", lower(channel())}, {"md5_sum", r.hash}}},
                    {"update",
                     {{"$setOnInsert",
                       {{"channel", lower(channel())}, {"md5_sum", r.hash}, {"ts", bson_date()}}}}},
                    {"upsert", true},
                    {"new", false}});
    bool seen = get(result, "value").is_object();
    if (seen) {
        log("Duplicated found!");
        metrics.count("duplicate_media_candidates");
    }
    return seen;
}
Media Sender::classify(const Json &s) const {
    auto url = text(s, "url");
    auto parsed = parse_url(url);
    auto host = parsed.host;
    auto low = lower(url);
    auto &items = get(get(s, "gallery_data"), "items");
    if (items.is_array()) {
        bool numeric = std::all_of(items.begin(), items.end(),
                                   [](auto &v) { return get(v, "id").is_number_integer(); });
        bool strings = std::all_of(items.begin(), items.end(),
                                   [](auto &v) { return get(v, "id").is_string(); });
        if (!numeric && !strings)
            throw Error(Kind::Media);
        std::map<std::string, Json> last;
        for (auto &item : items)
            last[id_string(get(item, "id"))] = item;
        std::vector<Json> ordered;
        for (auto &[key, item] : last)
            ordered.push_back(item);
        std::sort(ordered.begin(), ordered.end(), [&](auto &a, auto &b) {
            return numeric ? integer(get(a, "id")) < integer(get(b, "id"))
                           : text(a, "id") < text(b, "id");
        });
        std::vector<Json> group;
        std::vector<std::vector<Json>> groups;
        for (auto &item : ordered) {
            auto &source = get(get(get(s, "media_metadata"), text(item, "media_id")), "s");
            auto photo = get(source, "u").is_string();
            auto link = html_decode(text(source, photo ? "u" : "mp4"));
            if (link.empty())
                throw Error(Kind::Media);
            try {
                auto p = parse_url(link);
                if (p.host == "preview.redd.it")
                    link = "https://i.redd.it" + p.path;
                else
                    replace_all(link, "auto=webp", "auto=jpg");
            } catch (...) {
                replace_all(link, "auto=webp", "auto=jpg");
            }
            group.push_back({{"type", photo ? "photo" : "video"}, {"media", link}});
            if (group.size() == 10) {
                groups.push_back(group);
                group.clear();
            }
        }
        if (!group.empty())
            groups.push_back(group);
        return {"gallery", "", groups};
    }
    Json video = truth(get(s, "is_video")) ? get(get(s, "media"), "reddit_video") : Json(nullptr);
    if (video.is_null()) {
        auto &cross = get(s, "crosspost_parent_list");
        if (cross.is_array() && !cross.empty() && truth(get(cross[0], "is_video")))
            video = get(get(cross[0], "media"), "reddit_video");
    }
    if (!video.is_null())
        return {truth(get(video, "is_gif")) ? "gif" : "video", text(video, "fallback_url"), {}};
    if (truth(get(s, "is_self")))
        return {"text", "", {}};
    auto image = [&] {
        return low.ends_with(".jpg") || low.ends_with(".jpeg") || low.ends_with(".png");
    };
    if (host == "i.redd.it" && image())
        return {"img", url, {}};
    if (host == "i.imgur.com" || host == "i.stack.imgur.com") {
        if (low.ends_with(".gifv"))
            return {"gif", url.substr(0, url.size() - 5) + ".mp4", {}};
        if (low.ends_with(".gif") || low.ends_with(".mp4"))
            return {"gif", url, {}};
        if (image())
            return {"img", url, {}};
    }
    auto mime = [&](const std::string &u) {
        try {
            return media.request("HEAD", u).headers["content-type"];
        } catch (...) {
            return std::string();
        }
    };
    auto type = mime(url);
    if (type == "image/jpeg" || type == "image/png")
        return {"img", url, {}};
    if (type.find("image/gif") != std::string::npos) {
        if (url.ends_with(".gif")) {
            auto mp4 = url.substr(0, url.size() - 4) + ".mp4";
            if (mime(mp4) == "video/mp4")
                return {"gif", mp4, {}};
        }
        return {"gif", url, {}};
    }
    if (url.ends_with(".gifv")) {
        auto mp4 = url.substr(0, url.size() - 5) + ".mp4";
        if (mime(mp4) == "video/mp4")
            return {"gif", mp4, {}};
        auto gif = url.substr(0, url.size() - 1);
        if (mime(gif) == "image/gif")
            return {"gif", gif, {}};
    }
    if (host == "imgur.com" || host == "www.imgur.com" || host == "m.imgur.com")
        return imgur(url, parsed.path);
    if (host.find("gfycat.com") != std::string::npos) {
        auto parts = split(trim(parsed.path, "/"), "/");
        auto name = parts[0] == "detail" ? (parts.size() > 1 ? parts[1] : "") : parts[0];
        try {
            auto data = parse(media.metadata("https://api.gfycat.com/v1/gfycats/" + name));
            auto link = get(get(data, "gfyItem"), "mp4Url");
            if (link.is_string())
                return {"gif", text(link), {}};
        } catch (...) {
        }
    }
    return {"other", url, {}};
}
Media Sender::imgur(const std::string &url, const std::string &path) const {
    auto cfg = get(config->values, "imgur");
    if (cfg.is_null())
        try {
            cfg = Config(config->app / "configs/imgur.yml").values;
        } catch (...) {
        }
    if (cfg.is_null())
        return {"other", url, {}};
    auto parts = split(trim(path, "/"), "/");
    if (parts.empty() || parts[0].empty() || parts[0] == "topic")
        return {"other", url, {}};
    bool album = parts[0] == "a" || parts[0] == "gallery";
    auto identifier = album ? (parts.size() > 1 ? parts[1] : "") : parts.back();
    auto id = split(identifier, ".")[0];
    auto image = [](const Json &v) {
        bool animated = truth(get(v, "animated"));
        auto link = text(v, "link");
        if (animated) {
            if (!text(v, "mp4").empty())
                link = text(v, "mp4");
            else if (!text(v, "gifv").empty())
                link = text(v, "gifv");
        }
        if (link.ends_with(".gifv"))
            link.pop_back();
        return Json{{"type", animated ? "video" : "photo"}, {"media", link}};
    };
    for (auto &endpoint :
         album ? std::vector<std::string>{"album", "image"} : std::vector<std::string>{"image"}) {
        if (endpoint == "image" && parts[0] == "a")
            break;
        try {
            auto data = media
                            .request("GET", "https://api.imgur.com/3/" + endpoint + "/" + id,
                                     {{"Authorization", "Client-ID " + text(cfg, "client_id")}})
                            .json();
            if (get(data, "success") != true)
                continue;
            auto &info = get(data, "data");
            auto &images = get(info, "images");
            if (images.is_array()) {
                std::vector<std::vector<Json>> groups;
                std::vector<Json> group;
                for (auto &v : images) {
                    group.push_back(image(v));
                    if (group.size() == 10) {
                        groups.push_back(group);
                        group.clear();
                    }
                }
                if (!group.empty())
                    groups.push_back(group);
                return {"album", url, groups};
            }
            return {truth(get(info, "animated")) ? "gif" : "img", text(image(info), "media"), {}};
        } catch (...) {
        }
    }
    return {"other", url, {}};
}
Supply Sender::simple(Json submission, const Json &options, Reddit &reddit) const {
    if (get(options, "min_upvotes_limit").is_number() && get(submission, "score").is_null())
        submission = reddit.hydrate(submission);
    if (get(options, "min_upvotes_limit").is_number() &&
        number(get(submission, "score")) < number(get(options, "min_upvotes_limit")))
        return Supply::Skip;
    bool missing = !submission.contains("url") || !submission.contains("is_self") ||
                   (truth(get(submission, "is_gallery")) && !submission.contains("gallery_data")) ||
                   (get(get(submission, "gallery_data"), "items").is_array() &&
                    !submission.contains("media_metadata")) ||
                   (truth(get(submission, "is_video")) && !submission.contains("media"));
    Media info;
    try {
        if (missing)
            submission = reddit.hydrate(submission);
        info = classify(submission);
    } catch (...) {
        log("HTTP fail prevented at " + channel());
        return Supply::Skip;
    }
    for (auto key : {"title", "selftext", "score", "subreddit", "over_18"})
        if (!submission.contains(key)) {
            submission = reddit.hydrate(submission);
            break;
        }
    auto score = static_cast<int64_t>(number(get(submission, "score")));
    if ((!options.contains("nsfw_filter_out") || truth(get(options, "nsfw_filter_out"))) &&
        get(submission, "over_18") == true)
        return Supply::Reject;
    if (get(options, "check_dups") == true && !info.url.empty() && duplicate(info.url))
        return Supply::Reject;
    auto rule = options.contains(info.kind) ? get(options, info.kind) : Json(true);
    if (!truth(rule))
        return Supply::Reject;
    std::map<std::string, std::string> fields = {
        {"what", info.kind},
        {"url", info.url},
        {"title", text(submission, "title")},
        {"self_text", text(submission, "selftext")},
        {"link", text(submission, "url")},
        {"short_link", "https://redd.it/" + text(submission, "id")},
        {"subreddit_name", text(submission, "subreddit")},
        {"score", std::to_string(score)},
        {"upvotes", human(score)},
        {"channel", channel()}};
    for (auto &[key, value] : options.items())
        fields[key] = value.is_string() ? text(value) : value.dump();
    std::string fallback;
    if (info.kind == "text")
        fallback = "{title}\n\n{self_text}\n\n{short_link}\n{channel}";
    else if (info.kind == "video" || info.kind == "gallery")
        fallback = "{title}\n\n{short_link}\n{channel}";
    else if (info.kind == "album" || info.kind == "other")
        fallback = "{title}\n{link}\n\n{short_link}\n{channel}";
    else
        fallback = "{title}\n{short_link}\n{channel}";
    auto pattern = rule.is_string() ? text(rule) : fallback;
    if (info.kind == "text") {
        if (get(options, "max_selftext_len").is_number_unsigned() ||
            get(options, "max_selftext_len").is_number_integer())
            fields["self_text"] =
                unicode_split(text(submission, "selftext"),
                              static_cast<size_t>(number(get(options, "max_selftext_len"))))
                    .first +
                "...";
        bool preview = truth(get(options, "disable_web_page_preview"));
        auto markdown = pattern;
        replace_all(markdown, "{short_link}", "[{short_link}]({short_link})");
        replace_all(markdown, "{channel}", "[{channel}]({channel})");
        try {
            return send_text(format(markdown, fields), preview, "Markdown");
        } catch (const Error &e) {
            if (e.kind != Kind::Rejected)
                throw;
            log("Markdown fail in " + channel() + "; sending as plain text.");
            return send_text(format(pattern, fields), preview);
        }
    }
    auto body = format(pattern, fields);
    if (info.kind == "img")
        return send_image(info.url, body);
    if (info.kind == "gif")
        return send_gif(info.url, body);
    if (info.kind == "video") {
        auto dash = get(get(get(submission, "media"), "reddit_video"), "dash_url");
        return send_video(info.url, body,
                          dash.is_string() ? std::optional<std::string>(text(dash)) : std::nullopt);
    }
    if (info.kind == "gallery" || info.kind == "album")
        return send_gallery(info.groups, body);
    return send_text(body);
}
uint64_t clean(const Config &config, const std::optional<std::string> &channel) {
    long_sleep(1 / (std::numbers::pi * std::numbers::e));
    uint64_t removed = 0;
    for (auto &entry : std::filesystem::directory_iterator(config.app / "tmp")) {
        if (!entry.is_regular_file() || entry.path().filename() == "empty.md")
            continue;
        auto name = entry.path().filename().string();
        if (channel && name.find(channel->empty() ? "" : channel->substr(1)) == std::string::npos)
            continue;
        auto bytes = entry.file_size();
        std::error_code e;
        if (std::filesystem::remove(entry.path(), e))
            removed += bytes;
    }
    return removed;
}
} // namespace r2t
