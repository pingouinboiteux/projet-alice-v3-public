"""Runtime FPS protection; retained implementation, no training driver."""


def stop_reason(
    metrics,
    reference,
    *,
    stale_seconds,
    free_ram_bytes,
    minimum_fps=120,
    check_tails=True,
):
    if stale_seconds > 2:
        return "frame_measurement_stale"
    if free_ram_bytes < 6 * 1024**3:
        return "windows_ram_headroom"
    if metrics.get("frames", 0) < 100:
        return "insufficient_frame_measurement"
    # User-authorized 60 FPS target tolerates small drops, including a capped
    # game's 59.99 FPS measurement. Existing strict 90/120 policies are unchanged.
    floor = 55 if minimum_fps == 60 else minimum_fps
    if metrics["average_fps"] < floor:
        return f"average_below_{floor}fps"
    if not check_tails:
        return None
    if metrics["p95_ms"] > max(12, reference["p95_ms"] * 1.4):
        return "p95_degraded"
    if metrics["p99_ms"] > max(20, reference["p99_ms"] * 1.75):
        return "p99_degraded"
    if metrics["maximum_ms"] > 100:
        return "frame_over_100ms"
    return None
