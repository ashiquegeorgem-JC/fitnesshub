import threading
import time
from typing import Dict, List, Tuple

from app.core.config import settings
from app.core.exceptions import RateLimitExceededException


class InMemoryRateLimiter:
    """
    Thread-safe in-memory sliding-window rate limiter.
    Tracks timestamps per key and automatically purges expired entries.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: Dict[str, List[float]] = {}

    def is_allowed(
        self, key: str, max_attempts: int, window_seconds: int
    ) -> Tuple[bool, int]:
        """
        Check if the action is allowed under the rate limit.
        Returns:
            (is_allowed: bool, retry_after_seconds: int)
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            timestamps = self._records.get(key, [])
            # Filter timestamps within current window
            valid_timestamps = [t for t in timestamps if t > cutoff]

            if len(valid_timestamps) >= max_attempts:
                oldest_in_window = valid_timestamps[0]
                retry_after = int(oldest_in_window + window_seconds - now) + 1
                self._records[key] = valid_timestamps
                return False, max(1, retry_after)

            valid_timestamps.append(now)
            self._records[key] = valid_timestamps
            return True, 0

    def check_or_raise(
        self,
        key: str,
        max_attempts: int,
        window_seconds: int,
        action_name: str = "requests",
    ) -> None:
        """
        Check rate limit and raise RateLimitExceededException if exceeded.
        """
        allowed, retry_after = self.is_allowed(
            key, max_attempts, window_seconds
        )
        if not allowed:
            raise RateLimitExceededException(
                detail=(
                    f"Too many {action_name}. "
                    f"Please try again in {retry_after} seconds."
                ),
                retry_after=retry_after,
            )

    def reset(self, key: str) -> None:
        """
        Reset attempts for a key (e.g. after successful authentication).
        """
        with self._lock:
            self._records.pop(key, None)

    def clear(self) -> None:
        """Clear all entries (useful for test isolation)."""
        with self._lock:
            self._records.clear()


# Global rate limiter instance
limiter = InMemoryRateLimiter()
