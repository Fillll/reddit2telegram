#include "durable.hpp"
namespace r2t {
Json oldest_date() {
    return {{"$date", {{"$numberLong", "-62135596800000"}}}};
}
std::vector<int64_t> identifiers(const Json &event, const std::string &key) {
    auto &values = get(event, key);
    if (!values.is_array())
        throw Error(Kind::Config);
    std::vector<int64_t> ids;
    for (auto &value : values)
        ids.push_back(integer(value));
    return ids;
}
bool Lease::acquire() {
    try {
        db.update("settings", {{"_id", key}},
                  {{"$setOnInsert", {{"setting", key}, {"expires_at", oldest_date()}}}}, false,
                  true);
    } catch (const Error &e) {
        if (e.kind != Kind::Database || e.code != 11000)
            throw;
    }
    auto current = now();
    auto response = db.command(
        "findAndModify", "settings",
        {{"query", {{"_id", key}, {"expires_at", {{"$lte", bson_date(current)}}}}},
         {"update", {{"$set", {{"owner", owner}, {"expires_at", bson_date(current + 7200)}}}}},
         {"new", false}});
    auto &previous = get(response, "value");
    previous_owner = get(previous, "owner").is_string()
                         ? std::optional<std::string>(text(previous, "owner"))
                         : std::nullopt;
    return previous.is_object();
}
void Lease::renew() const {
    auto current = now();
    auto response = db.command(
        "update", "settings",
        {{"updates",
          Json::array(
              {{{"q",
                 {{"_id", key}, {"owner", owner}, {"expires_at", {{"$gt", bson_date(current)}}}}},
                {"u", {{"$set", {{"expires_at", bson_date(current + 7200)}}}}},
                {"multi", false},
                {"upsert", false}}})}});
    if (!number(get(response, "n")))
        throw Error(Kind::Lease);
}
void Lease::release() const {
    db.update("settings", {{"_id", key}, {"owner", owner}},
              {{"$set", {{"expires_at", oldest_date()}}}});
}
std::vector<int64_t> Checkpoint::ids() const {
    std::lock_guard guard(lock);
    return recorded;
}
void Checkpoint::record(const std::vector<int64_t> &ids) {
    std::vector<int64_t> all;
    {
        std::lock_guard guard(lock);
        recorded.insert(recorded.end(), ids.begin(), ids.end());
        all = recorded;
    }
    Json update;
    if (anniversary_path) {
        auto &path = *anniversary_path;
        update = {{"$set",
                   {{path + ".state", "sent"},
                    {path + ".message_ids", all},
                    {path + ".sent_at", bson_date()}}}};
    } else
        update = {{"$addToSet", {{"message_ids", {{"$each", ids}}}}}};
    auto response = db.command(
        "update", "settings",
        {{"updates",
          Json::array({{{"q", selector}, {"u", update}, {"multi", false}, {"upsert", false}}})}});
    if (anniversary_path && !number(get(response, "n")))
        throw Error(Kind::Lease);
}
} // namespace r2t
