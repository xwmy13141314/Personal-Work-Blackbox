# Release Notes v3.0.0

## Overview

`Personal Work Blackbox` in `v3.0.0` is no longer only a Windows desktop activity collector.
This release upgrades the repository into a dual-track system:

- the original `Blackbox` workflow for Windows collection and AI reporting
- the new `Personal Recorder` workflow for event-centric recording, extraction, privacy-aware storage, and extensible ingestion

## What Is New

### 1. Personal Recorder module

This release adds a new parallel module:

- `src/personal_recorder`

It introduces:

- unified `events` storage
- manual event capture
- realtime inbox ingestion
- Blackbox history import
- daily report generation
- weekly report generation
- `.ics` calendar export

### 2. Blackbox bridge

The new module can connect to the original Blackbox capture pipeline through:

- SQLite history import
- Windows runtime bridge
- keyboard buffered text ingestion
- clipboard and window-switch bridging

### 3. Privacy improvements

This release introduces a first privacy boundary:

- raw text is stored locally
- redacted text is stored separately
- reports and extraction use redacted content by default
- events are tagged by storage tier

## Why This Release Matters

The repository now supports two usage patterns:

### Continue using the original app

You can keep using:

- `python -m src.main --gui`
- existing Windows GUI and tray workflow

### Upgrade into a personal recorder

You can also use:

- `personal-recorder import-blackbox-db`
- `personal-recorder push-event`
- `personal-recorder watch-inbox`
- `personal-recorder build-day`
- `personal-recorder build-week`

This makes the project more suitable for:

- personal work logging
- structured daily and weekly review
- future integration with calendars, Git hooks, browser exports, and local AI summarization

## Preserved Behavior

This release does not remove the original Blackbox architecture.

Preserved:

- `src.main`
- original collectors
- original processors
- original storage layer
- original AI reporting layer
- original UI and packaging path

## Known Limits

Current limits in `v3.0.0`:

- sensitive app blacklist is not yet fully linked into the new module
- raw content is not yet separately encrypted
- project classification is still heuristic
- there is no correction UI yet
- local LLM summarization is not yet integrated into the new recorder pipeline

## Suggested Next Steps

- add stronger privacy and encryption controls
- add project tagging and manual correction
- add local-model summarization
- add more ingestion sources through inbox adapters
