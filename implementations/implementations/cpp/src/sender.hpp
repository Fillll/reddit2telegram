#pragma once
#include "database.hpp"
#include "reddit.hpp"
namespace r2t {
inline constexpr uint64_t media_limit = 50 * 1024 * 1024;
struct AckSink {
    virtual ~AckSink() = default;
    virtual void record(const std::vector<int64_t> &ids) = 0;
};
struct Media {
    std::string kind, url;
    std::vector<std::vector<Json>> groups;
};
class Sender {
    void ack(const Json &result) const;
    std::optional<std::string> dash_audio(const std::string &url) const;
    Media imgur(const std::string &url, const std::string &path) const;

  public:
    std::shared_ptr<const Config> config;
    Database db;
    Json destination;
    Http http, media;
    std::shared_ptr<std::counting_semaphore<2>> videos;
    Metrics metrics;
    std::shared_ptr<AckSink> acknowledgement;
    Sender(std::shared_ptr<const Config> config, Database db, Json destination, Metrics metrics,
           std::shared_ptr<std::counting_semaphore<2>> videos);
    std::string channel() const;
    Json api(const std::string &method, Json params = Json::object()) const;
    Supply send_text(const std::string &body, bool preview = false,
                     const std::optional<std::string> &mode = {}) const;
    Supply send_image(const std::string &url, const std::string &body) const;
    Supply send_gif(const std::string &url, const std::string &body) const;
    Supply send_gallery(const std::vector<std::vector<Json>> &groups,
                        const std::string &body) const;
    Supply send_video(const std::string &url, const std::string &body,
                      const std::optional<std::string> &dash = {}) const;
    uint64_t url_size(const std::string &url) const;
    bool was_before(const std::string &url) const;
    bool too_many_errors(const std::string &url) const;
    void mark(const std::string &url, bool sent) const;
    bool duplicate(const std::string &url) const;
    Media classify(const Json &submission) const;
    Supply simple(Json submission, const Json &options, Reddit &reddit) const;
};
std::string html_decode(std::string value);
std::string html_escape(std::string value);
uint64_t clean(const Config &config, const std::optional<std::string> &channel = {});
std::string command_output(const std::vector<std::string> &args);
bool mux(const Path &video, const Path &audio, const Path &output);
} // namespace r2t
