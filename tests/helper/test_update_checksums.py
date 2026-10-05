import base64
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER_SOURCE = PROJECT_ROOT / "helpers" / "update_checksums.py"
OFFICIAL_CHECKSUM = re.compile(r"^\s*!\s*checksum[\s:-]+([\w+/=]+).*[\r\n]+", re.IGNORECASE)
TIME_UPDATED_VALUE = re.compile(r"^[\t ]*![\t ]*time[\t ]*updated[\t ]*:[\t ]*(.*?)[\t ]*$", re.IGNORECASE)
LAST_MODIFIED_VALUE = re.compile(r"^[\t ]*![\t ]*last[\t -]*modified[\t ]*:[\t ]*(.*?)[\t ]*$", re.IGNORECASE)
TIMESTAMP_LINES = re.compile(
    rb"^[\t ]*![\t ]*(?:time[\t ]*updated|last[\t -]*modified)[\t ]*:[^\r\n]*(?:\r\n|\n|$)",
    re.IGNORECASE | re.MULTILINE,
)


def official_checksum(content: str) -> str:
    match = OFFICIAL_CHECKSUM.search(content[:200])
    if match:
        content = content.replace(match.group(0), "", 1)
    normalized = re.sub(r"\n+", "\n", content.replace("\r", ""))
    return base64.b64encode(hashlib.md5(normalized.encode("utf-8")).digest()).decode("ascii").rstrip("=")


def checked_list(body: str, line_ending: str = "\n") -> str:
    placeholder = f"! Checksum: 0000000000000000000000{line_ending}{body}"
    checksum = official_checksum(placeholder)
    return f"! Checksum: {checksum}{line_ending}{body}"


def fixture_repo(tmp_path: Path) -> Tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    helper = repo_root / "helpers" / "update_checksums.py"
    helper.parent.mkdir(parents=True)
    shutil.copy2(HELPER_SOURCE, helper)
    helper.chmod(0o755)
    (repo_root / "filters").mkdir()
    return repo_root, helper


def run_helper(
    repo_root: Path,
    helper: Path,
    *args: str,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(helper), *args],
        cwd=cwd or repo_root,
        capture_output=True,
        check=False,
        text=True,
    )


def assert_valid_checksum(file_path: Path) -> None:
    text = file_path.read_text(encoding="utf-8")
    match = OFFICIAL_CHECKSUM.search(text[:200])
    assert match is not None, f"{file_path} has no checksum visible to AdGuard"
    assert match.group(1).rstrip("=") == official_checksum(text)


def timestamp_values(text: str, pattern: re.Pattern[str]) -> list[str]:
    values = []
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            values.append(match.group(1).strip())
    return values


def assert_fresh_timestamps(text: str) -> str:
    updated = timestamp_values(text, TIME_UPDATED_VALUE)
    modified = timestamp_values(text, LAST_MODIFIED_VALUE)
    assert len(updated) == 1
    assert len(modified) == 1
    assert updated[0] == modified[0]
    parsed = datetime.fromisoformat(updated[0])
    assert parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0
    assert updated[0].endswith("+00:00")
    return updated[0]


def without_timestamp_lines(content: bytes) -> bytes:
    return TIMESTAMP_LINES.sub(b"", content)


def test_checksum_oracle_matches_known_adguard_fixture() -> None:
    body = "! Title: Known fixture\n! Description: Known filter\nexample.com##.ad\n"
    assert official_checksum(f"! Checksum: 0000000000000000000000\n{body}") == "wDhlhUXYGOfEsYF3OAWnbA"


