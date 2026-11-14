# Go implementation

Go is the primary application. From the repository root use `./r2t consumer`
and `./r2t scheduler`. Install the verified Native Go build artifact at
`implementations/implementations/go/dist/r2t-go`, or set `R2T_GO_BINARY`.
The launcher uses the existing configuration and schedule under
`reddit2telegram/`. Normal operation needs MongoDB and ffmpeg, without Python
application dependencies.

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

The completed live comparison and separate 48-hour support report are retained
in `implementations/benchmarks/results/`. Receiver failures and held uncertain
anniversary parts are documented there. This launcher change does not migrate
indexes or reset delivery state.
