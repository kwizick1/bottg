import os
import json
import logging
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from data import CONTENT

# ================= LOGGING =================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# ================= TOKEN =================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not found!")

# ================= DATABASE =================

DB_FILE = "users.json"

if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)


def load_users():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_users(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


USERS = load_users()

# ================= MENU =================


def main_menu():
    keyboard = [
        [InlineKeyboardButton("📚 Теория", callback_data="theory")],
        [InlineKeyboardButton("📝 Тесты", callback_data="tests")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")],
    ]
    return InlineKeyboardMarkup(keyboard)



def class_menu(mode):
    keyboard = []

    for cls in CONTENT.keys():
        keyboard.append([
            InlineKeyboardButton(
                f"{cls} класс",
                callback_data=f"{mode}_{cls}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Назад",
            callback_data="menu"
        )
    ])
    main()
