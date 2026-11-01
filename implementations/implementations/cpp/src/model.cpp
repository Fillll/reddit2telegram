#include "model.hpp"
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <sstream>
#include <thread>
namespace r2t {
const char *Error::what() const noexcept {
    switch (kind) {
    case Kind::Config:
        return "Config";
    case Kind::Io:
        return "Io";
    case Kind::Database:
        return "Database";
    case Kind::Network:
        return "Network";
    case Kind::Timeout:
        return "Timeout";
    case Kind::Reddit:
        return "Reddit";
    case Kind::Telegram:
        return "Telegram";
    case Kind::Rejected:
        return "Rejected";
    case Kind::Forbidden:
        return "Forbidden";
    case Kind::RateLimit:
        return "RateLimit";
    case Kind::Lease:
        return "Lease";
    case Kind::Announcement:
        return "Announcement";
    case Kind::Media:
        return "Media";
    case Kind::Template:
        return "Template";
    case Kind::UnknownTask:
        return "UnknownTask";
    case Kind::IncompletePort:
        return "IncompletePort";
    }
    return "NativeError";
}
Error safe_error() noexcept {
    try {
        throw;
    } catch (const Error &e) {
        return e;
    } catch (const Json::exception &) {
        return Error(Kind::Config);
    } catch (...) {
        return Error(Kind::Io);
    }
}
double now() {
    return std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch())
        .count();
}
const Json &get(const Json &v, const std::string &key) {
    static const Json null = nullptr;
    if (!v.is_object())
        return null;
    auto it = v.find(key);
    return it == v.end() ? null : *it;
}
std::string text(const Json &v) {
    return v.is_string() ? v.get<std::string>() : "";
}
std::string text(const Json &v, const std::string &key) {
    return text(get(v, key));
}
double number(const Json &v, double fallback) {
    if (v.is_number())
        return v.get<double>();
    for (auto key : {"$numberLong", "$numberInt", "$numberDouble"})
        if (get(v, key).is_string())
            try {
                return std::stod(text(v, key));
            } catch (...) {
                return fallback;
            }
    return fallback;
}
int64_t integer(const Json &v) {
    if (v.is_number_integer())
        return v.get<int64_t>();
    if (v.is_number_float()) {
        auto n = v.get<double>();
        if (std::isfinite(n) && std::trunc(n) == n && n >= -9.223372036854775808e18 &&
            n < 9.223372036854775808e18)
            return static_cast<int64_t>(n);
    }
    if (get(v, "$numberLong").is_string())
        try {
            return std::stoll(text(v, "$numberLong"));
        } catch (...) {
        }
    throw Error(Kind::Config);
}
bool truth(const Json &v) {
    if (v.is_null())
        return false;
    if (v.is_boolean())
        return v.get<bool>();
    if (v.is_number())
        return number(v) != 0;
    if (v.is_string())
        return !v.get_ref<const std::string &>().empty();
    return !v.empty();
}
Json parse(const std::string &s) {
    try {
        return Json::parse(s);
    } catch (...) {
        throw Error(Kind::Config);
    }
}
Json bson_date(double stamp) {
    return {{"$date", {{"$numberLong", std::to_string(static_cast<int64_t>(stamp * 1000))}}}};
}
std::optional<double> bson_timestamp(const Json &v) {
    auto &date = get(v, "$date");
    if (date.is_null())
        return {};
    if (date.is_string()) {
        std::tm tm{};
        auto s = text(date);
        char *end = strptime(s.c_str(), "%Y-%m-%dT%H:%M:%S", &tm);
        if (!end)
            return {};
        double seconds = static_cast<double>(timegm(&tm));
        if (*end == '.')
            try {
                seconds += std::stod(std::string("0") + end);
            } catch (...) {
            }
        return seconds;
    }
    return number(date) / 1000.;
}
std::string id_string(const Json &v) {
    if (v.is_string())
        return text(v);
    if (get(v, "$oid").is_string())
        return text(v, "$oid");
    return v.dump();
}
std::string lower(std::string v) {
    for (auto &c : v)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return v;
}
static uint32_t next_codepoint(const std::string &s, size_t &i) {
    auto c = static_cast<unsigned char>(s[i++]);
    if (c < 0x80)
        return c;
    int remaining = (c & 0xe0) == 0xc0 ? 1 : (c & 0xf0) == 0xe0 ? 2 : (c & 0xf8) == 0xf0 ? 3 : 0;
    uint32_t value = c & ((1u << (6 - remaining)) - 1);
    for (int n = 0; n < remaining && i < s.size(); n++) {
        auto b = static_cast<unsigned char>(s[i]);
        if ((b & 0xc0) != 0x80)
            break;
        value = (value << 6) | (b & 63);
        i++;
    }
    return value;
}
static bool whitespace(uint32_t c) {
    return (c >= 9 && c <= 13) || (c >= 0x1c && c <= 0x20) || c == 0x85 || c == 0xa0 ||
           c == 0x1680 || (c >= 0x2000 && c <= 0x200a) || c == 0x2028 || c == 0x2029 ||
           c == 0x202f || c == 0x205f || c == 0x3000;
}
std::string trim(const std::string &s, const std::string &chars) {
    if (chars == " \t\r\n") {
        size_t first = s.size(), last = 0;
        for (size_t i = 0; i < s.size();) {
            auto begin = i;
            auto c = next_codepoint(s, i);
            if (!whitespace(c)) {
                first = std::min(first, begin);
                last = i;
            }
        }
        return first == s.size() ? "" : s.substr(first, last - first);
    }
    auto a = s.find_first_not_of(chars);
    return a == std::string::npos ? "" : s.substr(a, s.find_last_not_of(chars) - a + 1);
}
std::vector<std::string> split(const std::string &s, const std::string &d) {
    std::vector<std::string> out;
    size_t start = 0, end;
    while ((end = s.find(d, start)) != std::string::npos) {
        out.push_back(s.substr(start, end - start));
        start = end + d.size();
    }
    out.push_back(s.substr(start));
    return out;
}
std::string join(const std::vector<std::string> &v, const std::string &d) {
    std::string out;
    bool first = true;
    for (const auto &s : v) {
        if (!first)
            out += d;
        first = false;
        out += s;
    }
    return out;
}
std::vector<std::string> words(const std::string &s) {
    std::vector<std::string> v;
    std::optional<size_t> start;
    for (size_t i = 0; i < s.size();) {
        auto begin = i;
        auto c = next_codepoint(s, i);
        if (whitespace(c)) {
            if (start) {
                v.push_back(s.substr(*start, begin - *start));
                start.reset();
            }
        } else if (!start)
            start = begin;
    }
    if (start)
        v.push_back(s.substr(*start));
    return v;
}
void replace_all(std::string &s, const std::string &a, const std::string &b) {
    size_t p = 0;
    while ((p = s.find(a, p)) != std::string::npos) {
        s.replace(p, a.size(), b);
        p += b.size();
    }
}
std::string read_file(const Path &p) {
    std::ifstream in(p, std::ios::binary);
    if (!in)
        throw Error(Kind::Io);
    std::ostringstream out;
    out << in.rdbuf();
    return out.str();
}
std::tm time_parts(double stamp, bool utc) {
    time_t t = static_cast<time_t>(stamp);
    std::tm result{};
    if (utc)
        gmtime_r(&t, &result);
    else
        localtime_r(&t, &result);
    return result;
}
std::string time_format(double stamp, const char *pattern, bool utc) {
    auto tm = time_parts(stamp, utc);
    char out[160];
    if (!strftime(out, sizeof(out), pattern, &tm))
        throw Error(Kind::Config);
    return out;
}
void log(const std::string &s, bool warning) {
    static std::mutex mutex;
    std::lock_guard guard(mutex);
    std::cerr << time_format(now(), "%Y-%m-%d %H:%M:%S") << " - r2t.cpp - "
              << (warning ? "WARNING" : "INFO") << " - " << s << '\n';
}
std::mt19937_64 &random() {
    thread_local std::mt19937_64 gen(std::random_device{}());
    return gen;
}
void pause(double low, double high) {
    std::this_thread::sleep_for(
        std::chrono::duration<double>(std::uniform_real_distribution<double>(low, high)(random())));
}
void short_sleep(double c) {
    pause(2 * c, 4 * c);
}
void long_sleep(double c) {
    pause(8 * c, 20 * c);
}
std::string digest(const std::string &s, const std::string &algorithm) {
    char *p = r2t_digest(algorithm.c_str(), s.data(), s.size());
    if (!p)
        throw Error(Kind::Io);
    std::string out(p);
    r2t_free(p);
    return out;
}
std::string uuid() {
    unsigned char bytes[16];
    if (RAND_bytes(bytes, 16) != 1)
        throw Error(Kind::Io);
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    std::string s;
    for (auto b : bytes) {
        s += "0123456789abcdef"[b >> 4];
        s += "0123456789abcdef"[b & 15];
    }
    return s;
}
std::string base64(const std::string &s) {
    std::string out(4 * ((s.size() + 2) / 3) + 1, '\0');
    auto n = EVP_EncodeBlock(reinterpret_cast<unsigned char *>(out.data()),
                             reinterpret_cast<const unsigned char *>(s.data()),
                             static_cast<int>(s.size()));
    if (n < 0)
        throw Error(Kind::Io);
    out.resize(n);
    return out;
}
std::string format(const std::string &p, const std::map<std::string, std::string> &f) {
    std::string out;
    for (size_t i = 0; i < p.size();) {
        char c = p[i++];
        if (c == '{' || c == '}') {
            if (i < p.size() && p[i] == c) {
                out += c;
                i++;
                continue;
            }
            if (c == '}')
                throw Error(Kind::Template);
            auto end = p.find('}', i);
            if (end == std::string::npos)
                throw Error(Kind::Template);
            auto it = f.find(p.substr(i, end - i));
            if (it == f.end())
                throw Error(Kind::Template);
            out += it->second;
            i = end + 1;
        } else
            out += c;
    }
    return out;
}
std::string human(int64_t n) {
    if (n > -1000 && n < 1000)
        return std::to_string(n);
    double value = n;
    int i = 0;
    while (std::abs(value) >= 1000 && i < 5) {
        i++;
        value = std::nearbyint(value / 100) / 10.;
    }
    std::ostringstream out;
    out << std::fixed << std::setprecision(1) << value
        << std::vector<std::string>{"", "k", "M", "G", "T", "P"}[i];
    return out.str();
}
size_t codepoints(const std::string &s) {
    return std::count_if(s.begin(), s.end(), [](unsigned char c) { return (c & 0xc0) != 0x80; });
}
std::pair<std::string, std::string> unicode_split(const std::string &s, size_t n) {
    size_t i = 0, count = 0;
    for (; i < s.size(); i++) {
        if ((static_cast<unsigned char>(s[i]) & 0xc0) != 0x80) {
            if (count == n)
                break;
            count++;
        }
    }
    return {s.substr(0, i), s.substr(i)};
}
Config::Config(const Path &p) {
    path = std::filesystem::canonical(p);
    app = path.parent_path().parent_path();
    root = app.parent_path();
    char *raw = r2t_yaml_json(path.c_str());
    if (!raw)
        throw Error(Kind::Config);
    ScopeExit release([&] { r2t_free(raw); });
    values = get(parse(raw), "value");
}
size_t Config::workers() const {
    return static_cast<size_t>(number(get(get(values, "pool"), "size"),
                                      std::max(1u, std::thread::hardware_concurrency())));
}
size_t Config::max_pending() const {
    return static_cast<size_t>(number(get(get(values, "consumer"), "max_pending"), workers()));
}
size_t Config::batch_size() const {
    return static_cast<size_t>(number(get(get(values, "consumer"), "batch_size"), workers() * 2));
}
Path Config::cron_path() const {
    Path p = text(values, "cron_file");
    return p.is_absolute() ? p : app / p;
}
} // namespace r2t
