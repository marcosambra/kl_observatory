from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


USAGE_HEADER_PATTERN = re.compile(
    r"^##\s+(?P<timestamp>.+?)\s+-\s+(?P<title>.+?)\s*$"
)


@dataclass(frozen=True)
class UsageEventRecord:
    source_key: str
    timestamp: datetime
    title: str
    summary: str
    remaining_story_points: int
    blocked_items: int
    actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SprintMetricRecord:
    source_key: str
    timestamp: datetime
    remaining_story_points: int
    blocked_items: int
    summary: str


@dataclass(frozen=True)
class CurrentSprintRecord:
    generated_at: datetime
    project: str
    user_email: str
    counts: dict[str, int]
    remaining_story_points: int
    remaining_work_hours: int
    raw_payload: dict[str, Any]


def parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if "T" not in normalized and " " in normalized:
        normalized = normalized.replace(" ", "T", 1)
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _safe_int(value: str) -> int:
    stripped = value.strip()
    if not stripped:
        return 0
    return int(stripped)


def parse_ai_usage_log(markdown: str) -> list[UsageEventRecord]:
    records: list[UsageEventRecord] = []
    current: dict[str, Any] | None = None
    collecting_actions = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        header_match = USAGE_HEADER_PATTERN.match(line)
        if header_match:
            if current is not None:
                records.append(
                    UsageEventRecord(
                        source_key=current["source_key"],
                        timestamp=current["timestamp"],
                        title=current["title"],
                        summary=current["summary"],
                        remaining_story_points=current["remaining_story_points"],
                        blocked_items=current["blocked_items"],
                        actions=current["actions"],
                    )
                )

            timestamp = parse_timestamp(header_match.group("timestamp"))
            title = header_match.group("title").strip()
            current = {
                "source_key": f"{timestamp.isoformat()}::{title}",
                "timestamp": timestamp,
                "title": title,
                "summary": "",
                "remaining_story_points": 0,
                "blocked_items": 0,
                "actions": [],
            }
            collecting_actions = False
            continue

        if current is None:
            continue

        if line.startswith("Resumo:"):
            current["summary"] = line.split(":", 1)[1].strip()
            collecting_actions = False
            continue

        if line.startswith("Story points restantes:"):
            current["remaining_story_points"] = _safe_int(line.split(":", 1)[1])
            collecting_actions = False
            continue

        if line.startswith("Itens bloqueados:"):
            current["blocked_items"] = _safe_int(line.split(":", 1)[1])
            collecting_actions = False
            continue

        if line.startswith("Acoes executadas:"):
            collecting_actions = True
            continue

        if collecting_actions and line.startswith("- "):
            current["actions"].append(line[2:].strip())

    if current is not None:
        records.append(
            UsageEventRecord(
                source_key=current["source_key"],
                timestamp=current["timestamp"],
                title=current["title"],
                summary=current["summary"],
                remaining_story_points=current["remaining_story_points"],
                blocked_items=current["blocked_items"],
                actions=current["actions"],
            )
        )

    return records


def parse_sprint_metrics(markdown: str) -> list[SprintMetricRecord]:
    records: list[SprintMetricRecord] = []

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|---"):
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or cells[0] == "Data":
            continue

        timestamp = parse_timestamp(cells[0])
        records.append(
            SprintMetricRecord(
                source_key=timestamp.isoformat(),
                timestamp=timestamp,
                remaining_story_points=_safe_int(cells[1]),
                blocked_items=_safe_int(cells[2]),
                summary=cells[3],
            )
        )

    return records


def load_current_sprint(path: Path) -> CurrentSprintRecord:
    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    counts = raw_payload.get("counts", {})

    return CurrentSprintRecord(
        generated_at=parse_timestamp(raw_payload["generated_at"]),
        project=raw_payload.get("project", ""),
        user_email=raw_payload.get("user_email", ""),
        counts={
            "assigned_items": _safe_int(str(counts.get("assigned_items", 0))),
            "blocked_items": _safe_int(str(counts.get("blocked_items", 0))),
            "open_prs": _safe_int(str(counts.get("open_prs", 0))),
            "user_stories": _safe_int(str(counts.get("user_stories", 0))),
        },
        remaining_story_points=_safe_int(
            str(raw_payload.get("remaining_story_points", 0))
        ),
        remaining_work_hours=_safe_int(str(raw_payload.get("remaining_work_hours", 0))),
        raw_payload=raw_payload,
    )


def read_usage_events(path: Path) -> list[UsageEventRecord]:
    return parse_ai_usage_log(path.read_text(encoding="utf-8"))


def read_sprint_metrics(path: Path) -> list[SprintMetricRecord]:
    return parse_sprint_metrics(path.read_text(encoding="utf-8"))


def serialize_usage_event(record: UsageEventRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["timestamp"] = record.timestamp.isoformat()
    return payload


def serialize_sprint_metric(record: SprintMetricRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["timestamp"] = record.timestamp.isoformat()
    return payload


def serialize_current_sprint(record: CurrentSprintRecord) -> dict[str, Any]:
    payload = dict(record.raw_payload)
    payload["generated_at"] = record.generated_at.isoformat()
    payload["counts"] = dict(record.counts)
    payload["remaining_story_points"] = record.remaining_story_points
    payload["remaining_work_hours"] = record.remaining_work_hours
    return payload
