#!/bin/sh
# Use within an activated virtualenv, or set PYTHON=/path/to/python.
set -eu
runner="${PYTHON:-python3}"
if [ "$(uname -s)" = "Darwin" ]; then
  omp_dir="$($runner -c 'import importlib.util,pathlib; s=importlib.util.find_spec("torch"); print(pathlib.Path(s.origin).parent/"lib" if s else "")')"
  if [ -n "$omp_dir" ]; then
    export DYLD_LIBRARY_PATH="$omp_dir${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
  fi
fi
exec "$runner" "$@"
