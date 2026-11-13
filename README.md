# URL Trackbye

Removes tracking parameters (`utm_*`, `fbclid`, Google's `sxsrf`/`ei`/..., YouTube's `si`, ...) from links, system-wide:

| Where | How |
| --- | --- |
| Copied links (any app) | `trackbye watch` cleans every single URL you copy (Wayland / wl-clipboard) |
| Links opened by other apps (Discord, mail, ...) | `trackbye open` as default browser cleans the URL, then starts your real browser |
| Links in the browser | The browser extension cleans the address **before the page loads**, and adds "Copy clean link address" to the context menu |

All parts share one rule list (`rules.json`). It is **not radical**: only known tracking parameters are removed, so
search terms (`q`), video times (`t`), playlists (`list`), product variants (`th`, `psc`) etc. stay. Login hosts are
excluded, and the extension can be switched off per site. No network access, no telemetry, Python standard library only.

Written from scratch for KDE Plasma on Wayland with Vivaldi/Chrome. Free software under the GNU GPL v3 or later.

## The app

`./trackbye.py` (no arguments) starts URL Trackbye as a tray app (needs `python3-pyqt6`, `wl-clipboard`). It cleans the
clipboard in the background and has one settings window for everything:

- clipboard cleaning on/off, notifications, **start with the desktop session**, hide the tray symbol
- **log** of cleaned links (clipboard, links opened by other apps, browser), with what was removed; stored only on this
  computer in `~/.local/state/trackbye/log.jsonl` (500 entries), can be switched off and cleared
- **messages** (what the app did, warnings and errors such as a missing `wl-clipboard`, a broken rules file or a
  crashed clipboard watcher; errors also show as a tray notice) in `~/.local/state/trackbye/events.jsonl`; if cleaning
  itself fails when you open a link, the link still opens unchanged
- **extension check**: the extension tells the app which version it runs (needs the rule sharing from the Browser tab).
  After an update, if the browser still runs an older extension than the files on disk, you get a notice (once per
  version), a warning in the messages and a hint in the Browser tab; the extension also reloads itself within about
  30 minutes
- your own rules, with a live "try a link" box
- browser setup: extension folder, sharing the rules with the extension, default browser for links from other apps

English and German. Starting it a second time just opens the settings window of the running app, so with a hidden tray
symbol you can also use the application menu entry "URL Trackbye" (created when you hide the symbol).

## Install

```bash
git clone <this repo> ~/GitHub/url-trackbye && cd ~/GitHub/url-trackbye
./trackbye.py clean 'https://www.youtube.com/watch?v=abc&si=xyz'   # try it
```

Needs Python 3.8+. For the clipboard part also `wl-clipboard` (`wl-paste`, `wl-copy`); for the tray app `python3-pyqt6`.

### Clipboard (Wayland)

`trackbye watch` runs in the foreground. To start it with your session, create
`~/.config/systemd/user/trackbye.service`:

```ini
[Unit]
Description=trackbye clipboard cleaner

[Service]
ExecStart=%h/GitHub/url-trackbye/trackbye.py watch
Restart=on-failure

[Install]
WantedBy=default.target
```

then `systemctl --user enable --now trackbye`. Only a clipboard that holds exactly one http(s) URL is changed;
copies marked by a password manager are never touched.

### Browser extension (Vivaldi / Chrome / Chromium)

1. Open `vivaldi://extensions`, enable developer mode, **Load unpacked**, choose the `extension` folder.
   The extension has a fixed ID (`kcppbmmghccgpmjafccjammekemegidd`).
2. Optional, so the extension uses the same rules as the program (including your own additions):
   `./trackbye.py install-native` (registers the native messaging host for the browsers found in `~/.config`).
   Without it the extension uses its bundled copy of `rules.json`. The popup shows which one is active. With the program
   installed the extension also picks up changed rules every 30 minutes and **reloads itself** when the extension
   files on disk have a newer version (after a `git pull`, bump `version` in `extension/manifest.json` for releases).

### Links from other apps (Discord, ...)

```bash
./trackbye.py install-handler              # writes trackbye.desktop
./trackbye.py install-handler --set-default   # also makes it your default browser
```

Set `"browser"` in `~/.config/trackbye/config.json` if your browser is not `vivaldi-stable`. Undo with
`xdg-settings set default-web-browser vivaldi-stable.desktop`.

## Your own rules

`~/.config/trackbye/rules.json` is merged with the built-in rules (same format):

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

The extension version must change exactly when the extension changes (the app only asks you to reload the extension
when its version differs, so unrelated program updates never do). A test checks this; after changing anything in
`extension/` bump `version` in `extension/manifest.json` and run `python3 tools/extension_version.py stamp`.

`extension/rules.json` must be a copy of `rules.json` (a test checks it): `cp rules.json extension/rules.json`.

## License

Copyright (C) 2026 Robin Zimmermann. URL Trackbye is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License v3.0 (see [LICENSE](LICENSE)); it comes without any warranty.
