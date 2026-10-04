# adblock-filters

A personal, self-curated adblocking filter list.

Filters are maintained for my own browsing needs and may change over time.

Lists are organized by domain under `filters/`.

## Filters and sources

<details>
<summary><strong>YouTube</strong></summary>

**List:** [YouTube annoyances](filters/youtube/yt-annoyances.txt)

**Sources:**

- [tadwohlrapp's YouTube filters](https://gist.github.com/tadwohlrapp/722bbe97cb20bb34da8df73675415cae/8b2f5e4eba8a8a45f077cb9c4b64ca8f5fdc6075)
- [mchangrh/yt-neuter](https://github.com/mchangrh/yt-neuter)

The list includes a local copy of yt-neuter's
[SponsorBlock filters](https://github.com/mchangrh/yt-neuter/blob/main/filters/sponsorblock.txt)
from [`upstream/sponsorblock.txt`](filters/youtube/upstream/sponsorblock.txt).

The latest [tadwohlrapp YouTube filters](filters/youtube/upstream/ublock-filter-youtube.txt)
are also mirrored for reference. They are not included in the custom list.

</details>

## Updating upstream filters

The [Sync upstream filters workflow](.github/workflows/sync-upstream.yml) checks
for updates every six hours at minute 17 UTC and can also be run manually from
GitHub Actions. It compares each downloaded file with the local copy and commits
only changed files to `main`.

To mirror another list, add a line to the workflow's `UPSTREAM_FILTERS` table:

```text
filters/<domain>/upstream/<filename>.txt https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>.txt
```

Then add a relative include to the custom list in that domain's folder:

```text
!#include upstream/<filename>.txt
```

Leave out the include when a mirrored file is only needed for reference.
To follow a gist's latest revision, use an unpinned raw URL:

```text
https://gist.githubusercontent.com/<user>/<gist-id>/raw/<filename>
```

[uBlock Origin requires relative includes](https://github.com/gorhill/uBlock/wiki/Static-filter-syntax#include-file-name)
within the list's directory or a subdirectory. Mirrored files are kept unchanged;
download failures leave the previous copies in place.

## License

Licensed under the [GNU General Public License v3.0](LICENSE.md).

Mirrored upstream files retain their original licenses. The included yt-neuter
SponsorBlock list is released under the
[Unlicense](https://github.com/mchangrh/yt-neuter/blob/main/LICENSE).
