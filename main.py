```python
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
    except:
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

    return InlineKeyboardMarkup(keyboard)


# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if str(user.id) not in USERS:
        USERS[str(user.id)] = {
            "name": user.first_name,
            "tests": 0,
            "correct": 0
        }
        save_users(USERS)

    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"Добро пожаловать в Physix Bot.\n"
        f"Бот для подготовки по физике."
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu()
    )

# ================= CALLBACKS =================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    # Главное меню
    if data == "menu":
        await query.edit_message_text(
            "🏠 Главное меню",
            reply_markup=main_menu()
        )
        return

    # Теория
    if data == "theory":
        await query.edit_message_text(
            "📚 Выберите класс:",
            reply_markup=class_menu("theory")
        )
        return

    # Тесты
    if data == "tests":
        await query.edit_message_text(
            "📝 Выберите класс:",
            reply_markup=class_menu("test")
        )
        return

    # Статистика
    if data == "stats":

        user_id = str(query.from_user.id)
        user = USERS.get(user_id)

        text = (
            f"📊 Статистика\n\n"
            f"👤 Имя: {user['name']}\n"
            f"📝 Тестов пройдено: {user['tests']}\n"
            f"✅ Правильных ответов: {user['correct']}"
        )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data="menu"
                    )
                ]
            ])
        )
        return

    # Теория классов
    if data.startswith("theory_"):

        cls = data.split("_")[1]

        keyboard = []

        for i, topic in enumerate(CONTENT[cls].keys()):
            keyboard.append([
                InlineKeyboardButton(
                    topic,
                    callback_data=f"topic_{cls}_{i}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data="theory"
            )
        ])

        await query.edit_message_text(
            f"📘 Темы {cls} класса:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Тема
    if data.startswith("topic_"):

        parts = data.split("_")

        cls = parts[1]
        index = int(parts[2])

        topic_name = list(CONTENT[cls].keys())[index]
        topic_data = CONTENT[cls][topic_name]

        text = (
            f"📖 {topic_name}\n\n"
            f"{topic_data['theory']}"
        )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data=f"theory_{cls}"
                    )
                ]
            ])
        )
        return


# ================= MAIN =================

def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))

    print("BOT STARTED")

    app.run_polling()


if __name__ == "__main__":
    main()
```
