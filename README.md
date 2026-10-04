# 🛡️ adblock-filters

**A personal, self-curated adblocking filter list.**

Filters are maintained for my own browsing needs and may change over time.
Each domain has its own folder under `filters/`.

## 📋 Filters and sources

<details>
<summary><strong>▶️ YouTube</strong></summary>

### Custom list

- **Filter list:** [YouTube annoyances](filters/youtube/yt-annoyances.txt).
- **Included:** The [SponsorBlock mirror](filters/youtube/upstream/sponsorblock.txt),
  pulled from [yt-neuter's SponsorBlock filters](https://github.com/mchangrh/yt-neuter/blob/main/filters/sponsorblock.txt).
- **Reference only:** The latest [tadwohlrapp YouTube filters](filters/youtube/upstream/ublock-filter-youtube.txt).
  This mirror is available for curation and is not included in the custom list.

### Source projects

- [tadwohlrapp's YouTube filters](https://gist.github.com/tadwohlrapp/722bbe97cb20bb34da8df73675415cae/8b2f5e4eba8a8a45f077cb9c4b64ca8f5fdc6075)
- [mchangrh/yt-neuter](https://github.com/mchangrh/yt-neuter)

</details>

<details>
<summary><strong>🔄 Upstream synchronisation and adding sources</strong></summary>

### Upstream synchronisation

The [**Adblock-Synchroniser** workflow](.github/workflows/sync-upstream.yml)
maintains local copies of the configured upstream lists.

**When it runs**

- **On push:** Every push to `main`.
- **Scheduled:** Every six hours, at minute 17 UTC.
- **Manual:** Use **Run workflow** in GitHub Actions.

**How it updates**

- **Changes only:** Compares file contents and commits only changed upstream files.
- **Original contents:** Preserves upstream files without rewriting their rules or comments.
- **Failed downloads:** Keeps the previous copies when a source cannot be downloaded.

Automated commits use GitHub's built-in `github-actions[bot]` identity. Pushes
made with its workflow token do not trigger another run.

### ➕ Adding upstream sources

1. **Add a source mapping** to the workflow's `UPSTREAM_FILTERS` table:

   ```text
   filters/<domain>/upstream/<filename>.txt https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>.txt
   ```

2. **Include it in your custom list** if you want its rules to apply:

   ```text
   !#include upstream/<filename>.txt
   ```

   For a **reference-only mirror**, leave out the include.

**Following the latest gist revision:** Use an unpinned raw URL:

```text
https://gist.githubusercontent.com/<user>/<gist-id>/raw/<filename>
```

**uBlock Origin includes:** Paths must be relative and stay within the list's
directory or a subdirectory. See the
[uBO include documentation](https://github.com/gorhill/uBlock/wiki/Static-filter-syntax#include-file-name).

</details>

## 📄 License

- **Project license:** [GNU General Public License v3.0](LICENSE.md).
- **Upstream licenses:** Mirrored files retain their original licenses.
- **SponsorBlock mirror:** Released under the
  [Unlicense](https://github.com/mchangrh/yt-neuter/blob/main/LICENSE).
