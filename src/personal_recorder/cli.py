from __future__ import annotations

import argparse
from pathlib import Path

from personal_recorder.bridges.blackbox_runtime import BlackboxRuntimeBridge
from personal_recorder.collectors.file_drop import FileDropCollector
from personal_recorder.collectors.manual import ManualCollector
from personal_recorder.collectors.system_snapshot import SnapshotOptions, SystemSnapshotCollector
from personal_recorder.config.settings import Settings
from personal_recorder.exporters.ics_exporter import ICSExporter
from personal_recorder.repositories.database import Database
from personal_recorder.repositories.event_repository import EventRepository
from personal_recorder.reports.generator import ReportGenerator
from personal_recorder.services.blackbox_importer import BlackboxImporter
from personal_recorder.services.inbox_watcher import InboxWatcher
from personal_recorder.services.pipeline import ProcessingPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="personal-recorder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db")
    subparsers.add_parser("import-sample")

    import_blackbox = subparsers.add_parser("import-blackbox-db")
    import_blackbox.add_argument("--db-path", required=True)
    import_blackbox.add_argument("--skip-sessions", action="store_true")

    add_manual = subparsers.add_parser("add-manual")
    add_manual.add_argument("--title", required=True)
    add_manual.add_argument("--content", default="")
    add_manual.add_argument("--tags", default="")
    add_manual.add_argument("--project")

    build_day = subparsers.add_parser("build-day")
    build_day.add_argument("--date", required=True)

    build_week = subparsers.add_parser("build-week")
    build_week.add_argument("--week-start", required=True)

    export_ics = subparsers.add_parser("export-ics")
    export_ics.add_argument("--date", required=True)
    export_ics.add_argument("--output")

    watch_inbox = subparsers.add_parser("watch-inbox")
    watch_inbox.add_argument("--poll-interval", type=float, default=2.0)
    watch_inbox.add_argument("--once", action="store_true")

    push_event = subparsers.add_parser("push-event")
    push_event.add_argument("--source", required=True)
    push_event.add_argument("--content", required=True)
    push_event.add_argument("--app-name")
    push_event.add_argument("--window-title")
    push_event.add_argument("--project")
    push_event.add_argument("--tags", default="")
    push_event.add_argument("--sensitivity", default="medium")

    bridge_blackbox = subparsers.add_parser("bridge-blackbox")
    bridge_blackbox.add_argument("--blackbox-src", required=True)
    bridge_blackbox.add_argument("--poll-interval", type=float, default=1.0)
    bridge_blackbox.add_argument("--disable-window", action="store_true")
    bridge_blackbox.add_argument("--disable-clipboard", action="store_true")
    bridge_blackbox.add_argument("--disable-keyboard", action="store_true")
    bridge_blackbox.add_argument("--clipboard-max-length", type=int, default=400)
    bridge_blackbox.add_argument("--keyboard-buffer-timeout", type=float, default=3.0)
    bridge_blackbox.add_argument("--keyboard-buffer-max-length", type=int, default=120)
    bridge_blackbox.add_argument("--capture-hotkeys", action="store_true")

    emit_blackbox_text = subparsers.add_parser("emit-blackbox-text")
    emit_blackbox_text.add_argument("--blackbox-src", required=True)
    emit_blackbox_text.add_argument("--text", required=True)
    emit_blackbox_text.add_argument("--source", default="keyboard")
    emit_blackbox_text.add_argument("--app-name", default="")
    emit_blackbox_text.add_argument("--window-title", default="")

    collect_snapshot = subparsers.add_parser("collect-snapshot")
    collect_snapshot.add_argument("--hours", type=int, default=24)
    collect_snapshot.add_argument("--max-events-per-source", type=int, default=100)
    collect_snapshot.add_argument("--roots", default="")
    collect_snapshot.add_argument("--disable-git", action="store_true")
    collect_snapshot.add_argument("--disable-shell", action="store_true")
    collect_snapshot.add_argument("--disable-files", action="store_true")
    collect_snapshot.add_argument("--disable-browser", action="store_true")

    collect_calendar = subparsers.add_parser("collect-calendar")
    collect_calendar.add_argument("--hours", type=int, default=72)
    collect_calendar.add_argument("--max-events", type=int, default=100)

    check_macos_permissions = subparsers.add_parser("check-macos-permissions")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    settings = Settings.load()
    database = Database(settings.db_path)
    repository = EventRepository(database)
    pipeline = ProcessingPipeline(repository)
    report_generator = ReportGenerator(repository)
    exporter = ICSExporter(repository)
    collector = ManualCollector()
    file_drop = FileDropCollector(settings.inbox_dir)
    snapshot_collector = SystemSnapshotCollector()
    blackbox_importer = BlackboxImporter(pipeline)
    runtime_bridge = None
    watcher = InboxWatcher(
        pipeline=pipeline,
        inbox_dir=settings.inbox_dir,
        archive_dir=settings.archive_dir,
        failed_dir=settings.failed_dir,
    )

    if args.command == "init-db":
        database.initialize()
        print(f"Database initialized at {settings.db_path}")
        return

    database.initialize()

    if args.command == "import-sample":
        input_path = settings.root_dir / "examples" / "sample_events.json"
        for raw_event in collector.load_json_events(input_path):
            pipeline.ingest(raw_event)
        print(f"Imported sample events from {input_path}")
        return

    if args.command == "import-blackbox-db":
        stats = blackbox_importer.import_sqlite(
            db_path=Path(args.db_path),
            include_sessions=not args.skip_sessions,
        )
        summary = ", ".join(f"{key}={value}" for key, value in stats.items())
        print(f"Imported Blackbox SQLite data from {args.db_path}: {summary}")
        return

    if args.command == "add-manual":
        raw_event = collector.build_record(
            title=args.title,
            content=args.content,
            tags=_parse_tags(args.tags),
            project=args.project,
        )
        event = pipeline.ingest(raw_event)
        print(f"Added manual event {event.id} with importance {event.importance_score:.2f}")
        return

    if args.command == "build-day":
        content = report_generator.build_daily_report(args.date)
        output = settings.reports_dir / f"daily-{args.date}.md"
        output.write_text(content, encoding="utf-8")
        repository.save_daily_report(args.date, content)
        print(f"Daily report written to {output}")
        return

    if args.command == "build-week":
        week_end, content = report_generator.build_weekly_report(args.week_start)
        output = settings.reports_dir / f"weekly-{args.week_start}-to-{week_end}.md"
        output.write_text(content, encoding="utf-8")
        repository.save_weekly_report(args.week_start, week_end, content)
        print(f"Weekly report written to {output}")
        return

    if args.command == "export-ics":
        output = Path(args.output) if args.output else settings.calendar_dir / f"{args.date}.ics"
        path = exporter.export_day(args.date, output)
        print(f"ICS exported to {path}")
        return

    if args.command == "push-event":
        output = file_drop.write_event(
            {
                "source": args.source,
                "content": args.content,
                "app_name": args.app_name,
                "window_title": args.window_title,
                "project": args.project,
                "tags": _parse_tags(args.tags),
                "sensitivity": args.sensitivity,
            }
        )
        print(f"Event written to inbox: {output}")
        return

    if args.command == "watch-inbox":
        if args.once:
            count = watcher.process_pending_files()
            print(f"Processed {count} inbox file(s) from {settings.inbox_dir}")
            return
        print(f"Watching inbox: {settings.inbox_dir}")
        watcher.serve_forever(poll_interval=args.poll_interval)
        return

    if args.command == "bridge-blackbox":
        runtime_bridge = BlackboxRuntimeBridge(
            inbox_dir=settings.inbox_dir,
            blackbox_src=Path(args.blackbox_src),
        )
        runtime_bridge.run(
            enable_window=not args.disable_window,
            enable_clipboard=not args.disable_clipboard,
            enable_keyboard=not args.disable_keyboard,
            clipboard_max_length=args.clipboard_max_length,
            poll_interval=args.poll_interval,
            keyboard_buffer_timeout=args.keyboard_buffer_timeout,
            keyboard_buffer_max_length=args.keyboard_buffer_max_length,
            capture_hotkeys=args.capture_hotkeys,
        )
        return

    if args.command == "emit-blackbox-text":
        runtime_bridge = BlackboxRuntimeBridge(
            inbox_dir=settings.inbox_dir,
            blackbox_src=Path(args.blackbox_src),
        )
        output = runtime_bridge.emit_text(
            text=args.text,
            source=args.source,
            process_name=args.app_name,
            window_title=args.window_title,
        )
        print(f"Blackbox text event written to inbox: {output}")
        return

    if args.command == "collect-snapshot":
        roots = _parse_roots(args.roots)
        if not roots:
            roots = [
                settings.root_dir,
                Path.home() / "Desktop",
                Path.home() / "Documents",
                Path.home() / "Downloads",
            ]
        options = SnapshotOptions(
            roots=roots,
            since_hours=args.hours,
            max_events_per_source=args.max_events_per_source,
        )
        events = snapshot_collector.collect(
            options=options,
            include_git=not args.disable_git,
            include_shell=not args.disable_shell,
            include_files=not args.disable_files,
            include_browser=not args.disable_browser,
        )
        for raw_event in events:
            pipeline.ingest(raw_event)
        print(f"Collected {len(events)} event(s) from local snapshot sources")
        return

    if args.command == "collect-calendar":
        options = SnapshotOptions(roots=[], since_hours=args.hours, max_events_per_source=args.max_events)
        events = snapshot_collector._collect_macos_calendar_events(options)
        for raw_event in events:
            pipeline.ingest(raw_event)
        print(f"Collected {len(events)} calendar event(s)")
        return

    if args.command == "check-macos-permissions":
        checks = snapshot_collector.check_macos_permissions()
        if not checks:
            print("macOS permission checks are only available on macOS")
            return
        for check in checks:
            print(f"[{check['status']}] {check['permission']}: {check['detail']}")
        return


def _parse_tags(raw: str) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_roots(raw: str) -> list[Path]:
    if not raw:
        return []
    return [Path(item.strip()).expanduser() for item in raw.split(",") if item.strip()]
