"""Локальний запуск сканера з автоматичним відкриттям браузера."""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

from ticker_bot.main import run

APP_NAME = "StockScanner"
LOCAL_URL = "http://127.0.0.1:8765"
TOKEN_PATTERN = re.compile(r"\d+:[A-Za-z0-9_-]{20,}")
_INSTANCE_LOCK: object | None = None


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _user_data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / APP_NAME


def _show_message(kind: str, title: str, message: str) -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    getattr(messagebox, kind)(title, message, parent=root)
    root.destroy()


def open_existing_scanner() -> bool:
    """Open the browser instead of starting a second bot/server instance."""
    try:
        with urllib.request.urlopen(f"{LOCAL_URL}/healthz", timeout=0.8) as response:
            payload = json.load(response)
        if response.status == 200 and payload.get("status") == "ok":
            webbrowser.open(LOCAL_URL)
            return True
    except (OSError, ValueError, urllib.error.URLError):
        pass
    return False


def acquire_instance_lock() -> bool:
    """Keep one local scanner process per Windows user."""
    global _INSTANCE_LOCK
    data_dir = _user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    handle = (data_dir / "scanner.lock").open("a+b")
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    _INSTANCE_LOCK = handle
    return True


def _save_local_token(path: Path, token: str) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        "# Локальні налаштування Stock Scanner. Не надсилайте цей файл іншим.\n"
        f"TELEGRAM_BOT_TOKEN={token}\n"
        "BOT_ENABLED=true\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def ensure_telegram_token() -> bool:
    data_dir = _user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    settings_path = data_dir / "settings.env"

    load_dotenv(settings_path, override=False)
    if not _is_frozen():
        load_dotenv(override=False)

    os.environ["API_HOST"] = "127.0.0.1"
    os.environ["API_PORT"] = "8765"
    os.environ["DATABASE_PATH"] = str(data_dir / "tickers.db")
    os.environ["LOCAL_SETTINGS_PATH"] = str(settings_path)
    os.environ.setdefault("APP_TIMEZONE", "America/New_York")

    if os.getenv("TELEGRAM_BOT_TOKEN", "").strip():
        os.environ["BOT_ENABLED"] = "true"
        return True

    import tkinter as tk
    from tkinter import messagebox, simpledialog

    root = tk.Tk()
    root.withdraw()
    token = simpledialog.askstring(
        "Перше налаштування",
        "Вставте токен Telegram-бота від @BotFather.\n"
        "Це потрібно зробити лише один раз.\n\n"
        "Щоб поки відкрити демо без бота, натисніть «Скасувати».",
        show="•",
        parent=root,
    )
    if token is None:
        root.destroy()
        os.environ["BOT_ENABLED"] = "false"
        return True
    token = token.strip()
    if not TOKEN_PATTERN.fullmatch(token):
        messagebox.showerror(
            "Некоректний токен",
            "Токен не схожий на токен від @BotFather.\nСканер зараз відкриється у демо-режимі.",
            parent=root,
        )
        root.destroy()
        os.environ["BOT_ENABLED"] = "false"
        return True

    _save_local_token(settings_path, token)
    os.environ["TELEGRAM_BOT_TOKEN"] = token
    os.environ["BOT_ENABLED"] = "true"
    messagebox.showinfo(
        "Готово",
        "Токен збережено лише на цьому комп’ютері.\nЗараз відкриється сканер.",
        parent=root,
    )
    root.destroy()
    return True


if __name__ == "__main__":
    if open_existing_scanner():
        raise SystemExit(0)
    if not acquire_instance_lock():
        for _ in range(30):
            if open_existing_scanner():
                raise SystemExit(0)
            time.sleep(0.25)
        _show_message(
            "showinfo",
            "Сканер уже запускається",
            "Зачекайте кілька секунд і відкрийте ярлик ще раз.",
        )
        raise SystemExit(0)
    try:
        if ensure_telegram_token():
            run(open_browser=True)
    except SystemExit as exc:
        if exc.code not in (None, 0):
            _show_message(
                "showerror",
                "Сканер не запустився",
                "Не вдалося запустити сканер.\nЗакрийте інші копії програми та спробуйте ще раз.",
            )
        raise
    except Exception:
        _show_message(
            "showerror",
            "Сканер не запустився",
            "Сталася помилка запуску. Зробіть знімок екрана й надішліть його мені.",
        )
        raise
