"""Compatibility entry point for installed services; the application is Go."""
import os
from pathlib import Path
import sys

if __name__ == '__main__':
    launcher = Path(__file__).resolve().parents[1] / 'r2t'
    os.execv(str(launcher), [str(launcher), 'consumer', *sys.argv[1:]])
