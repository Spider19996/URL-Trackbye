#!/bin/sh
# URL Trackbye installer (for the current user, no root needed).
#
#   ./install.sh                       install: menu entry, then asks about autostart / browser link / command
#   ./install.sh --yes                 install without questions (menu entry only)
#   ./install.sh --autostart --native --link    choose the extras on the command line
#   ./install.sh --uninstall [--purge]          remove everything again (--purge: also settings and log)
#
# The program itself stays where it is (this folder); nothing is copied.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
app="$here/trackbye.py"
autostart=0; native=0; link=0; yes=0; uninstall=0; purge=0

for arg in "$@"; do
  case "$arg" in
    --autostart) autostart=1 ;;
    --native) native=1 ;;
    --link) link=1 ;;
    --yes|-y) yes=1 ;;
    --uninstall) uninstall=1 ;;
    --purge) purge=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

if [ "$uninstall" = 1 ]; then
  if [ "$purge" = 1 ]; then exec "$app" uninstall --purge; fi
  exec "$app" uninstall
fi

# --- check what is needed --------------------------------------------------------------------------------------
distro=$(. /etc/os-release 2>/dev/null; echo "${ID:-} ${ID_LIKE:-}")
case "$distro" in
  *debian*|*ubuntu*) qt_hint="sudo apt install python3-pyqt6"; wl_hint="sudo apt install wl-clipboard" ;;
  *fedora*|*rhel*)   qt_hint="sudo dnf install python3-pyqt6"; wl_hint="sudo dnf install wl-clipboard" ;;
  *arch*)            qt_hint="sudo pacman -S python-pyqt6";    wl_hint="sudo pacman -S wl-clipboard" ;;
  *suse*)            qt_hint="sudo zypper install python3-qt6"; wl_hint="sudo zypper install wl-clipboard" ;;
  *)                 qt_hint="install PyQt6 for Python 3";      wl_hint="install wl-clipboard" ;;
esac

problems=0
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))'; then
  echo "Python 3.8 or newer is required." >&2
  exit 1
fi
if ! python3 -c 'import PyQt6.QtWidgets' >/dev/null 2>&1; then
  echo "Missing: PyQt6 (the tray app and settings window).  ->  $qt_hint"
  problems=1
fi
if ! command -v wl-paste >/dev/null 2>&1 || ! command -v wl-copy >/dev/null 2>&1; then
  echo "Missing: wl-clipboard (cleaning copied links, Wayland only).  ->  $wl_hint"
  problems=1
fi
if [ "$problems" = 1 ]; then
  echo "The program still installs; the parts above only work after you installed them."
fi

# --- questions (only when run by hand without options) ------------------------------------------------------------
ask() {  # ask "question" -> 0 for yes
  [ "$yes" = 1 ] && return 1
  [ -t 0 ] || return 1
  printf '%s [y/N] ' "$1"
  read -r answer || return 1
  case "$answer" in y|Y|yes|YES|j|J|ja) return 0 ;; *) return 1 ;; esac
}
if [ "$autostart$native$link" = "000" ] && [ "$yes" = 0 ] && [ -t 0 ]; then
  ask "Start URL Trackbye with the desktop session?" && autostart=1
  ask "Link the browser extension to the program (Vivaldi, Chrome, Firefox, ...)?" && native=1
  ask "Create the command 'trackbye' in ~/.local/bin?" && link=1
fi

# --- install ---------------------------------------------------------------------------------------------------
chmod +x "$app"
set -- install
[ "$autostart" = 1 ] && set -- "$@" --autostart
[ "$native" = 1 ] && set -- "$@" --native
[ "$link" = 1 ] && set -- "$@" --link
"$app" "$@"

echo
echo "Next: start 'URL Trackbye' from your application menu (or run $app)."
echo "The browser extension is installed from the app's Browser page."
