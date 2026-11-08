# Go implementation

This implementation ports the complete scheduled application to Go, using the
official MongoDB driver, Go HTTP/TLS and the stable YAML library. It does not
delegate application behavior to Python or another implementation executable.

It includes queue/scheduling, media delivery, custom channels, maintenance,
subscriber statistics and durable milestone/anniversary announcements. See
[PORTING.md](PORTING.md) for source coverage and the limits of source/build
verification.

The executable accepts `consumer --config /absolute/path/prod.yml` or
`scheduler --config /absolute/path/prod.yml`. `--describe` prints
build/dependency/literal identity and makes no app requests.

Source formatting and dependency lock generation run locally. Compilation,
vetting and packaging run on GitHub Actions away from the measured process.
The checksum-pinned Go 1.27.3 release uses the default optimizing compiler,
trimpath, no cgo and stripped debug tables. Build receipts include the checked
source, toolchain, dependencies, literal hashes and executable checksum.

Keep the draft unmerged during preceding windows. Review the exact checked
head and inspect the enabled artifact before the single fresh 24-hour live
window. Only actual live observations enter the final image and supporting
summaries in `implementations/benchmarks/results/`.
