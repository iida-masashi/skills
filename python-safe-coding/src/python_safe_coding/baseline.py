"""AST-policy baseline: record known violations so only *new* ones fail.

A baseline is a JSON file (default `.psc-baseline.json`) listing fingerprints of
violations the team has accepted as legacy. Each fingerprint is

    (file_path, rule_id, content_hash_of_offending_line)

We hash the offending line's content rather than its line number so that
reformatting (which shifts line numbers without changing semantics) does not
silently invalidate the baseline.

Scope: AST checker only. Ruff baselines are out of scope on the first pass —
their JSON schema is not under our control and would couple this format to
Ruff's release cadence.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

BASELINE_VERSION: Final = 1
DEFAULT_BASELINE_FILE: Final = ".psc-baseline.json"

# Matches a violation message produced by ast_checker.check_file:
#   "<path>:<lineno>: ERROR: <message>"
_VIOLATION_RE = re.compile(r"^(?P<path>.+?):(?P<lineno>\d+): ERROR: (?P<message>.+)$")

# Each AST policy message starts with a stable rule phrase. Map to short ids.
# When adding or renaming an AST rule in ast_checker.py, add its phrase here
# too (mirrors the _CHECKER_VERSION bump rule) — otherwise _classify silently
# falls back to "unknown" and per-rule baseline grouping breaks.
_RULE_PATTERNS: Final[tuple[tuple[str, str], ...]] = (
    ("Use polars instead of pandas", "polars-first"),
    ("Syntax error", "syntax-error"),
    ("Cannot read file", "io-error"),
)


@dataclass(frozen=True)
class Fingerprint:
    """Stable identity of a violation, robust to line-number drift."""

    file: str
    rule_id: str
    line_hash: str

    def to_dict(self) -> dict[str, str]:
        return {"file": self.file, "rule_id": self.rule_id, "line_hash": self.line_hash}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Fingerprint:
        return cls(
            file=data["file"], rule_id=data["rule_id"], line_hash=data["line_hash"]
        )


def _classify(message: str) -> str:
    for prefix, rule_id in _RULE_PATTERNS:
        if prefix in message:
            return rule_id
    return "unknown"


def _hash_line(content: str) -> str:
    return hashlib.sha1(
        content.strip().encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:16]


def fingerprint_violation(
    violation: str, *, root: Path | None = None
) -> Fingerprint | None:
    """Convert a single AST checker violation message into a Fingerprint.

    `root` (when given) is stripped from the file path so the baseline stays
    relative and portable across checkout locations.
    """
    match = _VIOLATION_RE.match(violation.strip())
    if not match:
        return None
    file_str = match.group("path")
    lineno = int(match.group("lineno"))
    message = match.group("message")
    rule_id = _classify(message)

    file_path = Path(file_str)
    rel = file_path
    if root is not None:
        try:
            rel = file_path.resolve().relative_to(root.resolve())
        except ValueError:
            rel = file_path

    line_hash = ""
    try:
        if file_path.exists():
            lines = file_path.read_text(encoding="utf-8").splitlines()
            if 1 <= lineno <= len(lines):
                line_hash = _hash_line(lines[lineno - 1])
    except OSError:
        line_hash = ""

    return Fingerprint(file=rel.as_posix(), rule_id=rule_id, line_hash=line_hash)


def fingerprint_all(
    violations: list[str], *, root: Path | None = None
) -> list[Fingerprint]:
    fps: list[Fingerprint] = []
    for v in violations:
        fp = fingerprint_violation(v, root=root)
        if fp is not None:
            fps.append(fp)
    return fps


def write_baseline(path: Path, fingerprints: list[Fingerprint]) -> None:
    payload = {
        "version": BASELINE_VERSION,
        "fingerprints": sorted(
            (fp.to_dict() for fp in fingerprints),
            key=lambda d: (d["file"], d["rule_id"], d["line_hash"]),
        ),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_baseline(path: Path) -> set[Fingerprint]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        # ValueError (not TypeError) is deliberate: both callers catch
        # (ValueError, OSError) and warn/return EXIT_CONFIG; a TypeError would
        # escape uncaught. The defect being fixed (I-5) is precisely that
        # data.get() raised an *uncaught* AttributeError here.
        raise ValueError(  # noqa: TRY004
            f"Baseline {path} must be a JSON object, got {type(data).__name__}."
        )
    version = data.get("version")
    if version != BASELINE_VERSION:
        raise ValueError(
            f"Baseline version mismatch: file={version} expected={BASELINE_VERSION}"
        )
    return {Fingerprint.from_dict(item) for item in data.get("fingerprints", [])}


def filter_new(
    violations: list[str],
    baseline: set[Fingerprint],
    *,
    root: Path | None = None,
) -> tuple[list[str], list[Fingerprint]]:
    """Return (violations not in baseline, baseline entries no longer present).

    The first list is what should fail the gate. The second is for "stale
    baseline" warnings — entries that refer to violations the user already
    fixed but forgot to remove from the baseline file.
    """
    new_violations: list[str] = []
    seen: set[Fingerprint] = set()
    for v in violations:
        fp = fingerprint_violation(v, root=root)
        if fp is None:
            new_violations.append(v)
            continue
        if fp in baseline:
            seen.add(fp)
        else:
            new_violations.append(v)
    stale = sorted(baseline - seen, key=lambda fp: (fp.file, fp.rule_id))
    return new_violations, stale
