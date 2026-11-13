#!/usr/bin/env python3
# URL Trackbye - removes tracking parameters from links.
# Copyright (C) 2026 Robin Zimmermann
# SPDX-License-Identifier: GPL-3.0-or-later
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later
# version. It is distributed WITHOUT ANY WARRANTY. See the LICENSE file or <https://www.gnu.org/licenses/>.
"""trackbye - remove tracking parameters from links, system-wide.

One small program with several jobs that all use the same rules (rules.json):

  trackbye clean URL...      print the cleaned URLs
  trackbye                   start the app (tray symbol, clipboard cleaning, log, settings) and open its window. Needs PyQt6.
  trackbye --background      the same without opening the window (used by the autostart entry)
  trackbye watch             watch the clipboard (Wayland, needs wl-clipboard) and clean copied URLs
  trackbye open [URL...]     clean the URLs and open them in the real browser (use as default browser)
  trackbye install-handler   write the desktop entry that makes `open` selectable as default browser
  trackbye install-native    register the native messaging host for the browser extension
  trackbye rules-update [--force]   download the published rule list now (the app does it daily when switched on)
  trackbye rules-reset       forget the downloaded list and use the rules that ship with the program
  trackbye install [--autostart] [--native] [--link]   set up for this user (menu entry, optional autostart, browser link, command)
  trackbye uninstall [--purge]   remove what install created (--purge: also settings and log)
  trackbye reload-extension  ask the browser extension to reload itself (after changing its files)
  trackbye native            native messaging host (started by the browser extension, not by you)

Only the Python standard library is used. Rules: exact parameter names, matched per site (domain and subdomains).
Your own additions go into ~/.config/trackbye/rules.json (same format, merged with the built-in rules).
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
CONFIG_DIR = os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), 'trackbye')
HOST_NAME = 'de.trackbye.host'
# Fixed by the "key" in extension/manifest.json, so the host manifest can name exactly this extension.
EXTENSION_ID = 'kcppbmmghccgpmjafccjammekemegidd'
STATE_DIR = os.path.join(os.environ.get('XDG_STATE_HOME', os.path.expanduser('~/.local/state')), 'trackbye')
LOG_PATH = os.path.join(STATE_DIR, 'log.jsonl')
LOG_MAX = 500
EVENTS_PATH = os.path.join(STATE_DIR, 'events.jsonl')
EVENTS_MAX = 300
EXTENSION_STATE = os.path.join(STATE_DIR, 'extension.json')
RELOAD_TRIGGER = os.path.join(STATE_DIR, 'reload-extension')
DEFAULT_CONFIG = {'browser': 'vivaldi-stable', 'notify': False, 'clipboard': True, 'previous_default': '',
                  'log': True, 'tray_icon': True, 'quick': ['clipboard', 'notify'], 'native_browsers': None, 'custom_browsers': [], 'rules_auto': True, 'rules_url': ''}
SCRIPT = os.path.realpath(__file__)
VERSION = '0.7.0'


# --------------------------------------------------------------------------------------------------------------
# Rules and cleaning
# --------------------------------------------------------------------------------------------------------------

def read_json(path, fallback, report=False):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except OSError:
        return fallback
    except ValueError as e:
        if report:
            diag('warning', 'Ignoring %s (invalid JSON: %s)' % (path, e))
        return fallback


# --------------------------------------------------------------------------------------------------------------
# The rule list: a small list ships with the program (offline fallback); a larger one is built outside of it
# (hand-written rules + ClearURLs names, see tools/build_rules.py), published, and downloaded by the program.
# --------------------------------------------------------------------------------------------------------------
REPO_URL = 'https://github.com/Spider19996/URL-Trackbye'
DEFAULT_RULES_URL = 'https://raw.githubusercontent.com/Spider19996/URL-Trackbye/rules/rules.json'
RULES_DOWNLOADED = os.path.join(CONFIG_DIR, 'rules.downloaded.json')
RULES_META = os.path.join(CONFIG_DIR, 'rules.meta.json')
RULES_MAX_BYTES = 1_500_000
RULES_CHECK_EVERY = 24 * 3600
_NAME = re.compile(r'^[A-Za-z0-9_.\-]{1,64}$')
_HOST = re.compile(r'^[a-z0-9][a-z0-9.\-]{0,252}$')


def validate_rules(doc):
    """Check a downloaded rule list strictly and return it cleaned; raise ValueError if anything is off.
    Only plain parameter names and host names are allowed, so even a manipulated list can do nothing but remove
    parameters from links."""
    if not isinstance(doc, dict):
        raise ValueError('not an object')

    def names(value, what, limit, pattern):
        if not isinstance(value, list) or len(value) > limit:
            raise ValueError(what + ': not a list or too long')
        out = []
        for item in value:
            if not isinstance(item, str) or not pattern.match(item):
                raise ValueError(what + ': bad entry')
            out.append(item)
        return list(dict.fromkeys(out))

    sites = []
    if not isinstance(doc.get('sites', []), list) or len(doc.get('sites', [])) > 1500:
        raise ValueError('sites: not a list or too long')
    for site in doc.get('sites', []):
        if not isinstance(site, dict):
            raise ValueError('sites: bad entry')
        sites.append({'name': str(site.get('name', ''))[:80], 'hosts': names(site.get('hosts', []), 'hosts', 100, _HOST),
                      'remove': names(site.get('remove', []), 'remove', 500, _NAME),
                      'source': str(site.get('source', ''))[:40]})
    return {
        'version': int(doc.get('version', 0)),
        'built': str(doc.get('built', ''))[:40],
        'sources': [{k: str(v)[:200] for k, v in src.items()} for src in doc.get('sources', []) if isinstance(src, dict)][:10],
        'exclude_hosts': names(doc.get('exclude_hosts', []), 'exclude_hosts', 500, _HOST),
        'global_remove': names(doc.get('global_remove', []), 'global_remove', 2000, _NAME),
        'sites': sites,
    }


def shipped_rules():
    own = read_json(os.path.join(HERE, 'rules.json'), {}, True)
    return {'version': own.get('version', 1), 'exclude_hosts': list(own.get('exclude_hosts', [])),
            'global_remove': list(own.get('global_remove', [])), 'sites': list(own.get('sites', []))}


def builtin_rules():
    """The downloaded list if there is a valid one, else the small shipped list."""
    downloaded = read_json(RULES_DOWNLOADED, None)
    if isinstance(downloaded, dict) and downloaded.get('sites') is not None:
        return {'version': downloaded.get('version', 1), 'exclude_hosts': list(downloaded.get('exclude_hosts', [])),
                'global_remove': list(downloaded.get('global_remove', [])), 'sites': list(downloaded.get('sites', []))}
    return shipped_rules()


def rules_info():
    """What the settings window shows: where the rules come from, how many there are, when they were checked."""
    meta = read_json(RULES_META, {})
    downloaded = read_json(RULES_DOWNLOADED, None)
    current = builtin_rules()
    return {'source': 'downloaded' if isinstance(downloaded, dict) else 'shipped', 'version': current.get('version'),
            'built': (downloaded or {}).get('built', ''), 'sources': (downloaded or {}).get('sources', []),
            'global': len(current['global_remove']), 'sites': len(current['sites']),
            'checked': meta.get('checked', 0), 'url': meta.get('url', ''), 'error': meta.get('error', '')}


def rules_due():
    cfg = load_config()
    return bool(cfg.get('rules_auto')) and time.time() - read_json(RULES_META, {}).get('checked', 0) > RULES_CHECK_EVERY


def rules_update(force=False):
    """Download the rule list, validate it and store it. Returns (status, message): updated / unchanged / error.
    Only this call talks to the network; it sends no personal data (a plain GET with a generic user agent)."""
    cfg = load_config()
    url = cfg.get('rules_url') or DEFAULT_RULES_URL
    meta = read_json(RULES_META, {})
    meta['url'] = url
    if not (url.startswith('https://') or url.startswith('http://127.0.0.1')):
        meta['error'] = 'The rules address must start with https://'
        write_json(RULES_META, meta)
        return 'error', meta['error']
    request = urllib.request.Request(url, headers={'User-Agent': 'url-trackbye/' + VERSION})
    if meta.get('etag') and not force and os.path.exists(RULES_DOWNLOADED):
        request.add_header('If-None-Match', meta['etag'])
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(RULES_MAX_BYTES + 1)
            etag = response.headers.get('ETag', '')
        if len(raw) > RULES_MAX_BYTES:
            raise ValueError('the list is too large')
        doc = validate_rules(json.loads(raw.decode('utf-8')))
        write_json(RULES_DOWNLOADED, doc)
        meta.update(etag=etag, checked=time.time(), error='')
        write_json(RULES_META, meta)
        message = 'Rules updated: version %s, %d global names, %d sites' % (doc['version'], len(doc['global_remove']), len(doc['sites']))
        diag('info', message)
        return 'updated', message
    except urllib.error.HTTPError as e:
        if e.code == 304:
            meta.update(checked=time.time(), error='')
            write_json(RULES_META, meta)
            return 'unchanged', 'The rules are up to date.'
        message = 'Could not download the rules (HTTP %d)%s' % (e.code, ': no list has been published yet' if e.code == 404 else '')
    except (urllib.error.URLError, OSError, ValueError) as e:
        message = 'Could not use the downloaded rules: %s' % e
    meta.update(checked=time.time(), error=message)
    write_json(RULES_META, meta)
    diag('warning', message)
    return 'error', message


def rules_reset():
    for path in (RULES_DOWNLOADED, RULES_META):
        if os.path.exists(path):
            os.remove(path)


def load_rules():
    """Built-in rules plus the user's additions (union of lists, user sites appended)."""
    rules = builtin_rules()
    user = read_json(os.path.join(CONFIG_DIR, 'rules.json'), {}, True)
    return {
        'version': rules.get('version', 1),
        'exclude_hosts': list(rules.get('exclude_hosts', [])) + list(user.get('exclude_hosts', [])),
        'global_remove': list(rules.get('global_remove', [])) + list(user.get('global_remove', [])),
        'sites': list(rules.get('sites', [])) + list(user.get('sites', [])),
    }


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')


