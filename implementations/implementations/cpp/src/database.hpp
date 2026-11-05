#pragma once
#include "model.hpp"
namespace r2t {
class Database {
    std::shared_ptr<void> pool;
    std::string name;

  public:
    explicit Database(const Config &config);
    Json command(const std::string &command, const Json &value,
                 const Json &fields = Json::object()) const;
    std::vector<Json> find(const std::string &collection, const Json &filter = Json::object(),
                           const Json &sort = Json::object(), int64_t limit = 0,
                           const Json &projection = Json::object()) const;
    std::optional<Json> one(const std::string &collection, const Json &filter = Json::object(),
                            const Json &sort = Json::object()) const;
    int64_t update(const std::string &collection, const Json &filter, const Json &update,
                   bool multi = false, bool upsert = false) const;
    std::optional<Json> claim(const std::string &collection, const Json &filter, const Json &update,
                              const Json &sort = Json::object(),
                              const Json &projection = Json::object(), bool upsert = false) const;
    int64_t insert(const std::string &collection, const std::vector<Json> &documents) const;
    int64_t remove(const std::string &collection, const Json &filter, bool one = false) const;
    int64_t count(const std::string &collection, const Json &filter = Json::object()) const;
};
} // namespace r2t
