#pragma once
#include "sender.hpp"
namespace r2t {
Json oldest_date();
std::vector<int64_t> identifiers(const Json &event, const std::string &key);
class Lease {
  public:
    Database db;
    std::string key, owner = uuid();
    std::optional<std::string> previous_owner;
    Lease(Database db, std::string key) : db(std::move(db)), key(std::move(key)) {}
    bool acquire();
    void renew() const;
    void release() const;
};
class Checkpoint : public AckSink {
    Database db;
    Json selector;
    std::optional<std::string> anniversary_path;
    mutable std::mutex lock;
    std::vector<int64_t> recorded;

  public:
    Checkpoint(Database db, Json selector, std::optional<std::string> path,
               std::vector<int64_t> ids)
        : db(std::move(db)), selector(std::move(selector)), anniversary_path(std::move(path)),
          recorded(std::move(ids)) {}
    std::vector<int64_t> ids() const;
    void record(const std::vector<int64_t> &ids) override;
};
} // namespace r2t
