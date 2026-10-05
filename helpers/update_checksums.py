#!/usr/bin/env python3
"""Refresh timestamps and AdGuard checksums in existing custom-list headers."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


HEADER_LINE = re.compile(
    r"^[\t ]*![\t ]*checksum[\t :\-]+[^\r\n]*(?:\r\n|\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
ADGUARD_CHECKSUM = re.compile(
    r"^\s*!\s*checksum[\s:-]+([\w+/=]+).*[\r\n]+",
    re.IGNORECASE,
)
# Match the final digest's length: AdGuard searches only the first 200 characters.
PLACEHOLDER = "0000000000000000000000"
TIME_UPDATED_LINE = re.compile(
    r"^[\t ]*![\t ]*time[\t ]*updated[\t ]*:[^\r\n]*(?:\r\n|\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
LAST_MODIFIED_LINE = re.compile(
    r"^[\t ]*![\t ]*last[\t -]*modified[\t ]*:[^\r\n]*(?:\r\n|\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
CHECKSUM_VALUE = re.compile(r"^[\t ]*![\t ]*checksum[\t :\-]+(.*)$", re.IGNORECASE)


class ChecksumError(Exception):
    """Raised when a checksum candidate cannot be processed safely."""


@dataclass
class PlannedFile:
    path: Path
    relative_path: str
    content: bytes
    needs_update: bool
    mode: int
    old_checksum: str
    new_checksum: str
    old_time_updated: Optional[str]
    new_time_updated: str
    old_last_modified: Optional[str]
    new_last_modified: str


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh timestamps and checksums for stale lists under filters/; "
            "never add missing checksum headers or change versions."
        )
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="report planned changes without writing"
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="refresh dates and rewrite every eligible file, even if its checksum is current",
    )
    return parser.parse_args(argv)


def regular_filter_files(filters_root: Path) -> List[Path]:
    files: List[Path] = []

    def raise_walk_error(error: OSError) -> None:
        raise error

    for root, directory_names, file_names in os.walk(
        filters_root, topdown=True, followlinks=False, onerror=raise_walk_error
    ):
        current = Path(root)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name.lower() != "upstream" and not (current / name).is_symlink()
        )
        for name in sorted(file_names):
            file_path = current / name
            if file_path.is_symlink():
                continue
            try:
                file_mode = file_path.lstat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISREG(file_mode):
                files.append(file_path)
    return files


def remove_official_checksum(candidate: str) -> str:
    match = ADGUARD_CHECKSUM.search(candidate[:200])
    if match is None:
        raise ChecksumError("could not form an AdGuard checksum header within the first 200 characters")
    return candidate.replace(match.group(0), "", 1)


def calculate_checksum(body: str, line_ending: str) -> str:
    candidate = f"! Checksum: {PLACEHOLDER}{line_ending}{body}"
    normalized = remove_official_checksum(candidate)
    normalized = normalized.replace("\r", "")
    normalized = re.sub(r"\n+", "\n", normalized)
    digest = hashlib.md5(normalized.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii").rstrip("=")


def replace_timestamp(
    body: str,
    pattern: re.Pattern[str],
    canonical_name: str,
    timestamp: str,
    relative_path: str,
) -> tuple[str, bool]:
    matches = list(pattern.finditer(body))
    if len(matches) > 1:
        raise ChecksumError(f"{relative_path}: found multiple {canonical_name} aliases")
    if not matches:
        return body, False

    match = matches[0]
    if match.group(0).endswith("\r\n"):
        line_ending = "\r\n"
    elif match.group(0).endswith("\n"):
        line_ending = "\n"
    else:
        line_ending = ""
    replacement = f"! {canonical_name}: {timestamp}{line_ending}"
    return body[: match.start()] + replacement + body[match.end() :], True


def timestamp_value(body: str, pattern: re.Pattern[str]) -> Optional[str]:
    match = pattern.search(body)
    if match is None:
        return None
    return match.group(0).rstrip("\r\n").split(":", 1)[1].strip()


def display_value(value: Optional[str]) -> str:
    if value is None:
        return "(missing)"
    return value if value else "(empty)"


def plan_status(plan: PlannedFile, dry_run: bool, force: bool) -> str:
    if dry_run:
        if force:
            return "would force"
        return "would update" if plan.needs_update else "current"
    if force:
        return "forced"
    return "updated" if plan.needs_update else "current"


def plan_details(plan: PlannedFile, status: str) -> List[str]:
    if status in ("updated", "forced", "would update", "would force"):
        checksum = f"{display_value(plan.old_checksum)} -> {display_value(plan.new_checksum)}"
        updated = f"{display_value(plan.old_time_updated)} -> {display_value(plan.new_time_updated)}"
        modified = f"{display_value(plan.old_last_modified)} -> {display_value(plan.new_last_modified)}"
    else:
        checksum = display_value(plan.old_checksum)
        updated = display_value(plan.old_time_updated)
        modified = display_value(plan.old_last_modified)
    return [
        f"Checksum: {checksum}",
        f"TimeUpdated: {updated}",
        f"Last modified: {modified}",
    ]


def print_plan_tree(plans: List[PlannedFile], statuses: dict[str, str]) -> None:
    root: dict = {"directories": {}, "files": []}
    for plan in plans:
        parts = Path(plan.relative_path).parts[1:]
        node = root
        for directory in parts[:-1]:
            node = node["directories"].setdefault(directory, {"directories": {}, "files": []})
        node["files"].append(plan)

    def print_node(node: dict, indentation: int) -> None:
        for plan in sorted(node["files"], key=lambda entry: Path(entry.relative_path).name):
            status = statuses[plan.relative_path]
            prefix = " " * indentation
            print(f"{prefix}{Path(plan.relative_path).name} [{status}]")
            for detail in plan_details(plan, status):
                print(f"{prefix}  {detail}")
        for name in sorted(node["directories"]):
            print(f"{' ' * indentation}{name}")
            print_node(node["directories"][name], indentation + 2)

    print_node(root, 0)


def line_ending_for(header: re.Match[str], text: str) -> str:
    matched_header = header.group(0)
    if matched_header.endswith("\r\n"):
        return "\r\n"
    if matched_header.endswith("\n"):
        return "\n"
    existing = re.search(r"\r\n|\n", text)
    return existing.group(0) if existing is not None else "\n"


def preflight_file(
    file_path: Path,
    repo_root: Path,
    timestamp: str,
    force: bool,
) -> PlannedFile | None:
    raw_content = file_path.read_bytes()
    searchable_text = raw_content.decode("utf-8", errors="replace")
    headers = list(HEADER_LINE.finditer(searchable_text))
    relative_path = file_path.relative_to(repo_root).as_posix()

    if not headers:
        return None
    if len(headers) > 1:
        raise ChecksumError(f"{relative_path}: found {len(headers)} checksum headers")

    try:
        text = raw_content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ChecksumError(f"{relative_path}: checksum candidate is not valid UTF-8") from error

    header = headers[0]
    body = text[: header.start()] + text[header.end() :]
    line_ending = line_ending_for(header, text)
    value_match = CHECKSUM_VALUE.match(header.group(0).rstrip("\r\n"))
    stored_checksum = value_match.group(1).strip() if value_match else ""
    old_time_updated = timestamp_value(body, TIME_UPDATED_LINE)
    old_last_modified = timestamp_value(body, LAST_MODIFIED_LINE)
    # Compare before refreshing dates so a current list remains unchanged.
    current_checksum = calculate_checksum(body, line_ending)
    needs_update = force or stored_checksum != current_checksum

    updated_body, has_time_updated = replace_timestamp(
        body, TIME_UPDATED_LINE, "TimeUpdated", timestamp, relative_path
    )
    updated_body, has_last_modified = replace_timestamp(
        updated_body, LAST_MODIFIED_LINE, "Last modified", timestamp, relative_path
    )

    if not needs_update:
        updated_text = text
        new_checksum = stored_checksum
        new_time_updated = old_time_updated or ""
        new_last_modified = old_last_modified or ""
    else:
        missing_fields = ""
        if not has_time_updated:
            missing_fields += f"! TimeUpdated: {timestamp}{line_ending}"
        if not has_last_modified:
            missing_fields += f"! Last modified: {timestamp}{line_ending}"
        updated_body = missing_fields + updated_body
        new_checksum = calculate_checksum(updated_body, line_ending)
        new_time_updated = timestamp_value(updated_body, TIME_UPDATED_LINE) or ""
        new_last_modified = timestamp_value(updated_body, LAST_MODIFIED_LINE) or ""
        updated_text = f"! Checksum: {new_checksum}{line_ending}{updated_body}"

    original_mode = stat.S_IMODE(file_path.lstat().st_mode)
    return PlannedFile(
        path=file_path,
        relative_path=relative_path,
        content=updated_text.encode("utf-8"),
        needs_update=needs_update,
        mode=original_mode,
        old_checksum=stored_checksum,
        new_checksum=new_checksum,
        old_time_updated=old_time_updated,
        new_time_updated=new_time_updated,
        old_last_modified=old_last_modified,
        new_last_modified=new_last_modified,
    )


def atomic_replace(file_path: Path, content: bytes, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{file_path.name}.update-checksums-",
        suffix=".tmp",
        dir=file_path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.chmod(temporary_path, mode, follow_symlinks=False)
        os.replace(temporary_path, file_path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    filters_root = repo_root / "filters"
    if filters_root.is_symlink() or not filters_root.is_dir():
        print("update_checksums: filters/ is missing or is not a directory", file=sys.stderr)
        return 1

    try:
        files = regular_filter_files(filters_root)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        plans: List[PlannedFile] = []
        skipped_without_checksum = 0
        for file_path in files:
            plan = preflight_file(file_path, repo_root, timestamp, args.force)
            if plan is None:
                skipped_without_checksum += 1
            else:
                plans.append(plan)
    except (OSError, ChecksumError) as error:
        print(f"update_checksums: {error}", file=sys.stderr)
        return 1

    counts = {
        "updated": 0,
        "forced": 0,
        "would update": 0,
        "would force": 0,
        "current": 0,
    }
    statuses: dict[str, str] = {}
    for plan in plans:
        state = plan_status(plan, args.dry_run, args.force)
        counts[state] += 1
        statuses[plan.relative_path] = state

    if not args.dry_run:
        try:
            for plan in plans:
                if plan.needs_update:
                    atomic_replace(plan.path, plan.content, plan.mode)
        except OSError as error:
            print(f"update_checksums: {error}", file=sys.stderr)
            return 1

    print_plan_tree(plans, statuses)
    print(
        "Totals: "
        f"{len(files)} files scanned, {len(plans)} with checksum headers, "
        f"{skipped_without_checksum} skipped without headers, "
        f"{counts['updated']} updated, {counts['forced']} forced, "
        f"{counts['would update']} would update, {counts['would force']} would force, "
        f"{counts['current']} current."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
