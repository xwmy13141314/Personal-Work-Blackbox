from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    root_dir: Path
    data_dir: Path
    db_path: Path
    reports_dir: Path
    calendar_dir: Path
    inbox_dir: Path
    archive_dir: Path
    failed_dir: Path

    @classmethod
    def load(cls, root_dir: Path | None = None) -> "Settings":
        root = root_dir or Path(__file__).resolve().parents[3]
        data_dir = root / "data"
        reports_dir = data_dir / "reports"
        calendar_dir = data_dir / "calendar"
        inbox_dir = data_dir / "inbox"
        archive_dir = inbox_dir / "processed"
        failed_dir = inbox_dir / "failed"
        db_path = data_dir / "personal_recorder.db"
        settings = cls(
            root_dir=root,
            data_dir=data_dir,
            db_path=db_path,
            reports_dir=reports_dir,
            calendar_dir=calendar_dir,
            inbox_dir=inbox_dir,
            archive_dir=archive_dir,
            failed_dir=failed_dir,
        )
        settings.ensure_dirs()
        return settings

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.calendar_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)
