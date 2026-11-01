#include "database.h"
#include <stdlib.h>
#include <string.h>
Database *db_new(const Config *config, Error *error) {
    const json_t *values = get(config->values, "db");
    const char *host = field(values, "host");
    STR(uri) = strstr(host, "://") ? xstrdup(host) : strf("mongodb://%s", host);
    void *pool = r2t_db_open(uri);
    REQUIRE(pool, E_DATABASE, NULL);
    Database *db = xcalloc(1, sizeof(*db));
    db->pool = pool;
    db->name = xstrdup(field(values, "name"));
    if (!*db->name) {
        db_free(db);
        error_set(error, E_CONFIG, 0);
        return NULL;
    }
    return db;
}
void db_free(Database *db) {
    if (db) {
        r2t_db_close(db->pool);
        free(db->name);
        free(db);
    }
}
void auto_db_free(Database **db) {
    db_free(*db);
}
json_t *db_command(const Database *db, const char *command, const json_t *value,
                   const json_t *fields, Error *error) {
    json_auto_t *request = JO(P(command, jr(value))).p;
    const char *key;
    json_t *v;
    json_object_foreach(fields, key, v) jset(request, key, v);
    STR(wire) = dump_json(request);
    int code = 0;
    BSONSTR(raw) = r2t_db_command(db->pool, db->name, wire, &code);
    if (!raw || code) {
        error_set(error, E_DATABASE, code);
        return NULL;
    }
    json_auto_t *response = parse_json(raw, strlen(raw), error);
    TRY(response, NULL);
    json_t *write = json_array_get(get(response, "writeErrors"), 0);
    if (write) {
        error_set(error, E_DATABASE, (int)number(get(write, "code"), -1));
        return NULL;
    }
    json_t *concern = get(response, "writeConcernError");
    if (!json_is_null(concern)) {
        error_set(error, E_DATABASE, (int)number(get(concern, "code"), -1));
        return NULL;
    }
    return jrelease(&response);
}
json_t *db_find(const Database *db, const char *collection, const json_t *filter,
                const json_t *sort, int64_t limit, const json_t *projection, Error *error) {
    json_auto_t *fields = JO(P("filter", filter ? jr(filter) : JO0()), P("batchSize", ji(1000))).p;
    if (json_object_size(sort))
        jset(fields, "sort", sort);
    if (limit > 0)
        json_object_set_new(fields, "limit", ji(limit).p);
    if (json_object_size(projection))
        jset(fields, "projection", projection);
    json_auto_t *name = js(collection).p;
    json_auto_t *response = db_command(db, "find", name, fields, error);
    TRY(response, NULL);
    json_auto_t *out = json_array();
    if (!out)
        abort();
    json_t *cursor = get(response, "cursor");
    json_t *batch = get(cursor, "firstBatch");
    REQUIRE(json_is_array(batch), E_DATABASE, NULL);
    size_t i;
    json_t *doc;
    json_array_foreach(batch, i, doc) jappend(out, doc);
    int64_t id;
    REQUIRE(integer(get(cursor, "id"), &id), E_DATABASE, NULL);
    while (id) {
        STR(value) = strf("%lld", (long long)id);
        json_auto_t *cursor_id = JO(P("$numberLong", js(value))).p;
        json_auto_t *more = JO(P("collection", js(collection)), P("batchSize", ji(1000))).p;
        json_auto_t *next = db_command(db, "getMore", cursor_id, more, error);
        TRY(next, NULL);
        cursor = get(next, "cursor");
        batch = get(cursor, "nextBatch");
        REQUIRE(json_is_array(batch), E_DATABASE, NULL);
        json_array_foreach(batch, i, doc) jappend(out, doc);
        REQUIRE(integer(get(cursor, "id"), &id), E_DATABASE, NULL);
    }
    return jrelease(&out);
}
json_t *db_one(const Database *db, const char *collection, const json_t *filter, const json_t *sort,
               Error *error) {
    json_auto_t *list = db_find(db, collection, filter, sort, 1, NULL, error);
    TRY(list, NULL);
    return json_incref(json_array_get(list, 0));
}
bool db_update(const Database *db, const char *collection, const json_t *filter,
               const json_t *update, bool multi, bool upsert, int64_t *modified, Error *error) {
    json_auto_t *fields = JO(P("updates", JA(JO(P("q", jr(filter)), P("u", jr(update)),
                                                P("multi", jb(multi)), P("upsert", jb(upsert))))),
                             P("ordered", jb(true)))
                              .p;
    json_auto_t *name = js(collection).p;
    json_auto_t *result = db_command(db, "update", name, fields, error);
    TRY(result, false);
    if (modified)
        *modified = (int64_t)number(get(result, "nModified"), 0);
    return true;
}
json_t *db_claim(const Database *db, const char *collection, const json_t *filter,
                 const json_t *update, const json_t *sort, const json_t *projection, bool upsert,
                 Error *error) {
    json_auto_t *fields = JO(P("query", jr(filter)), P("update", jr(update)), P("new", jb(true)),
                             P("upsert", jb(upsert)))
                              .p;
    if (json_object_size(sort))
        jset(fields, "sort", sort);
    if (json_object_size(projection))
        jset(fields, "fields", projection);
    json_auto_t *name = js(collection).p;
    json_auto_t *response = db_command(db, "findAndModify", name, fields, error);
    TRY(response, NULL);
    json_t *value = get(response, "value");
    return json_is_object(value) ? json_incref(value) : NULL;
}
bool db_insert(const Database *db, const char *collection, const json_t *documents, Error *error) {
    if (!json_array_size(documents))
        return true;
    json_auto_t *fields = JO(P("documents", jr(documents)), P("ordered", jb(true))).p;
    json_auto_t *name = js(collection).p;
    json_auto_t *result = db_command(db, "insert", name, fields, error);
    return result != NULL;
}
bool db_delete(const Database *db, const char *collection, const json_t *filter, bool one,
               int64_t *removed, Error *error) {
    json_auto_t *fields = JO(P("deletes", JA(JO(P("q", jr(filter)), P("limit", ji(one ? 1 : 0))))),
                             P("ordered", jb(true)))
                              .p;
    json_auto_t *name = js(collection).p;
    json_auto_t *result = db_command(db, "delete", name, fields, error);
    TRY(result, false);
    if (removed)
        *removed = (int64_t)number(get(result, "n"), 0);
    return true;
}
bool db_count(const Database *db, const char *collection, const json_t *filter, int64_t *count,
              Error *error) {
    json_auto_t *fields = JO(P("query", filter ? jr(filter) : JO0())).p;
    json_auto_t *name = js(collection).p;
    json_auto_t *result = db_command(db, "count", name, fields, error);
    TRY(result, false);
    *count = (int64_t)number(get(result, "n"), 0);
    return true;
}
