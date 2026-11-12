"""URL Trackbye tray app: runs in the background, cleans copied links and has a settings window.

Started by `trackbye tray` (needs PyQt6). The clipboard is watched by `wl-paste --watch` (Wayland), which calls
`trackbye filter-clip` for every change; this app only starts, stops and restarts that watcher.
"""
import os
import shutil
import sys
import time

from PyQt6.QtCore import QLocale, QProcess, QTimer, QUrl, Qt
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                             QPlainTextEdit, QPushButton, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QTabWidget,
                             QVBoxLayout, QWidget)

import trackbye as tb

ASSETS = os.path.join(tb.HERE, 'assets')
ICON = os.path.join(ASSETS, 'trackbye.png')  # app and window icon
TEST_MARKER = 'trackbye-test'
TEST_URL = 'https://example.com/?id=5&utm_source=trackbye-test&utm_medium=email&fbclid=trackbye-test'
SERVER_NAME = 'trackbye-app'  # a second start talks to the running app through this socket

# (English, German)
TEXT = {
    'title': ('URL Trackbye', 'URL Trackbye'),
    'clip': ('Clean copied links', 'Kopierte Links säubern'),
    'notify': ('Show a notification when a link was cleaned', 'Benachrichtigung zeigen, wenn ein Link gesäubert wurde'),
    'autostart': ('Start with the desktop session', 'Mit der Desktop-Sitzung starten'),
    'browser': ('Browser command (used to open links)', 'Browser-Befehl (zum Öffnen von Links)'),
    'settings': ('Settings…', 'Einstellungen…'),
    'quit': ('Quit', 'Beenden'),
    'tab_general': ('General', 'Allgemein'),
    'tab_rules': ('Rules', 'Regeln'),
    'tab_browser': ('Browser', 'Browser'),
    'tab_about': ('Info and log', 'Info und Protokoll'),
    'no_wl': ('wl-clipboard (wl-paste, wl-copy) is missing: copied links cannot be cleaned. Install it: sudo apt install wl-clipboard',
              'wl-clipboard (wl-paste, wl-copy) fehlt: kopierte Links können nicht gesäubert werden. Installieren: sudo apt install wl-clipboard'),
    'rules_help': ('Your own additions to the built-in rules. One parameter name per line (exact names, no wildcards).',
                   'Deine eigenen Ergänzungen zu den eingebauten Regeln. Ein Parametername pro Zeile (genaue Namen, keine Platzhalter).'),
    'global': ('Remove on every site', 'Auf jeder Seite entfernen'),
    'excluded': ('Never change links on these domains', 'Links dieser Domains nie ändern'),
    'sites': ('Remove only on certain sites', 'Nur auf bestimmten Seiten entfernen'),
    'col_domains': ('Domains (comma separated)', 'Domains (durch Komma getrennt)'),
    'col_params': ('Parameters (comma separated)', 'Parameter (durch Komma getrennt)'),
    'add_row': ('Add site', 'Seite hinzufügen'),
    'del_row': ('Remove selected', 'Auswahl entfernen'),
    'save': ('Save', 'Speichern'),
    'saved': ('Saved.', 'Gespeichert.'),
    'builtin': ('Built-in rules: {p} parameters and {s} sites', 'Eingebaute Regeln: {p} Parameter und {s} Seiten'),
    'try': ('Try it: paste a link', 'Ausprobieren: Link einfügen'),
    'ext_head': ('Browser extension', 'Browser-Erweiterung'),
    'ext_help': ('Load it once: open vivaldi://extensions (or chrome://extensions), enable developer mode, "Load unpacked", choose this folder.',
                 'Einmal laden: vivaldi://extensions (oder chrome://extensions) öffnen, Entwicklermodus einschalten, "Entpackte Erweiterung laden", diesen Ordner wählen.'),
    'open_folder': ('Open folder', 'Ordner öffnen'),
    'native_head': ('Share the rules with the extension (native messaging)', 'Regeln mit der Erweiterung teilen (Native Messaging)'),
    'col_browser': ('Browser', 'Browser'),
    'col_found': ('Found', 'Gefunden'),
    'col_reg': ('Registered', 'Eingerichtet'),
    'register': ('Register', 'Einrichten'),
    'yes': ('yes', 'ja'),
    'no': ('no', 'nein'),
    'opener_head': ('Links from other apps (Discord, mail, …)', 'Links aus anderen Programmen (Discord, Mail, …)'),
    'opener_help': ('Make URL Trackbye the default browser: it cleans the link and then opens your real browser.',
                    'URL Trackbye als Standardbrowser eintragen: Es säubert den Link und öffnet dann deinen echten Browser.'),
    'opener_status': ('Default browser now: {d}', 'Aktueller Standardbrowser: {d}'),
    'install_entry': ('Install menu entry', 'Menüeintrag installieren'),
    'make_default': ('Use as default browser', 'Als Standardbrowser verwenden'),
    'restore_default': ('Restore previous default browser', 'Vorherigen Standardbrowser wiederherstellen'),
    'confirm_default': ('Make URL Trackbye your default browser? You can restore the previous one here at any time.',
                        'URL Trackbye als Standardbrowser festlegen? Den vorherigen kannst du hier jederzeit wiederherstellen.'),
    'about': ('Removes tracking parameters from links: in the clipboard, in links opened by other apps and in the browser (extension).\nMIT license.',
              'Entfernt Tracking-Parameter aus Links: in der Zwischenablage, in Links aus anderen Programmen und im Browser (Erweiterung).\nMIT-Lizenz.'),
    'tab_log': ('Cleaned links', 'Gesäuberte Links'),
    'tray_icon': ('Show the tray icon (if hidden: start URL Trackbye again or use the application menu entry to open this window)',
                  'Tray-Symbol anzeigen (wenn ausgeblendet: URL Trackbye erneut starten oder den Eintrag im Anwendungsmenü nutzen)'),
    'log_on': ('Keep a log of cleaned links', 'Protokoll über gesäuberte Links führen'),
    'quit_app': ('Quit URL Trackbye', 'URL Trackbye beenden'),
    'log_help': ('Newest first. The log is stored on this computer only (up to 500 entries).',
                 'Neueste zuerst. Das Protokoll liegt nur auf diesem Computer (bis zu 500 Einträge).'),
    'col_time': ('Time', 'Zeit'),
    'col_source': ('From', 'Quelle'),
    'col_removed': ('Removed', 'Entfernt'),
    'col_link': ('Cleaned link', 'Gesäuberter Link'),
    'src_clipboard': ('Clipboard', 'Zwischenablage'),
    'src_opener': ('Opened by an app', 'Von Programm geöffnet'),
    'src_browser': ('Browser', 'Browser'),
    'src_browser-copy': ('Browser (copy)', 'Browser (Kopie)'),
    'log_copy': ('Copy cleaned link', 'Gesäuberten Link kopieren'),
    'log_clear': ('Clear log', 'Protokoll leeren'),
    'tab_events': ('Messages', 'Meldungen'),
    'events_help': ('What the app did and what went wrong. Send this when you report a problem.',
                    'Was die App getan hat und was schiefging. Bei Problemen bitte mitschicken.'),
    'only_problems': ('Only warnings and errors', 'Nur Warnungen und Fehler'),
    'col_level': ('Level', 'Stufe'),
    'col_message': ('Message', 'Meldung'),
    'lvl_info': ('Info', 'Info'),
    'lvl_warning': ('Warning', 'Warnung'),
    'lvl_error': ('Error', 'Fehler'),
    'events_clear': ('Clear messages', 'Meldungen leeren'),
    'events_copy': ('Copy all', 'Alle kopieren'),
    'problem': ('URL Trackbye: problem', 'URL Trackbye: Problem'),
    'ext_installed': ('Version in the browser:', 'Version im Browser:'),
    'ext_current': ('Current version:', 'Aktuelle Version:'),
    'ext_state': ('Status:', 'Status:'),
    'ext_ok': ('up to date', 'aktuell'),
    'ext_none': ('unknown', 'unbekannt'),
    'ext_old': ('Extension is outdated: the browser runs {r}, available is {a}. Reload it on the extensions page (it also reloads itself within about 30 minutes).',
                'Erweiterung veraltet: Der Browser nutzt {r}, verfügbar ist {a}. Auf der Erweiterungsseite neu laden (sie lädt sich auch selbst innerhalb von etwa 30 Minuten neu).'),
    'ext_old_short': ('outdated: reload it on the extensions page', 'veraltet: auf der Erweiterungsseite neu laden'),
    'ext_unknown': ('no contact yet (not loaded, or the rule sharing below is not set up)',
                    'noch kein Kontakt (nicht geladen oder die Regel-Anbindung unten nicht eingerichtet)'),
    'ext_note': ('The version only changes when the extension itself changed; program updates that do not touch it never ask you to reload it.',
                 'Die Version ändert sich nur, wenn die Erweiterung selbst geändert wurde; Programm-Updates ohne Änderung daran verlangen kein Neuladen.'),
    'ext_older': ('an older version', 'eine ältere Version'),
    'ext_page': ('Open the extensions page', 'Erweiterungsseite öffnen'),
    'ext_notice_title': ('URL Trackbye: update the extension', 'URL Trackbye: Erweiterung aktualisieren'),
    'quick_head': ('Quick settings in the tray menu (right click)', 'Schnelleinstellungen im Tray-Menü (Rechtsklick)'),
    'm_clipboard': ('Clean copied links', 'Kopierte Links säubern'),
    'm_notify': ('Notifications', 'Benachrichtigungen'),
    'm_log': ('Keep log', 'Protokoll führen'),
    'm_autostart': ('Start with the desktop', 'Mit dem Desktop starten'),
    'example_text': ('Example: a rule for the domain "example.com" that removes "ref" and "source" turns\n'
                     'https://example.com/page?id=5&ref=newsletter&source=mail   into   https://example.com/page?id=5\n'
                     'Everything else in the link stays. Rules apply to the domain and all its subdomains.',
                     'Beispiel: Eine Regel für die Domain "example.com", die "ref" und "source" entfernt, macht aus\n'
                     'https://example.com/page?id=5&ref=newsletter&source=mail   den Link   https://example.com/page?id=5\n'
                     'Alles andere im Link bleibt. Regeln gelten für die Domain und alle ihre Unterdomains.'),
    'insert_example': ('Insert example rule', 'Beispielregel einfügen'),
    'ph_global': ('e.g. my_tracker (one name per line)', 'z. B. my_tracker (ein Name pro Zeile)'),
    'ph_excluded': ('e.g. shop.example.org (one domain per line)', 'z. B. shop.example.org (eine Domain pro Zeile)'),
    'try_hint': ('Changes show here right away; they only apply to real links after you press Save.',
                 'Änderungen sieht man hier sofort; für echte Links gelten sie erst nach "Speichern".'),
    'tab_test': ('Test', 'Test'),
    'tst_help': ('Try each part with this example link. The tracking parts (utm_source, utm_medium, fbclid) should disappear, only "?id=5" should stay.',
                 'Probiere jeden Teil mit diesem Beispiel-Link aus. Die Tracking-Teile (utm_source, utm_medium, fbclid) sollten verschwinden, nur "?id=5" bleibt.'),
    'tst_url': ('Example link (with tracking):', 'Beispiel-Link (mit Tracking):'),
    'tst_expect': ('Expected result:', 'Erwartetes Ergebnis:'),
    'tst_copy': ('1. Copy the example link', '1. Beispiel-Link kopieren'),
    'tst_copy_info': ('Tests the clipboard cleaning. Then paste it anywhere to see the result.',
                      'Testet das Säubern der Zwischenablage. Danach irgendwo einfügen, um das Ergebnis zu sehen.'),
    'tst_browser': ('2. Open it in the browser', '2. Im Browser öffnen'),
    'tst_browser_info': ('Tests the browser extension: the address bar should show only ?id=5 (the page example.com opens).',
                         'Testet die Browser-Erweiterung: Die Adresszeile sollte nur ?id=5 zeigen (es öffnet sich die Seite example.com).'),
    'tst_system': ('3. Open it like another app would', '3. Wie ein anderes Programm öffnen'),
    'tst_system_info': ('Tests the link opener (Discord, mail, …): it works when URL Trackbye is the default browser.',
                        'Testet den Link-Öffner (Discord, Mail, …): Er greift, wenn URL Trackbye der Standardbrowser ist.'),
    'tst_none': ('not tested yet', 'noch nicht getestet'),
    'tst_wait': ('waiting …', 'warte …'),
    'tst_ok': ('✓ cleaned at {t}, removed: {r}', '✓ gesäubert um {t}, entfernt: {r}'),
    'tst_fail_clip': ('✗ nothing happened. Is "Clean copied links" on and wl-clipboard installed? See Messages.',
                      '✗ nichts passiert. Ist "Kopierte Links säubern" an und wl-clipboard installiert? Siehe Meldungen.'),
    'tst_fail_browser': ('✗ not seen here. Look at the address bar. It shows up here only with the extension loaded and the rule sharing set up (Browser tab).',
                         '✗ hier nicht gesehen. Schau in die Adresszeile. Hier erscheint es nur mit geladener Erweiterung und eingerichteter Regel-Anbindung (Tab Browser).'),
    'tst_fail_system': ('✗ not seen: URL Trackbye is not your default browser (Browser tab), or the system opened the link directly.',
                        '✗ nicht gesehen: URL Trackbye ist nicht dein Standardbrowser (Tab Browser) oder das System hat den Link direkt geöffnet.'),
    'tst_row_clip': ('Clipboard', 'Zwischenablage'),
    'tst_row_browser': ('Browser extension', 'Browser-Erweiterung'),
    'tst_row_system': ('Link opener', 'Link-Öffner'),
    'show_builtin': ('Show built-in rules', 'Eingebaute Regeln anzeigen'),
}
LANG = 1 if QLocale.system().name().startswith('de') else 0


