from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class ManualCollector:
    def build_record(
        self,
        title: str,
        content: str,
        tags: list[str],
        project: str | None = None,
    ) -> dict:
        body = content.strip()
        if title.strip():
            body = f"{title.strip()}。{body}" if body else title.strip()
        return {
            "source": "manual",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "content": body,
            "tags": tags,
            "project": project,
            "metadata": {"origin": "manual_cli"},
        }

    def load_json_events(self, input_path: Path) -> list[dict]:
        data = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("sample event file must contain a list")
        return data
