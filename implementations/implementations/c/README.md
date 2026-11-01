# Plain C implementation

This implementation ports the scheduled application to C17. Application
behavior executes in C; there is no C++/Swift/Rust implementation executable or
Python worker behind this variant. The platform module wraps MongoDB's C driver,
libcurl/OpenSSL, libyaml and Linux APIs. Jansson represents JSON documents.

The complete scheduled source includes queue/scheduling, normal and custom
channel rules, streaming media, maintenance, durable milestones and
anniversaries, safe reporting and schema-1 measurement events. See
[PORTING.md](PORTING.md) for source coverage and live validation limits.

The native executable accepts `consumer --config /absolute/path/prod.yml` or
`scheduler --config /absolute/path/prod.yml`. `--describe` prints source,
compiler, library and literal-configuration identity without reading app
credentials or making app requests. It is not a benchmark.

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

Keep this draft unmerged during preceding measurement windows. The complete
source and exact checked artifact must be reviewed before the single fresh 24-hour
production run. No historical or simulated benchmark input is used.
