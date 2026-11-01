#pragma once
#include "queue.hpp"
namespace r2t {
struct Channel {
    Json destination;
    std::string subreddit;
    std::optional<std::string> ranking;
    size_t limit;
    bool requires_submission;
    Json options;
};
std::vector<std::string> public_modules(const App &app);
std::pair<Json, std::string> identity(const App &app, const std::string &module);
Channel resolve(const App &app, const std::string &module);
Supply maintenance(const App &app, const std::string &module, Sender &sender);
Supply post(const App &app, const std::string &module, const Channel &channel,
            const Json &submission, Sender &sender, Reddit &reddit);
std::optional<std::string> tags(const App &app, const std::string &module);
Supply nice(const App &app, const std::string &module, const Json &submission, Sender &sender,
            Reddit &reddit, const std::string &heading = "", const std::string &ending = "",
            const std::optional<std::string> &channel = {});
} // namespace r2t
