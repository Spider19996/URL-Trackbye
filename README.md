# linkfeger

Removes tracking parameters (`utm_*`, `fbclid`, Google's `sxsrf`/`ei`/..., YouTube's `si`, ...) from links, system-wide:

| Where | How |
| --- | --- |
| Copied links (any app) | `linkfeger watch` cleans every single URL you copy (Wayland / wl-clipboard) |
| Links opened by other apps (Discord, mail, ...) | `linkfeger open` as default browser cleans the URL, then starts your real browser |
| Links in the browser | The browser extension cleans the address **before the page loads**, and adds "Copy clean link address" to the context menu |

All parts share one rule list (`rules.json`). It is **not radical**: only known tracking parameters are removed, so
search terms (`q`), video times (`t`), playlists (`list`), product variants (`th`, `psc`) etc. stay. Login hosts are
excluded, and the extension can be switched off per site. No network access, no telemetry, Python standard library only.

Written from scratch for KDE Plasma on Wayland with Vivaldi/Chrome; MIT licensed.

## Install

```bash
git clone <this repo> ~/GitHub/linkfeger && cd ~/GitHub/linkfeger
./linkfeger.py clean 'https://www.youtube.com/watch?v=abc&si=xyz'   # try it
```

Needs Python 3.8+. For the clipboard part also `wl-clipboard` (`wl-paste`, `wl-copy`).

### Clipboard (Wayland)

`linkfeger watch` runs in the foreground. To start it with your session, create
`~/.config/systemd/user/linkfeger.service`:

```ini
[Unit]
Description=linkfeger clipboard cleaner

[Service]
ExecStart=%h/GitHub/linkfeger/linkfeger.py watch
Restart=on-failure

[Install]
WantedBy=default.target
```

then `systemctl --user enable --now linkfeger`. Only a clipboard that holds exactly one http(s) URL is changed;
copies marked by a password manager are never touched.

### Browser extension (Vivaldi / Chrome / Chromium)

1. Open `vivaldi://extensions`, enable developer mode, **Load unpacked**, choose the `extension` folder.
   The extension has a fixed ID (`kcppbmmghccgpmjafccjammekemegidd`).
2. Optional, so the extension uses the same rules as the program (including your own additions):
   `./linkfeger.py install-native` (registers the native messaging host for the browsers found in `~/.config`).
   Without it the extension uses its bundled copy of `rules.json`. The popup shows which one is active.

### Links from other apps (Discord, ...)

```bash
./linkfeger.py install-handler              # writes linkfeger.desktop
./linkfeger.py install-handler --set-default   # also makes it your default browser
```

Set `"browser"` in `~/.config/linkfeger/config.json` if your browser is not `vivaldi-stable`. Undo with
`xdg-settings set default-web-browser vivaldi-stable.desktop`.

## Your own rules

`~/.config/linkfeger/rules.json` is merged with the built-in rules (same format):

```json
{ "global_remove": ["my_tracker"], "sites": [{ "hosts": ["example.com"], "remove": ["ref"] }], "exclude_hosts": ["shop.example.org"] }
```

Rules use exact parameter names (no wildcards) and match a domain plus its subdomains.
Optional `config.json`: `{"browser": "vivaldi-stable", "notify": true}` (`notify` shows a desktop notification).

## Limits

- The extension cannot see links that a page redirects through its own tracking service (e.g. `l.wl.co`); the final
  page is cleaned when it loads.
- The extension changes the address before loading; a few sites may then behave differently. Use the per-site switch.
- Clipboard watching needs a compositor with the data-control protocol (KDE Plasma, Sway, Hyprland; not GNOME).

## Development

```bash
python3 -m unittest discover -s tests   # Python
node tests/test_extension.mjs           # the extension's cleaner, same test vectors
```

`extension/rules.json` must be a copy of `rules.json` (a test checks it): `cp rules.json extension/rules.json`.
