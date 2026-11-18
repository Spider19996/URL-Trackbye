# Third-party material

## ClearURLs rules (parameter names)

The repository itself does **not** contain ClearURLs data. The rule list that URL Trackbye downloads is built outside of the
program (`tools/build_rules.py`, run by `.github/workflows/rules.yml`) from our own `rules.json` and tracking parameter names
taken from the **ClearURLs Rules** database, and published on the branch `rules` of the repository together with this
notice and the license text:

- Source: <https://github.com/ClearURLs/Rules> (`data.minify.json`, downloaded from <https://rules2.clearurls.xyz/>)
- Copyright: ClearURLs authors and contributors (Kevin Röbert and others)
- License: **GNU Lesser General Public License v3.0** (full text in [`COPYING.LESSER`](COPYING.LESSER))
- The exact version used is recorded in the published list (`sources[].sha256`, `built`).

What was changed: `tools/import_clearurls.py` converts the rules. ClearURLs describes parameters with regular
expressions; only plain names and simple alternations were taken over, only for providers without exceptions, and a short list
of names that pages often need themselves (for example `ref`, `source`, `th`) was left out. Everything else was skipped.
The result is stored as plain JSON. That part stays under the LGPL-3.0; URL Trackbye itself (GPL-3.0-or-later) may
be combined with it (LGPL-3.0, section 3 allows the combined work under the GPL-3.0).

URL Trackbye is not affiliated with or endorsed by ClearURLs.
