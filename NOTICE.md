# Third-party material

## ClearURLs rules (parameter names)

`rules.clearurls.json` (and the copy of it inside `extension/rules.json`) contains tracking parameter names taken from
the **ClearURLs Rules** database:

- Source: <https://github.com/ClearURLs/Rules> (`data.minify.json`, downloaded from <https://rules2.clearurls.xyz/>)
- Copyright: ClearURLs authors and contributors (Kevin Röbert and others)
- License: **GNU Lesser General Public License v3.0** (full text in [`COPYING.LESSER`](COPYING.LESSER))
- The exact version used is recorded in `rules.clearurls.json` (`source.sha256`, `source.imported`).

What was changed: `tools/import_clearurls.py` converts the rules. ClearURLs describes parameters with regular
expressions; only plain names and simple alternations were taken over, only for providers without exceptions, and a short list
of names that pages often need themselves (for example `ref`, `source`, `th`) was left out. Everything else was skipped.
The result is stored as plain JSON. The file stays under the LGPL-3.0; URL Trackbye itself (GPL-3.0-or-later) may
be combined with it (LGPL-3.0, section 3 allows the combined work under the GPL-3.0).

URL Trackbye is not affiliated with or endorsed by ClearURLs.
Re-run `python3 tools/import_clearurls.py` to refresh the data (it verifies the published hash first).
