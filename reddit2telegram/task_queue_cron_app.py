"""Compatibility entry point; scheduling defaults to Go."""
import os
from pathlib import Path
import sys

if __name__ == '__main__':
    launcher = Path(__file__).resolve().parents[1] / 'r2t'
    os.execv(str(launcher), [str(launcher), 'scheduler', *sys.argv[1:]])
