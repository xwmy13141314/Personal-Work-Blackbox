from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from personal_recorder.collectors.macos_snapshot import MacOSSnapshotCollector


@dataclass
class SnapshotOptions:
    roots: list[Path]
    since_hours: int = 24
    max_events_per_source: int = 100


class SystemSnapshotCollector:
    def __init__(self) -> None:
        self._home = Path.home()
        self._macos = MacOSSnapshotCollector()

    def collect(
        self,
        options: SnapshotOptions,
        include_git: bool = True,
        include_shell: bool = True,
        include_files: bool = True,
        include_browser: bool = True,
    ) -> list[dict]:
        events: list[dict] = []
        if include_git:
            events.extend(self._collect_git_events(options))
        if include_shell:
            events.extend(self._collect_shell_events(options))
        if include_files:
            events.extend(self._collect_recent_file_events(options))
        if include_browser:
            events.extend(self._collect_browser_events(options))
            events.extend(self._collect_macos_browser_events(options))
        events.extend(self._collect_macos_foreground_events())
        events.extend(self._collect_macos_clipboard_events())
        events.sort(key=lambda item: item["timestamp"])
        return events

    def _collect_git_events(self, options: SnapshotOptions) -> list[dict]:
        events: list[dict] = []
        repos = self._discover_git_repos(options.roots, limit=30)
        since = f"{options.since_hours} hours ago"
        for repo in repos:
            events.extend(self._collect_git_repo_state(repo))
            try:
                result = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(repo),
                        "log",
                        f"--since={since}",
                        f"--max-count={options.max_events_per_source}",
                        "--pretty=format:%H%x1f%aI%x1f%an%x1f%s",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except Exception:
                continue
            if result.returncode != 0 or not result.stdout.strip():
                continue
            for line in result.stdout.splitlines():
                parts = line.split("\x1f")
                if len(parts) != 4:
                    continue
                commit_sha, authored_at, author_name, subject = parts
                events.append(
                    {
                        "source": "git",
                        "timestamp": authored_at,
                        "app_name": "git",
                        "window_title": repo.name,
                        "content": f"Git 提交：{subject}",
                        "project": repo.name,
                        "tags": ["git", "commit"],
                        "metadata": {
                            "repo_path": str(repo),
                            "commit_sha": commit_sha,
                            "author_name": author_name,
                        },
                    }
                )
        return events[: options.max_events_per_source]

    def _collect_git_repo_state(self, repo: Path) -> list[dict]:
        events: list[dict] = []
        now = datetime.now().isoformat(timespec="seconds")

        branch = self._run_git(repo, ["branch", "--show-current"])
        status = self._run_git(repo, ["status", "--short"])
        diff_stat = self._run_git(repo, ["diff", "--stat", "--", "."])

        if branch:
            events.append(
                {
                    "source": "git_branch",
                    "timestamp": now,
                    "app_name": "git",
                    "window_title": repo.name,
                    "content": f"当前 Git 分支：{branch.strip()}",
                    "project": repo.name,
                    "tags": ["git", "branch"],
                    "metadata": {"repo_path": str(repo)},
                }
            )

        if status:
            changed_files = [line.strip() for line in status.splitlines() if line.strip()]
            if changed_files:
                preview = "；".join(changed_files[:8])
                events.append(
                    {
                        "source": "git_status",
                        "timestamp": now,
                        "app_name": "git",
                        "window_title": repo.name,
                        "content": f"Git 工作区变更：{preview}",
                        "project": repo.name,
                        "tags": ["git", "status"],
                        "metadata": {
                            "repo_path": str(repo),
                            "changed_files": changed_files[:30],
                        },
                    }
                )

        if diff_stat:
            lines = [line.strip() for line in diff_stat.splitlines() if line.strip()]
            if lines:
                preview = "；".join(lines[:6])
                events.append(
                    {
                        "source": "git_diff",
                        "timestamp": now,
                        "app_name": "git",
                        "window_title": repo.name,
                        "content": f"Git diff 摘要：{preview}",
                        "project": repo.name,
                        "tags": ["git", "diff"],
                        "metadata": {
                            "repo_path": str(repo),
                            "diff_stat_preview": lines[:20],
                        },
                    }
                )

        return events

    def _collect_shell_events(self, options: SnapshotOptions) -> list[dict]:
        cutoff = datetime.now() - timedelta(hours=options.since_hours)
        files = [
            ("zsh", self._home / ".zsh_history"),
            ("bash", self._home / ".bash_history"),
        ]
        events: list[dict] = []
        for shell_name, path in files:
            if not path.exists():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for line in reversed(lines):
                parsed = self._parse_shell_history_line(shell_name, line, cutoff)
                if parsed:
                    events.append(parsed)
                if len(events) >= options.max_events_per_source:
                    return list(reversed(events))
        return list(reversed(events))

    def _collect_recent_file_events(self, options: SnapshotOptions) -> list[dict]:
        cutoff = datetime.now().timestamp() - options.since_hours * 3600
        events: list[dict] = []
        skip_dirs = {".git", ".venv", "node_modules", "__pycache__", "Library"}
        for root in options.roots:
            if not root.exists():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [name for name in dirnames if name not in skip_dirs and not name.startswith(".")]
                for filename in filenames:
                    path = Path(dirpath) / filename
                    try:
                        stat = path.stat()
                    except Exception:
                        continue
                    if stat.st_mtime < cutoff:
                        continue
                    events.append(
                        {
                            "source": "filesystem_recent",
                            "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                            "app_name": "filesystem",
                            "window_title": path.name,
                            "content": f"最近修改文件：{path.name}",
                            "project": self._infer_project_from_path(path, options.roots),
                            "tags": ["file", "recent"],
                            "metadata": {
                                "path": str(path),
                                "size": stat.st_size,
                                "modified_at": stat.st_mtime,
                            },
                        }
                    )
                    if len(events) >= options.max_events_per_source:
                        return sorted(events, key=lambda item: item["timestamp"])
        return sorted(events, key=lambda item: item["timestamp"])

    def _collect_browser_events(self, options: SnapshotOptions) -> list[dict]:
        events: list[dict] = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=options.since_hours)
        browser_paths = {
            "chrome": self._home / "Library/Application Support/Google/Chrome/Default/History",
            "edge": self._home / "Library/Application Support/Microsoft Edge/Default/History",
            "brave": self._home / "Library/Application Support/BraveSoftware/Brave-Browser/Default/History",
        }
        for browser_name, history_path in browser_paths.items():
            if not history_path.exists():
                continue
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    copied = Path(tmpdir) / f"{browser_name}-History"
                    shutil.copy2(history_path, copied)
                    conn = sqlite3.connect(copied)
                    rows = conn.execute(
                        """
                        SELECT urls.url, urls.title, visits.visit_time
                        FROM visits
                        JOIN urls ON urls.id = visits.url
                        ORDER BY visits.visit_time DESC
                        LIMIT ?
                        """,
                        (options.max_events_per_source,),
                    ).fetchall()
                    conn.close()
            except Exception:
                continue
            for url, title, visit_time in rows:
                visited_at = self._chrome_time_to_datetime(visit_time)
                if visited_at < cutoff:
                    continue
                events.append(
                    {
                        "source": "browser_history",
                        "timestamp": visited_at.astimezone().replace(tzinfo=None).isoformat(timespec="seconds"),
                        "app_name": browser_name,
                        "window_title": title or url,
                        "content": f"浏览网页：{title or url}",
                        "tags": ["browser", browser_name],
                        "metadata": {
                            "url": url,
                            "browser": browser_name,
                        },
                    }
                )
        events.sort(key=lambda item: item["timestamp"])
        return events[: options.max_events_per_source]

    def _collect_macos_browser_events(self, options: SnapshotOptions) -> list[dict]:
        if not self._is_macos():
            return []
        return self._macos.collect_safari_history(
            since_hours=options.since_hours,
            max_events=options.max_events_per_source,
        )

    def _collect_macos_foreground_events(self) -> list[dict]:
        if not self._is_macos():
            return []
        return self._macos.collect_foreground_app_snapshot()

    def _collect_macos_clipboard_events(self) -> list[dict]:
        if not self._is_macos():
            return []
        return self._macos.collect_clipboard_snapshot()

    def _discover_git_repos(self, roots: list[Path], limit: int) -> list[Path]:
        repos: list[Path] = []
        seen: set[Path] = set()
        for root in roots:
            if not root.exists():
                continue
            if (root / ".git").exists():
                repos.append(root)
                seen.add(root.resolve())
                continue
            for dirpath, dirnames, _ in os.walk(root):
                dirnames[:] = [name for name in dirnames if name not in {".venv", "node_modules", "__pycache__"}]
                candidate = Path(dirpath)
                if (candidate / ".git").exists():
                    resolved = candidate.resolve()
                    if resolved not in seen:
                        repos.append(candidate)
                        seen.add(resolved)
                    dirnames[:] = []
                if len(repos) >= limit:
                    return repos
        return repos

    def _parse_shell_history_line(self, shell_name: str, line: str, cutoff: datetime) -> dict | None:
        if shell_name == "zsh" and line.startswith(": "):
            try:
                prefix, command = line.split(";", 1)
                timestamp_part = prefix.split(":")[1].strip()
                executed_at = datetime.fromtimestamp(int(timestamp_part))
            except Exception:
                return None
            if executed_at < cutoff:
                return None
            return {
                "source": "shell_history",
                "timestamp": executed_at.isoformat(timespec="seconds"),
                "app_name": shell_name,
                "window_title": command[:60],
                "content": f"终端命令：{command}",
                "tags": ["shell", shell_name],
                "sensitivity": "high",
                "metadata": {"shell": shell_name},
            }
        if shell_name == "bash":
            command = line.strip()
            if not command:
                return None
            try:
                executed_at = datetime.fromtimestamp(Path(self._home / ".bash_history").stat().st_mtime)
            except Exception:
                executed_at = datetime.now()
            if executed_at < cutoff:
                return None
            return {
                "source": "shell_history",
                "timestamp": executed_at.isoformat(timespec="seconds"),
                "app_name": shell_name,
                "window_title": command[:60],
                "content": f"终端命令：{command}",
                "tags": ["shell", shell_name],
                "sensitivity": "high",
                "metadata": {"shell": shell_name, "timestamp_precision": "file_mtime"},
            }
        return None

    @staticmethod
    def _run_git(repo: Path, args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), *args],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    @staticmethod
    def _chrome_time_to_datetime(value: int) -> datetime:
        epoch_start = datetime(1601, 1, 1, tzinfo=timezone.utc)
        return epoch_start + timedelta(microseconds=value)

    @staticmethod
    def _infer_project_from_path(path: Path, roots: list[Path]) -> str | None:
        for root in roots:
            try:
                relative = path.relative_to(root)
                if relative.parts:
                    return relative.parts[0]
            except Exception:
                continue
        return path.parent.name if path.parent.name else None

    @staticmethod
    def _is_macos() -> bool:
        return subprocess.run(["uname"], capture_output=True, text=True).stdout.strip() == "Darwin"
