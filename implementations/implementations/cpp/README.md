# Native C++ implementation

This work in progress implements the scheduled application in C++23. The C
platform module wraps libmongoc/libbson, libcurl/OpenSSL, libyaml and Linux APIs;
all application behavior belongs in C++. No Python worker performs native work.

Foundations include pooled MongoDB commands with BSON IDs/dates, configuration,
credential-safe errors, schema-1 telemetry, streaming media transport and Reddit
OAuth/listings/hydration. Queue, posting, channel policies and full maintenance
and durable-announcement behavior remain in progress. `full_port_complete=false`
blocks execution before reading application configuration or accessing its queue.

Release compilation runs on GitHub Actions, away from the measured host. LLVM
23.1.4 and nlohmann/json 3.12.0 downloads are pinned by SHA-256; runtime library
versions, compiler/source identity, literal configuration hashes and an executable
checksum are recorded with the artifact. Build and `--describe` use no application
credentials or application requests. They are not performance observations.

Keep the draft unmerged during active measurement windows. Live evidence will
come only from one fresh 24-hour production run after the complete source port
and exact build artifact have been reviewed.
