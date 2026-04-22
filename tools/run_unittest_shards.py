from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def discover_test_modules(root: Path) -> list[str]:
    modules: list[str] = []
    for path in sorted(root.rglob("test_*.py")):
        if "__pycache__" in path.parts:
            continue
        module_path = path.relative_to(Path.cwd()).with_suffix("")
        modules.append(".".join(module_path.parts))
    return modules


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unittest modules in isolated subprocess shards.")
    parser.add_argument("--root", default="tests", help="Directory that contains unittest modules.")
    parser.add_argument("--verbose", action="store_true", help="Print every spawned unittest command.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"Test root does not exist: {root}", file=sys.stderr)
        return 2

    modules = discover_test_modules(root)
    if not modules:
        print(f"No unittest modules found under {root}", file=sys.stderr)
        return 2

    print(f"Running {len(modules)} unittest shard(s) from {root} using isolated Python subprocesses.")
    for index, module in enumerate(modules, start=1):
        command = [sys.executable, str(Path("tools") / "run_unittest_module.py"), module]
        if args.verbose:
            print(f"[{index}/{len(modules)}] {' '.join(command)}")
        else:
            print(f"[{index}/{len(modules)}] {module}")
        completed = subprocess.run(command, cwd=Path.cwd(), check=False)
        if completed.returncode != 0:
            print(
                f"Unittest shard failed: {module} (exit code {completed.returncode})",
                file=sys.stderr,
            )
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
