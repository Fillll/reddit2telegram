#include "build_info.hpp"
#include "model.hpp"
#include "queue.hpp"
#include <iostream>
namespace r2t {
inline constexpr bool full_port_complete = false;
}
int main(int argc, char **argv) {
    using namespace r2t;
    try {
        std::vector<std::string> args(argv + 1, argv + argc);
        if (std::find(args.begin(), args.end(), "--describe") != args.end()) {
            r2t_init();
            std::cout << Json({{"language", "cpp"},
                               {"version", build::version},
                               {"compiler", build::compiler},
                               {"source_commit", build::commit},
                               {"full_port_complete", full_port_complete},
                               {"profile", "Release -O3 -DNDEBUG; LTO"},
                               {"standard", "C++23"},
                               {"json_library", "nlohmann/json 3.12.0"},
                               {"mongodb_client", r2t_mongoc_version()},
                               {"http_client", r2t_curl_version()},
                               {"configuration_sha256",
                                {{"local_channels", digest(build::local_channels)},
                                 {"weighted_channel", digest(build::weighted_channel)},
                                 {"milestones", digest(build::milestones)}}}})
                             .dump()
                      << '\n';
            return 0;
        }
        if (std::find(args.begin(), args.end(), "--version") != args.end()) {
            std::cout << "r2t-cpp " << build::version << '\n';
            return 0;
        }
        if (!full_port_complete)
            throw Error(Kind::IncompletePort);
        Path filename = "configs/prod.yml";
        auto option = std::find(args.begin(), args.end(), "--config");
        if (option != args.end() && option + 1 != args.end())
            filename = *(option + 1);
        auto config = std::make_shared<Config>(filename);
        auto arenas = number(get(get(config->values, "pool"), "malloc_arenas"), 4);
        if (!std::isfinite(arenas) || arenas < 1 || arenas > INT32_MAX ||
            std::trunc(arenas) != arenas)
            throw Error(Kind::Config);
        r2t_allocator(static_cast<int>(arenas), 0);
        log("Limited native allocator to " + std::to_string(int(arenas)) + " arenas");
        Reporter reporter(*config);
        auto role = args.empty() ? "consumer" : args[0];
        try {
            App app(config, Database(*config), reporter);
            if (role == "consumer")
                consumer(app);
            else if (role == "scheduler")
                scheduler(app);
            else
                throw Error(Kind::Config);
        } catch (...) {
            reporter.capture(safe_error(), role);
            throw;
        }
        return 0;
    } catch (...) {
        auto error = safe_error();
        log(std::string("r2t-cpp: ") + error.what(), true);
        return 1;
    }
}
