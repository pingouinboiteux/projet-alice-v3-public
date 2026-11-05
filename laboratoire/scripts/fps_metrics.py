"""Runtime FPS protection; retained implementation, no training driver."""
import math
from statistics import fmean

def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None

def summary(values):
    ordered = sorted(v for v in values if v is not None and v > 0)
    if not ordered:
        return {"frames": 0}

    def percentile(fraction):
        position = (len(ordered) - 1) * fraction
        lower = math.floor(position)
        upper = math.ceil(position)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    return {
        "frames": len(ordered),
        "average_fps": 1000 / fmean(ordered),
        "one_percent_low_fps": 1000
        / fmean(ordered[-max(1, math.ceil(len(ordered) * 0.01)) :]),
        "p50_ms": percentile(0.5),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
        "maximum_ms": ordered[-1],
        "percent_frames_over_8_333ms": 100
        * sum(v > 1000 / 120 for v in ordered)
        / len(ordered),
    }
