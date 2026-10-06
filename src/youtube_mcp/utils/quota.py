"""Client-side YouTube API quota tracking.

YouTube Data API v3 has a default daily quota of 10,000 units.
This module tracks usage and hard-fails when the quota is exhausted.

Since 2026-06-01 Google bills ``videos.insert`` to a separate Video Uploads
bucket (1 unit per upload, 100 uploads per day) instead of charging 1,600
units against the 10,000-unit pool, so uploads are tallied on their own.
"""

from datetime import date


class QuotaExhaustedError(Exception):
    def __init__(self, used: int, limit: int, bucket: str = "API"):
        self.used = used
        self.limit = limit
        self.bucket = bucket
        unit = "uploads" if bucket == "video upload" else "units"
        super().__init__(
            f"YouTube {bucket} quota exhausted: {used}/{limit} {unit} used today. "
            f"Resets at midnight Pacific Time."
        )


# Quota costs per operation type against the 10,000-unit daily pool
# (from Google's documentation).
QUOTA_COSTS = {
    "list": 1,
    "insert": 50,
    "update": 50,
    "delete": 50,
    "search": 100,
    "caption_insert": 400,
    "caption_update": 450,
    "thumbnail_set": 50,
}

# Operations billed to the separate Video Uploads bucket, 1 unit each.
UPLOAD_OPERATIONS = frozenset({"video_insert"})
UPLOAD_DAILY_LIMIT = 100


class QuotaTracker:
    def __init__(self, daily_limit: int = 10_000, upload_limit: int = UPLOAD_DAILY_LIMIT):
        self.daily_limit = daily_limit
        self.upload_limit = upload_limit
        self._used = 0
        self._uploads = 0
        self._date = date.today()

    def _reset_if_new_day(self):
        today = date.today()
        if today != self._date:
            self._used = 0
            self._uploads = 0
            self._date = today

    def consume(self, operation: str, count: int = 1):
        """Consume quota units for an operation. Raises QuotaExhaustedError if exhausted."""
        self._reset_if_new_day()
        if operation in UPLOAD_OPERATIONS:
            if self._uploads + count > self.upload_limit:
                raise QuotaExhaustedError(self._uploads, self.upload_limit, "video upload")
            self._uploads += count
            return
        cost = QUOTA_COSTS.get(operation, 1) * count
        if self._used + cost > self.daily_limit:
            raise QuotaExhaustedError(self._used, self.daily_limit)
        self._used += cost

    @property
    def used(self) -> int:
        self._reset_if_new_day()
        return self._used

    @property
    def remaining(self) -> int:
        self._reset_if_new_day()
        return self.daily_limit - self._used

    def status(self) -> dict:
        self._reset_if_new_day()
        return {
            "used": self._used,
            "remaining": self.remaining,
            "limit": self.daily_limit,
            "uploads_used": self._uploads,
            "uploads_remaining": self.upload_limit - self._uploads,
            "uploads_limit": self.upload_limit,
            "date": str(self._date),
        }
