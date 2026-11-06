#include "reddit.hpp"
#include <array>
#include <thread>
namespace r2t {
void Reddit::authorize() {
    if (!token.empty() && now() < expiry)
        return;
    const auto &c = get(config.values, "reddit");
    auto response = http.request("POST", "https://www.reddit.com/api/v1/access_token",
                                 {{"User-Agent", text(c, "user_agent")},
                                  {"Authorization", "Basic " + base64(text(c, "client_id") + ":" +
                                                                      text(c, "client_secret"))},
                                  {"Content-Type", "application/x-www-form-urlencoded"}},
                                 form({{"grant_type", "password"},
                                       {"username", text(c, "username")},
                                       {"password", text(c, "password")}}));
    if (!response.ok())
        throw Error(Kind::Reddit);
    auto data = response.json();
    token = text(data, "access_token");
    if (token.empty())
        throw Error(Kind::Reddit);
    expiry = now() + number(get(data, "expires_in"), 3600) - 10;
}
void Reddit::feedback(const Response &r) {
    try {
        auto remaining = std::stod(r.headers.at("x-ratelimit-remaining"));
        auto reset = std::stod(r.headers.at("x-ratelimit-reset"));
        auto used = std::stod(r.headers.at("x-ratelimit-used"));
        next = now() +
               (remaining <= 0
                    ? reset
                    : std::min(reset, std::clamp(reset - (600 - 600 / (remaining + used) * used),
                                                 0., 10.)));
    } catch (...) {
    }
}
Json Reddit::get_page(const std::string &path, std::map<std::string, std::string> fields) {
    fields["raw_json"] = "1";
    for (int attempt = 0; attempt < 3; attempt++) {
        if (attempt > 0)
            pause(attempt == 1 ? 0 : 2, attempt == 1 ? 2 : 4);
        if (next > now())
            std::this_thread::sleep_for(std::chrono::duration<double>(next - now()));
        authorize();
        Response response;
        try {
            response =
                http.request("GET", "https://oauth.reddit.com" + path + "?" + form(fields),
                             {{"User-Agent", text(get(config.values, "reddit"), "user_agent")},
                              {"Authorization", "Bearer " + token}});
        } catch (...) {
            if (attempt == 2)
                throw;
            continue;
        }
        feedback(response);
        auto code = response.status;
        if (code == 401) {
            token.clear();
            expiry = 0;
            if (attempt < 2)
                continue;
        }
        static constexpr std::array retry_codes = {408, 500, 502, 503, 504, 520, 522};
        if (std::find(retry_codes.begin(), retry_codes.end(), code) != retry_codes.end() &&
            attempt < 2)
            continue;
        if (code >= 400)
            throw Error(Kind::Reddit);
        return response.json();
    }
    throw Error(Kind::Reddit);
}
Json Reddit::listing(const std::string &subreddit, const std::string &ranking, size_t limit,
                     const std::optional<std::string> &after) {
    std::map<std::string, std::string> fields = {
        {"limit", std::to_string(std::min(size_t(25), limit))}};
    if (after)
        fields["after"] = *after;
    if (ranking == "top")
        fields["t"] = "all";
    return get_page("/r/" + subreddit + "/" + ranking, fields);
}
Json Reddit::hydrate(const Json &submission) {
    auto id = text(submission, "id");
    if (id.empty())
        throw Error(Kind::Reddit);
    auto response = get_page("/comments/" + id, {{"limit", "2048"}, {"sort", "confidence"}});
    if (!response.is_array() || response.empty())
        throw Error(Kind::Reddit);
    auto children = get(get(response[0], "data"), "children");
    if (!children.is_array() || children.empty() || !get(children[0], "data").is_object())
        throw Error(Kind::Reddit);
    return get(children[0], "data");
}
} // namespace r2t
