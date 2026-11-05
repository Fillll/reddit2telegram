#pragma once
#include "http.hpp"
namespace r2t {
class Reddit {
    Config config;
    std::string token;
    double expiry = 0, next = 0;
    void authorize();
    void feedback(const Response &response);

  public:
    Http http;
    Reddit(Config config, Metrics metrics) : config(std::move(config)), http(std::move(metrics)) {}
    Json get_page(const std::string &path, std::map<std::string, std::string> fields = {});
    Json listing(const std::string &subreddit, const std::string &ranking, size_t limit,
                 const std::optional<std::string> &after);
    Json hydrate(const Json &submission);
};
} // namespace r2t
