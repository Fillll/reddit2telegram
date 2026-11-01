#include "durable.h"
#include <stdlib.h>
JOwned oldest_date(void) {
    return JO(P("$date", JO(P("$numberLong", js("-62135596800000")))));
}
json_t *identifiers(const json_t *event, const char *key, Error *error) {
    json_t *values = get(event, key);
    REQUIRE(json_is_array(values), E_CONFIG, NULL);
    size_t i;
    json_t *value;
    json_array_foreach(values, i, value) {
        int64_t id;
        REQUIRE(integer(value, &id), E_CONFIG, NULL);
    }
    return json_deep_copy(values);
}
Lease lease_new(Database *db, const char *key) {
    return (Lease){db, xstrdup(key), uuid_text(), NULL};
}
void lease_free(Lease *lease) {
    free(lease->key);
    free(lease->owner);
    free(lease->previous_owner);
}
bool update_matched(Database *db, const json_t *selector, const json_t *update, bool *matched,
                    Error *error) {
    json_auto_t *collection = js("settings").p;
    json_auto_t *fields = JO(P("updates", JA(JO(P("q", jr(selector)), P("u", jr(update)),
                                                P("multi", jb(false)), P("upsert", jb(false))))))
                              .p;
    json_auto_t *response = db_command(db, "update", collection, fields, error);
    TRY(response, false);
    *matched = number(get(response, "n"), 0) != 0;
    return true;
}
bool lease_acquire(Lease *lease, bool *acquired, Error *error) {
    json_auto_t *filter = JO(P("_id", js(lease->key))).p;
    json_auto_t *initial =
        JO(P("$setOnInsert", JO(P("setting", js(lease->key)), P("expires_at", oldest_date())))).p;
    Error local = {0};
    if (!db_update(lease->db, "settings", filter, initial, false, true, NULL, &local) &&
        (local.kind != E_DATABASE || local.code != 11000)) {
        *error = local;
        return false;
    }
    double current = now();
    json_auto_t *collection = js("settings").p;
    json_auto_t *fields =
        JO(P("query", JO(P("_id", js(lease->key)), P("expires_at", JO(P("$lte", jdate(current)))))),
           P("update", JO(P("$set", JO(P("owner", js(lease->owner)),
                                       P("expires_at", jdate(current + 7200)))))),
           P("new", jb(false)))
            .p;
    json_auto_t *response = db_command(lease->db, "findAndModify", collection, fields, error);
    TRY(response, false);
    json_t *previous = get(response, "value");
    free(lease->previous_owner);
    lease->previous_owner =
        json_is_string(get(previous, "owner")) ? xstrdup(field(previous, "owner")) : NULL;
    *acquired = json_is_object(previous);
    return true;
}
bool lease_renew(const Lease *lease, Error *error) {
    double current = now();
    json_auto_t *filter = JO(P("_id", js(lease->key)), P("owner", js(lease->owner)),
                             P("expires_at", JO(P("$gt", jdate(current)))))
                              .p;
    json_auto_t *update = JO(P("$set", JO(P("expires_at", jdate(current + 7200))))).p;
    bool matched;
    TRY(update_matched(lease->db, filter, update, &matched, error), false);
    REQUIRE(matched, E_LEASE, false);
    return true;
}
bool lease_release(const Lease *lease, Error *error) {
    json_auto_t *filter = JO(P("_id", js(lease->key)), P("owner", js(lease->owner))).p;
    json_auto_t *update = JO(P("$set", JO(P("expires_at", oldest_date())))).p;
    return db_update(lease->db, "settings", filter, update, false, false, NULL, error);
}
Checkpoint *checkpoint_new(Database *db, const json_t *selector, const char *path,
                           const json_t *recorded) {
    Checkpoint *checkpoint = xcalloc(1, sizeof(*checkpoint));
    checkpoint->db = db;
    checkpoint->selector = json_deep_copy(selector);
    checkpoint->recorded = recorded ? json_deep_copy(recorded) : json_array();
    checkpoint->path = path ? xstrdup(path) : NULL;
    pthread_mutex_init(&checkpoint->lock, NULL);
    return checkpoint;
}
void checkpoint_free(Checkpoint *checkpoint) {
    if (!checkpoint)
        return;
    json_decref(checkpoint->selector);
    json_decref(checkpoint->recorded);
    free(checkpoint->path);
    pthread_mutex_destroy(&checkpoint->lock);
    free(checkpoint);
}
void auto_checkpoint_free(Checkpoint **checkpoint) {
    checkpoint_free(*checkpoint);
}
json_t *checkpoint_ids(Checkpoint *checkpoint) {
    pthread_mutex_lock(&checkpoint->lock);
    json_t *result = json_deep_copy(checkpoint->recorded);
    pthread_mutex_unlock(&checkpoint->lock);
    return result;
}
bool checkpoint_record(void *data, const json_t *ids, Error *error) {
    Checkpoint *checkpoint = data;
    REQUIRE(json_is_array(ids), E_CONFIG, false);
    pthread_mutex_lock(&checkpoint->lock);
    size_t i;
    json_t *value;
    json_array_foreach(ids, i, value) jappend(checkpoint->recorded, value);
    json_auto_t *all = json_deep_copy(checkpoint->recorded);
    pthread_mutex_unlock(&checkpoint->lock);
    json_auto_t *update = NULL;
    if (checkpoint->path) {
        STR(state) = strf("%s.state", checkpoint->path);
        STR(messages) = strf("%s.message_ids", checkpoint->path);
        STR(sent) = strf("%s.sent_at", checkpoint->path);
        update =
            JO(P("$set", JO(P(state, js("sent")), P(messages, jr(all)), P(sent, jdate(now()))))).p;
    } else {
        update = JO(P("$addToSet", JO(P("message_ids", JO(P("$each", jr(ids))))))).p;
    }
    bool matched;
    TRY(update_matched(checkpoint->db, checkpoint->selector, update, &matched, error), false);
    REQUIRE(!checkpoint->path || matched, E_LEASE, false);
    return true;
}