def user_rules():
    """Only the user's own additions (what the settings window edits)."""
    user = read_json(os.path.join(CONFIG_DIR, 'rules.json'), {})
    return {'global_remove': list(user.get('global_remove', [])), 'exclude_hosts': list(user.get('exclude_hosts', [])),
            'sites': list(user.get('sites', []))}


def save_user_rules(rules):
    write_json(os.path.join(CONFIG_DIR, 'rules.json'), rules)


def save_config(cfg):
    write_json(os.path.join(CONFIG_DIR, 'config.json'), cfg)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(read_json(os.path.join(CONFIG_DIR, 'config.json'), {}))
    return cfg


def host_matches(host, domains):
    return any(host == d or host.endswith('.' + d) for d in domains)


def is_url(text):
    """True for a single http(s) URL (no spaces or line breaks)."""
    t = text.strip()
    return t.lower().startswith(('http://', 'https://')) and not any(c.isspace() for c in t)


def clean_url(url, rules):
    """Return the URL without tracking parameters; the text is otherwise left exactly as it was."""
    if not is_url(url):
        return url
    url = url.strip()
    frag = ''
    if '#' in url:
        i = url.index('#')
        url, frag = url[:i], url[i:]
    if '?' not in url:
        return url + frag
    head, query = url.split('?', 1)
    rest = head.split('://', 1)[1]
    host = rest.split('/', 1)[0].rsplit('@', 1)[-1].split(':', 1)[0].lower()
    if host_matches(host, rules.get('exclude_hosts', [])):
        return head + '?' + query + frag
    remove = set(rules.get('global_remove', []))
    for site in rules.get('sites', []):
        if host_matches(host, site.get('hosts', [])):
            remove.update(site.get('remove', []))
    kept = [p for p in query.split('&') if p and p.split('=', 1)[0] not in remove]
    new_query = '&'.join(kept)
    return head + ('?' + new_query if new_query else '') + frag


