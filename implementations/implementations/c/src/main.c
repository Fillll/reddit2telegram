#include "app.h"
#include "build_info.h"
#include "model.h"
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static const bool full_port_complete = false;
int main(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--describe")) {
            r2t_init();
            STR(local) = digest_text(R2T_LOCAL_CHANNELS, "SHA256");
            STR(weighted) = digest_text(R2T_WEIGHTED_CHANNEL, "SHA256");
            STR(milestones) = digest_text(R2T_MILESTONES, "SHA256");
            json_auto_t *meta =
                JO(P("language", js("c")), P("version", js(R2T_VERSION)),
                   P("source_commit", js(R2T_COMMIT)), P("compiler", js(R2T_COMPILER)),
                   P("standard", js("C17 with GCC/Clang scope cleanup")),
                   P("profile", js("Release O3 NDEBUG thin LTO")),
                   P("full_port_complete", jb(full_port_complete)),
                   P("json_library", js(jansson_version_str())),
                   P("mongodb_client", js(r2t_mongoc_version())),
                   P("http_client", js(r2t_curl_version())),
                   P("configuration_sha256",
                     JO(P("local_channels", js(local)), P("weighted_channel", js(weighted)),
                        P("milestones", js(milestones)))))
                    .p;
            STR(output) = dump_json(meta);
            puts(output);
            return 0;
        }
        if (!strcmp(argv[i], "--version")) {
            printf("r2t-c %s\n", R2T_VERSION);
            return 0;
        }
    }
    if (!full_port_complete) {
        log_info("r2t-c: IncompletePort", true);
        return 1;
    }
    const char *filename = "configs/prod.yml";
    for (int i = 1; i + 1 < argc; i++)
        if (!strcmp(argv[i], "--config"))
            filename = argv[i + 1];
    const char *role = argc > 1 ? argv[1] : "consumer";
    Error error = {0};
    Config *config __attribute__((cleanup(auto_config_free))) = config_load(filename, &error);
    if (!config)
        goto fail;
    double arenas = number(get(get(config->values, "pool"), "malloc_arenas"), 4);
    if (!isfinite(arenas) || arenas < 1 || arenas > INT_MAX || trunc(arenas) != arenas) {
        error_set(&error, E_CONFIG, 0);
        goto fail;
    }
    r2t_allocator((int)arenas, 0);
    {
        STR(message) = strf("Limited native allocator to %d arenas", (int)arenas);
        log_info(message, false);
    }
    Reporter *reporter = reporter_new(config, &error);
    if (!reporter)
        goto fail;
    Database *db = db_new(config, &error);
    bool okay = false;
    if (db) {
        sem_t videos;
        if (sem_init(&videos, 0, 2))
            error_set(&error, E_IO, 0);
        else {
            App app = {config, db, &videos, reporter};
            if (!strcmp(role, "consumer"))
                okay = consumer_run(&app, &error);
            else if (!strcmp(role, "scheduler"))
                okay = scheduler_run(&app, &error);
            else
                error_set(&error, E_CONFIG, 0);
            sem_destroy(&videos);
        }
        db_free(db);
    }
    if (!okay)
        reporter_capture(reporter, error, role);
    reporter_free(reporter);
    if (okay)
        return 0;
fail:
    {
        STR(message) = strf("r2t-c: %s", error_name(error));
        log_info(message, true);
    }
    return 1;
}
