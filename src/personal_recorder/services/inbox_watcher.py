from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from personal_recorder.services.pipeline import ProcessingPipeline


class InboxWatcher:
    def __init__(
        self,
        pipeline: ProcessingPipeline,
        inbox_dir: Path,
        archive_dir: Path,
        failed_dir: Path,
    ):
        self.pipeline = pipeline
        self.inbox_dir = inbox_dir
        self.archive_dir = archive_dir
        self.failed_dir = failed_dir

    def serve_forever(self, poll_interval: float = 2.0) -> None:
        while True:
            self.process_pending_files()
            time.sleep(poll_interval)

    def process_pending_files(self) -> int:
        count = 0
        for path in sorted(self.inbox_dir.glob("*.json")):
            if self._is_too_fresh(path):
                continue
            self._process_file(path)
            count += 1
        return count

    def _process_file(self, path: Path) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                for item in raw:
                    self.pipeline.ingest(item)
            else:
                self.pipeline.ingest(raw)
            shutil.move(str(path), str(self.archive_dir / path.name))
        except Exception as exc:
            target = self.failed_dir / f"{path.stem}.error.json"
            target.write_text(
                json.dumps(
                    {
                        "error": str(exc),
                        "original_file": path.name,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            shutil.move(str(path), str(self.failed_dir / path.name))

    @staticmethod
    def _is_too_fresh(path: Path) -> bool:
        return (time.time() - path.stat().st_mtime) < 0.2