# --------------------------------------------------------------------------------------------------------------
# Log of cleaned links (one JSON object per line, newest last, trimmed to LOG_MAX)
# --------------------------------------------------------------------------------------------------------------

def query_keys(url):
    base = url.split('#', 1)[0]
    query = base.split('?', 1)[1] if '?' in base else ''
    return [p.split('=', 1)[0] for p in query.split('&') if p]


def removed_params(before, after):
    kept = query_keys(after)
    gone = []
    for key in query_keys(before):
        if key in kept:
            kept.remove(key)
        else:
            gone.append(key)
    return gone


def read_log():
    entries = []
    try:
        with open(LOG_PATH, encoding='utf-8') as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return entries


def write_log(entries):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = LOG_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for e in entries[-LOG_MAX:]:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    os.replace(tmp, LOG_PATH)


def clear_log():
    write_log([])


def log_event(source, before, after):
    """Remember that a link was cleaned. A second step on the same link within 3 seconds (the browser cleans in
    several passes) is merged into the previous entry."""
    if before == after or not load_config().get('log', True):
        return
    now = time.time()
    entries = read_log()
    last = entries[-1] if entries else None
    if last and last.get('src') == source and now - last.get('t', 0) < 3 and last.get('to') in (before, after):
        # another pass over the same link (the browser cleans in several steps, reported in any order)
        gone = last.get('removed', [])
        gone += [k for k in removed_params(before, after) if k not in gone]
        last['removed'] = gone
        last['to'] = after
        if len(query_keys(before)) > len(query_keys(last.get('from', ''))):
            last['from'] = before
    else:
        entries.append({'t': now, 'src': source, 'from': before, 'to': after, 'removed': removed_params(before, after)})
    write_log(entries)


# --------------------------------------------------------------------------------------------------------------
# Messages: what the app did and what went wrong (levels: info, warning, error)
# --------------------------------------------------------------------------------------------------------------

def read_events():
    entries = []
    try:
        with open(EVENTS_PATH, encoding='utf-8') as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return entries


def write_events(entries):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = EVENTS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for e in entries[-EVENTS_MAX:]:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    os.replace(tmp, EVENTS_PATH)


def diag(level, message, where=''):
    """Record a message. The same message within a minute is only counted, so a repeating problem does not flood it."""
    try:
        now = time.time()
        entries = read_events()
        last = entries[-1] if entries else None
        if last and last.get('msg') == message and last.get('level') == level and now - last.get('t', 0) < 60:
            last['count'] = last.get('count', 1) + 1
            last['t'] = now
        else:
            entries.append({'t': now, 'level': level, 'msg': message, 'where': where, 'count': 1})
        write_events(entries)
    except OSError:
        pass  # the log must never break the program


