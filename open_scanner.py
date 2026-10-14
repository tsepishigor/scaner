"""Локальний запуск сканера з автоматичним відкриттям браузера."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

from ticker_bot.main import run


def ensure_telegram_token() -> bool:
    load_dotenv()
    if os.getenv("TELEGRAM_BOT_TOKEN", "").strip():
        return True

    import tkinter as tk
    from tkinter import messagebox, simpledialog

    root = tk.Tk()
    root.withdraw()
    token = simpledialog.askstring(
        "Перше налаштування",
        "Вставте токен Telegram-бота від @BotFather.\nЦе потрібно зробити лише один раз.",
        show="•",
        parent=root,
    )
    if token is None:
        root.destroy()
        return False
    token = token.strip()
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{20,}", token):
        messagebox.showerror(
            "Некоректний токен",
            "Токен не схожий на токен від @BotFather. Запустіть файл ще раз.",
            parent=root,
        )
        root.destroy()
        return False

    template_path = Path(__file__).with_name(".env.example")
    env_path = Path(__file__).with_name(".env")
    template = template_path.read_text(encoding="utf-8")
    configured = template.replace("TELEGRAM_BOT_TOKEN=", f"TELEGRAM_BOT_TOKEN={token}", 1)
    env_path.write_text(configured, encoding="utf-8")
    messagebox.showinfo(
        "Готово",
        "Токен збережено лише на цьому комп’ютері. Зараз відкриється сканер.",
        parent=root,
    )
    root.destroy()
    return True


if __name__ == "__main__":
    if ensure_telegram_token():
        run(open_browser=True)
