import os
import logging
import random
import json
import sys
import time
from typing import Dict, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
import telegram

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- ЗАГРУЗКА КОНТЕНТА ---
try:
    from data import CONTENT
except ImportError:
    print("\nОШИБКА: Файл data.py не найден!\n")
    sys.exit(1)

# --- НАСТРОЙКИ ---
TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = 8707709434  # Твой ID
DB_PATH = os.getenv('DB_PATH', '.')

USERS_FILE = os.path.join(DB_PATH, 'users_db.json')
STATS_FILE = os.path.join(DB_PATH, 'stats_db.json')

# Базы данных в памяти
ALL_USERS_IDS: Dict[int, Dict[str, Any]] = {}
user_stats: Dict[int, Dict[str, Any]] = {}
user_sessions: Dict[int, Dict[str, Any]] = {}

# --- РАБОТА С БД ---
def load_db():
    global ALL_USERS_IDS, user_stats
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                ALL_USERS_IDS = {int(k): v for k, v in data.items()}
            except: pass
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                user_stats = {int(k): v for k, v in data.items()}
            except: pass

def save_db():
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(ALL_USERS_IDS, f, ensure_ascii=False, indent=4)
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

load_db()

# --- КЛАВИАТУРЫ ---
def get_main_reply_keyboard():
    return ReplyKeyboardMarkup([['🏠 Главное меню']], resize_keyboard=True, is_persistent=True)

def build_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton('📚 Изучение тем', callback_data='menu:study')],
        [InlineKeyboardButton('📝 Пройти тест', callback_data='menu:test')],
        [InlineKeyboardButton('ℹ️ О боте', callback_data='menu:about')],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_class_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    for cls in sorted(CONTENT.keys(), key=int):
        buttons.append([InlineKeyboardButton(f'Класс {cls}', callback_data=f'{prefix}:class:{cls}')])
    buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='menu:main')])
    return InlineKeyboardMarkup(buttons)

def build_topics_keyboard(class_id: str, prefix: str) -> InlineKeyboardMarkup:
    topics = list(CONTENT.get(class_id, {}).keys())
    kb = [[InlineKeyboardButton(t, callback_data=f'{prefix}:topic:{class_id}:{i}')] for i, t in enumerate(topics)]
    kb.append([InlineKeyboardButton('⬅️ Назад', callback_data=f'{prefix}:back_to_classes')])
    return InlineKeyboardMarkup(kb)

# --- ОБРАБОТЧИКИ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ALL_USERS_IDS
    user = update.effective_user
    chat_id = update.effective_chat.id

    if chat_id not in ALL_USERS_IDS:
        ALL_USERS_IDS[chat_id] = {
            'id': user.id,
            'first_name': user.first_name,
            'username': user.username
        }
        save_db()

    await update.message.reply_text(
        f"Привет, {user.first_name}! Я твой помощник по физике.",
        reply_markup=get_main_reply_keyboard()
    )
    await update.message.reply_text("Выберите раздел:", reply_markup=build_main_menu())

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🏠 Главное меню":
        await update.message.reply_text("Возвращаю в меню:", reply_markup=build_main_menu())
        return
    await update.message.reply_text("Пожалуйста, используйте кнопки меню для управления ботом.")

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'menu:main':
        await query.edit_message_text('Главное меню:', reply_markup=build_main_menu())
    elif data == 'menu:study':
        await query.edit_message_text('Выберите класс:', reply_markup=build_class_keyboard('study'))
    elif data == 'menu:test':
        await query.edit_message_text('Выберите класс для теста:', reply_markup=build_class_keyboard('test'))
    elif data == 'menu:about':
        await query.edit_message_text('Бот-справочник по физике.\nСоздан для помощи в изучении тем и сдаче тестов.', 
                                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='menu:main')]]))

    # Логика выбора классов и тем
    parts = data.split(':')
    if len(parts) >= 3:
        prefix, action, cls = parts[0], parts[1], parts[2]
        
        if action == 'class':
            await query.edit_message_text(f'Класс {cls}:', reply_markup=build_topics_keyboard(cls, prefix))
        
        elif action == 'topic':
            topic_idx = int(parts[3])
            topic_name = list(CONTENT[cls].keys())[topic_idx]
            topic_data = CONTENT[cls][topic_name]
            
            if prefix == 'study':
                text = f"<b>{topic_name}</b>\n\n{topic_data['theory']}"
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton('📝 Тест по теме', callback_data=f'test:topic:{cls}:{topic_idx}')],
                    [InlineKeyboardButton('⬅️ Назад', callback_data=f'study:class:{cls}')]
                ])
                await query.edit_message_text(text, reply_markup=kb, parse_mode='HTML')
            
            elif prefix == 'test':
                # Здесь можно добавить запуск теста (упрощено для стабильности)
                await query.edit_message_text(f"Функция теста для темы '{topic_name}' в разработке.")

    if data.endswith('back_to_classes'):
        prefix = data.split(':')[0]
        await query.edit_message_text('Выберите класс:', reply_markup=build_class_keyboard(prefix))

# --- ЗАПУСК ---
def main():
    if not TOKEN:
        print("ОШИБКА: BOT_TOKEN не установлен!")
        return
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
