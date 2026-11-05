"""Runtime FPS protection; retained implementation, no training driver."""
import csv
import threading
import time
from collections import deque
from fps_metrics import number, summary

class Frames:
    def __init__(self, stream, pid):
        self.rows = deque(maxlen=15000)
        self.lock = threading.Lock()
        self.error = None
        self.anchor = None
        self.chain = None
        self.last_any = None
        self.chains = {}
        self.thread = threading.Thread(
            target=self.read, args=(stream, pid), daemon=True
        )
        self.thread.start()

    def read(self, stream, pid):
        try:
            reader = csv.DictReader(stream)
            if not {
                "ProcessID",
                "MsBetweenPresents",
                "TimeInMs",
                "MsBetweenDisplayChange",
                "SwapChainAddress",
            }.issubset(reader.fieldnames or []):
                raise ValueError("Unexpected PresentMon frame format")
            for row in reader:
                interval = number(row.get("MsBetweenPresents"))
                stamp = number(row.get("TimeInMs"))
                if (
                    row.get("ProcessID") == str(pid)
                    and interval
                    and interval > 0
                    and stamp is not None
                ):
                    with self.lock:
                        key = row["SwapChainAddress"]
                        self.chains[key] = self.chains.get(key, 0) + 1
                        self.last_any = {
                            "arrived": time.monotonic(),
                            "stamp": stamp,
                            "chain": key,
                        }
                        if self.chain is None:
                            self.chain = row["SwapChainAddress"]
                        if row["SwapChainAddress"] != self.chain:
                            continue
                        arrived = time.monotonic()
                        offset = arrived - stamp / 1000
                        self.anchor = (
                            offset if self.anchor is None else min(self.anchor, offset)
                        )
                        self.rows.append(
                            (
                                arrived,
                                interval,
                                stamp,
                                number(row.get("MsBetweenDisplayChange")),
                            )
                        )
        except (csv.Error, OSError, ValueError, KeyError, TypeError) as exc:
            self.error = repr(exc)

    def metrics(self, seconds=5):
        now = time.monotonic()
        with self.lock:
            latest = self.rows[-1][2] if self.rows else 0
            # A pipe can deliver batches. Use the frame clock for the window and
            # also detect delayed source timestamps, not only delayed delivery.
            rows = [r for r in self.rows if r[2] >= latest - seconds * 1000]
            stale = (
                max(now - self.rows[-1][0], now - (latest / 1000 + self.anchor))
                if self.rows
                else 999
            )
        return summary([r[1] for r in rows]), stale, rows

    def display_metrics(self, seconds=5):
        _, source_stale, rows = self.metrics(seconds)
        displayed = [r for r in rows if r[3] is not None and r[3] > 0]
        return summary([r[3] for r in displayed]), max(
            source_stale, time.monotonic() - displayed[-1][0]
        ) if displayed else 999
