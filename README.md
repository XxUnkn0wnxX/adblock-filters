# 🛡️ adblock-filters

**A personal, self-curated adblocking filter list.**

Filters are maintained for my own browsing needs and may change over time.
Each domain has its own folder under `filters/`.

## 📋 Filters and sources

<details>
<summary><strong>▶️ YouTube</strong></summary>

### Custom list

- **Filter list:** [YouTube annoyances](filters/youtube/yt-annoyances.txt).
- **Subscription:** [🛡️ Subscribe to YouTube annoyances](https://subscribe.adblockplus.org/?location=https%3A%2F%2Fraw.githubusercontent.com%2FXxUnkn0wnxX%2Fadblock-filters%2Fmain%2Ffilters%2Fyoutube%2Fyt-annoyances.txt&title=YouTube%20annoyances).

  > **Raw URL fallback:** [Raw YouTube annoyances list](https://raw.githubusercontent.com/XxUnkn0wnxX/adblock-filters/main/filters/youtube/yt-annoyances.txt).

- **Reference only:** The [SponsorBlock mirror](filters/youtube/upstream/sponsorblock.txt),
  pulled from [yt-neuter's SponsorBlock filters](https://github.com/mchangrh/yt-neuter/blob/main/filters/sponsorblock.txt).
- **Reference only:** The latest [tadwohlrapp YouTube filters](filters/youtube/upstream/ublock-filter-youtube.txt).
  Neither upstream mirror is currently included in the custom list.

### Source projects

- [tadwohlrapp's YouTube filters](https://gist.github.com/tadwohlrapp/722bbe97cb20bb34da8df73675415cae/8b2f5e4eba8a8a45f077cb9c4b64ca8f5fdc6075)
- [mchangrh/yt-neuter](https://github.com/mchangrh/yt-neuter)

</details>

<details>
<summary><strong>🧰 Maintaining custom lists</strong></summary>

When I change a custom list, I increment its patch version and keep
`Expires: 6 hours (update frequency)`. After editing, I run the helper. On a
checksum mismatch, it updates
`TimeUpdated` and `Last modified` to the same current UTC timestamp and then
recalculates the checksum. `--force` refreshes dates and checksum even when the
checksum is already current; the helper never changes `Version`.

```sh
python3 helpers/update_checksums.py
python3 helpers/update_checksums.py --dry-run
python3 helpers/update_checksums.py --dry-run --force
python3 helpers/update_checksums.py --force
python3 helpers/update_checksums.py --help
```

The helper excludes `upstream/` directories and never adds a missing checksum
header, even with `--force`. A current checksum leaves dates and file contents
unchanged during a normal run. Upstream-only syncs and checksum-only
verification do not need version or date bumps.

Output groups eligible files by folder within `filters/`, with each filename,
status, and metadata beneath it. Updates and dry runs show **old → new**
checksums and dates. **`skipped` means a custom list is already current**, so its
existing values are displayed. Only lists with checksum headers are reported
and counted; upstream folders and files without checksum headers are excluded.

See the [checksum helper guide](docs/checksum-helper.md) for setup, usage, and
testing.

</details>

<details>
<summary><strong>🔄 Upstream synchronisation and adding sources</strong></summary>

### Upstream synchronisation

The [**Adblock-Synchroniser** workflow](.github/workflows/sync-upstream.yml)
maintains local copies of the configured upstream lists.

**When it runs**

- **On push:** Changes to `.txt` files under `filters/` on `main`, excluding
  `upstream/` folders.
- **Scheduled:** Every six hours, at minute 17 UTC.
- **Manual:** Use **Run workflow** in GitHub Actions.

**How it updates**

- **Changes only:** Compares file contents and commits only changed upstream files.
- **Original contents:** Preserves upstream files without rewriting their rules or comments.
- **Failed downloads:** Keeps the previous copies when a source cannot be downloaded.

The custom list's **version, update dates, and checksum** describe that file and
are maintained when it is edited. The sync workflow updates upstream mirrors
only and does not modify the custom list.

Automated commits use GitHub's built-in `github-actions[bot]` identity. Pushes
made with its workflow token do not trigger another run.

### ➕ Adding upstream sources

1. **Add a source mapping** to the workflow's `UPSTREAM_FILTERS` table:

   ```text
   filters/<domain>/upstream/<filename>.txt https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>.txt
   ```

2. **To use a mirror's rules**, add a relative include directive to the custom
   list:

   ```text
   !#include upstream/<filename>.txt
   ```

   For a **reference-only mirror**, leave out the include.

**Following the latest gist revision:** Use an unpinned raw URL:

```text
https://gist.githubusercontent.com/<user>/<gist-id>/raw/<filename>
```

**uBlock Origin includes:** Include paths
must be relative and stay within the list's directory or a subdirectory. For
example, if I later include the SponsorBlock mirror in
`filters/youtube/yt-annoyances.txt`, `!#include upstream/sponsorblock.txt`
resolves to `filters/youtube/upstream/sponsorblock.txt` in this repository.
Use the Subscribe link above to add the custom list. See the
[uBO include documentation](https://github.com/gorhill/uBlock/wiki/Static-filter-syntax#include-file-name).

</details>

## 📄 License

- **Project license:** [GNU General Public License v3.0](LICENSE.md).
- **Upstream licenses:** Mirrored files retain their original licenses.
- **SponsorBlock mirror:** Released under the
  [Unlicense](https://github.com/mchangrh/yt-neuter/blob/main/LICENSE).
