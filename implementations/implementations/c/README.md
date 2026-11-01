# Plain C implementation

This work in progress implements the scheduled application in C17. Application
behavior executes in C; there is no C++/Swift/Rust implementation executable or
Python worker behind this variant. The platform module wraps MongoDB's C driver,
libcurl/OpenSSL, libyaml and Linux APIs. Jansson represents JSON documents.

The initial foundation includes configuration, typed JSON ownership builders,
scope cleanup, credential-safe errors, Unicode text handling, pooled MongoDB
commands preserving BSON IDs/dates, streaming media transport and schema-1
measurement events. Queue/scheduling, posting, channel policies, maintenance,
durable announcements and error reporting remain in progress.
`full_port_complete=false` blocks app execution before reading configuration.

Owned JSON locals use Jansson's documented GCC/Clang `json_auto_t` cleanup;
typed builders consume owned values and require explicit retention of borrowed
nodes. Errors return through ordinary function scopes. No longjmp bypasses
cleanup. The reference ownership documentation is
<https://jansson.readthedocs.io/en/latest/apiref.html#scope-dereferencing>.

Release compilation runs on GitHub Actions with checksum-pinned LLVM 23.1.4,
away from the measured host. Artifacts bundle required libraries with a
transitive runtime search path and record source/compiler/library identity,
literal configuration hashes and executable checksum. Build/metadata checks
make no app requests and are not performance observations.

Keep this draft unmerged during active measurement windows. The complete
source and checked artifact must be reviewed before the single fresh 24-hour
production run. No historical or simulated benchmark input is used.
