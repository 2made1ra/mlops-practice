"""Debug script for exercising the linter, formatter and type checker.

Usage: uv run python scripts/debug_tools.py 1 2 3 10
"""

import sys

from mlops_practice.metrics import mean, median
from mlops_practice.preprocessing import min_max_scale


def summarize(values: list[float], precision: int = 3) -> dict[str, float]:
    """Return basic statistics of ``values`` rounded to ``precision`` digits."""
    return {
        "mean": round(mean(values), precision),
        "median": round(median(values), precision),
    }


def main(argv: list[str]) -> int:
    values = [float(arg) for arg in argv] or [1.0, 2.0, 3.0, 10.0]
    for name, value in summarize(values).items():
        print(f"{name}: {value}")
    print(f"scaled: {min_max_scale(values)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
