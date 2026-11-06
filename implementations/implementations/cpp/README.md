# Native C++ implementation

This implements the scheduled application in C++23. The C
platform module wraps libmongoc/libbson, libcurl/OpenSSL, libyaml and Linux APIs;
all application behavior belongs in C++. No Python worker performs native work.

Source coverage includes pooled MongoDB commands with BSON IDs/dates, configuration,
schema-1 telemetry, streaming media delivery, Reddit acquisition, queue/scheduling,
channel policies, channel intake, cleanup, weekly reporting, subscriber snapshots,
durable milestone/anniversary delivery and credential-safe error reporting.
See PORTING.md for the mapping and review limits. Complete source compilation
and packaging passed; the enabled application must pass an exact-head build
and artifact review before deployment. No C++ live validation has run yet.

Release compilation runs on GitHub Actions, away from the measured host. LLVM
23.1.4 and nlohmann/json 3.12.0 downloads are pinned by SHA-256; runtime library
versions, compiler/source identity, literal configuration hashes and an executable
checksum are recorded with the artifact. Build and `--describe` use no application
credentials or application requests. They are not performance observations.

Keep the draft unmerged during active measurement windows. Live evidence will
come only from one fresh 24-hour production run after the complete source port
and exact build artifact have been reviewed.
