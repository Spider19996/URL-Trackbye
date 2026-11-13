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
  trackbye                   start the app (tray symbol, clipboard cleaning, log, settings). Needs PyQt6.
  trackbye watch             watch the clipboard (Wayland, needs wl-clipboard) and clean copied URLs
  trackbye open [URL...]     clean the URLs and open them in the real browser (use as default browser)
  trackbye install-handler   write the desktop entry that makes `open` selectable as default browser
  trackbye install-native    register the native messaging host for the browser extension
  trackbye reload-extension  ask the browser extension to reload itself (after changing its files)
  trackbye native            native messaging host (started by the browser extension, not by you)

Only the Python standard library is used. Rules: exact parameter names, matched per site (domain and subdomains).
Your own additions go into ~/.config/trackbye/rules.json (same format, merged with the built-in rules).
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback

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
                  'log': True, 'tray_icon': True, 'quick': ['clipboard', 'notify']}
SCRIPT = os.path.realpath(__file__)
VERSION = '0.6.0'


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


def load_rules():
    """Built-in rules plus the user's additions (union of lists, user sites appended)."""
    rules = read_json(os.path.join(HERE, 'rules.json'), {}, True)
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
    """Write the desktop entry that lets trackbye open links (selectable as default browser)."""
    path = desktop_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('[Desktop Entry]\nType=Application\nName=URL Trackbye (clean links, then open browser)\n'
                'Exec=' + SCRIPT + ' open %U\nTerminal=false\nIcon=' + os.path.join(HERE, 'assets', 'trackbye.png')
                + '\nCategories=Network;WebBrowser;\nMimeType=x-scheme-handler/http;x-scheme-handler/https;\n')
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


NATIVE_BROWSERS = {'Vivaldi': 'vivaldi', 'Chromium': 'chromium', 'Google Chrome': 'google-chrome',
                   'Brave': 'BraveSoftware/Brave-Browser'}


def native_manifest_path(folder):
    return os.path.join(os.path.expanduser('~/.config/' + folder), 'NativeMessagingHosts', HOST_NAME + '.json')


def install_native(folders=None):
    """Register the native messaging host for the given browser config folders (default: all that exist)."""
    manifest = {
        'name': HOST_NAME,
        'description': 'URL Trackbye: shares the cleaning rules with the browser extension',
        'path': SCRIPT,
        'type': 'stdio',
        'allowed_origins': ['chrome-extension://' + EXTENSION_ID + '/'],
    }
    written = []
    for folder in folders or NATIVE_BROWSERS.values():
        if not os.path.isdir(os.path.expanduser('~/.config/' + folder)):
            continue
        target = native_manifest_path(folder)
        write_json(target, manifest)
        written.append(target)
    return written


def cmd_install_native():
    for target in install_native():
        print('Wrote ' + target)


AUTOSTART = os.path.expanduser('~/.config/autostart/trackbye.desktop')


def set_autostart(on):
    if on:
        os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
        with open(AUTOSTART, 'w', encoding='utf-8') as f:
            f.write('[Desktop Entry]\nType=Application\nName=URL Trackbye\nExec=' + SCRIPT + '\nTerminal=false\n'
                    'Icon=' + os.path.join(HERE, 'assets', 'trackbye.png') + '\nX-KDE-autostart-after=panel\n')
    elif os.path.exists(AUTOSTART):
        os.remove(AUTOSTART)


LAUNCHER = os.path.expanduser('~/.local/share/applications/trackbye-app.desktop')


def install_launcher():
    """Application menu entry, so the settings stay reachable while the tray symbol is hidden."""
    os.makedirs(os.path.dirname(LAUNCHER), exist_ok=True)
    with open(LAUNCHER, 'w', encoding='utf-8') as f:
        f.write('[Desktop Entry]\nType=Application\nName=URL Trackbye\nComment=Remove tracking from links\n'
                'Exec=' + SCRIPT + '\nTerminal=false\nIcon=' + os.path.join(HERE, 'assets', 'trackbye.png') +
                '\nCategories=Network;Utility;\n')


def note_extension(msg):
    """The extension names its running version in every message; remember it (and when we last heard from it)."""
    state = read_json(EXTENSION_STATE, {})
    state['version'] = msg.get('ext')  # None: an older extension that does not report it
    state['seen'] = time.time()
    write_json(EXTENSION_STATE, state)


def extension_outdated(max_age=3 * 86400):
    """(running, available) if the browser runs an older extension than the files on disk, else None.
    Only counts if the extension was heard from recently (otherwise it is probably not installed any more)."""
    state = read_json(EXTENSION_STATE, {})
    available = extension_version()
    if not state or not available or time.time() - state.get('seen', 0) > max_age:
        return None
    running = state.get('version')
    return None if running == available else (running or '', available)


def extension_version():
    return read_json(os.path.join(HERE, 'extension', 'manifest.json'), {}).get('version', '')


def cmd_tray():
    try:
        import tray
    except ImportError as e:
        sys.exit('The tray app needs PyQt6 (Debian/Ubuntu/PikaOS: sudo apt install python3-pyqt6). ' + str(e))
    sys.exit(tray.run())


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
    have a different version than the running extension, or when `trackbye reload-extension` was run."""
    lock = threading.Lock()
    state = {'ext': None, 'watching': False}

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
                diag('info', 'Asking the browser extension to reload (requested)')
                send({'type': 'reload', 'reason': 'requested'})
            elif state['ext'] and disk and disk != state['ext'] and asked_for != disk:
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
        diag('error', '%s failed: %s: %s' % (cmd if not cmd.startswith('chrome-extension') else 'native host',
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
    if len(argv) > 1 and argv[1].startswith('chrome-extension://'):
        return cmd_native()
    cmd = argv[1] if len(argv) > 1 else 'tray'
    rest = argv[2:]
    if cmd == 'clean':
        cmd_clean(rest)
    elif cmd == 'tray':
        cmd_tray()
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
    elif cmd == 'reload-extension':
        cmd_reload_extension()
    else:
        print(__doc__)
        return 0 if cmd in ('help', '-h', '--help') else 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
