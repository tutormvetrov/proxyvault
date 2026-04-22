from __future__ import annotations

import argparse
import importlib
import os
import sys
import unittest
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    parser = argparse.ArgumentParser(description="Run a single unittest module and exit without interpreter teardown.")
    parser.add_argument("module", help="Dotted unittest module path, for example tests.test_i18n")
    args = parser.parse_args()

    module = importlib.import_module(args.module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if result.wasSuccessful() else 1)
    return 0


if __name__ == "__main__":
    main()
