import unittest
from io import StringIO

from fps_policy import stop_reason
from fps_frames import Frames


class ProgressiveGuardTests(unittest.TestCase):
    def test_authorized_60fps_target_tolerates_small_drops_but_keeps_stop_guards(self):
        metrics = dict(frames=180, average_fps=59.99, p95_ms=18, p99_ms=20, maximum_ms=25)
        def decide(**changes):
            return stop_reason(metrics | changes, metrics, stale_seconds=.1,
                free_ram_bytes=8 * 1024**3, minimum_fps=60, check_tails=False)
        self.assertIsNone(decide())
        self.assertIsNone(decide(average_fps=56))
        self.assertEqual(decide(average_fps=54), 'average_below_55fps')
        self.assertEqual(stop_reason(metrics, metrics, stale_seconds=.1,
            free_ram_bytes=5 * 1024**3, minimum_fps=60, check_tails=False), 'windows_ram_headroom')
        self.assertEqual(stop_reason(metrics, metrics, stale_seconds=3,
            free_ram_bytes=8 * 1024**3, minimum_fps=60, check_tails=False), 'frame_measurement_stale')

    def setUp(self):
        self.reference = {"p95_ms": 7.7, "p99_ms": 8.4}
        self.metrics = {
            "frames": 720,
            "average_fps": 144,
            "p95_ms": 7.8,
            "p99_ms": 9,
            "maximum_ms": 40,
        }

    def reason(self, **changes):
        return stop_reason(
            self.metrics | changes,
            self.reference,
            stale_seconds=0.1,
            free_ram_bytes=12 * 1024**3,
        )

    def test_measured_baseline_with_short_outliers_is_not_falsely_stopped(self):
        self.assertIsNone(self.reason())

    def test_low_average_stops(self):
        self.assertEqual(self.reason(average_fps=119), "average_below_120fps")

    def test_tail_degradation_stops(self):
        self.assertEqual(self.reason(p99_ms=25), "p99_degraded")

    def test_p95_degradation_stops(self):
        self.assertEqual(self.reason(p95_ms=14), "p95_degraded")

    def test_long_frame_stops(self):
        self.assertEqual(self.reason(maximum_ms=101), "frame_over_100ms")

    def test_missing_measurement_stops(self):
        self.assertEqual(self.reason(frames=0), "insufficient_frame_measurement")

    def test_stale_measurement_stops(self):
        self.assertEqual(
            stop_reason(
                self.metrics,
                self.reference,
                stale_seconds=3,
                free_ram_bytes=12 * 1024**3,
            ),
            "frame_measurement_stale",
        )

    def test_low_ram_stops(self):
        self.assertEqual(
            stop_reason(
                self.metrics,
                self.reference,
                stale_seconds=0,
                free_ram_bytes=5 * 1024**3,
            ),
            "windows_ram_headroom",
        )

    def test_user_90fps_policy_stops_below_90(self):
        self.assertEqual(
            stop_reason(
                self.metrics | {"average_fps": 89},
                self.reference,
                stale_seconds=0.1,
                free_ram_bytes=12 * 1024**3,
                minimum_fps=90,
                check_tails=False,
            ),
            "average_below_90fps",
        )

    def test_user_90fps_policy_accepts_95_and_keeps_memory_guard(self):
        metrics = self.metrics | {"average_fps": 95, "p99_ms": 30}
        self.assertIsNone(
            stop_reason(
                metrics,
                self.reference,
                stale_seconds=0.1,
                free_ram_bytes=12 * 1024**3,
                minimum_fps=90,
                check_tails=False,
            )
        )
        self.assertEqual(
            stop_reason(
                metrics,
                self.reference,
                stale_seconds=0.1,
                free_ram_bytes=5 * 1024**3,
                minimum_fps=90,
                check_tails=False,
            ),
            "windows_ram_headroom",
        )


class FrameInstrumentTests(unittest.TestCase):
    def feed(self, extra_chain=False):
        lines = [
            "ProcessID,MsBetweenPresents,TimeInMs,MsBetweenDisplayChange,SwapChainAddress"
        ]
        for i in range(1440):
            lines.append(f"1,{1000 / 144},{i * 1000 / 144},{1000 / 144},primary")
            if extra_chain:
                lines.append(f"1,{1000 / 144},{i * 1000 / 144},{1000 / 144},other")
        frames = Frames(StringIO("\n".join(lines)), 1)
        frames.thread.join(timeout=2)
        self.assertIsNone(frames.error)
        return frames

    def test_batched_delivery_uses_frame_clock_for_five_second_window(self):
        metrics, stale, _ = self.feed().metrics(5)
        self.assertGreaterEqual(metrics["frames"], 719)
        self.assertLessEqual(metrics["frames"], 721)
        self.assertLess(stale, 2)
        self.assertAlmostEqual(metrics["average_fps"], 144)

    def test_second_swapchain_does_not_double_the_frame_count(self):
        metrics, _, _ = self.feed(extra_chain=True).metrics(5)
        self.assertLessEqual(metrics["frames"], 721)

    def test_short_window_still_uses_correct_frame_clock(self):
        frames = self.feed()
        metrics, _, _ = frames.metrics(1.5)
        displayed, _ = frames.display_metrics(1.5)
        self.assertGreaterEqual(metrics["frames"], 215)
        self.assertLessEqual(metrics["frames"], 217)
        self.assertEqual(metrics["frames"], displayed["frames"])
