#pragma once
#include <nlohmann/json.hpp>
#include <chrono>
#include <algorithm>
#include <cmath>
#include <map>
#include <filesystem>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <random>
#include <semaphore>
#include <string>
#include <vector>
#include "CR2T.h"

namespace r2t {
using Json = nlohmann::ordered_json;
using Path = std::filesystem::path;
enum class Kind { Config, Io, Database, Network, Timeout, Reddit, Telegram,
    Rejected, Forbidden, RateLimit, Lease, Announcement, Media, Template, UnknownTask, IncompletePort };
struct Error : std::exception {
    Kind kind; int code;
    explicit Error(Kind kind, int code=0):kind(kind),code(code){}
    const char *what() const noexcept override;
};
Error safe_error() noexcept;
double now();
const Json &get(const Json &v, const std::string &key);
std::string text(const Json &v);
std::string text(const Json &v, const std::string &key);
double number(const Json &v, double fallback=0);
int64_t integer(const Json &v);
bool truth(const Json &v);
Json parse(const std::string &s);
Json bson_date(double timestamp=now());
std::optional<double> bson_timestamp(const Json &value);
std::string id_string(const Json &v);
std::string lower(std::string value);
std::string trim(const std::string &s, const std::string &chars=" \t\r\n");
std::vector<std::string> split(const std::string &s, const std::string &delimiter);
std::string join(const std::vector<std::string> &parts, const std::string &delimiter);
std::vector<std::string> words(const std::string &s);
void replace_all(std::string &s, const std::string &a, const std::string &b);
std::string read_file(const Path &p);
void log(const std::string &message, bool warning=false);
void pause(double low, double high);
void short_sleep(double coefficient=1);
void long_sleep(double coefficient=1);
std::mt19937_64 &random();
std::string digest(const std::string &value, const std::string &algorithm="SHA256");
std::string uuid();
std::string base64(const std::string &s);
std::string format(const std::string &pattern, const std::map<std::string,std::string> &fields);
std::string human(int64_t value);
std::string time_format(double timestamp, const char *format, bool utc=false);
std::tm time_parts(double timestamp, bool utc=false);
size_t codepoints(const std::string &s);
std::pair<std::string,std::string> unicode_split(const std::string &s, size_t count);
enum class Supply { Sent, Reject, Skip, Stop };
struct Config {
    Json values;
    Path path, app, root;
    explicit Config(const Path &path);
    size_t workers() const;
    size_t max_pending() const;
    size_t batch_size() const;
    Path cron_path() const;
};
struct ScopeExit {
    std::function<void()> fn;
    ~ScopeExit(){ if(fn) fn(); }
    ScopeExit(const ScopeExit&)=delete;
    explicit ScopeExit(std::function<void()> fn):fn(std::move(fn)){}
};
}
