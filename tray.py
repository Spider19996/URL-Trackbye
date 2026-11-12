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
from PyQt6.QtWidgets import (QApplication, QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                             QPlainTextEdit, QPushButton, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QTabWidget,
                             QVBoxLayout, QWidget)

import trackbye as tb

ASSETS = os.path.join(tb.HERE, 'assets')
ICON = os.path.join(ASSETS, 'trackbye.png')  # app and window icon
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
    'show_builtin': ('Show built-in rules', 'Eingebaute Regeln anzeigen'),
}
LANG = 1 if QLocale.system().name().startswith('de') else 0


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
        self.chk_clip = QCheckBox(t('clip'))
        self.chk_clip.setChecked(cfg['clipboard'])
        self.chk_clip.toggled.connect(self.app.set_clipboard)
        self.chk_notify = QCheckBox(t('notify'))
        self.chk_notify.setChecked(cfg['notify'])
        self.chk_notify.toggled.connect(lambda on: self.save_cfg('notify', on))
        self.chk_auto = QCheckBox(t('autostart'))
        self.chk_auto.setChecked(os.path.exists(tb.AUTOSTART))
        self.chk_auto.toggled.connect(tb.set_autostart)
        self.chk_log = QCheckBox(t('log_on'))
        self.chk_log.setChecked(cfg['log'])
        self.chk_log.toggled.connect(lambda on: self.save_cfg('log', on))
        self.chk_tray = QCheckBox(t('tray_icon'))
        self.chk_tray.setChecked(cfg['tray_icon'])
        self.chk_tray.toggled.connect(self.app.set_tray_visible)
        for w in (self.chk_clip, self.chk_notify, self.chk_log, self.chk_auto, self.chk_tray):
            form.addWidget(w)
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
        box.addWidget(self.ed_global)

        box.addWidget(QLabel(t('excluded')))
        self.ed_excluded = QPlainTextEdit('\n'.join(rules['exclude_hosts']))
        self.ed_excluded.setMaximumHeight(60)
        box.addWidget(self.ed_excluded)

        box.addWidget(QLabel(t('sites')))
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
        save = QPushButton(t('save'))
        save.clicked.connect(self.save_rules)
        self.saved_label = QLabel('')
        for b in (add, delete):
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
        self.try_in.textChanged.connect(lambda s: self.try_out.setText(tb.clean_url(s, tb.load_rules()) if tb.is_url(s) else ''))
        box.addWidget(self.try_in)
        box.addWidget(self.try_out)
        return page

    def add_site_row(self, domains, params):
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        self.tbl.setItem(row, 0, QTableWidgetItem(domains))
        self.tbl.setItem(row, 1, QTableWidgetItem(params))

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
        box.addWidget(open_btn, alignment=Qt.AlignmentFlag.AlignLeft)

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

    def refresh_browser_tab(self):
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
        menu = QMenu()
        title = QAction(t('title'))
        title.setEnabled(False)
        self.act_clip = QAction(t('clip'))
        self.act_clip.setCheckable(True)
        self.act_clip.toggled.connect(self.set_clipboard)
        act_settings = QAction(t('settings'))
        act_settings.triggered.connect(self.show_settings)
        act_quit = QAction(t('quit'))
        act_quit.triggered.connect(self.quit)
        for a in (title, self.act_clip):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(act_settings)
        menu.addAction(act_quit)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_activated)

        on = tb.load_config()['clipboard']
        self.act_clip.blockSignals(True)
        self.act_clip.setChecked(on)
        self.act_clip.blockSignals(False)
        self.apply(on)
        tb.diag('info', 'URL Trackbye %s started' % tb.VERSION)
        self.seen = max([e.get('t', 0) for e in tb.read_events()] or [0])
        self.notice_timer = QTimer()
        self.notice_timer.timeout.connect(self.check_problems)
        self.notice_timer.start(3000)
        show_tray = tb.load_config()['tray_icon'] and QSystemTrayIcon.isSystemTrayAvailable()
        self.tray.setVisible(show_tray)
        if not show_tray or not os.path.exists(os.path.join(tb.CONFIG_DIR, 'config.json')):
            self.show_settings()  # no tray symbol to click, or first start: open the settings

    def apply(self, on):
        self.service.sync(on)
        self.tray.setIcon(self.icon_on if on else self.icon_off)
        self.tray.setToolTip(t('title') + (' – ' + t('clip') if on else ''))

    def set_clipboard(self, on):
        cfg = tb.load_config()
        cfg['clipboard'] = bool(on)
        tb.save_config(cfg)
        self.apply(on)
        for w, name in ((self.act_clip, None),):
            if w.isChecked() != on:
                w.blockSignals(True)
                w.setChecked(on)
                w.blockSignals(False)
        if self.window is not None and self.window.chk_clip.isChecked() != on:
            self.window.chk_clip.blockSignals(True)
            self.window.chk_clip.setChecked(on)
            self.window.chk_clip.blockSignals(False)

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
