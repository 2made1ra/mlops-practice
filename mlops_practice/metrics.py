"""Descriptive statistics over plain Python sequences."""


def mean(values: list[float]) -> float:
    """Return the arithmetic mean of ``values``."""
    if not values:
        raise ValueError("mean() requires at least one value")
    return sum(values) / len(values)
