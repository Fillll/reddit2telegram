#ifndef R2T_C_DATABASE_H
#define R2T_C_DATABASE_H
#include "model.h"
typedef struct {
    void *pool;
    char *name;
} Database;
Database *db_new(const Config *config, Error *error);
void db_free(Database *db);
void auto_db_free(Database **db);
json_t *db_command(const Database *db, const char *command, const json_t *value,
                   const json_t *fields, Error *error);
json_t *db_find(const Database *db, const char *collection, const json_t *filter,
                const json_t *sort, int64_t limit, const json_t *projection, Error *error);
json_t *db_one(const Database *db, const char *collection, const json_t *filter, const json_t *sort,
               Error *error);
bool db_update(const Database *db, const char *collection, const json_t *filter,
               const json_t *update, bool multi, bool upsert, int64_t *modified, Error *error);
json_t *db_claim(const Database *db, const char *collection, const json_t *filter,
                 const json_t *update, const json_t *sort, const json_t *projection, bool upsert,
                 Error *error);
bool db_insert(const Database *db, const char *collection, const json_t *documents, Error *error);
bool db_delete(const Database *db, const char *collection, const json_t *filter, bool one,
               int64_t *removed, Error *error);
bool db_count(const Database *db, const char *collection, const json_t *filter, int64_t *count,
              Error *error);
#endif
