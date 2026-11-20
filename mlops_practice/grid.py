"""Run a baseline and a Cartesian hyperparameter grid in individual training containers."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from copy import deepcopy
from itertools import product
import json
from pathlib import Path
import re
import subprocess
from typing import Any
from uuid import uuid4


def read_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return config


def override(config: dict[str, Any], key: str, value: object) -> None:
    parts = key.split(".")
    target = config
    for part in parts[:-1]:
        target = target[part]
    if parts[-1] not in target:
        raise ValueError(f"Unknown grid parameter {key!r}")
    target[parts[-1]] = value


def runs(path: Path, series: str) -> Iterator[dict[str, Any]]:
    spec = read_config(path)
    baseline = read_config(path.parent / spec["baseline"])
    base = read_config(path.parent / spec["base"])
    grid = spec["grid"]
    if not isinstance(grid, dict) or not grid:
        raise ValueError("grid must be a nonempty mapping of dotted keys to lists")
    for key, values in grid.items():
        if not isinstance(values, list) or not values:
            raise ValueError(f"Expected at least one value for {key}")
    baseline["run_name"] += f"-{series}"
    yield baseline
    for number, values in enumerate(product(*grid.values()), start=1):
        config = deepcopy(base)
        labels: list[str] = []
        for key, value in zip(grid, values, strict=True):
            override(config, key, value)
            label = re.sub(r"[^a-zA-Z0-9.]+", "-", str(value)).strip("-")
            labels.append(f"{key.split('.')[-1]}-{label}")
        config["run_name"] += f"-{'-'.join(labels)}-{series}-{number}"
        yield config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="JSON grid with relative base paths")
    args = parser.parse_args()
    series = uuid4().hex[:12]
    for config in runs(args.config, series):
        print(f"Starting {config['run_name']}", flush=True)
        subprocess.run(
            ["docker", "compose", "run", "--no-deps", "--rm", "-T", "train", "/dev/stdin"],
            input=json.dumps(config),
            text=True,
            check=True,
        )


if __name__ == "__main__":
    main()
