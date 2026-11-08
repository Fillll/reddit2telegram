#ifndef R2T_C_DURABLE_H
#define R2T_C_DURABLE_H
#include "sender.h"
JOwned oldest_date(void);
json_t *identifiers(const json_t *event, const char *key, Error *error);
typedef struct {
    Database *db;
    char *key, *owner, *previous_owner;
} Lease;
Lease lease_new(Database *db, const char *key);
void lease_free(Lease *lease);
bool lease_acquire(Lease *lease, bool *acquired, Error *error);
bool lease_renew(const Lease *lease, Error *error);
bool lease_release(const Lease *lease, Error *error);
typedef struct {
    Database *db;
    json_t *selector, *recorded;
    char *path;
    pthread_mutex_t lock;
} Checkpoint;
Checkpoint *checkpoint_new(Database *db, const json_t *selector, const char *path,
                           const json_t *recorded);
void checkpoint_free(Checkpoint *checkpoint);
void auto_checkpoint_free(Checkpoint **checkpoint);
#define CHECKPOINT(name) Checkpoint *name __attribute__((cleanup(auto_checkpoint_free)))
json_t *checkpoint_ids(Checkpoint *checkpoint);
bool checkpoint_record(void *checkpoint, const json_t *ids, Error *error);
bool update_matched(Database *db, const json_t *selector, const json_t *update, bool *matched,
                    Error *error);
#endif
