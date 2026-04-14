#!/usr/bin/env python3
"""
Opens a filled XFA PDF in Acrobat, clicks Validate via image match, saves in place.

Usage:
  python acrobat_validate.py <input_pdf> --button-image <path>

  button_image: screenshot of the Validate button in Acrobat, cropped tight, saved as PNG.

Dependencies:
  pip install pyautogui pillow
"""

import sys
import os
import time
import subprocess
import argparse
import winreg
import ctypes

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import pyautogui
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def find_acrobat_exe():
    for reg_hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(reg_hive,
                r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Acrobat.exe')
            path, _ = winreg.QueryValueEx(key, '')
            if path and os.path.exists(path):
                return path
        except Exception:
            pass
    for c in (r'C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe',
              r'C:\Program Files (x86)\Adobe\Acrobat DC\Acrobat\Acrobat.exe'):
        if os.path.exists(c):
            return c
    raise FileNotFoundError('Adobe Acrobat not found')


def wait_for_acrobat_window(timeout=30):
    user32 = ctypes.windll.user32
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        hwnd = user32.FindWindowW('AcrobatSDIWindow', None)
        if hwnd:
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 400 and h > 300:
                print(f'[PY] Acrobat window ready: {w}x{h}')
                return hwnd
    raise TimeoutError('Acrobat window did not appear')


def bring_to_front(hwnd):
    user32 = ctypes.windll.user32
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)


def click_validate(hwnd, button_image):
    bring_to_front(hwnd)
    for confidence in (0.9, 0.8, 0.7):
        try:
            loc = pyautogui.locateCenterOnScreen(button_image, confidence=confidence)
            if loc:
                print(f'[PY] Validate button found at {loc} (confidence={confidence})')
                pyautogui.click(loc)
                print('[PY] Clicked — waiting for validation ...')
                time.sleep(5)
                print('[PY] Confirming validation modal ...')
                pyautogui.press('enter')
                time.sleep(3)
                return True
        except Exception as e:
            print(f'[PY] Image search confidence={confidence}: {e}')
    print(f'[PY] ERROR: Validate button not found on screen (image: {button_image})')
    return False


def save_in_place(hwnd, input_pdf):
    bring_to_front(hwnd)
    print(f'[PY] Saving in place → {input_pdf}')
    pyautogui.hotkey('ctrl', 's')
    time.sleep(2.0)
    if os.path.exists(input_pdf):
        print(f'[PY] Saved: {os.path.getsize(input_pdf)/1024:.1f} KB')
        return True
    print('[PY] WARN: file not found after save')
    return False


def close_acrobat(hwnd):
    bring_to_front(hwnd)
    pyautogui.hotkey('alt', 'F4')
    time.sleep(1.5)
    pyautogui.press('n')
    time.sleep(0.8)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_pdf')
    parser.add_argument('output_pdf', nargs='?', help='ignored — script saves in place')
    parser.add_argument('--button-image', required=True)
    args = parser.parse_args()

    input_pdf    = os.path.abspath(args.input_pdf)
    button_image = os.path.abspath(args.button_image)

    print(f'[PY] Input        : {input_pdf}')
    print(f'[PY] Button image : {button_image}')

    if not os.path.exists(input_pdf):
        print(f'[PY] ERROR: input not found: {input_pdf}')
        sys.exit(1)
    if not os.path.exists(button_image):
        print(f'[PY] ERROR: button image not found: {button_image}')
        sys.exit(1)

    acro_exe = find_acrobat_exe()
    subprocess.run(['taskkill', '/F', '/IM', 'Acrobat.exe'], capture_output=True)
    subprocess.Popen([acro_exe, input_pdf])

    print('[PY] Waiting for Acrobat ...')
    hwnd = wait_for_acrobat_window(timeout=30)
    time.sleep(6)   # XFA engine init

    # imm5707 only: tab through fields to fire XFA change/calculate events
    # so dynamic fields (e.g. MarriageInPerson) become visible before validation.
    if 'imm5707' in input_pdf.replace('\\', '/').lower():
        bring_to_front(hwnd)
        print('[PY] imm5707: tabbing through fields to trigger XFA events ...')
        for _ in range(30):
            pyautogui.press('tab')
            time.sleep(0.15)
        time.sleep(1.0)

    # Click window center to re-focus before Ctrl+Home
    user32 = ctypes.windll.user32
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2
    print(f'[PY] Clicking window center ({cx}, {cy}) to re-focus ...')
    pyautogui.click(cx, cy)
    time.sleep(0.5)

    # imm5707: scroll back to page 1 so the Validate button is visible
    if 'imm5707' in input_pdf.replace('\\', '/').lower():
        print('[PY] imm5707: scrolling to start (Ctrl+Home) ...')
        pyautogui.hotkey('ctrl', 'Home')
        time.sleep(1.0)

    ok = click_validate(hwnd, button_image)
    if not ok:
        sys.exit(1)

    save_in_place(hwnd, input_pdf)
    close_acrobat(hwnd)
    print('[PY] Done.')


if __name__ == '__main__':
    main()
