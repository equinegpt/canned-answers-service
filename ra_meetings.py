# ra_meetings.py
from __future__ import annotations

import json
import os
from datetime import date
from typing import Dict, Optional
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

# You can override this in Render env if needed
RA_CRAWLER_BASE_URL = os.getenv(
    "RA_CRAWLER_BASE_URL",
    "https://ra-crawler.onrender.com",
)


@lru_cache(maxsize=64)
def fetch_meeting_labels(
    start: Optional[date],
    end: Optional[date],
) -> Dict[int, str]:
    """
    Ask RA-crawler for races in a date range and build:

        { pf_meeting_id: "Track (STATE)" }

    If anything goes wrong, returns {} so we safely fall back to IDs.
    """

    params = {}
    if start is not None:
        params["start_date"] = start.isoformat()
    if end is not None:
        params["end_date"] = end.isoformat()

    query = f"?{urlencode(params)}" if params else ""
    url = f"{RA_CRAWLER_BASE_URL.rstrip('/')}/races{query}"

    try:
        with urlopen(url, timeout=5) as resp:
            raw = resp.read()
        data = json.loads(raw.decode("utf-8"))
    except (URLError, HTTPError, json.JSONDecodeError, TimeoutError, OSError):
        # On any error, just return empty mapping – UI will show Meeting ID.
        return {}

    labels: Dict[int, str] = {}

    # Be tolerant about key names – RA-crawler may use meetingId/track/state
    for item in data:
        mid = (
            item.get("meetingId")
            or item.get("meeting_id")
            or item.get("pf_meeting_id")
        )
        track = item.get("track") or item.get("track_name")
        state = item.get("state")

        if mid is None or track is None:
            continue

        try:
            mid_int = int(mid)
        except (TypeError, ValueError):
            continue

        label = f"{track} ({state})" if state else str(track)

        # First one wins; we just need one label per meeting
        if mid_int not in labels:
            labels[mid_int] = label

    return labels