def test_recurses_domains_and_filenames_with_spaces_from_another_cwd(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    root_file = repo_root / "filters" / "root list.txt"
    first = repo_root / "filters" / "youtube" / "list with spaces.txt"
    sibling = repo_root / "filters" / "youtube" / "another.txt"
    second = repo_root / "filters" / "example" / "nested" / "no-extension"
    root_file.parent.mkdir(parents=True, exist_ok=True)
    first.parent.mkdir(parents=True)
    sibling.parent.mkdir(parents=True, exist_ok=True)
    second.parent.mkdir(parents=True)
    root_contents = checked_list(
        "! Title: Root list\n! Version: 1.0.0\n"
        "! TimeUpdated: 2020-01-01T00:00:00+00:00\n"
        "! Last modified: 2020-01-01T00:00:00+00:00\nexample.net##.ad\n"
    )
    sibling_contents = checked_list(
        "! Title: Sibling\n! Version: 1.0.0\n"
        "! TimeUpdated: 2020-01-01T00:00:00+00:00\n"
        "! Last modified: 2020-01-01T00:00:00+00:00\nexample.org##.ad\n"
    )
    root_file.write_text(root_contents, encoding="utf-8")
    first_body = (
        "! Title: YouTube\n! Version: 1.4.2\n"
        "! Time Updated: 2020-01-01T00:00:00+00:00\n"
        "! Last-Modified: 2020-01-01T00:00:00+00:00\nexample.com##.ad\n"
    )
    second_body = (
        "! Title: Example\n! Version: 2.0.7\n"
        "! TimeUpdated: 2020-01-01T00:00:00+00:00\n"
        "! LastModified: 2020-01-01T00:00:00+00:00\nexample.org##.banner\n"
    )
    first.write_text(f"! Checksum: stale\n{first_body}", encoding="utf-8")
    sibling.write_text(sibling_contents, encoding="utf-8")
    second.write_text(f"! Checksum: stale\n{second_body}", encoding="utf-8")
    first.chmod(0o640)

    result = run_helper(repo_root, helper, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "root list.txt [skipped]\n  Checksum: " in result.stdout
    assert "example\n  nested\n    no-extension [updated]" in result.stdout
    assert "youtube\n  another.txt [skipped]" in result.stdout
    assert "  list with spaces.txt [updated]" in result.stdout
    assert "filters/" not in result.stdout
    assert "    Checksum: " in result.stdout
    assert_valid_checksum(first)
    assert_valid_checksum(second)
    first_text = first.read_text(encoding="utf-8")
    second_text = second.read_text(encoding="utf-8")
    assert "! Version: 1.4.2\n" in first_text
    assert "! Version: 2.0.7\n" in second_text
    first_timestamp = assert_fresh_timestamps(first_text)
    assert assert_fresh_timestamps(second_text) == first_timestamp
    first_checksum = OFFICIAL_CHECKSUM.search(first_text[:200]).group(1)
    second_checksum = OFFICIAL_CHECKSUM.search(second_text[:200]).group(1)
    for filename, old_checksum, new_checksum in (
        ("list with spaces.txt", "stale", first_checksum),
        ("no-extension", "stale", second_checksum),
    ):
        assert f"{filename} [updated]" in result.stdout
        assert f"  Checksum: {old_checksum} -> {new_checksum}" in result.stdout
        assert f"  TimeUpdated: 2020-01-01T00:00:00+00:00 -> {first_timestamp}" in result.stdout
        assert f"  Last modified: 2020-01-01T00:00:00+00:00 -> {first_timestamp}" in result.stdout
    assert stat.S_IMODE(first.stat().st_mode) == 0o640
    assert not any("update-checksums-" in name for name in os.listdir(first.parent))

    stable_bytes = {file_path: file_path.read_bytes() for file_path in (first, second, root_file, sibling)}
    stable_stats = {file_path: file_path.stat() for file_path in (first, second, root_file, sibling)}
    second_run = run_helper(repo_root, helper)
    assert second_run.returncode == 0, second_run.stderr
    assert "[skipped]" in second_run.stdout
    for file_path in stable_bytes:
        assert file_path.read_bytes() == stable_bytes[file_path]
        assert file_path.stat().st_mtime_ns == stable_stats[file_path].st_mtime_ns
        assert file_path.stat().st_ino == stable_stats[file_path].st_ino


def test_current_checksum_is_noop_and_preserves_mtime(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    file_path = repo_root / "filters" / "youtube" / "current.txt"
    file_path.parent.mkdir(parents=True)
    contents = checked_list(
        "! Title: Current\n! Version: 1.0.0\n"
        "! TimeUpdated: 2020-01-01T00:00:00+00:00\n"
        "! Last modified: 2020-01-01T00:00:00+00:00\nexample.com##.ad\n"
    )
    file_path.write_text(contents, encoding="utf-8")
    known_time = 1_577_934_245_000_000_000
    os.utime(file_path, ns=(known_time, known_time))
    before = file_path.stat()

    result = run_helper(repo_root, helper)
    after = file_path.stat()
    assert result.returncode == 0, result.stderr
    assert "current.txt [skipped]" in result.stdout
    assert f"  Checksum: {OFFICIAL_CHECKSUM.search(contents[:200]).group(1)}" in result.stdout
    assert "  TimeUpdated: 2020-01-01T00:00:00+00:00" in result.stdout
    assert "  Last modified: 2020-01-01T00:00:00+00:00" in result.stdout
    assert file_path.read_text(encoding="utf-8") == contents
    assert "2020-01-01T00:00:00+00:00" in file_path.read_text(encoding="utf-8")
    assert after.st_mtime_ns == before.st_mtime_ns
    assert after.st_ino == before.st_ino


def test_missing_timestamp_fields_stay_missing_until_a_checksum_update(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    file_path = repo_root / "filters" / "youtube" / "no-dates.txt"
    file_path.parent.mkdir(parents=True)
    contents = checked_list("! Title: No dates\n! Version: 1.0.4\nexample.com##.ad\n")
    file_path.write_text(contents, encoding="utf-8")

    normal = run_helper(repo_root, helper)
    assert normal.returncode == 0, normal.stderr
    assert file_path.read_text(encoding="utf-8") == contents
    assert "TimeUpdated" not in contents
    assert "Last modified" not in contents

    forced = run_helper(repo_root, helper, "--force")
    updated = file_path.read_text(encoding="utf-8")
    assert forced.returncode == 0, forced.stderr
    assert "! Version: 1.0.4\n" in updated
    assert_fresh_timestamps(updated)
    assert_valid_checksum(file_path)


def load_helper_module(helper: Path):
    module_name = f"update_checksums_fixture_{abs(hash(helper))}"
    spec = importlib.util.spec_from_file_location(module_name, helper)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_force_rewrites_same_bytes_when_run_timestamp_is_unchanged(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    file_path = repo_root / "filters" / "youtube" / "force-twice.txt"
    file_path.parent.mkdir(parents=True)
    body = (
        "! Title: Force twice\n! Version: 4.0.9\n"
        "! TimeUpdated: 2020-01-01T00:00:00+00:00\n"
        "! Last modified: 2020-01-01T00:00:00+00:00\nexample.com##.ad\n"
    )
    file_path.write_text(checked_list(body), encoding="utf-8")
    helper_module = load_helper_module(helper)
    fixed_timestamp = datetime(2026, 10, 5, 3, 14, 15, tzinfo=timezone.utc)

    class FixedDateTime:
        @staticmethod
        def now(tz):
            assert tz is timezone.utc
            return fixed_timestamp

    monkeypatch.setattr(helper_module, "datetime", FixedDateTime)
    old_checksum = OFFICIAL_CHECKSUM.search(file_path.read_text(encoding="utf-8")[:200]).group(1)
    assert helper_module.main(["--force"]) == 0
    first_output = capsys.readouterr().out
    first_bytes = file_path.read_bytes()
    first_inode = file_path.stat().st_ino
    updated_text = first_bytes.decode("utf-8")
    assert "! Version: 4.0.9\n" in updated_text
    assert_fresh_timestamps(updated_text)
    assert_valid_checksum(file_path)
    new_checksum = OFFICIAL_CHECKSUM.search(updated_text[:200]).group(1)
    assert f"  Checksum: {old_checksum} -> {new_checksum}" in first_output
    assert "  TimeUpdated: 2020-01-01T00:00:00+00:00 -> 2026-10-05T03:14:15+00:00" in first_output
    assert "  Last modified: 2020-01-01T00:00:00+00:00 -> 2026-10-05T03:14:15+00:00" in first_output

    assert helper_module.main(["--force"]) == 0
    second_output = capsys.readouterr().out
    assert file_path.read_bytes() == first_bytes
    assert file_path.stat().st_ino != first_inode
    assert f"  Checksum: {new_checksum} -> {new_checksum}" in second_output
    assert "  TimeUpdated: 2026-10-05T03:14:15+00:00 -> 2026-10-05T03:14:15+00:00" in second_output


def test_force_rewrites_existing_only_and_skips_nested_upstream_and_symlinks(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    filters = repo_root / "filters"
    forced_file = filters / "site" / "custom file"
    no_header = filters / "site" / "no-header"
    upper_upstream = filters / "site" / "UPSTREAM" / "nested" / "list.txt"
    nested_upstream = filters / "site" / "nested" / "UpStReAm" / "list"
    outside_file = tmp_path / "outside-list.txt"
    outside_dir_file = tmp_path / "outside-directory" / "linked.txt"
    symlink_file = filters / "site" / "linked-list"
    symlink_dir = filters / "site" / "linked-directory"
    for file_path in (forced_file, no_header, upper_upstream, nested_upstream, outside_file, outside_dir_file):
        file_path.parent.mkdir(parents=True, exist_ok=True)
    current = checked_list(
        "! Title: Force\n! Version: 3.2.1\n"
        "! TimeUpdated: 2020-01-01T00:00:00+00:00\n"
        "! Last modified: 2020-01-01T00:00:00+00:00\nexample.com##.ad\n"
    )
    forced_file.write_text(current, encoding="utf-8")
    no_header.write_text("! Title: No checksum\nexample.net##.ad\n", encoding="utf-8")
    upper_upstream.write_text(current, encoding="utf-8")
    nested_upstream.write_text(current, encoding="utf-8")
    outside_file.write_text(current, encoding="utf-8")
    outside_dir_file.write_text(current, encoding="utf-8")
    symlink_file.symlink_to(outside_file)
    symlink_dir.symlink_to(outside_dir_file.parent, target_is_directory=True)
    old_time = 1_577_934_245_000_000_000
    os.utime(forced_file, ns=(old_time, old_time))
    os.utime(no_header, ns=(old_time, old_time))
    forced_before = forced_file.stat()
    missing_before = no_header.stat()
    excluded_files = (upper_upstream, nested_upstream, outside_file, outside_dir_file)
    excluded_before = {file_path: file_path.stat() for file_path in excluded_files}

    result = run_helper(repo_root, helper, "--force")
    assert result.returncode == 0, result.stderr
    assert "custom file [forced]" in result.stdout
    assert "no-header" not in result.stdout
    assert "UPSTREAM" not in result.stdout
    assert "UpStReAm" not in result.stdout
    assert "linked-list" not in result.stdout
    assert "linked-directory" not in result.stdout
    assert "Totals: 1 filter checked, 0 updated, 1 forced, 0 would update, 0 would force, 0 skipped (no update needed)." in result.stdout
    assert forced_file.stat().st_mtime_ns > forced_before.st_mtime_ns
    forced_text = forced_file.read_text(encoding="utf-8")
    assert "! Version: 3.2.1\n" in forced_text
    assert_fresh_timestamps(forced_text)
    assert no_header.stat().st_mtime_ns == missing_before.st_mtime_ns
    assert no_header.read_text(encoding="utf-8") == "! Title: No checksum\nexample.net##.ad\n"
    assert upper_upstream.read_text(encoding="utf-8") == current
    assert nested_upstream.read_text(encoding="utf-8") == current
    assert outside_file.read_text(encoding="utf-8") == current
    assert outside_dir_file.read_text(encoding="utf-8") == current
    for file_path, before in excluded_before.items():
        after = file_path.stat()
        assert after.st_mtime_ns == before.st_mtime_ns
        assert after.st_ino == before.st_ino
    assert symlink_file.is_symlink()
    assert symlink_dir.is_symlink()


def test_dry_run_and_dry_run_force_do_not_write(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    directory = repo_root / "filters" / "youtube"
    directory.mkdir(parents=True)
    current_file = directory / "current.txt"
    stale_file = directory / "stale.txt"
    no_header_files = [directory / f"ignored-{index}.txt" for index in range(4)]
    upstream_files = [
        directory / "upstream" / "source.txt",
        directory / "nested" / "UPSTREAM" / "source.txt",
    ]
    current = checked_list(
        "! Title: Dry run\n! Version: 1.0.0\n"
        "! TimeUpdated: 2020-01-01T00:00:00+00:00\n"
        "! Last modified: 2020-01-01T00:00:00+00:00\nexample.com##.ad\n"
    )
    stale = (
        "! Checksum: stale\n! Title: Dry run\n! Version: 1.0.1\n"
        "! TimeUpdated: 2020-01-01T00:00:00+00:00\n"
        "! Last modified: 2020-01-01T00:00:00+00:00\nexample.net##.ad\n"
    )
    current_file.write_text(current, encoding="utf-8")
    stale_file.write_text(stale, encoding="utf-8")
    for index, file_path in enumerate(no_header_files):
        file_path.write_text(f"! Title: Ignore {index}\nexample.org##.ad\n", encoding="utf-8")
    for file_path in upstream_files:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(current, encoding="utf-8")
    known_time = 1_577_934_245_000_000_000
    for file_path in (current_file, stale_file):
        os.utime(file_path, ns=(known_time, known_time))
    before_bytes = {current_file: current_file.read_bytes(), stale_file: stale_file.read_bytes()}
    before_stats = {current_file: current_file.stat(), stale_file: stale_file.stat()}

    ordinary_dry_run = run_helper(repo_root, helper, "--dry-run")
    assert ordinary_dry_run.returncode == 0, ordinary_dry_run.stderr
    assert "stale.txt [would update]" in ordinary_dry_run.stdout
    assert "current.txt [skipped]" in ordinary_dry_run.stdout
    assert "Totals: 2 filters checked, 0 updated, 0 forced, 1 would update, 0 would force, 1 skipped (no update needed)." in ordinary_dry_run.stdout
    assert all(file_path.name not in ordinary_dry_run.stdout for file_path in no_header_files + upstream_files)

    for file_path in before_bytes:
        assert file_path.read_bytes() == before_bytes[file_path]
        assert file_path.stat().st_mtime_ns == before_stats[file_path].st_mtime_ns
        assert file_path.stat().st_ino == before_stats[file_path].st_ino

    normal_update = run_helper(repo_root, helper)
    assert normal_update.returncode == 0, normal_update.stderr
    assert "stale.txt [updated]" in normal_update.stdout
    assert "current.txt [skipped]" in normal_update.stdout
    assert "Totals: 2 filters checked, 1 updated, 0 forced, 0 would update, 0 would force, 1 skipped (no update needed)." in normal_update.stdout
    before_force_bytes = {current_file: current_file.read_bytes(), stale_file: stale_file.read_bytes()}
    before_force_stats = {current_file: current_file.stat(), stale_file: stale_file.stat()}

    forced_dry_run = run_helper(repo_root, helper, "--dry-run", "--force")
    assert forced_dry_run.returncode == 0, forced_dry_run.stderr
    assert "current.txt [would force]" in forced_dry_run.stdout
    assert "stale.txt [would force]" in forced_dry_run.stdout
    for file_content in before_force_bytes.values():
        old_checksum = OFFICIAL_CHECKSUM.search(file_content.decode("utf-8")[:200]).group(1)
        assert f"Checksum: {old_checksum} -> " in forced_dry_run.stdout
    assert "  TimeUpdated: 2020-01-01T00:00:00+00:00 -> " in forced_dry_run.stdout
    assert "  Last modified: 2020-01-01T00:00:00+00:00 -> " in forced_dry_run.stdout
    assert "Totals: 2 filters checked, 0 updated, 0 forced, 0 would update, 2 would force, 0 skipped (no update needed)." in forced_dry_run.stdout
    for file_path in before_force_bytes:
        after = file_path.stat()
        assert file_path.read_bytes() == before_force_bytes[file_path]
        assert after.st_mtime_ns == before_force_stats[file_path].st_mtime_ns
        assert after.st_ino == before_force_stats[file_path].st_ino


def test_dry_run_force_previews_exact_values_for_a_current_file(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    file_path = repo_root / "filters" / "youtube" / "current.txt"
    file_path.parent.mkdir(parents=True)
    body = (
        "! Title: Current force preview\n! Version: 1.2.3\n"
        "! TimeUpdated: 2020-01-01T00:00:00+00:00\n"
        "! Last modified: 2020-01-01T00:00:00+00:00\nexample.com##.ad\n"
    )
    file_path.write_text(checked_list(body), encoding="utf-8")
    before_bytes = file_path.read_bytes()
    before_stat = file_path.stat()
    helper_module = load_helper_module(helper)
    fixed_timestamp = datetime(2026, 10, 5, 3, 14, 15, tzinfo=timezone.utc)

    class FixedDateTime:
        @staticmethod
        def now(tz):
            assert tz is timezone.utc
            return fixed_timestamp

    monkeypatch.setattr(helper_module, "datetime", FixedDateTime)
    assert helper_module.main(["--dry-run", "--force"]) == 0
    output = capsys.readouterr().out
    old_checksum = OFFICIAL_CHECKSUM.search(before_bytes.decode("utf-8")[:200]).group(1)
    expected_body = body.replace("2020-01-01T00:00:00+00:00", "2026-10-05T03:14:15+00:00")
    expected_checksum = OFFICIAL_CHECKSUM.search(checked_list(expected_body)[:200]).group(1)
    assert "current.txt [would force]" in output
    assert f"  Checksum: {old_checksum} -> {expected_checksum}" in output
    assert "  TimeUpdated: 2020-01-01T00:00:00+00:00 -> 2026-10-05T03:14:15+00:00" in output
    assert "  Last modified: 2020-01-01T00:00:00+00:00 -> 2026-10-05T03:14:15+00:00" in output
    assert file_path.read_bytes() == before_bytes
    after_stat = file_path.stat()
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns
    assert after_stat.st_ino == before_stat.st_ino


def test_relocates_header_and_preserves_crlf_body_bytes(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    file_path = repo_root / "filters" / "youtube" / "relocated.txt"
    file_path.parent.mkdir(parents=True)
    body = (
        "! Title: Before checksum\r\n"
        "! Time Updated: 2020-01-01T00:00:00+00:00\r\n"
        "! Version: 2.1.0\r\n"
        "! Last-Modified: 2020-01-01T00:00:00+00:00\r\n"
        "! Title: Relocated\r\nexample.com##.ad\r\n"
    )
    prefix = "! Title: First\r\n\r\n"
    file_path.write_bytes(f"{prefix}! checksum : stale\r\n{body}".encode("utf-8"))

    result = run_helper(repo_root, helper)
    assert result.returncode == 0, result.stderr
    updated = file_path.read_bytes()
    match = re.match(rb"^! Checksum: [A-Za-z0-9+/]+\r\n", updated)
    assert match is not None
    original_body = (prefix + body).encode("utf-8")
    assert without_timestamp_lines(updated[match.end() :]) == without_timestamp_lines(original_body)
    assert b"! TimeUpdated: " in updated
    assert b"! Last modified: " in updated
    assert b"\r\n" in updated
    assert_fresh_timestamps(updated.decode("utf-8"))
    assert b"! Version: 2.1.0\r\n" in updated
    assert_valid_checksum(file_path)


def test_matches_adguard_normalization_for_leading_blank_lines(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    file_path = repo_root / "filters" / "youtube" / "leading-blank-lines.txt"
    file_path.parent.mkdir(parents=True)
    body = "\n\n! Title: Leading blanks\nexample.com##.ad\n"
    file_path.write_text(f"! Checksum: stale\n{body}", encoding="utf-8")

    result = run_helper(repo_root, helper)
    assert result.returncode == 0, result.stderr
    assert body in file_path.read_text(encoding="utf-8")
    assert_valid_checksum(file_path)


def test_same_length_placeholder_handles_adguard_200_character_boundary(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    file_path = repo_root / "filters" / "youtube" / "search-boundary.txt"
    file_path.parent.mkdir(parents=True)
    body = "\n" * 170 + "! Title: Search boundary\nexample.com##.ad\n"
    file_path.write_text(f"! Checksum: stale\n{body}", encoding="utf-8")

    result = run_helper(repo_root, helper)
    assert result.returncode == 0, result.stderr
    assert_valid_checksum(file_path)


def test_duplicate_headers_fail_before_any_file_is_rewritten(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    first = repo_root / "filters" / "youtube" / "a-stale.txt"
    duplicate = repo_root / "filters" / "youtube" / "z-duplicate.txt"
    first.parent.mkdir(parents=True)
    stale_bytes = b"! Checksum: stale\n! Title: Stale\nexample.com##.ad\n"
    duplicate_bytes = b"! Checksum: old\n! Title: Duplicate\n! Checksum: again\nexample.net##.ad\n"
    first.write_bytes(stale_bytes)
    duplicate.write_bytes(duplicate_bytes)

    result = run_helper(repo_root, helper)
    assert result.returncode != 0
    assert "found 2 checksum headers" in result.stderr
    assert first.read_bytes() == stale_bytes
    assert duplicate.read_bytes() == duplicate_bytes


def test_invalid_utf8_fails_before_any_file_is_rewritten(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    first = repo_root / "filters" / "youtube" / "a-stale.txt"
    invalid = repo_root / "filters" / "youtube" / "z-invalid.txt"
    first.parent.mkdir(parents=True)
    stale_bytes = b"! Checksum: stale\n! Title: Stale\nexample.com##.ad\n"
    invalid_bytes = b"! Checksum: stale\n! Title: Invalid\n\xff"
    first.write_bytes(stale_bytes)
    invalid.write_bytes(invalid_bytes)

    result = run_helper(repo_root, helper)
    assert result.returncode != 0
    assert "checksum candidate is not valid UTF-8" in result.stderr
    assert first.read_bytes() == stale_bytes
    assert invalid.read_bytes() == invalid_bytes


@pytest.mark.parametrize(
    ("duplicate_lines", "error_text"),
    [
        (
            "! TimeUpdated: 2020-01-01T00:00:00+00:00\n"
            "! Time Updated: 2020-01-02T00:00:00+00:00\n",
            "multiple TimeUpdated aliases",
        ),
        (
            "! Last modified: 2020-01-01T00:00:00+00:00\n"
            "! Last-Modified: 2020-01-02T00:00:00+00:00\n",
            "multiple Last modified aliases",
        ),
    ],
)
def test_duplicate_timestamp_aliases_fail_before_any_write(
    tmp_path: Path, duplicate_lines: str, error_text: str
) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    first = repo_root / "filters" / "youtube" / "a-stale.txt"
    duplicate = repo_root / "filters" / "youtube" / "z-duplicate-dates.txt"
    first.parent.mkdir(parents=True)
    stale_bytes = b"! Checksum: stale\n! Title: Stale\nexample.com##.ad\n"
    duplicate_bytes = (
        "! Checksum: stale\n! Title: Duplicate dates\n"
        f"{duplicate_lines}! Version: 1.0.0\nexample.net##.ad\n"
    ).encode("utf-8")
    first.write_bytes(stale_bytes)
    duplicate.write_bytes(duplicate_bytes)

    result = run_helper(repo_root, helper)
    assert result.returncode != 0
    assert error_text in result.stderr
    assert first.read_bytes() == stale_bytes
    assert duplicate.read_bytes() == duplicate_bytes


def test_help_and_unsupported_arguments(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    help_result = run_helper(repo_root, helper, "--help", cwd=tmp_path)
    assert help_result.returncode == 0, help_result.stderr
    assert "usage:" in help_result.stdout.lower()

    invalid_result = run_helper(repo_root, helper, "--unknown")
    assert invalid_result.returncode != 0
    assert "unrecognized arguments: --unknown" in invalid_result.stderr


def test_rejects_symlink_filters_root_without_touching_target(tmp_path: Path) -> None:
    repo_root, helper = fixture_repo(tmp_path)
    filters_root = repo_root / "filters"
    filters_root.rmdir()
    target_filters = tmp_path / "external-filters"
    target_file = target_filters / "youtube" / "custom.txt"
    target_file.parent.mkdir(parents=True)
    contents = checked_list("! Title: External\nexample.com##.ad\n")
    target_file.write_text(contents, encoding="utf-8")
    filters_root.symlink_to(target_filters, target_is_directory=True)
    before = target_file.stat()

    for flags in (("--force",), ("--dry-run", "--force")):
        result = run_helper(repo_root, helper, *flags)
        after = target_file.stat()
        assert result.returncode != 0
        assert "filters/ is missing or is not a directory" in result.stderr
        assert target_file.read_text(encoding="utf-8") == contents
        assert after.st_mtime_ns == before.st_mtime_ns
        assert after.st_ino == before.st_ino