def clear_events():
    write_events([])


# --------------------------------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------------------------------

def notify(text):
    if load_config().get('notify') and shutil.which('notify-send'):
        subprocess.run(['notify-send', '-a', 'trackbye', 'trackbye', text], check=False)


def cmd_clean(args):
    rules = load_rules()
    for url in args:
        print(clean_url(url, rules))


def clipboard_is_secret():
    """Password managers mark their copies; never touch those."""
    out = subprocess.run(['wl-paste', '--list-types'], capture_output=True, text=True, check=False).stdout
    return 'passwordManagerHint' in out


def cmd_filter_clip():
    """Called by `wl-paste --watch` for every clipboard change; the new content arrives on stdin."""
    text = sys.stdin.read()
    if not load_config().get('clipboard', True) or not is_url(text) or clipboard_is_secret():
        return
    cleaned = clean_url(text, load_rules())
    if cleaned != text.strip():
        # wl-copy stays in the background to serve the clipboard and keeps inherited pipes open, so its output goes
        # to a temp file (never a pipe: waiting for a pipe would block until the clipboard changes again).
        with tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(['wl-copy', '--type', 'text/plain'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                    stderr=err)
            proc.communicate(cleaned.encode('utf-8'))
            if proc.returncode != 0:
                err.seek(0)
                diag('error', 'wl-copy failed (exit %d): %s' % (proc.returncode, err.read().decode('utf-8', 'replace').strip()),
                     'clipboard')
                return
        log_event('clipboard', text.strip(), cleaned)
        notify('Cleaned the copied link')


def cmd_watch():
    if not shutil.which('wl-paste') or not shutil.which('wl-copy'):
        sys.exit('trackbye watch needs wl-clipboard (wl-paste and wl-copy) on Wayland.')
    cmd = ['wl-paste', '--type', 'text', '--watch', sys.executable, os.path.realpath(__file__), 'filter-clip']
    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        pass


def cmd_open(args):
    browser = load_config()['browser']
    if os.path.basename(shutil.which(browser) or browser) in ('trackbye', 'trackbye.py'):
        sys.exit('The "browser" setting must name the real browser, not trackbye.')
    rules = load_rules()
    urls = []
    for a in args:
        cleaned = clean_url(a, rules)
        log_event('opener', a, cleaned)
        urls.append(cleaned)
    os.execvp(browser, [browser] + urls)


def desktop_file():
    return os.path.join(os.path.expanduser('~/.local/share/applications'), 'trackbye.desktop')


def install_handler():
    """Desktop entry of the link opener: shows up as "URL Trackbye Link Opener" when you pick a default browser."""
    path = desktop_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('[Desktop Entry]\nType=Application\nName=URL Trackbye Link Opener\nName[de]=URL Trackbye Link-\u00d6ffner\n'
                'GenericName=Web Browser\nGenericName[de]=Webbrowser\n'
                'Comment=Removes tracking from the link, then opens it in your browser\n'
                'Comment[de]=Entfernt das Tracking aus dem Link und \u00f6ffnet ihn dann in deinem Browser\n'
                'Exec=' + SCRIPT + ' open %U\nTerminal=false\nIcon=' + os.path.join(HERE, 'assets', 'trackbye.png')
                + '\nCategories=Network;WebBrowser;\nMimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;\n')
    return path


def default_browser():
    return subprocess.run(['xdg-settings', 'get', 'default-web-browser'], capture_output=True, text=True,
                          check=False).stdout.strip()


def set_default_browser(desktop):
    subprocess.run(['xdg-settings', 'set', 'default-web-browser', desktop], check=False)


def cmd_install_handler(args):
    print('Wrote ' + install_handler())
    if '--set-default' in args:
        cfg = load_config()
        current = default_browser()
        if current and current != 'trackbye.desktop':
            cfg['previous_default'] = current
            save_config(cfg)
        set_default_browser('trackbye.desktop')
        print('Default browser set to trackbye. Undo: xdg-settings set default-web-browser ' + (current or '<browser>.desktop'))
    else:
        print('To use it as default browser, run again with --set-default or pick it in the system settings.')


FIREFOX_ID = 'url-trackbye@spider19996'  # must match browser_specific_settings in extension/manifest.json

# Browsers the app knows. "dir" is where the browser looks for native messaging host files, "detect" tells whether
# the browser is installed. Chromium-like browsers want the extension origin, Firefox-like ones the add-on id.
BUILTIN_BROWSERS = [
    {'id': 'vivaldi', 'name': 'Vivaldi', 'kind': 'chromium', 'dir': '~/.config/vivaldi/NativeMessagingHosts',
     'detect': '~/.config/vivaldi', 'bins': ['vivaldi-stable', 'vivaldi']},
    {'id': 'chromium', 'name': 'Chromium', 'kind': 'chromium', 'dir': '~/.config/chromium/NativeMessagingHosts',
     'detect': '~/.config/chromium', 'bins': ['chromium', 'chromium-browser']},
    {'id': 'google-chrome', 'name': 'Google Chrome', 'kind': 'chromium', 'dir': '~/.config/google-chrome/NativeMessagingHosts',
     'detect': '~/.config/google-chrome', 'bins': ['google-chrome-stable', 'google-chrome']},
    {'id': 'BraveSoftware/Brave-Browser', 'name': 'Brave', 'kind': 'chromium',
     'dir': '~/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts', 'detect': '~/.config/BraveSoftware/Brave-Browser',
     'bins': ['brave-browser', 'brave']},
    {'id': 'firefox', 'name': 'Firefox', 'kind': 'firefox', 'dir': '~/.mozilla/native-messaging-hosts',
     'detect': '~/.mozilla/firefox', 'bins': ['firefox', 'firefox-esr']},
]

# Well-known derivatives: they show up in the list by themselves as soon as they are installed, no setup needed.
# (Their folders follow the usual pattern of each family; not every one has been tried.)
DERIVATIVES = [
    {'id': 'microsoft-edge', 'name': 'Microsoft Edge', 'kind': 'chromium', 'dir': '~/.config/microsoft-edge/NativeMessagingHosts',
     'detect': '~/.config/microsoft-edge', 'bins': ['microsoft-edge-stable', 'microsoft-edge']},
    {'id': 'opera', 'name': 'Opera', 'kind': 'chromium', 'dir': '~/.config/opera/NativeMessagingHosts',
     'detect': '~/.config/opera', 'bins': ['opera']},
    {'id': 'floorp', 'name': 'Floorp', 'kind': 'firefox', 'dir': '~/.floorp/native-messaging-hosts',
     'detect': '~/.floorp', 'bins': ['floorp']},
    {'id': 'librewolf', 'name': 'LibreWolf', 'kind': 'firefox', 'dir': '~/.librewolf/native-messaging-hosts',
     'detect': '~/.librewolf', 'bins': ['librewolf']},
    {'id': 'zen', 'name': 'Zen Browser', 'kind': 'firefox', 'dir': '~/.zen/native-messaging-hosts',
     'detect': '~/.zen', 'bins': ['zen-browser', 'zen']},
    {'id': 'waterfox', 'name': 'Waterfox', 'kind': 'firefox', 'dir': '~/.waterfox/native-messaging-hosts',
     'detect': '~/.waterfox', 'bins': ['waterfox']},
]


def browser_entries():
    """Built-in browsers, installed derivatives, and the ones the user added (config "custom_browsers")."""
    entries = [dict(b) for b in BUILTIN_BROWSERS]
    entries += [dict(d) for d in DERIVATIVES if browser_found(d)]
    for c in load_config().get('custom_browsers') or []:
        entries.append({'id': 'custom:' + c['name'], 'name': c['name'], 'kind': c['kind'], 'dir': c['dir'],
                        'detect': c['dir'], 'bins': [], 'custom': True})
    return entries


def browser_found(entry):
    """Installed? Its program is on the PATH or its profile folder exists (Firefox has none before its first start)."""
    if any(shutil.which(b) for b in entry.get('bins', [])):
        return True
    path = os.path.expanduser(entry['detect'])
    return os.path.isdir(path) or bool(entry.get('custom') and os.path.isdir(os.path.dirname(path.rstrip('/'))))


def browser_binary(entry):
    """The command that starts this browser, or None."""
    return next((b for b in entry.get('bins', []) if shutil.which(b)), None)


def build_firefox_folder():
    """The Firefox build as an unpacked folder (dist/firefox-unpacked) for temporary loading in about:debugging."""
    sys.path.insert(0, os.path.join(HERE, 'tools'))
    import package_extension
    return package_extension.build_firefox_folder()


def latest_xpi():
    """The newest signed Firefox package in dist/ (made by tools/sign_firefox.py), or None."""
    import glob
    files = glob.glob(os.path.join(HERE, 'dist', 'url-trackbye-*.xpi'))
    def key(path):
        m = re.search(r'url-trackbye-([\d.]+)\.xpi$', path)
        return [int(x) for x in m.group(1).split('.')] if m else []
    return max(files, key=key) if files else None


def suggest_native_dir(name, kind):
    """For the "add browser" dialog: (folder, profile found?) guessed from the browser's name and family."""
    slug = ''.join(c for c in name.lower() if c.isalnum() or c == '-') or 'browser'
    if kind == 'firefox':
        for base in ('~/.' + slug, '~/.config/' + slug):
            if os.path.isdir(os.path.expanduser(base)):
                return base + '/native-messaging-hosts', True
        return '~/.mozilla/native-messaging-hosts', False
    base = '~/.config/' + slug
    return base + '/NativeMessagingHosts', os.path.isdir(os.path.expanduser(base))


def native_manifest_path(entry):
    return os.path.join(os.path.expanduser(entry['dir']), HOST_NAME + '.json')


def install_native(ids=None):
    """Register the native messaging host for the browsers with these ids (default: all installed ones)."""
    base = {
        'name': HOST_NAME,
        'description': 'URL Trackbye: shares the cleaning rules with the browser extension',
        'path': SCRIPT,
        'type': 'stdio',
    }
    written = []
    for entry in browser_entries():
        if (ids is not None and entry['id'] not in ids) or not browser_found(entry):
            continue
        manifest = dict(base)
        if entry['kind'] == 'firefox':
            manifest['allowed_extensions'] = [FIREFOX_ID]
        else:
            manifest['allowed_origins'] = ['chrome-extension://' + EXTENSION_ID + '/']
        target = native_manifest_path(entry)
        write_json(target, manifest)
        written.append(target)
    return written


def uninstall_native(ids):
    removed = []
    for entry in browser_entries():
        target = native_manifest_path(entry)
        if entry['id'] in ids and os.path.exists(target):
            os.remove(target)
            removed.append(target)
    return removed


def cmd_install_native():
    for target in install_native():
        print('Wrote ' + target)


AUTOSTART = os.path.expanduser('~/.config/autostart/trackbye.desktop')


def set_autostart(on):
    if on:
        os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
        with open(AUTOSTART, 'w', encoding='utf-8') as f:
            f.write('[Desktop Entry]\nType=Application\nName=URL Trackbye\nComment=Start URL Trackbye with the desktop\nExec=' + SCRIPT + ' --background\nTerminal=false\n'
                    'Icon=' + os.path.join(HERE, 'assets', 'trackbye.png') + '\nX-KDE-autostart-after=panel\n')
    elif os.path.exists(AUTOSTART):
        os.remove(AUTOSTART)


LAUNCHER = os.path.expanduser('~/.local/share/applications/trackbye-app.desktop')


def install_launcher():
    """Application menu entry "URL Trackbye": starts the app (tray symbol, settings)."""
    os.makedirs(os.path.dirname(LAUNCHER), exist_ok=True)
    with open(LAUNCHER, 'w', encoding='utf-8') as f:
        f.write('[Desktop Entry]\nType=Application\nName=URL Trackbye\nGenericName=Link cleaner\nGenericName[de]=Link-Reiniger\n'
                'Comment=Settings and clipboard cleaning for URL Trackbye\n'
                'Comment[de]=Einstellungen und Zwischenablage-Reinigung von URL Trackbye\n'
                'Exec=' + SCRIPT + '\nTerminal=false\nIcon=' + os.path.join(HERE, 'assets', 'trackbye.png') +
                '\nCategories=Utility;\n')


# What to look for in the path of a browser process to tell which browser it is (most specific first).
PROCESS_HINTS = [('vivaldi', 'vivaldi'), ('brave', 'BraveSoftware/Brave-Browser'), ('microsoft-edge', 'microsoft-edge'),
                 ('msedge', 'microsoft-edge'), ('opera', 'opera'), ('floorp', 'floorp'), ('librewolf', 'librewolf'),
                 ('zen', 'zen'), ('waterfox', 'waterfox'), ('firefox', 'firefox'), ('chromium', 'chromium'),
                 ('google-chrome', 'google-chrome'), ('/chrome/chrome', 'google-chrome')]


def browser_id_from_process(text):
    """Browser id (as in browser_entries) for the path/command line of a browser process, or None."""
    low = text.lower()
    return next((browser_id for hint, browser_id in PROCESS_HINTS if hint in low), None)


def parent_browser():
    """The native host is started by the browser: look at the parent process to see which one it is."""
    try:
        ppid = os.getppid()
        text = os.path.realpath('/proc/%d/exe' % ppid) + ' ' + open('/proc/%d/cmdline' % ppid, 'rb').read().replace(b'\0', b' ').decode('utf-8', 'replace')[:300]
    except OSError:
        return None
    return browser_id_from_process(text)


def note_extension(msg):
    """The extension names its running version in every message; remember it, per browser (and when we last heard)."""
    state = read_json(EXTENSION_STATE, {})
    state.setdefault('version', None)  # None: an older extension that does not report its version
    state['seen'] = time.time()
    if msg.get('ext'):
        state['version'] = msg['ext']
    browser = parent_browser()
    if browser:
        entry = state.setdefault('browsers', {}).setdefault(browser, {})
        entry['seen'] = state['seen']
        if msg.get('ext'):
            entry['version'] = msg['ext']
    write_json(EXTENSION_STATE, state)


def extension_versions(max_age=3 * 86400):
    """{browser id: running extension version} for browsers heard from recently ('' = reports no version)."""
    state = read_json(EXTENSION_STATE, {})
    now = time.time()
    return {b: v.get('version') or '' for b, v in (state.get('browsers') or {}).items() if now - v.get('seen', 0) <= max_age}


def extension_outdated(max_age=3 * 86400):
    """(running, available) if a browser runs an older extension than the files on disk, else None.
    Only counts if the extension was heard from recently (otherwise it is probably not installed any more)."""
    available = extension_version()
    if not available:
        return None
    versions = extension_versions(max_age)
    if not versions:  # browsers not recognised: fall back to the overall version
        state = read_json(EXTENSION_STATE, {})
        if not state or time.time() - state.get('seen', 0) > max_age:
            return None
        versions = {'': state.get('version') or ''}
    old = [v for v in versions.values() if v != available]
    return (old[0], available) if old else None


def extension_version():
    return read_json(os.path.join(HERE, 'extension', 'manifest.json'), {}).get('version', '')


BIN_LINK = os.path.expanduser('~/.local/bin/trackbye')


def cmd_install(args):
    """Set URL Trackbye up for this user (everything lives in the home folder, no root needed)."""
    install_launcher()
    print('Menu entry "URL Trackbye": ' + LAUNCHER)
    if '--autostart' in args:
        set_autostart(True)
        print('Starts with the desktop session: ' + AUTOSTART)
    if '--native' in args:
        written = install_native()
        print('Link to the browser extension in %d browser(s):' % len(written))
        for target in written:
            print('  ' + target)
    if '--link' in args:
        os.makedirs(os.path.dirname(BIN_LINK), exist_ok=True)
        if os.path.islink(BIN_LINK) or os.path.exists(BIN_LINK):
            os.remove(BIN_LINK)
        os.symlink(SCRIPT, BIN_LINK)
        print('Command "trackbye": ' + BIN_LINK + ' (make sure ~/.local/bin is in your PATH)')


def cmd_uninstall(args):
    """Remove everything `install` and the app's settings window created; --purge also deletes settings and log."""
    cfg = load_config()
    if default_browser() == 'trackbye.desktop' and cfg.get('previous_default'):
        set_default_browser(cfg['previous_default'])
        print('Default browser restored to ' + cfg['previous_default'])
    for path in (LAUNCHER, desktop_file(), AUTOSTART):
        if os.path.exists(path):
            os.remove(path)
            print('Removed ' + path)
    for entry in browser_entries():
        target = native_manifest_path(entry)
        if os.path.exists(target):
            os.remove(target)
            print('Removed ' + target)
    if os.path.islink(BIN_LINK) and os.path.realpath(BIN_LINK) == SCRIPT:
        os.remove(BIN_LINK)
        print('Removed ' + BIN_LINK)
    if '--purge' in args:
        for folder in (CONFIG_DIR, STATE_DIR):
            shutil.rmtree(folder, ignore_errors=True)
            print('Removed ' + folder)
    print('Done. The extension itself is removed in the browser (its extensions page).')


def cmd_tray(background=False):
    try:
        import tray
    except ImportError as e:
        sys.exit('The tray app needs PyQt6 (Debian/Ubuntu/PikaOS: sudo apt install python3-pyqt6). ' + str(e))
    sys.exit(tray.run(background))


# Native messaging: each message is a 4-byte length (native byte order) followed by UTF-8 JSON.
def read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    size = struct.unpack('=I', raw)[0]
    return json.loads(sys.stdin.buffer.read(size).decode('utf-8'))


def send_message(obj):
    data = json.dumps(obj).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('=I', len(data)) + data)
    sys.stdout.buffer.flush()


