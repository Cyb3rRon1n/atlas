# Vendored front-end libraries

Served by `atlas web` at `/static/<name>` (allow-listed in `atlas/web/server.py`), so the map
works with no internet access. Do not edit these files - replace them with a new pinned release.

| File | Package | Version | sha256 | License |
|---|---|---|---|---|
| `cytoscape.min.js` | [cytoscape](https://js.cytoscape.org/) `dist/cytoscape.min.js` | 3.34.3 | `5f3b5b529546d5af1fc5628590af033b74511a5b6f789f5f4682845863228b91` | MIT |
| `elk.bundled.js` | [elkjs](https://github.com/kieler/elkjs) `lib/elk.bundled.js` (layout for /cabling) | 0.9.3 | `b0745abd7f23cd91690a1587e377edbe19fd7233c783300290936720546216d4` | EPL-2.0 |

Update: download the new `dist/` file from `https://cdn.jsdelivr.net/npm/<package>@<version>/...`,
record its sha256 here, and check `tests/test_web_server.py::test_vendored_files_match_pinned_hashes`.