# key, label in the settings window, short label in the tray menu, theme icon name
OPTIONS = [
    ('clipboard', 'clip', 'm_clipboard', 'edit-paste'),
    ('notify', 'notify', 'm_notify', 'preferences-desktop-notification'),
    ('log', 'log_on', 'm_log', 'view-list-text'),
    ('autostart', 'autostart', 'm_autostart', 'system-run'),
]


def option_state(key):
    if key == 'autostart':
        return os.path.exists(tb.AUTOSTART)
    return bool(tb.load_config()[key])


def sync(widget, on):
    widget.blockSignals(True)
    widget.setChecked(bool(on))
    widget.blockSignals(False)


def t(key, **kw):
    return TEXT[key][LANG].format(**kw) if kw else TEXT[key][LANG]


def lines(widget):
    return [ln.strip() for ln in widget.toPlainText().splitlines() if ln.strip()]


def split_csv(text):
    return [p.strip() for p in text.split(',') if p.strip()]


# --------------------------------------------------------------------------------------------------------------
# Clipboard watcher process
# --------------------------------------------------------------------------------------------------------------

class ClipboardService:
    """Keeps `wl-paste --watch` running while clipboard cleaning is switched on."""

    def __init__(self):
        self.proc = None
        self.wanted = False
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.start)

    @staticmethod
    def available():
        return bool(shutil.which('wl-paste') and shutil.which('wl-copy'))

    def start(self):
        self.wanted = True
        if not self.available():
            tb.diag('warning', 'wl-clipboard (wl-paste, wl-copy) is not installed: copied links cannot be cleaned')
            return
        if self.proc is not None:
            return
        self.proc = QProcess()
        self.proc.finished.connect(self._finished)
        self.proc.start('wl-paste', ['--type', 'text', '--watch', sys.executable, tb.SCRIPT, 'filter-clip'])
        tb.diag('info', 'Clipboard cleaning started')

    def stop(self):
        self.wanted = False
        self.timer.stop()
        if self.proc is not None:
            proc, self.proc = self.proc, None
            proc.finished.disconnect()
            proc.terminate()
            proc.waitForFinished(1000)
            tb.diag('info', 'Clipboard cleaning stopped')

    def _finished(self, code=0, status=None):
        proc, self.proc = self.proc, None
        if self.wanted:
            err = bytes(proc.readAllStandardError()).decode('utf-8', 'replace').strip() if proc is not None else ''
            tb.diag('error', 'The clipboard watcher stopped (exit %s)%s; restarting in 3 seconds' % (code, ': ' + err if err else ''))
            self.timer.start(3000)

    def sync(self, on):
        self.start() if on else self.stop()


