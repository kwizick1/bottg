import os
import logging
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
from telegram.error import InvalidToken

# --- НАСТРОЙКИ ЛОГИРОВАНИЯ ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- ИМПОРТ КОНТЕНТА ---
try:
    from data import CONTENT
except ImportError:
    print("\nКРИТИЧЕСКАЯ ОШИБКА: Файл data.py не найден!\n")
    sys.exit(1)

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
TOKEN = os.getenv('BOT_TOKEN')
DB_PATH = os.getenv('DB_PATH', '.')
USERS_FILE = os.path.join(DB_PATH, 'users_db.json')

ALL_USERS_IDS: Dict[int, Dict[str, Any]] = {}
user_sessions: Dict[int, Dict[str, Any]] = {} # Для хранения состояния тестов

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
def load_db():
    global ALL_USERS_IDS
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Конвертируем ключи обратно в int
                ALL_USERS_IDS = {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.error(f"Ошибка загрузки БД: {e}")

def save_db():
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(ALL_USERS_IDS, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения БД: {e}")

load_db()

# --- КЛАВИАТУРЫ ---
def get_main_reply_keyboard():
    """Кнопка под полем ввода"""
    return ReplyKeyboardMarkup([['🏠 Главное меню']], resize_keyboard=True, is_persistent=True)

def build_main_menu() -> InlineKeyboardMarkup:
    """Главные инлайн-кнопки"""
    keyboard = [
        [InlineKeyboardButton('📚 Изучение тем', callback_data='menu:study')],
        [InlineKeyboardButton('📝 Пройти тест', callback_data='menu:test')],
        [InlineKeyboardButton('📊 Моя статистика', callback_data='menu:stats')],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_class_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """Выбор класса"""
    buttons = []
    for cls in sorted(CONTENT.keys(), key=int):
        buttons.append([InlineKeyboardButton(f'{cls} класс', callback_data=f'{prefix}:class:{cls}')])
    buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='menu:main')])
    return InlineKeyboardMarkup(buttons)

def build_topics_keyboard(class_id: str, prefix: str) -> InlineKeyboardMarkup:
    """Выбор темы"""
    topics = list(CONTENT.get(class_id, {}).keys())
    kb = []
    for i, t_name in enumerate(topics):
        kb.append([InlineKeyboardButton(t_name, callback_data=f'{prefix}:topic:{class_id}:{i}')])
    kb.append([InlineKeyboardButton('⬅️ Назад', callback_data=f'{prefix}:back_to_classes')])
    return InlineKeyboardMarkup(kb)

# --- ЛОГИКА ТЕСТОВ ---
async def send_test_question(query, session):
    cls = session['class']
    t_idx = session['topic_idx']
    q_idx = session['current_q']
    
    topic_name = list(CONTENT[cls].keys())[t_idx]
    questions = CONTENT[cls][topic_name].get('questions', [])

    if q_idx < len(questions):
        q_data = questions[q_idx]
        keyboard = []
        for i, opt in enumerate(q_data['options']):
            is_correct = 1 if i == q_data['a'] else 0
            keyboard.append([InlineKeyboardButton(opt, callback_data=f"ans:{is_correct}")])
        
        text = f"<b>Тест: {topic_name}</b>\nВопрос {q_idx + 1} из {len(questions)}\n\n{q_data['q']}"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        # Конец теста
        score = session['score']
        total = len(questions)
        
        # Обновляем статистику пользователя
        user_id = query.from_user.id
        if user_id in ALL_USERS_IDS:
            ALL_USERS_IDS[user_id]['solved'] = ALL_USERS_IDS[user_id].get('solved', 0) + score
            save_db()

        await query.edit_message_text(
            f"<b>Тест завершен!</b>\n\nВаш результат: {score} из {total} правильных ответов.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню", callback_data="menu:main")]]),
            parse_mode='HTML'
        )
        if user_id in user_sessions:
            del user_sessions[user_id]

# --- ОБРАБОТЧИКИ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ALL_USERS_IDS
    user = update.effective_user
    chat_id = update.effective_chat.id

    if chat_id not in ALL_USERS_IDS:
        ALL_USERS_IDS[chat_id] = {
            'first_name': user.first_name,
            'username': user.username,
            'joined': time.ctime(),
            'solved': 0
        }
        save_db()

    await update.message.reply_text(
        f"Привет, {user.first_name}! Я твой помощник по физике Physix.",
        reply_markup=get_main_reply_keyboard()
    )
    await update.message.reply_text("Выберите раздел для начала:", reply_markup=build_main_menu())

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🏠 Главное меню":
        await update.message.reply_text("Возвращаю вас в главное меню:", reply_markup=build_main_menu())
        return
    await update.message.reply_text("Пожалуйста, используйте кнопки меню для навигации.")

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    data = query.data

    # Обработка ответов на тесты
    if data.startswith('ans:'):
        is_correct = int(data.split(':')[1])
        if user_id in user_sessions:
            if is_correct:
                user_sessions[user_id]['score'] += 1
            user_sessions[user_id]['current_q'] += 1
            await send_test_question(query, user_sessions[user_id])
        return

    # Навигация
    if data == 'menu:main':
        await query.edit_message_text('Выберите раздел:', reply_markup=build_main_menu())
    elif data == 'menu:study':
        await query.edit_message_text('Выберите класс:', reply_markup=build_class_keyboard('study'))
    elif data == 'menu:test':
        await query.edit_message_text('Выберите класс для теста:', reply_markup=build_class_keyboard('test'))
    elif data == 'menu:stats':
        solved = ALL_USERS_IDS.get(user_id, {}).get('solved', 0)
        await query.edit_message_text(
            f"📊 <b>Ваша статистика:</b>\nВсего правильных ответов: {solved}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")]]),
            parse_mode='HTML'
        )

    # Работа с подразделами (Классы и Темы)
    parts = data.split(':')
    if len(parts) >= 3:
        prefix, action, cls = parts[0], parts[1], parts[2]
        
        if action == 'class':
            await query.edit_message_text(f'Темы для {cls} класса:', reply_markup=build_topics_keyboard(cls, prefix))
        
        elif action == 'topic':
            t_idx = int(parts[3])
            topic_name = list(CONTENT[cls].keys())[t_idx]
            
            if prefix == 'study':
                theory_text = CONTENT[cls][topic_name]['theory']
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton('📝 Пройти тест по теме', callback_data=f'test:topic:{cls}:{t_idx}')],
                    [InlineKeyboardButton('⬅️ Назад', callback_data=f'study:class:{cls}')]
                ])
                await query.edit_message_text(theory_text, reply_markup=kb, parse_mode='HTML')
            
            elif prefix == 'test':
                user_sessions[user_id] = {'class': cls, 'topic_idx': t_idx, 'current_q': 0, 'score': 0}
                await send_test_question(query, user_sessions[user_id])

    if data.endswith('back_to_classes'):
        prefix = data.split(':')[0]
        await query.edit_message_text('Выберите класс:', reply_markup=build_class_keyboard(prefix))

# --- ЗАПУСК БОТА ---
def main():
    if not TOKEN:
        print("ОШИБКА: Переменная BOT_TOKEN не установлена!")
        return
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("Физик-бот запущен успешно!")
    app.run_polling()

if __name__ == '__main__':
    main()
