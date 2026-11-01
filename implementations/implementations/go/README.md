# Go implementation

This work in progress implements the scheduled application in Go, using the
official MongoDB driver, Go HTTP/TLS and the stable YAML library. It does not
delegate application behavior to Python or another implementation executable.

The completion guard currently blocks application execution before loading
credentials. `--describe` prints build/dependency/literal identity and makes no
app requests. Queue/scheduling, complete media delivery, custom channels,
maintenance and durable announcements remain required before enabling it.

Source formatting and dependency lock generation run locally. Compilation,
vetting and packaging run on GitHub Actions away from the measured process.
The checksum-pinned Go 1.27.3 release uses the default optimizing compiler,
trimpath, no cgo and stripped debug tables. Build receipts include the checked
source, toolchain, dependencies, literal hashes and executable checksum.

Keep the draft unmerged during preceding windows. Source coverage and exact
enabled artifact inspection are required before the single fresh 24-hour live
window. Only actual live observations enter the final image and supporting
summaries in `implementations/benchmarks/results/`.
