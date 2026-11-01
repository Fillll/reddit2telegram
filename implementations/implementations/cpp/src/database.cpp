#include "database.hpp"
namespace r2t {
Database::Database(const Config &config) {
    auto &db = get(config.values, "db");
    auto host = text(db, "host");
    if (host.find("://") == std::string::npos)
        host = "mongodb://" + host;
    pool = {r2t_db_open(host.c_str()), r2t_db_close};
    name = text(db, "name");
    if (!pool || name.empty())
        throw Error(Kind::Database);
}
Json Database::command(const std::string &key, const Json &value, const Json &fields) const {
    Json command = Json::object();
    command[key] = value;
    for (auto &[k, v] : fields.items())
        command[k] = v;
    int code = 0;
    auto wire = command.dump();
    char *raw = r2t_db_command(pool.get(), name.c_str(), wire.c_str(), &code);
    ScopeExit release([&] {
        if (raw)
            r2t_free(raw);
    });
    if (!raw)
        throw Error(Kind::Database, code);
    auto response = parse(raw);
    if (code)
        throw Error(Kind::Database, code);
    auto &errors = get(response, "writeErrors");
    if (errors.is_array() && !errors.empty())
        throw Error(Kind::Database, static_cast<int>(number(get(errors[0], "code"), -1)));
    auto &concern = get(response, "writeConcernError");
    if (!concern.is_null())
        throw Error(Kind::Database, static_cast<int>(number(get(concern, "code"), -1)));
    return response;
}
std::vector<Json> Database::find(const std::string &collection, const Json &filter,
                                 const Json &sort, int64_t limit, const Json &projection) const {
    Json fields = {{"filter", filter}, {"batchSize", 1000}};
    if (!sort.empty())
        fields["sort"] = sort;
    if (limit > 0)
        fields["limit"] = limit;
    if (!projection.empty())
        fields["projection"] = projection;
    auto response = command("find", collection, fields);
    auto cursor = get(response, "cursor");
    std::vector<Json> docs;
    for (auto &doc : get(cursor, "firstBatch"))
        docs.push_back(doc);
    auto id = integer(get(cursor, "id"));
    while (id) {
        response = command("getMore", {{"$numberLong", std::to_string(id)}},
                           {{"collection", collection}, {"batchSize", 1000}});
        cursor = get(response, "cursor");
        for (auto &doc : get(cursor, "nextBatch"))
            docs.push_back(doc);
        id = integer(get(cursor, "id"));
    }
    return docs;
}
std::optional<Json> Database::one(const std::string &collection, const Json &filter,
                                  const Json &sort) const {
    auto docs = find(collection, filter, sort, 1);
    return docs.empty() ? std::nullopt : std::optional<Json>(docs[0]);
}
int64_t Database::update(const std::string &collection, const Json &filter, const Json &values,
                         bool multi, bool upsert) const {
    return static_cast<int64_t>(number(get(
        command(
            "update", collection,
            {{"updates",
              Json::array({{{"q", filter}, {"u", values}, {"multi", multi}, {"upsert", upsert}}})},
             {"ordered", true}}),
        "nModified")));
}
std::optional<Json> Database::claim(const std::string &collection, const Json &filter,
                                    const Json &update, const Json &sort, const Json &projection,
                                    bool upsert) const {
    Json fields = {{"query", filter}, {"update", update}, {"new", true}, {"upsert", upsert}};
    if (!sort.empty())
        fields["sort"] = sort;
    if (!projection.empty())
        fields["fields"] = projection;
    auto response = command("findAndModify", collection, fields);
    return get(response, "value").is_object() ? std::optional<Json>(response["value"])
                                              : std::nullopt;
}
int64_t Database::insert(const std::string &collection, const std::vector<Json> &docs) const {
    if (docs.empty())
        return 0;
    return static_cast<int64_t>(
        number(get(command("insert", collection, {{"documents", docs}, {"ordered", true}}), "n")));
}
int64_t Database::remove(const std::string &collection, const Json &filter, bool one) const {
    return static_cast<int64_t>(
        number(get(command("delete", collection,
                           {{"deletes", Json::array({{{"q", filter}, {"limit", one ? 1 : 0}}})},
                            {"ordered", true}}),
                   "n")));
}
int64_t Database::count(const std::string &collection, const Json &filter) const {
    return static_cast<int64_t>(
        number(get(command("count", collection, {{"query", filter}}), "n")));
}
} // namespace r2t
