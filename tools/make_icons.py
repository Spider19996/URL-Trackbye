#!/usr/bin/env python3
"""Render the PNG icons from assets/*.svg. Needs chromium (headless, draws the SVG) and PyQt6 (scales the result).

Run after changing an SVG: python3 tools/make_icons.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QImage

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ASSETS = os.path.join(ROOT, 'assets')
EXT = os.path.join(ROOT, 'extension', 'icons')
BIG = 256


def draw(svg_text, tmp, name):
    """Draw SVG text to a transparent BIGxBIG PNG with headless Chromium."""
    svg_path = os.path.join(tmp, name + '.svg')
    html_path = os.path.join(tmp, name + '.html')
    out = os.path.join(tmp, name + '.png')
    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(svg_text)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write('<html><body style="margin:0;background:transparent"><img src="%s.svg" width="%d" height="%d"></body></html>'
                % (name, BIG, BIG))
    browser = shutil.which('chromium') or shutil.which('google-chrome') or shutil.which('chromium-browser')
    if not browser:
        sys.exit('chromium or google-chrome is needed to draw the SVGs')
    subprocess.run([browser, '--headless=new', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
                    '--default-background-color=00000000', '--window-size=%d,%d' % (BIG, BIG),
                    '--screenshot=' + out, 'file://' + html_path], check=True, capture_output=True)
    return QImage(out)


def save(img, size, path):
    img.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation).save(path)


def main():
    QGuiApplication(sys.argv[:1])
    color = open(os.path.join(ASSETS, 'trackbye.svg'), encoding='utf-8').read()
    gray = color.replace('#2f9bf0', '#9aa0a6').replace('#0b3d7a', '#5f6368').replace('#fff3b0', '#e8eaed')
    glyph = open(os.path.join(ASSETS, 'trackbye-symbolic.svg'), encoding='utf-8').read()
    dark_glyph = glyph.replace('#ffffff', '#232629')
    os.makedirs(EXT, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        img_color, img_gray = draw(color, tmp, 'color'), draw(gray, tmp, 'gray')
        img_light, img_dark = draw(glyph, tmp, 'light'), draw(dark_glyph, tmp, 'dark')
    for size in (16, 32, 48, 128):
        save(img_color, size, os.path.join(EXT, 'icon%d.png' % size))
        save(img_gray, size, os.path.join(EXT, 'off%d.png' % size))
    save(img_color, 256, os.path.join(ASSETS, 'trackbye.png'))
    save(img_light, 64, os.path.join(ASSETS, 'tray-light.png'))  # white glyph for dark panels
    save(img_dark, 64, os.path.join(ASSETS, 'tray-dark.png'))    # dark glyph for light panels


if __name__ == '__main__':
    main()