def cmd_native():
    """Native messaging host. One-shot calls get one answer per message. An extension that opens a long-lived port
    starts with {"type": "hello"}; then this process also pushes {"type": "reload"} when the extension files on disk
    have a different version than the running extension, or when `trackbye reload-extension` was run (development
    installs only: the hello says "dev")."""
    lock = threading.Lock()
    state = {'ext': None, 'dev': False, 'watching': False}

    def send(obj):
        with lock:
            send_message(obj)

    def mtime():
        try:
            return os.stat(RELOAD_TRIGGER).st_mtime_ns
        except OSError:
            return 0

    def watch():
        seen_trigger = mtime()
        asked_for = None
        while True:
            time.sleep(1)
            disk = extension_version()
            if mtime() != seen_trigger:
                seen_trigger = mtime()
                if state['dev']:
                    diag('info', 'Asking the browser extension to reload (requested)')
                    send({'type': 'reload', 'reason': 'requested'})
            elif state['dev'] and state['ext'] and disk and disk != state['ext'] and asked_for != disk:
                asked_for = disk
                diag('info', 'Asking the browser extension to reload (%s -> %s)' % (state['ext'], disk))
                send({'type': 'reload', 'reason': 'version'})

    while True:
        msg = read_message()
        if msg is None:
            return
        kind = msg.get('type')
        note_extension(msg)
        if kind == 'hello':
            state['ext'] = msg.get('ext')
            # Only an unpacked/temporary (development) install picks up new files on reload. An installed, signed or
            # store version would just reload the same code, over and over, so it is never asked to.
            state['dev'] = bool(msg.get('dev'))
            note = read_json(EXTENSION_STATE, {})
            note['dev'] = state['dev']
            write_json(EXTENSION_STATE, note)
            diag('info', 'Browser extension %s connected' % (msg.get('ext') or '(old version)'))
            if not state['watching']:
                state['watching'] = True
                threading.Thread(target=watch, daemon=True).start()
            send({'ok': True})
        elif kind == 'rules':
            send({'ok': True, 'rules': load_rules()})
        elif kind == 'log':
            url = str(msg.get('url', ''))
            log_event(str(msg.get('source', 'browser')), url, clean_url(url, load_rules()))
            send({'ok': True})
        elif kind == 'diag':
            diag(str(msg.get('level', 'error')), str(msg.get('message', '')), 'browser extension')
            send({'ok': True})
        elif kind == 'open-settings':
            # same as starting the app by hand: opens the window of the running app, or starts the app
            subprocess.Popen([sys.executable, SCRIPT], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            send({'ok': True})
        elif kind == 'exclude':
            # the extension's "not on this site" switch, kept in the program's own list so every part agrees
            host = str(msg.get('host', '')).strip().lower()
            if host:
                rules = user_rules()
                hosts = [h for h in rules['exclude_hosts'] if h != host]
                rules['exclude_hosts'] = hosts + [host] if msg.get('on') else hosts
                save_user_rules(rules)
                diag('info', '%s %s the list of sites that are never changed' % (host, 'added to' if msg.get('on') else 'removed from'))
            send({'ok': True})
        elif kind == 'stats':
            entries = read_log()
            midnight = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
            send({'ok': True, 'total': len(entries), 'today': len([e for e in entries if e.get('t', 0) >= midnight]),
                  'recent': [{'t': e.get('t'), 'to': e.get('to'), 'removed': e.get('removed', [])} for e in entries[-5:]][::-1]})
        elif kind == 'version':
            send({'ok': True, 'version': extension_version(), 'program': VERSION})
        elif kind == 'clean':
            send({'ok': True, 'url': clean_url(str(msg.get('url', '')), load_rules())})
        else:
            send({'ok': True, 'pong': True})


def cmd_reload_extension():
    """Ask every connected browser extension to reload itself (used after changing extension files)."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(RELOAD_TRIGGER, 'w', encoding='utf-8') as f:
        f.write(str(time.time()))
    print('Asked the browser extension to reload (needs the extension 0.6.0+ loaded and the rule sharing set up).')


def main(argv):
    cmd = argv[1] if len(argv) > 1 else 'tray'
    try:
        return run(argv)
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as e:  # noqa: BLE001 - last resort: record it instead of failing silently
        diag('error', '%s failed: %s: %s' % (cmd if not (cmd.startswith('chrome-extension') or cmd.endswith('.json')) else 'native host',
                                             type(e).__name__, e), ''.join(traceback.format_exception_only(type(e), e)).strip())
        if cmd == 'open':  # the link must still open, even if cleaning broke
            try:
                os.execvp(load_config()['browser'], [load_config()['browser']] + argv[2:])
            except OSError as e2:
                diag('error', 'Could not start the browser "%s": %s' % (load_config()['browser'], e2))
        if cmd == 'filter-clip':
            return 0
        print('trackbye: ' + str(e), file=sys.stderr)
        return 1


def run(argv):
    # The browser starts a native host with the extension origin as its only argument.
    # Chrome-like browsers pass the extension origin, Firefox passes the path of this host's manifest and the add-on id.
    if len(argv) > 1 and (argv[1].startswith('chrome-extension://') or (argv[1].endswith('.json') and HOST_NAME in argv[1])):
        return cmd_native()
    cmd = argv[1] if len(argv) > 1 else 'tray'
    rest = argv[2:]
    if cmd == 'clean':
        cmd_clean(rest)
    elif cmd in ('tray', '--background'):
        # started with an argument (autostart): stay in the background; plain start (menu entry): open the window
        cmd_tray(background=len(argv) > 1)
    elif cmd == 'watch':
        cmd_watch()
    elif cmd == 'filter-clip':
        cmd_filter_clip()
    elif cmd == 'open':
        cmd_open(rest)
    elif cmd == 'install-handler':
        cmd_install_handler(rest)
    elif cmd == 'install-native':
        cmd_install_native()
    elif cmd == 'native':
        cmd_native()
    elif cmd == 'rules-update':
        status, message = rules_update('--force' in rest)
        print(json.dumps({'status': status, 'message': message}))
        return 0 if status != 'error' else 1
    elif cmd == 'rules-reset':
        rules_reset()
        print('Back to the rules that ship with the program.')
    elif cmd == 'install':
        cmd_install(rest)
    elif cmd == 'uninstall':
        cmd_uninstall(rest)
    elif cmd == 'reload-extension':
        cmd_reload_extension()
    else:
        print(__doc__)
        return 0 if cmd in ('help', '-h', '--help') else 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
