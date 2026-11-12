#!/usr/bin/env python3
"""trackbye - remove tracking parameters from links, system-wide.

One small program with several jobs that all use the same rules (rules.json):

  trackbye clean URL...      print the cleaned URLs
  trackbye tray              tray app (needs PyQt6): clipboard cleaning, settings window, browser setup
  trackbye watch             watch the clipboard (Wayland, needs wl-clipboard) and clean copied URLs
  trackbye open [URL...]     clean the URLs and open them in the real browser (use as default browser)
  trackbye install-handler   write the desktop entry that makes `open` selectable as default browser
  trackbye install-native    register the native messaging host for the browser extension
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

HERE = os.path.dirname(os.path.realpath(__file__))
CONFIG_DIR = os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), 'trackbye')
HOST_NAME = 'de.trackbye.host'
# Fixed by the "key" in extension/manifest.json, so the host manifest can name exactly this extension.
EXTENSION_ID = 'kcppbmmghccgpmjafccjammekemegidd'
DEFAULT_CONFIG = {'browser': 'vivaldi-stable', 'notify': False, 'clipboard': True, 'previous_default': ''}
SCRIPT = os.path.realpath(__file__)
VERSION = '0.2.1'


# --------------------------------------------------------------------------------------------------------------
# Rules and cleaning
# --------------------------------------------------------------------------------------------------------------

def read_json(path, fallback):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return fallback


def load_rules():
    """Built-in rules plus the user's additions (union of lists, user sites appended)."""
    rules = read_json(os.path.join(HERE, 'rules.json'), {})
    user = read_json(os.path.join(CONFIG_DIR, 'rules.json'), {})
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
        subprocess.run(['wl-copy', '--type', 'text/plain'], input=cleaned.encode('utf-8'), check=False)
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
    os.execvp(browser, [browser] + [clean_url(a, rules) for a in args])


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
            f.write('[Desktop Entry]\nType=Application\nName=URL Trackbye\nExec=' + SCRIPT + ' tray\nTerminal=false\n'
                    'Icon=' + os.path.join(HERE, 'assets', 'trackbye.png') + '\nX-KDE-autostart-after=panel\n')
    elif os.path.exists(AUTOSTART):
        os.remove(AUTOSTART)


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
    while True:
        msg = read_message()
        if msg is None:
            return
        kind = msg.get('type')
        if kind == 'rules':
            send_message({'ok': True, 'rules': load_rules()})
        elif kind == 'version':
            send_message({'ok': True, 'version': extension_version(), 'program': VERSION})
        elif kind == 'clean':
            send_message({'ok': True, 'url': clean_url(str(msg.get('url', '')), load_rules())})
        else:
            send_message({'ok': True, 'pong': True})


def main(argv):
    # The browser starts a native host with the extension origin as its only argument.
    if len(argv) > 1 and argv[1].startswith('chrome-extension://'):
        return cmd_native()
    cmd = argv[1] if len(argv) > 1 else ''
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
    else:
        print(__doc__)
        return 0 if cmd in ('', '-h', '--help') else 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
