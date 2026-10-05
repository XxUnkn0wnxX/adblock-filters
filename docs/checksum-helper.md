# 🔐 Checksum Helper

Use the checksum helper after editing a custom filter to refresh its existing
`! Checksum:` header and update its `TimeUpdated` and `Last modified` fields.
It scans the repository's `filters/` tree and leaves upstream mirrors alone.
The helper does not add checksum headers to files that do not already have
one.

See the [filter overview and subscription links](../README.md) for the lists in
this repository.

## 🚀 Usage

Run the helper from the repository root with Python 3:

```sh
python3 helpers/update_checksums.py
```

Preview checksum changes without writing files:

```sh
python3 helpers/update_checksums.py --dry-run
```

Refresh dates and rewrite every eligible checksum header, including headers
that are already current:

```sh
python3 helpers/update_checksums.py --force
```

Combine force mode with a preview to see which eligible files would be
rewritten:

```sh
python3 helpers/update_checksums.py --dry-run --force
```

Show the command options:

```sh
python3 helpers/update_checksums.py --help
```

The helper can also be called from another working directory; it locates the
repository relative to its own script. It uses the Python standard library and
does not need a package install. You can also run it directly if executable:

```sh
./helpers/update_checksums.py --dry-run
```

| Option | Effect |
| --- | --- |
| `-h`, `--help` | Print usage and exit. |
| `-n`, `--dry-run` | Report planned changes without writing any files, including when combined with force mode. |
| `-f`, `--force` | Refresh dates and rewrite every eligible checksum header, even when its checksum is current. |

## 👀 Output

Output groups eligible files by their folders within `filters/`. Files directly
inside `filters/` appear at the top level; nested folders add an indentation
level. Each filename has its status, checksum, and both update dates beneath
it. Changed files show the old and new values, for example:

```text
youtube
  yt-annoyances.txt [updated]
    Checksum: 5PfSVn0Us5tiznLM5cEZ7Q -> NQf92riUaOGfXZHK7t5pYw
    TimeUpdated: 2026-10-05T00:04:17+00:00 -> 2026-10-05T00:39:49+00:00
    Last modified: 2026-10-05T00:04:17+00:00 -> 2026-10-05T00:39:49+00:00
```

- **`skipped`:** The custom list was checked and needs no update; its existing
  metadata is displayed and the file is left unchanged.
- **`updated` / `forced`:** The displayed new values were written to the file.
- **`would update` / `would force`:** Dry-run previews the same metadata changes
  without writing them.

Missing and empty fields are displayed as `(missing)` and `(empty)`.
The final totals count only eligible custom lists and their result statuses.
`skipped (no update needed)` counts lists whose checksums are already current.
Upstream directories and files without checksum headers do not appear in the
output or contribute to any total.

## 🗂️ Which files are checked?

The helper recursively scans regular files under `filters/`, regardless of
extension, and selects files that already contain a `! Checksum:` comment.
Every directory named `upstream` is excluded, without regard to letter case.
Symbolic links are not followed.

For example, `filters/youtube/yt-annoyances.txt` is eligible when it has a
checksum header. Both files under `filters/youtube/upstream/` are outside the
helper's scope, including all output and counts. Files without checksum headers
are also outside its reporting totals; no placeholder files are needed for
other domains or mirrors.

By default, the helper compares the stored checksum with the checksum
calculated from the file as it currently stands, including its current dates.
If they differ, it refreshes `TimeUpdated` and `Last modified` to the same
current UTC timestamp, then calculates and writes the final checksum. A
current file is left byte-for-byte unchanged, including its dates. Force mode
refreshes dates and checksum for every eligible file, even when its checksum
is current. Dry-run mode reports the planned changes without writing anything,
including when combined with force mode.

Neither mode creates a missing checksum header. If timestamps are missing
when an eligible file is updated, the helper adds them; otherwise it replaces
the existing fields in place. `Version` is always managed manually. If the
helper finds multiple checksum headers or invalid UTF-8 while preparing
changes, it reports an error before writing any files. Rewrites preserve file
permissions, line-ending style, and body bytes outside the updated timestamp
and checksum headers. The checksum header is placed on the first line for
AdGuard compatibility.

## 📝 Updating a custom list

For a substantive custom-list change, finish the list content before running
the helper. A typical sequence is:

1. Edit the rules or include directives in the custom list.
2. Increment `Version` by one patch level when needed, such as `1.0.0` to
   `1.0.1`, unless the user directs otherwise. The helper never changes
   `Version`.
3. Run the helper. When an update is needed, it refreshes `TimeUpdated` and
   `Last modified` to the same current UTC ISO 8601 timestamp with `+00:00`,
   then calculates and writes the final checksum.
4. Review the preview and resulting diff before committing:

   ```sh
   python3 helpers/update_checksums.py --dry-run
   git diff --check
   git diff
   ```

Upstream-only updates and checksum verification without a content change do not
require a version bump. A forced rewrite refreshes dates even without a content
change. `Expires: 6 hours (update frequency)` is the client update-check
interval; it does not set a release schedule and should stay unchanged unless
explicitly requested. User instructions may override the usual version/date
handling.

## 🧮 How the checksum is calculated

When a checksum update is triggered, the helper refreshes dates before
calculating the final checksum. The checksum excludes its own `! Checksum:`
comment, so writing it does not change the next calculation. If a list contains
an `!#include` directive, the literal directive is hashed; the included file's
contents are not expanded into the checksum input. The checksum is an MD5
digest of normalized UTF-8 content, encoded as Base64 without padding.
Normalization removes carriage returns and collapses repeated line feeds,
following the
[AdGuard FiltersDownloader checksum implementation](https://github.com/AdguardTeam/FiltersDownloader/blob/master/src/checksum.ts).

## 🧪 Tests

Set up the development environment once, from the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

The virtual environment and pytest/Python bytecode caches are ignored by the
repository.

Then run the focused helper tests with pytest:

```sh
python -m pytest tests/helper
```

The tests use isolated temporary fixtures and cover file discovery and
exclusions, automatic date updates, unchanged versions, no-op and dry-run
safety, LF and CRLF files, relocated headers, checksum validity, and invalid
input safety. Run this suite after
changing the helper or checksum algorithm. For a custom-list-only edit, use the
helper, preview, and diff checks above.

See the [helper source](../helpers/update_checksums.py) and
[helper tests](../tests/helper/test_update_checksums.py).