# --------------------------------------------------------------------------------------------------------------
# Settings window
# --------------------------------------------------------------------------------------------------------------

class SettingsWindow(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle(t('title'))
        self.setWindowIcon(QIcon(ICON))
        self.resize(640, 560)
        tabs = QTabWidget()
        tabs.addTab(self.general_tab(), t('tab_general'))
        tabs.addTab(self.rules_tab(), t('tab_rules'))
        tabs.addTab(self.browser_tab(), t('tab_browser'))
        tabs.addTab(self.about_tab(), t('tab_about'))
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

    # --- General ---------------------------------------------------------------------------------------------
    def general_tab(self):
        cfg = tb.load_config()
        page = QWidget()
        form = QVBoxLayout(page)
        self.checks = {}
        for key, label, _, _ in OPTIONS:
            chk = QCheckBox(t(label))
            chk.setChecked(option_state(key))
            chk.toggled.connect(lambda on, k=key: self.app.set_option(k, on))
            self.checks[key] = chk
            form.addWidget(chk)
        self.chk_tray = QCheckBox(t('tray_icon'))
        self.chk_tray.setChecked(cfg['tray_icon'])
        self.chk_tray.toggled.connect(self.app.set_tray_visible)
        form.addWidget(self.chk_tray)
        quick = QGroupBox(t('quick_head'))
        quick_box = QVBoxLayout(quick)
        self.quick_checks = {}
        for key, _, menu_label, _ in OPTIONS:
            chk = QCheckBox(t(menu_label))
            chk.setChecked(key in cfg['quick'])
            chk.toggled.connect(self.save_quick)
            self.quick_checks[key] = chk
            quick_box.addWidget(chk)
        form.addWidget(quick)
        if not ClipboardService.available():
            warn = QLabel(t('no_wl'))
            warn.setWordWrap(True)
            warn.setStyleSheet('color: #c0392b')
            form.addWidget(warn)
        row = QFormLayout()
        self.edit_browser = QLineEdit(cfg['browser'])
        self.edit_browser.editingFinished.connect(lambda: self.save_cfg('browser', self.edit_browser.text().strip() or 'vivaldi-stable'))
        row.addRow(t('browser'), self.edit_browser)
        form.addLayout(row)
        form.addStretch(1)
        quit_btn = QPushButton(t('quit_app'))
        quit_btn.clicked.connect(self.app.quit)
        form.addWidget(quit_btn, alignment=Qt.AlignmentFlag.AlignRight)
        return page

    def save_quick(self):
        self.save_cfg('quick', [k for k, _, _, _ in OPTIONS if self.quick_checks[k].isChecked()])
        self.app.rebuild_menu()

    def save_cfg(self, key, value):
        cfg = tb.load_config()
        cfg[key] = value
        tb.save_config(cfg)

    # --- Rules -----------------------------------------------------------------------------------------------
    def rules_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        help_label = QLabel(t('rules_help'))
        help_label.setWordWrap(True)
        box.addWidget(help_label)
        rules = tb.user_rules()

        box.addWidget(QLabel(t('global')))
        self.ed_global = QPlainTextEdit('\n'.join(rules['global_remove']))
        self.ed_global.setMaximumHeight(80)
        self.ed_global.setPlaceholderText(t('ph_global'))
        box.addWidget(self.ed_global)

        box.addWidget(QLabel(t('excluded')))
        self.ed_excluded = QPlainTextEdit('\n'.join(rules['exclude_hosts']))
        self.ed_excluded.setMaximumHeight(60)
        self.ed_excluded.setPlaceholderText(t('ph_excluded'))
        box.addWidget(self.ed_excluded)

        box.addWidget(QLabel(t('sites')))
        example = QLabel(t('example_text'))
        example.setWordWrap(True)
        example.setStyleSheet('color: gray')
        box.addWidget(example)
        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels([t('col_domains'), t('col_params')])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setColumnWidth(0, 250)
        for site in rules['sites']:
            self.add_site_row(', '.join(site.get('hosts', [])), ', '.join(site.get('remove', [])))
        box.addWidget(self.tbl)
        buttons = QHBoxLayout()
        add = QPushButton(t('add_row'))
        add.clicked.connect(lambda: self.add_site_row('', ''))
        delete = QPushButton(t('del_row'))
        delete.clicked.connect(lambda: [self.tbl.removeRow(i.row()) for i in sorted(self.tbl.selectionModel().selectedRows(), key=lambda x: -x.row())])
        example_btn = QPushButton(t('insert_example'))
        example_btn.clicked.connect(self.insert_example)
        save = QPushButton(t('save'))
        save.clicked.connect(self.save_rules)
        self.saved_label = QLabel('')
        for b in (add, delete, example_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(self.saved_label)
        buttons.addWidget(save)
        box.addLayout(buttons)

        merged = tb.load_rules()
        builtin = QPushButton(t('show_builtin'))
        builtin.clicked.connect(self.show_builtin)
        info = QHBoxLayout()
        info.addWidget(QLabel(t('builtin', p=len(merged['global_remove']), s=len(merged['sites']))))
        info.addStretch(1)
        info.addWidget(builtin)
        box.addLayout(info)

        box.addWidget(QLabel(t('try')))
        self.try_in = QLineEdit()
        self.try_out = QLabel('')
        self.try_out.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.try_out.setWordWrap(True)
        self.try_in.textChanged.connect(self.update_try)
        self.ed_global.textChanged.connect(self.update_try)
        self.ed_excluded.textChanged.connect(self.update_try)
        self.tbl.itemChanged.connect(self.update_try)
        hint = QLabel(t('try_hint'))
        hint.setStyleSheet('color: gray')
        box.addWidget(self.try_in)
        box.addWidget(self.try_out)
        box.addWidget(hint)
        return page

    def add_site_row(self, domains, params):
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        self.tbl.setItem(row, 0, QTableWidgetItem(domains))
        self.tbl.setItem(row, 1, QTableWidgetItem(params))

    def editor_rules(self):
        """The user rules as currently typed in the editors (not necessarily saved yet)."""
        sites = []
        for r in range(self.tbl.rowCount()):
            hosts = split_csv(self.tbl.item(r, 0).text() if self.tbl.item(r, 0) else '')
            remove = split_csv(self.tbl.item(r, 1).text() if self.tbl.item(r, 1) else '')
            if hosts and remove:
                sites.append({'hosts': hosts, 'remove': remove})
        return {'global_remove': lines(self.ed_global), 'exclude_hosts': lines(self.ed_excluded), 'sites': sites}

    def update_try(self, *_):
        text = self.try_in.text()
        if not tb.is_url(text):
            self.try_out.setText('')
            return
        builtin = tb.read_json(os.path.join(tb.HERE, 'rules.json'), {})
        mine = self.editor_rules()
        merged = {k: list(builtin.get(k, [])) + list(mine[k]) for k in ('exclude_hosts', 'global_remove', 'sites')}
        self.try_out.setText(tb.clean_url(text, merged))

    def insert_example(self):
        self.add_site_row('example.com', 'ref, source')
        self.tbl.scrollToBottom()
        self.try_in.setText('https://example.com/page?id=5&ref=newsletter&source=mail')

    def save_rules(self):
        sites = []
        for r in range(self.tbl.rowCount()):
            hosts = split_csv(self.tbl.item(r, 0).text() if self.tbl.item(r, 0) else '')
            remove = split_csv(self.tbl.item(r, 1).text() if self.tbl.item(r, 1) else '')
            if hosts and remove:
                sites.append({'hosts': hosts, 'remove': remove})
        tb.save_user_rules({'global_remove': lines(self.ed_global), 'exclude_hosts': lines(self.ed_excluded), 'sites': sites})
        self.saved_label.setText(t('saved'))
        QTimer.singleShot(2500, lambda: self.saved_label.setText(''))
        self.try_in.textChanged.emit(self.try_in.text())

    def show_builtin(self):
        r = tb.read_json(os.path.join(tb.HERE, 'rules.json'), {})
        text = 'Everywhere:\n  ' + ', '.join(r.get('global_remove', [])) + '\n\nNever changed:\n  ' + ', '.join(r.get('exclude_hosts', []))
        for s in r.get('sites', []):
            text += '\n\n' + s.get('name', '') + ' (' + ', '.join(s['hosts']) + '):\n  ' + ', '.join(s['remove'])
        dlg = QPlainTextEdit(text)
        dlg.setReadOnly(True)
        dlg.setWindowTitle(t('show_builtin'))
        dlg.resize(560, 480)
        self._builtin = dlg
        dlg.show()

    # --- Test ------------------------------------------------------------------------------------------------
    def test_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        help_label = QLabel(t('tst_help'))
        help_label.setWordWrap(True)
        box.addWidget(help_label)
        form = QFormLayout()
        url = QLineEdit(TEST_URL)
        url.setReadOnly(True)
        form.addRow(t('tst_url'), url)
        expected = QLineEdit(tb.clean_url(TEST_URL, tb.load_rules()))
        expected.setReadOnly(True)
        form.addRow(t('tst_expect'), expected)
        box.addLayout(form)
        self.tests = {}     # key -> time the test was started
        self.test_labels = {}
        steps = (('clipboard', 'tst_copy', 'tst_copy_info', 'tst_row_clip', self.test_copy),
                 ('browser', 'tst_browser', 'tst_browser_info', 'tst_row_browser', self.test_browser),
                 ('opener', 'tst_system', 'tst_system_info', 'tst_row_system', self.test_system))
        for key, button, info, row, action in steps:
            line = QHBoxLayout()
            btn = QPushButton(t(button))
            btn.setMinimumWidth(240)
            btn.clicked.connect(action)
            line.addWidget(btn)
            text = QLabel(t(info))
            text.setWordWrap(True)
            text.setStyleSheet('color: gray')
            line.addWidget(text, 1)
            box.addLayout(line)
            result = QLabel(t('tst_row_' + {'clipboard': 'clip', 'browser': 'browser', 'opener': 'system'}[key]) + ': ' + t('tst_none'))
            result.setWordWrap(True)
            result.setContentsMargins(12, 0, 0, 6)
            result.setMinimumHeight(44)
            result.setAlignment(Qt.AlignmentFlag.AlignTop)
            box.addWidget(result)
            self.test_labels[key] = result
        box.addStretch(1)
        return page

    def start_test(self, key):
        self.tests[key] = time.time()
        self.show_test(key, t('tst_wait'))

    def test_copy(self):
        self.start_test('clipboard')
        QApplication.clipboard().setText(TEST_URL)

    def test_browser(self):
        self.start_test('browser')
        QProcess.startDetached(tb.load_config()['browser'], [TEST_URL])

    def test_system(self):
        self.start_test('opener')
        QDesktopServices.openUrl(QUrl(TEST_URL))

    def show_test(self, key, text, color=''):
        names = {'clipboard': 'tst_row_clip', 'browser': 'tst_row_browser', 'opener': 'tst_row_system'}
        label = self.test_labels[key]
        label.setText(t(names[key]) + ': ' + text)
        label.setStyleSheet('color: ' + color if color else '')

    def refresh_tests(self):
        """Look in the log for the effect of each started test; give up after 12 seconds."""
        if not self.tests:
            return
        events = tb.read_log()
        fail = {'clipboard': 'tst_fail_clip', 'browser': 'tst_fail_browser', 'opener': 'tst_fail_system'}
        for key, started in list(self.tests.items()):
            hit = [e for e in events if e.get('src') == key and TEST_MARKER in e.get('from', '') and e.get('t', 0) >= started - 1]
            if hit:
                e = hit[-1]
                self.show_test(key, t('tst_ok', t=time.strftime('%H:%M:%S', time.localtime(e['t'])), r=', '.join(e.get('removed', []))), '#1e8449')
                del self.tests[key]
            elif time.time() - started > 12:
                self.show_test(key, t(fail[key]), '#c0392b')
                del self.tests[key]

    # --- Log -------------------------------------------------------------------------------------------------
    def log_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        help_label = QLabel(t('log_help'))
        help_label.setWordWrap(True)
        box.addWidget(help_label)
        self.log_table = QTableWidget(0, 4)
        self.log_table.setHorizontalHeaderLabels([t('col_time'), t('col_source'), t('col_removed'), t('col_link')])
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.setColumnWidth(0, 120)
        self.log_table.setColumnWidth(1, 130)
        self.log_table.setColumnWidth(2, 170)
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        box.addWidget(self.log_table)
        row = QHBoxLayout()
        copy = QPushButton(t('log_copy'))
        copy.clicked.connect(self.copy_log_link)
        clear = QPushButton(t('log_clear'))
        clear.clicked.connect(self.clear_log)
        row.addWidget(copy)
        row.addStretch(1)
        row.addWidget(clear)
        box.addLayout(row)
        self.log_signature = None
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.refresh_log)
        self.log_timer.timeout.connect(lambda: self.refresh_events())
        self.log_timer.timeout.connect(self.refresh_tests)
        self.refresh_log()
        return page

    def refresh_log(self):
        try:
            st = os.stat(tb.LOG_PATH)
            signature = (st.st_mtime_ns, st.st_size)
        except OSError:
            signature = None
        if signature == self.log_signature:
            return
        self.log_signature = signature
        entries = list(reversed(tb.read_log()))[:300]
        self.log_table.setRowCount(len(entries))
        for i, e in enumerate(entries):
            stamp = time.strftime('%d.%m. %H:%M:%S', time.localtime(e.get('t', 0)))
            source = TEXT['src_' + e.get('src', '')][LANG] if 'src_' + e.get('src', '') in TEXT else e.get('src', '')
            cells = [stamp, source, ', '.join(e.get('removed', [])), e.get('to', '')]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(e.get('from', '') + '\n→ ' + e.get('to', ''))
                self.log_table.setItem(i, c, item)

    def copy_log_link(self):
        rows = self.log_table.selectionModel().selectedRows()
        if rows:
            QApplication.clipboard().setText(self.log_table.item(rows[0].row(), 3).text())

    def clear_log(self):
        tb.clear_log()
        self.refresh_log()

    def showEvent(self, event):
        self.log_timer.start(1500)
        self.refresh_log()
        super().showEvent(event)

    def hideEvent(self, event):
        self.log_timer.stop()
        super().hideEvent(event)

    # --- Messages --------------------------------------------------------------------------------------------
    def events_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        help_label = QLabel(t('events_help'))
        help_label.setWordWrap(True)
        box.addWidget(help_label)
        self.only_problems = QCheckBox(t('only_problems'))
        self.only_problems.toggled.connect(lambda _: self.refresh_events(True))
        box.addWidget(self.only_problems)
        self.ev_table = QTableWidget(0, 3)
        self.ev_table.setHorizontalHeaderLabels([t('col_time'), t('col_level'), t('col_message')])
        self.ev_table.horizontalHeader().setStretchLastSection(True)
        self.ev_table.setColumnWidth(0, 120)
        self.ev_table.setColumnWidth(1, 80)
        self.ev_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ev_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.ev_table.verticalHeader().setVisible(False)
        box.addWidget(self.ev_table)
        row = QHBoxLayout()
        copy = QPushButton(t('events_copy'))
        copy.clicked.connect(self.copy_events)
        clear = QPushButton(t('events_clear'))
        clear.clicked.connect(self.clear_events)
        row.addWidget(copy)
        row.addStretch(1)
        row.addWidget(clear)
        box.addLayout(row)
        self.ev_signature = None
        self.refresh_events(True)
        return page

    def shown_events(self):
        entries = list(reversed(tb.read_events()))
        if self.only_problems.isChecked():
            entries = [e for e in entries if e.get('level') in ('warning', 'error')]
        return entries[:300]

    def refresh_events(self, force=False):
        try:
            st = os.stat(tb.EVENTS_PATH)
            signature = (st.st_mtime_ns, st.st_size)
        except OSError:
            signature = None
        if signature == self.ev_signature and not force:
            return
        self.ev_signature = signature
        entries = self.shown_events()
        self.ev_table.setRowCount(len(entries))
        colors = {'warning': QColor('#b9770e'), 'error': QColor('#c0392b')}
        for i, e in enumerate(entries):
            level = e.get('level', 'info')
            message = e.get('msg', '') + (' (x%d)' % e['count'] if e.get('count', 1) > 1 else '')
            cells = [time.strftime('%d.%m. %H:%M:%S', time.localtime(e.get('t', 0))), t('lvl_' + level) if 'lvl_' + level in TEXT else level, message]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(e.get('where') or e.get('msg', ''))
                if level in colors:
                    item.setForeground(colors[level])
                self.ev_table.setItem(i, c, item)

    def copy_events(self):
        lines = ['%s [%s] %s' % (time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(e.get('t', 0))), e.get('level', ''),
                                  e.get('msg', '')) for e in reversed(self.shown_events())]
        QApplication.clipboard().setText('URL Trackbye ' + tb.VERSION + '\n' + '\n'.join(lines))

    def clear_events(self):
        tb.clear_events()
        self.refresh_events(True)

    # --- Browser ---------------------------------------------------------------------------------------------
    def browser_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.addWidget(self.heading(t('ext_head')))
        ext = os.path.join(tb.HERE, 'extension')
        path = QLabel(ext)
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(path)
        help_label = QLabel(t('ext_help'))
        help_label.setWordWrap(True)
        box.addWidget(help_label)
        open_btn = QPushButton(t('open_folder'))
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(ext)))
        row_ext = QHBoxLayout()
        row_ext.addWidget(open_btn)
        page_btn = QPushButton(t('ext_page'))
        page_btn.clicked.connect(self.open_extensions_page)
        row_ext.addWidget(page_btn)
        row_ext.addStretch(1)
        box.addLayout(row_ext)
        form = QFormLayout()
        self.ext_installed = QLabel('')
        self.ext_current = QLabel('')
        self.ext_state = QLabel('')
        self.ext_state.setWordWrap(True)
        form.addRow(t('ext_installed'), self.ext_installed)
        form.addRow(t('ext_current'), self.ext_current)
        form.addRow(t('ext_state'), self.ext_state)
        box.addLayout(form)
        note = QLabel(t('ext_note'))
        note.setWordWrap(True)
        note.setStyleSheet('color: gray')
        box.addWidget(note)

        box.addWidget(self.heading(t('native_head')))
        self.native = QTableWidget(len(tb.NATIVE_BROWSERS), 3)
        self.native.setHorizontalHeaderLabels([t('col_browser'), t('col_found'), t('col_reg')])
        self.native.horizontalHeader().setStretchLastSection(True)
        self.native.setMaximumHeight(170)
        self.native.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.native.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.native.verticalHeader().setVisible(False)
        box.addWidget(self.native)
        self.native_buttons = []
        for i, (name, folder) in enumerate(tb.NATIVE_BROWSERS.items()):
            self.native.setItem(i, 0, QTableWidgetItem(name))
            self.native.setItem(i, 1, QTableWidgetItem(''))
            self.native.setItem(i, 2, QTableWidgetItem(''))
        reg = QPushButton(t('register'))
        reg.clicked.connect(self.register_native)
        box.addWidget(reg, alignment=Qt.AlignmentFlag.AlignLeft)

        box.addWidget(self.heading(t('opener_head')))
        help2 = QLabel(t('opener_help'))
        help2.setWordWrap(True)
        box.addWidget(help2)
        self.opener_status = QLabel('')
        box.addWidget(self.opener_status)
        row = QHBoxLayout()
        for text, fn in ((t('install_entry'), self.install_entry), (t('make_default'), self.make_default),
                         (t('restore_default'), self.restore_default)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        box.addLayout(row)
        box.addStretch(1)
        self.refresh_browser_tab()
        return page

    @staticmethod
    def heading(text):
        label = QLabel('<b>' + text + '</b>')
        return label

    def open_extensions_page(self):
        browser = tb.load_config()['browser']
        scheme = 'vivaldi' if 'vivaldi' in browser else 'chrome'
        QProcess.startDetached(browser, [scheme + '://extensions'])

    def refresh_ext_status(self):
        state = tb.read_json(tb.EXTENSION_STATE, {})
        current = tb.extension_version() or t('ext_none')
        outdated = tb.extension_outdated()
        self.ext_current.setText(current)
        self.ext_state.setStyleSheet('')
        if not state:
            self.ext_installed.setText(t('ext_none'))
            self.ext_state.setText(t('ext_unknown'))
        elif outdated:
            self.ext_installed.setText(outdated[0] or t('ext_older'))
            self.ext_state.setText(t('ext_old_short'))
            self.ext_state.setStyleSheet('color: #c0392b')
        else:
            self.ext_installed.setText(state.get('version') or t('ext_none'))
            self.ext_state.setText(t('ext_ok'))

    def refresh_browser_tab(self):
        self.refresh_ext_status()
        for i, (name, folder) in enumerate(tb.NATIVE_BROWSERS.items()):
            found = os.path.isdir(os.path.expanduser('~/.config/' + folder))
            registered = os.path.exists(tb.native_manifest_path(folder))
            self.native.item(i, 1).setText(t('yes') if found else t('no'))
            self.native.item(i, 2).setText(t('yes') if registered else t('no'))
        self.opener_status.setText(t('opener_status', d=tb.default_browser() or '?'))

    def register_native(self):
        written = tb.install_native()
        tb.diag('info', 'Registered the browser extension link for: ' + (', '.join(written) or 'no browser found'))
        self.refresh_browser_tab()

    def install_entry(self):
        tb.install_handler()
        self.refresh_browser_tab()

    def make_default(self):
        if QMessageBox.question(self, t('title'), t('confirm_default')) != QMessageBox.StandardButton.Yes:
            return
        tb.install_handler()
        tb.diag('info', 'URL Trackbye set as default browser')
        cfg = tb.load_config()
        current = tb.default_browser()
        if current and current != 'trackbye.desktop':
            cfg['previous_default'] = current
            tb.save_config(cfg)
        tb.set_default_browser('trackbye.desktop')
        self.refresh_browser_tab()

    def restore_default(self):
        previous = tb.load_config().get('previous_default')
        if previous:
            tb.set_default_browser(previous)
            tb.diag('info', 'Default browser restored to ' + previous)
        else:
            tb.diag('warning', 'No previous default browser is known; pick one in the system settings')
        self.refresh_browser_tab()

    # --- About -----------------------------------------------------------------------------------------------
    def about_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.addWidget(QLabel('<b>URL Trackbye ' + tb.VERSION + '</b>'))
        text = QLabel(t('about') + '\n' + tb.HERE)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(text)
        logs = QTabWidget()
        logs.addTab(self.test_tab(), t('tab_test'))
        logs.addTab(self.log_tab(), t('tab_log'))
        logs.addTab(self.events_tab(), t('tab_events'))
        box.addWidget(logs, 1)
        return page


# --------------------------------------------------------------------------------------------------------------
# Tray
# --------------------------------------------------------------------------------------------------------------

class TrayApp:
    def __init__(self, qapp):
        self.qapp = qapp
        self.service = ClipboardService()
        self.window = None
        # The tray glyph is white on dark panels and dark on light panels (follows the desktop theme).
        dark_panel = qapp.palette().color(QPalette.ColorRole.Window).lightness() < 128
        glyph = QPixmap(os.path.join(ASSETS, 'tray-light.png' if dark_panel else 'tray-dark.png'))
        dim = QPixmap(glyph.size())
        dim.fill(Qt.GlobalColor.transparent)
        painter = QPainter(dim)
        painter.setOpacity(0.4)
        painter.drawPixmap(0, 0, glyph)
        painter.end()
        self.icon_on = QIcon(glyph)
        self.icon_off = QIcon(dim)

        self.tray = QSystemTrayIcon()
        self.option_actions = {}
        self.rebuild_menu()
        self.tray.activated.connect(self.on_activated)

        on = tb.load_config()['clipboard']
        self.apply(on)
        tb.diag('info', 'URL Trackbye %s started' % tb.VERSION)
        self.seen = max([e.get('t', 0) for e in tb.read_events()] or [0])
        self.notice_timer = QTimer()
        self.notice_timer.timeout.connect(self.check_problems)
        self.notice_timer.timeout.connect(self.check_extension)
        QTimer.singleShot(15000, self.check_extension)
        self.notice_timer.start(3000)
        show_tray = tb.load_config()['tray_icon'] and QSystemTrayIcon.isSystemTrayAvailable()
        self.tray.setVisible(show_tray)
        if not show_tray or not os.path.exists(os.path.join(tb.CONFIG_DIR, 'config.json')):
            self.show_settings()  # no tray symbol to click, or first start: open the settings

    def apply(self, on):
        self.service.sync(on)
        self.tray.setIcon(self.icon_on if on else self.icon_off)
        self.tray.setToolTip(t('title') + (' – ' + t('clip') if on else ''))

    def rebuild_menu(self):
        """Tray (right click) menu: the quick settings you picked, then Settings and Quit, with icons."""
        menu = QMenu()
        title = QAction(QIcon(ICON), 'URL Trackbye ' + tb.VERSION, menu)  # parent keeps the action alive
        title.setEnabled(False)
        menu.addAction(title)
        menu.addSeparator()
        quick = tb.load_config()['quick']
        self.option_actions = {}
        for key, _, menu_label, icon in OPTIONS:
            if key not in quick:
                continue
            act = QAction(QIcon.fromTheme(icon), t(menu_label), menu)
            act.setCheckable(True)
            act.setChecked(option_state(key))
            act.toggled.connect(lambda on, k=key: self.set_option(k, on))
            menu.addAction(act)
            self.option_actions[key] = act
        if self.option_actions:
            menu.addSeparator()
        act_settings = QAction(QIcon.fromTheme('configure', QIcon.fromTheme('preferences-system')), t('settings'), menu)
        act_settings.triggered.connect(self.show_settings)
        act_quit = QAction(QIcon.fromTheme('application-exit'), t('quit'), menu)
        act_quit.triggered.connect(self.quit)
        menu.addAction(act_settings)
        menu.addAction(act_quit)
        self.menu = menu
        self.tray.setContextMenu(menu)

    def set_option(self, key, on):
        on = bool(on)
        if key == 'autostart':
            tb.set_autostart(on)
        else:
            cfg = tb.load_config()
            cfg[key] = on
            tb.save_config(cfg)
            if key == 'clipboard':
                self.apply(on)
        self.refresh_checks()

    def refresh_checks(self):
        """Keep the menu entries and the settings window checkboxes in line with the real state."""
        for key, act in self.option_actions.items():
            sync(act, option_state(key))
        if self.window is not None:
            for key, chk in self.window.checks.items():
                sync(chk, option_state(key))

    def check_extension(self):
        """Tell the user once per available version when the browser still runs an older extension."""
        outdated = tb.extension_outdated()
        if not outdated:
            return
        state = tb.read_json(tb.EXTENSION_STATE, {})
        if state.get('notified_for') == outdated[1]:
            return
        state['notified_for'] = outdated[1]
        tb.write_json(tb.EXTENSION_STATE, state)
        message = t('ext_old', r=outdated[0] or t('ext_older'), a=outdated[1])
        tb.diag('warning', message)
        if self.tray.isVisible():
            self.tray.showMessage(t('ext_notice_title'), message, QSystemTrayIcon.MessageIcon.Warning, 12000)
        elif shutil.which('notify-send'):
            QProcess.startDetached('notify-send', ['-a', 'URL Trackbye', t('ext_notice_title'), message])

    def check_problems(self):
        """Show a tray notice for errors that appeared since the last check (also from the browser helper)."""
        fresh = [e for e in tb.read_events() if e.get('t', 0) > self.seen]
        if fresh:
            self.seen = max(e['t'] for e in fresh)
            errors = [e for e in fresh if e.get('level') == 'error']
            if errors and self.tray.isVisible():
                self.tray.showMessage(t('problem'), errors[-1].get('msg', ''), QSystemTrayIcon.MessageIcon.Critical, 8000)

    def set_tray_visible(self, on):
        cfg = tb.load_config()
        cfg['tray_icon'] = bool(on)
        tb.save_config(cfg)
        if on:
            self.tray.setVisible(QSystemTrayIcon.isSystemTrayAvailable())
        else:
            tb.install_launcher()  # keep a way back to the settings
            self.tray.setVisible(False)

    def show_settings(self):
        if self.window is None:
            self.window = SettingsWindow(self)
        self.window.refresh_browser_tab()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_settings()

    def quit(self):
        tb.diag('info', 'URL Trackbye quit')
        self.service.stop()
        self.tray.hide()
        self.qapp.quit()


def run():
    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName('trackbye')
    qapp.setWindowIcon(QIcon(ICON))
    qapp.setQuitOnLastWindowClosed(False)
    # Already running? Ask that instance to show its settings window and leave.
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b'show')
        sock.flush()
        sock.waitForBytesWritten(300)
        print('URL Trackbye is already running; its settings window was opened.')
        return 0
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)
    app = TrayApp(qapp)

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.readyRead.connect(lambda: (conn.readAll(), app.show_settings()))
    server.newConnection.connect(on_connection)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print('No system tray found on this desktop: running with the settings window only.', file=sys.stderr)
    return qapp.exec()
