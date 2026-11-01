#include "build_info.h"
#include "model.h"
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
    log_info("r2t-c: UnknownTask", true);
    return 1;
}
