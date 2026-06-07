from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4


class FileDropCollector:
    def __init__(self, inbox_dir: Path):
        self.inbox_dir = inbox_dir

    def write_event(self, raw_event: dict) -> Path:
        event = dict(raw_event)
        event.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
        event.setdefault("metadata", {})

        filename = f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid4().hex}.json"
        output = self.inbox_dir / filename
        output.write_text(
            json.dumps(event, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output
