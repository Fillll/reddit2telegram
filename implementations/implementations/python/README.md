# Python implementation

The complete previous Python application is retained in `reddit2telegram/`.
Go is the default application; Python is an explicit alternative alongside
Rust, Swift, C++ and C.

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r implementations/implementations/python/requirements.txt
implementations/implementations/python/run consumer
implementations/implementations/python/run scheduler
```

`R2T_PYTHON` selects a different interpreter. The previously measured Python 3.15
dependency lock remains in `../../benchmarks/configurations/python315-requirements.lock`.
Earlier measurement results remain unchanged.

The launcher sets the application's working directory and passes the shared
`reddit2telegram/configs/prod.yml` path. `--config /absolute/path/prod.yml`
overrides it. Links to the configuration, schedule and temporary directory
preserve relative-path behavior. Channel modules and their legacy tag files
are retained here; the primary application's legacy tags link points here.
Explicit Python launches do not redirect to Go.

Only one consumer should own the live queue. Stop the current consumer before
choosing another implementation. Python tests in the root `tests/` directory
import this location; root requirements remain a compatibility include.
