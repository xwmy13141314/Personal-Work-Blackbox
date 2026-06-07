# Changelog

## v3.0.0 - 2026-06-07

### Added

- Added `src/personal_recorder` as a parallel module inside the original repository.
- Added a unified `events` data model for personal activity recording.
- Added `personal-recorder` CLI entrypoint.
- Added Blackbox SQLite history import for:
  - `sessions`
  - `text_segments`
  - `clipboard_records`
  - `window_events`
- Added inbox-based realtime ingestion:
  - `push-event`
  - `watch-inbox`
- Added Windows runtime bridge for Blackbox collectors:
  - window switch bridge
  - clipboard bridge
  - keyboard buffered text bridge
- Added daily report and weekly report generation for the new recorder pipeline.
- Added `.ics` calendar export.
- Added rule-based importance extraction and action-item extraction.
- Added privacy-aware layered storage:
  - raw content
  - redacted content
  - derived summary
  - storage tier tagging
- Added first-wave local snapshot collectors:
  - Git activity
  - Git branch, status, and diff snapshots
  - shell history
  - recent file modifications
  - Chrome-family browser history

### Changed

- Upgraded repository positioning from a single Windows Blackbox app to a dual-track repository:
  - original Blackbox workflow
  - new Personal Recorder workflow
- Updated `README.md` to describe both usage paths clearly.
- Updated `pyproject.toml` to expose the `personal-recorder` CLI.

### Preserved

- Preserved the original `src.main` application entrypoint.
- Preserved the original Windows GUI and tray workflow.
- Preserved the original collector, processor, storage, AI, UI, and packaging structure.
- Preserved the original Blackbox use case for Windows desktop activity capture.

### Notes

- This version introduces a stronger personal knowledge and reporting workflow without removing the original Blackbox flow.
- Privacy protection currently uses rule-based redaction and storage tier tagging.
- Git transport on the local machine was unstable, so the repository update was ultimately synchronized through authenticated GitHub API writes.

## v2.3 - 2026-05-27

- Added weekly and monthly report support.
- Added period report persistence.
- Improved prompt templates and cross-day statistics.
- Reorganized repository directories and packaging assets.

## v2.2 - 2026-05-19

- Improved database query and statistics tests.
- Verified actual AI daily report generation flow.
- Initialized repository version control.

## v2.1 - 2026-05-14

- Fixed clipboard monitoring crash on 64-bit Python.
- Fixed GUI startup crash behavior.
- Improved PyInstaller packaging and startup error visibility.
