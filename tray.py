"""URL Trackbye tray app: runs in the background, cleans copied links and has a settings window.

Started by `trackbye tray` (needs PyQt6). The clipboard is watched by `wl-paste --watch` (Wayland), which calls
`trackbye filter-clip` for every change; this app only starts, stops and restarts that watcher.
"""
import os
import shutil
import sys

from PyQt6.QtCore import QLockFile, QLocale, QProcess, QStandardPaths, QTimer, QUrl, Qt
from PyQt6.QtGui import QAction, QDesktopServices, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                             QPlainTextEdit, QPushButton, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QTabWidget,
                             QVBoxLayout, QWidget)

import trackbye as tb

ICON = os.path.join(tb.HERE, 'extension', 'icons', 'icon128.png')

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
    'tab_about': ('About', 'Info'),
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
        if self.proc is not None or not self.available():
            return
        self.proc = QProcess()
        self.proc.finished.connect(self._finished)
        self.proc.start('wl-paste', ['--type', 'text', '--watch', sys.executable, tb.SCRIPT, 'filter-clip'])

    def stop(self):
        self.wanted = False
        self.timer.stop()
        if self.proc is not None:
            proc, self.proc = self.proc, None
            proc.finished.disconnect()
            proc.terminate()
            proc.waitForFinished(1000)

    def _finished(self):
        self.proc = None
        if self.wanted:
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
        for w in (self.chk_clip, self.chk_notify, self.chk_auto):
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
        tb.install_native()
        self.refresh_browser_tab()

    def install_entry(self):
        tb.install_handler()
        self.refresh_browser_tab()

    def make_default(self):
        if QMessageBox.question(self, t('title'), t('confirm_default')) != QMessageBox.StandardButton.Yes:
            return
        tb.install_handler()
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
        self.refresh_browser_tab()

    # --- About -----------------------------------------------------------------------------------------------
    def about_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.addWidget(QLabel('<h2>URL Trackbye ' + tb.VERSION + '</h2>'))
        text = QLabel(t('about'))
        text.setWordWrap(True)
        box.addWidget(text)
        folder = QLabel(tb.HERE)
        folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(folder)
        box.addStretch(1)
        return page


# --------------------------------------------------------------------------------------------------------------
# Tray
# --------------------------------------------------------------------------------------------------------------

class TrayApp:
    def __init__(self, qapp):
        self.qapp = qapp
        self.service = ClipboardService()
        self.window = None
        self.icon_on = QIcon(ICON)
        pm = QPixmap(ICON)
        dim = QPixmap(pm.size())
        dim.fill(Qt.GlobalColor.transparent)
        painter = QPainter(dim)
        painter.setOpacity(0.4)
        painter.drawPixmap(0, 0, pm)
        painter.end()
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
        self.tray.show()
        if not os.path.exists(os.path.join(tb.CONFIG_DIR, 'config.json')):
            self.show_settings()  # first start: open the settings once

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
        self.service.stop()
        self.tray.hide()
        self.qapp.quit()


def run():
    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName('trackbye')
    qapp.setQuitOnLastWindowClosed(False)
    lock_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
    lock = QLockFile(os.path.join(lock_dir, 'trackbye-tray.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        print('URL Trackbye is already running.')
        return 0
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print('No system tray found on this desktop.', file=sys.stderr)
        return 1
    app = TrayApp(qapp)  # noqa: F841 (kept alive by the event loop)
    return qapp.exec()
