"""Build a portable replay bundle; run --help for optional paths and verification."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.delivery.package import main

if __name__ == "__main__":
    main()
