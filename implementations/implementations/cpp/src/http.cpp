#include "http.hpp"
#include <curl/curl.h>
namespace r2t {
Json Response::json() const {
    try {
        return parse(body);
    } catch (...) {
        throw Error(Kind::Network);
    }
}
Http::Http(Metrics m, bool t)
    : handle(r2t_http_open(), r2t_http_close), telegram(t), metrics(std::move(m)) {
    if (!handle)
        throw Error(Kind::Network);
}
Response Http::request(const std::string &method, const std::string &url,
                       const std::map<std::string, std::string> &headers, const std::string &body,
                       const Json &multipart, const Path &output, uint64_t limit,
                       const std::string &algorithm, bool allow_initial_failure) const {
    std::string prefix = telegram ? "telegram" : "http", lines;
    for (auto &[key, value] : headers)
        lines += key + ": " + value + "\n";
    auto spec = multipart.dump();
    auto raw = r2t_http_request(
        handle.get(), method.c_str(), url.c_str(), lines.c_str(), body.data(), body.size(),
        multipart.is_null() ? nullptr : spec.c_str(), output.empty() ? nullptr : output.c_str(),
        limit, telegram ? 30 : (method == "HEAD" ? 3 : 5),
        telegram ? 30 : (method == "HEAD" ? 8 : 20), telegram ? 0 : 1,
        algorithm.empty() ? nullptr : algorithm.c_str());
    metrics.count(prefix + "_request_attempts");
    if (!raw) {
        metrics.count(prefix + "_transport_errors");
        throw Error(Kind::Network);
    }
    ScopeExit release([&] { r2t_response_free(raw); });
    metrics.count(prefix + "_requests", raw->requests);
    if (raw->requests > 1)
        metrics.count(prefix + "_request_attempts", raw->requests - 1);
    metrics.count(prefix + "_http_errors", raw->http_errors);
    metrics.count(prefix + "_rate_limits", raw->rate_limits);
    metrics.count(prefix + "_response_body_bytes", raw->received);
    if (telegram)
        metrics.count("telegram_request_body_bytes", raw->sent);
    if (raw->error && !raw->too_large) {
        metrics.count(prefix + "_transport_errors");
        if (!allow_initial_failure || (raw->status >= 200 && raw->status < 300))
            throw Error(raw->error == 28 || raw->error == 42 ? Kind::Timeout : Kind::Network);
    }
    Response response;
    response.status = static_cast<int>(raw->status);
    response.too_large = raw->too_large;
    response.hash = raw->body_digest ? raw->body_digest : "";
    if (raw->body)
        response.body.assign(reinterpret_cast<char *>(raw->body), raw->length);
    if (raw->headers)
        for (auto &line : split(raw->headers, "\r\n")) {
            auto colon = line.find(':');
            if (colon != std::string::npos)
                response.headers[lower(line.substr(0, colon))] = trim(line.substr(colon + 1));
        }
    return response;
}
bool Http::download(const std::string &url, const Path &output, uint64_t limit) const {
    bool ok = false;
    try {
        auto r = request("GET", url, {}, "", nullptr, output, limit);
        ok = r.ok() && !r.too_large;
    } catch (...) {
    }
    if (!ok) {
        std::error_code error;
        std::filesystem::remove(output, error);
    }
    return ok;
}
std::string Http::metadata(const std::string &url) const {
    auto r = request("GET", url, {}, "", nullptr, {}, 1024 * 1024);
    if (!r.ok() || r.too_large)
        throw Error(Kind::Media);
    return r.body;
}
Json Http::api(const std::string &token, const std::string &method, const Json &params,
               const Path &video) const {
    Response response;
    auto url = "https://api.telegram.org/bot" + token + "/" + method;
    if (video.empty())
        response = request("POST", url, {{"Content-Type", "application/json"}}, params.dump());
    else {
        Json fields = Json::object();
        for (auto &[key, value] : params.items())
            fields[key] = value.is_string() ? text(value) : value.dump();
        response = request("POST", url, {}, "",
                           {{"fields", fields},
                            {"files",
                             {{"video",
                               {{"path", video.string()},
                                {"filename", "video.mp4"},
                                {"content_type", "video/mp4"}}}}}});
    }
    auto body = response.json();
    if (!response.ok() || get(body, "ok") != true) {
        switch (response.status) {
        case 400:
            throw Error(Kind::Rejected);
        case 403:
            throw Error(Kind::Forbidden);
        case 429:
            throw Error(Kind::RateLimit);
        default:
            throw Error(Kind::Telegram);
        }
    }
    auto result = get(body, "result");
    if (method.starts_with("send") || method == "forwardMessage")
        metrics.delivery(result);
    return result;
}
std::string encode(const std::string &s) {
    std::string out;
    for (unsigned char c : s) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
            c == '-' || c == '_' || c == '.' || c == '~')
            out += static_cast<char>(c);
        else {
            out += '%';
            out += "0123456789ABCDEF"[c >> 4];
            out += "0123456789ABCDEF"[c & 15];
        }
    }
    return out;
}
std::string form(const std::map<std::string, std::string> &fields) {
    std::vector<std::string> parts;
    for (auto &[key, value] : fields)
        parts.push_back(encode(key) + "=" + encode(value));
    return join(parts, "&");
}
ParsedURL parse_url(const std::string &value) {
    r2t_init();
    auto url = curl_url();
    if (!url)
        throw Error(Kind::Media);
    ScopeExit release([&] { curl_url_cleanup(url); });
    if (curl_url_set(url, CURLUPART_URL, value.c_str(), 0) != CURLUE_OK)
        throw Error(Kind::Media);
    auto part = [&](CURLUPart which) {
        char *raw = nullptr;
        if (curl_url_get(url, which, &raw, 0) != CURLUE_OK)
            return std::string();
        std::string s(raw);
        curl_free(raw);
        return s;
    };
    return {part(CURLUPART_SCHEME), part(CURLUPART_HOST), part(CURLUPART_PATH),
            part(CURLUPART_QUERY),  part(CURLUPART_USER), part(CURLUPART_PASSWORD),
            part(CURLUPART_PORT)};
}
} // namespace r2t
