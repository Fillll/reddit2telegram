# Language implementations

Go is the default production implementation, launched by `../../r2t` from this
directory, or `./r2t` from the repository root. Install its verified build artifact
at `go/dist/r2t-go`, or provide `R2T_GO_BINARY`.

The complete Python application and dependency requirements live in `python/`,
alongside Rust, Swift, C++ and C. Choose it explicitly with `python/run consumer`
or `python/run scheduler`. Configuration, schedule and MongoDB records are shared;
only one consumer should run at a time.

Each implementation must
implement the complete live workload and the shared benchmark event contract.
See `../benchmarks/README.md` for the experiment requirements.
