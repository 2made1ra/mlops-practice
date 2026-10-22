"""Feature scaling helpers over plain Python sequences."""


def min_max_scale(values: list[float]) -> list[float]:
    """Rescale ``values`` linearly into the ``[0, 1]`` range."""
    if not values:
        raise ValueError("min_max_scale() requires at least one value")
    low, high = min(values), max(values)
    if low == high:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]
