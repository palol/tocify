"""Run the test suite via unittest discovery. Entry point for the tocify-test script."""

import sys
import unittest
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    tests_dir = project_root / "tests"
    if not tests_dir.is_dir():
        print(f"Tests directory not found: {tests_dir}", file=sys.stderr)
        sys.exit(1)
    loader = unittest.TestLoader()
    suite = loader.discover(str(tests_dir), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
