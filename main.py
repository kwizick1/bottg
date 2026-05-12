import os
import logging
import json
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

# --- Инициализация ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from data import CONTENT
except ImportError:
    logger.error("data.py не найден!")
    exit(1)

TOKEN = os.getenv('BOT_TOKEN')
DB_PATH = os.getenv('DB_PATH', '.')
USERS_FILE = os.path.join(DB_PATH, 'users_v2.json')

ALL_USERS: Dict[int, Dict[str, Any]] = {}
user_sessions: Dict[int, Dict[str, Any]] = {}

# --- Работа с данными ---
def load_db():
    global ALL_USERS
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                ALL_USERS = {int(k): v for k, v in data.items()}
            except: pass

def save_db():
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(ALL_USERS, f, ensure_ascii=False, indent=4)

load_db()

# --- Кнопки ---
def get_main_keyboard():
    return ReplyKeyboardMarkup([['🏠 Главное меню']], resize_keyboard=True, is_persistent=True)

def build_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📚 Учебник 7-11', callback_data='menu:study')],
        [InlineKeyboardButton('📝 Пройти тесты', callback_data='menu:test')],
        [InlineKeyboardButton('📊 Статистика', callback_data='menu:stats')]
    ])

def build_class_menu(prefix):
    btns = [[InlineKeyboardButton(f'🔹 {c} класс', callback_data=f'{prefix}:class:{c}')] for c in CONTENT.keys()]
    btns.append([InlineKeyboardButton('⬅️ Назад', callback_data='menu:main')])
    return InlineKeyboardMarkup(btns)

def build_topic_menu(cls, prefix):
    topics = list(CONTENT[cls].keys())
    btns = [[InlineKeyboardButton(t, callback_data=f'{prefix}:topic:{cls}:{i}')] for i, t in enumerate(topics)]
    btns.append([InlineKeyboardButton('⬅️ К классам', callback_data=f'{prefix}:back')])
    return InlineKeyboardMarkup(btns)

# --- Логика тестов ---
async def send_next_question(query, uid):
    session = user_sessions[uid]
    cls, t_idx, q_idx = session['cls'], session['t_idx'], session['q_idx']
    
    topic_name = list(CONTENT[cls].keys())[t_idx]
    questions = CONTENT[cls][topic_name].get('questions', [])

    if q_idx < len(questions):
        q = questions[q_idx]
        kb = [[InlineKeyboardButton(opt, callback_data=f"ans:{1 if i==q['a'] else 0}")] for i, opt in enumerate(q['options'])]
        text = f"<b>📝 Вопрос {q_idx+1}/{len(questions)}</b>\n\n{q['q']}"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    else:
        # Финал
        score = session['score']
        ALL_USERS[uid]['solved'] = ALL_USERS[uid].get('solved', 0) + score
        save_db()
        await query.edit_message_text(f"🏁 <b>Тест завершен!</b>\n\nВаш результат: {score} из {len(questions)}", 
                                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню", callback_data="menu:main")]]), parse_mode='HTML')
        del user_sessions[uid]

# --- Обработчики ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ALL_USERS:
        ALL_USERS[uid] = {'name': update.effective_user.first_name, 'solved': 0, 'joined': time.ctime()}
        save_db()
    
    await update.message.reply_text(f"Привет, {update.effective_user.first_name}! Я твой личный помощник по физике Physix.", reply_markup=get_main_keyboard())
    await update.message.reply_text("Выберите раздел:", reply_markup=build_main_menu())

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()
    
    data = query.data
    if data.startswith('ans:'):
        if uid in user_sessions:
            if int(data.split(':')[1]): user_sessions[uid]['score'] += 1
            user_sessions[uid]['q_idx'] += 1
            await send_next_question(query, uid)
        return

    if data == 'menu:main': await query.edit_message_text("Главное меню:", reply_markup=build_main_menu())
    elif data == 'menu:study': await query.edit_message_text("Выберите класс:", reply_markup=build_class_menu('study'))
    elif data == 'menu:test': await query.edit_message_text("Выберите класс для теста:", reply_markup=build_class_menu('test'))
    elif data == 'menu:stats':
        s = ALL_USERS[uid].get('solved', 0)
        await query.edit_message_text(f"📊 <b>Ваша статистика:</b>\n\nРешено вопросов: {s}\nСтатус: {'Новичок' if s < 10 else 'Знаток'}", 
                                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")]]), parse_mode='HTML')

    parts = data.split(':')
    if len(parts) >= 3:
        pref, act, val = parts[0], parts[1], parts[2]
        if act == 'class': await query.edit_message_text(f"Темы {val} класса:", reply_markup=build_topic_menu(val, pref))
        elif act == 'topic':
            t_idx = int(parts[3])
            t_name = list(CONTENT[val].keys())[t_idx]
            if pref == 'study':
                text = f"📖 <b>{t_name}</b>\n\n{CONTENT[val][t_name]['theory']}"
                kb = [[InlineKeyboardButton("✍️ Пройти тест", callback_data=f"test:topic:{val}:{t_idx}")], [InlineKeyboardButton("⬅️ Назад", callback_data=f"study:class:{val}")]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            else:
                user_sessions[uid] = {'cls': val, 't_idx': t_idx, 'q_idx': 0, 'score': 0}
                await send_next_question(query, uid)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🏠 Главное меню":
        await update.message.reply_text("Переходим в главное меню:", reply_markup=build_main_menu())

def main():
    if not TOKEN: return print("BOT_TOKEN не найден!")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("Бот запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()
