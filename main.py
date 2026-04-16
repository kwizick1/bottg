"""
Physics Reference & Quiz Telegram Bot (v4.2 с Вынесенным Контентом и Webhook/Polling)
Совместим с python-telegram-bot v22.5

Особенности:
1. Контент (теория, формулы, тесты) вынесен в data.py.
2. Поддержка команды /help_admin.
3. Управление базой данных (save_db, list_users, broadcast, send_to).
4. Интеграция с Gemini.
"""

import os
import logging
import random
import re
import json
import sys
from google import genai
from google.api_core import exceptions
import time
from typing import Dict, Any, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.error import InvalidToken, BadRequest
import telegram
from urllib.parse import quote

# ------------------------- ИМПОРТ КОНТЕНТА -------------------------
try:
    # Импортируем словари из отдельного файла data.py
    from data import CONTENT, FORMULA_CAPTIONS
except ImportError:
    # На случай, если файл data.py не будет найден
    print("\n\nКРИТИЧЕСКАЯ ОШИБКА: Не удалось импортировать CONTENT и FORMULA_CAPTIONS из data.py. Убедитесь, что файл data.py существует.\n\n")
    sys.exit(1)


try:
    from google import genai
except ImportError:
    genai = None 
    logger.warning("Библиотека 'google-genai' не найдена. Функции ИИ будут отключены.")


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ------------------------- TOKEN LOADING -------------------------

def load_token() -> str:
    """Загружает токен бота исключительно из переменной окружения BOT_TOKEN."""
    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.error('BOT_TOKEN environment variable not set. This is required for deployment.')
        raise ValueError("BOT_TOKEN is required and not set in environment variables.")
    logger.info('Loaded BOT_TOKEN from environment variable.')
    return token.strip()

TOKEN = load_token()


# получение токена для гемини 

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') 
ai_client = None

if GEMINI_API_KEY and genai:
    try:
        # Инициализация клиента
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Клиент Gemini успешно инициализирован.")
    except Exception as e:
        logger.error(f"Ошибка инициализации Gemini: {e}")


# ========================= BROADCAST & USER DB CONFIG =========================

# !!! ОБЯЗАТЕЛЬНО ЗАМЕНИТЕ ЭТОТ ID НА ВАШ ЛИЧНЫЙ TELEGRAM ID !!!
OWNER_ID = 8707709434  # <--- ВАШ ID

# Глобальная переменная для хранения информации о пользователях
ALL_USERS_IDS: Dict[int, Dict[str, Any]] = {}
user_stats: Dict[int, Dict[str, Any]] = {}

# --- Чтение пути для постоянной базы данных ---
# Если переменная окружения DB_PATH задана (например, на Railway Volume), используем ее.
# Иначе используем текущую директорию ('.').
DB_PATH = os.getenv('DB_PATH', '.')

# Файлы для сохранения данных
USERS_FILE = os.path.join(DB_PATH, 'users_db.json')
STATS_FILE = os.path.join(DB_PATH, 'stats_db.json')

def load_user_ids():
    """Загружает данные пользователей из JSON-файла."""
    # Убедимся, что директория существует
    if not os.path.exists(DB_PATH):
        os.makedirs(DB_PATH)

    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                ALL_USERS_IDS.update({int(k): v for k, v in data.items()})
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Ошибка загрузки базы пользователей: {e}. Начинаем с пустой базы.")
                pass
    logger.info(f"Loaded {len(ALL_USERS_IDS)} users from user DB: {USERS_FILE}.")

def save_user_ids():
    """Сохраняет данные пользователей в JSON-файл."""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(ALL_USERS_IDS, f, ensure_ascii=False, indent=4)
        logger.info(f"Saved {len(ALL_USERS_IDS)} users to user DB: {USERS_FILE}.")
    except Exception as e:
        logger.error(f"Ошибка сохранения базы пользователей: {e}")

def load_stats():
    """Загружает данные статистики из JSON-файла."""
    # Убедимся, что директория существует
    if not os.path.exists(DB_PATH):
        os.makedirs(DB_PATH)

    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                user_stats.update({int(k): v for k, v in data.items()})
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Ошибка загрузки статистики: {e}. Начинаем с пустой статистики.")
                pass
    logger.info(f"Loaded {len(user_stats)} users' stats from DB: {STATS_FILE}.")

def save_stats():
    """Сохраняет данные статистики в JSON-файл."""
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_stats, f, ensure_ascii=False, indent=4)
        logger.info(f"Saved {len(user_stats)} users' stats to DB: {STATS_FILE}.")
    except Exception as e:
        logger.error(f"Ошибка сохранения статистики: {e}")

def get_main_reply_keyboard():
    keyboard = [['🏠 Главное меню']]
    return ReplyKeyboardMarkup(
        keyboard, 
        resize_keyboard=True, 
        is_persistent=True  
    )
# Вызываем загрузку данных при запуске скрипта
load_user_ids()
load_stats()
# ------------------------- FORMULA CONVERSION UTILS -------------------------

def convert_latex_to_simple_text(latex_code: str) -> str:
    """
    Преобразует сложный LaTeX-код в простой, читаемый Юникод-текст,
    используя символ деления (÷) вместо слэша.
    """

    text = latex_code.strip()

    # 1. Замена дроби 1/2 на специальный символ Юникода
    text = text.replace(r"\frac{1}{2}", "½")

    # 2. Замена остальных дробей: \frac{A}{B} -> (A) ÷ (B)
    def replace_frac(match):
        num = match.group(1).strip()
        den = match.group(2).strip()
        if len(num) == 1 and len(den) == 1:
             return f"{num} ÷ {den}"
        return f"({num}) ÷ ({den})"

    text = re.sub(r"\\frac{([^}]+)}{([^}]+)}", replace_frac, text)

    # 3. Замена операторов и специальных символов
    text = text.replace(r"\cdot", " * ")
    text = text.replace(r"\rho", "ρ")
    text = text.replace(r"\lambda", "λ")
    text = text.replace(r"\mu", "μ")
    text = text.replace(r"\alpha", "α")
    text = text.replace(r"\sin", "sin")
    text = text.replace(r"\cos", "cos")
    text = text.replace(r"\theta_1", "θ₁")
    text = text.replace(r"\theta_2", "θ₂")
    text = text.replace(r"|", "")
    text = text.replace(r"\text{ж}", "ж")
    text = text.replace(r"\text{Н}", "Н")
    text = text.replace(r"\text{м}", "м")
    text = text.replace(r"\text{Кл}", "Кл")
    text = text.replace(r"\text{дптр}", "дптр")
    text = text.replace(r"\approx", "≈")

    # 4. Замена степеней: ^2, ^3 -> ², ³
    text = re.sub(r"\^2\b", "²", text)
    text = re.sub(r"\^3\b", "³", text)
    text = re.sub(r"\^9\b", "⁹", text)
    text = text.replace(r"\^{-6}", "⁻⁶")

    # 5. Индексы
    text = text.replace(r"t_1", "t₁")
    text = text.replace(r"t_2", "t₂")
    text = text.replace(r"q_1", "q₁")
    text = text.replace(r"q_2", "q₂")
    text = text.replace(r"d_o", "d₀")
    text = text.replace(r"d_i", "dᵢ")

    # 6. Убираем лишние фигурные скобки
    text = text.replace("{", "").replace("}", "")

    # 7. Финальная очистка:
    text = re.sub(r"\s+", " ", text).strip()

    return text.strip()


# ------------------------- SESSIONS & STATS -------------------------
user_sessions: Dict[int, Dict[str, Any]] = {}
# ------------------------- HELPERS -------------------------

def build_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton('📚 Изучение тем', callback_data='menu:study')],
        [InlineKeyboardButton('📝 Пройти тест', callback_data='menu:test')],
        [InlineKeyboardButton('💡 Спросить Репетитора (ИИ)', callback_data='menu:ai_chat')],
        [InlineKeyboardButton('ℹ️ О боте, поддержка', callback_data='menu:about')],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_class_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    # Теперь классы берутся из импортированного словаря CONTENT
    for cls in sorted(CONTENT.keys()): 
        buttons.append([InlineKeyboardButton(f'Класс {cls}', callback_data=f'{prefix}:class:{cls}')])
    buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='menu:main')])
    return InlineKeyboardMarkup(buttons)


def build_topics_keyboard(class_id: str, prefix: str) -> InlineKeyboardMarkup:
    topics = list(CONTENT.get(class_id, {}).keys())
    kb = [[InlineKeyboardButton(t, callback_data=f'{prefix}:topic:{class_id}:{i}')] for i, t in enumerate(topics)]
    kb.append([InlineKeyboardButton('⬅️ Назад', callback_data=f'{prefix}:back_to_classes')])
    return InlineKeyboardMarkup(kb)


# ------------------------- HANDLERS -------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Регистрация пользователя
    if chat_id not in ALL_USERS_IDS:
        user_data = {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name if user.last_name else '',
            'username': user.username if user.username else '',
            'joined': time.ctime()
        }
        ALL_USERS_IDS[chat_id] = user_data
        save_user_ids()

    # Отправляем текстовую кнопку "🏠 Главное меню"
    await update.message.reply_text(
        "Добро пожаловать в справочник по физике! Используйте меню ниже для навигации.",
        reply_markup=get_main_reply_keyboard()
    )
    
    # Отображаем встроенные (inline) кнопки меню
    await update.message.reply_text(
        f'Привет, {user.first_name or "друг"}! Я — справочник по физике. Выберите действие ниже.',
        reply_markup=build_main_menu()
    )


async def ai_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Основная логика для обработки запроса нейросети с логикой повторных попыток (Retry).
    """
    user_prompt = update.effective_message.text
    chat_id = update.effective_chat.id

    if not user_prompt:
        return

    if not ai_client:
        await update.effective_message.reply_text("⛔️ Функция ИИ временно недоступна. Убедитесь, что API-ключ настроен.", parse_mode='HTML')
        return
    
    await context.bot.send_chat_action(chat_id, telegram.constants.ChatAction.TYPING)

    system_prompt = (
        "Ты — эксперт-репетитор по школьной физике (7-11 класс). Отвечай на вопросы "
        "максимально точно и дружелюбно. Используй Markdown для форматирования "
        "и LaTeX-синтаксис в одинарных знаках доллара ($) для формул (например, $E=mc^2$). "
        "Всегда начинай ответ с краткого и прямого пояснения."
    )
    full_prompt = f"ИНСТРУКЦИЯ:\n{system_prompt}\n\nВОПРОС:\n{user_prompt}"

    # --- ЛОГИКА ПОВТОРНЫХ ПОПЫТОК (RETRY LOGIC) ---
    MAX_RETRIES = 3
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            # 2. Вызываем API
            response = ai_client.models.generate_content(
                model='gemini-1.5-flash',
                contents=[
                    {"role": "user", "parts": [{"text": full_prompt}]} 
                ]
            )
            
            # Если запрос успешен, выходим из цикла
            await update.effective_message.reply_text(
                response.text, 
                parse_mode='Markdown'
            )
            return # Успешное выполнение, выходим из функции

        except exceptions.ResourceExhausted as e:
            # Обрабатываем 503 UNAVAILABLE (или 429 Rate Limit)
            last_exception = e
            logger.warning(f"Попытка {attempt + 1}: Модель перегружена (503/429). Ожидание 3 секунды...")
            
           if attempt < MAX_RETRIES - 1:
               time.sleep(10)
            else:
                # Если это была последняя попытка, логика отправит ошибку ниже
                pass

        except Exception as e:
            # Обработка всех других ошибок (токен, неизвестные ошибки)
            logger.error(f"Критическая ошибка Gemini API на попытке {attempt + 1}: {e}")
            last_exception = e
            break # Выход из цикла для не-503 ошибок

    # --- Если все попытки провалились ---
    if last_exception:
        error_details = str(last_exception)
        
        if chat_id == OWNER_ID:
            await update.effective_message.reply_text(
                f"❌ Ошибка API Gemini после {MAX_RETRIES} попыток (для администратора):\n<code>{error_details}</code>", 
                parse_mode='HTML'
            )
        else:
            await update.effective_message.reply_text(
                "❌ Извините, нейросеть сейчас перегружена. Пожалуйста, попробуйте задать вопрос через пару минут."
            )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # --- 1. Обработка главного меню ---
    if data == 'menu:study':
        await query.edit_message_text('Выберите класс для изучения:', reply_markup=build_class_keyboard('study'))
        return

    if data == 'menu:test':
        await query.edit_message_text('Выберите класс для теста:', reply_markup=build_class_keyboard('test'))
        return

    if data == 'menu:about':
        about_text = (
            'Этот бот — интерактивный справочник и тестировщик по школьной физике\n\n'
            'Функции:\n- Изучение тем с теорией и формулами\n- Прохождение тестов по выбранной теме и классу\n- Сохранение краткой статистики (в текущей сессии)\n\n'
            'По всем ошибкам и вопросам обращаться: @physicstheorysupport_bot.'
        )
        
    if data == 'menu:ai_chat':
        uid = query.from_user.id
        
        if not ai_client:
            await query.edit_message_text("⛔️ Функция ИИ временно недоступна.", reply_markup=build_main_menu(), parse_mode='HTML')
            return
            
        # Устанавливаем режим AI
        user_sessions[uid] = user_sessions.get(uid, {})
        user_sessions[uid]['mode'] = 'ai_chat'
        
        chat_message = (
            "💡 **Режим ИИ-Репетитора активирован!**\n\n"
            "Вы можете задавать вопросы по физике напрямую, без команд.\n"
            "Чтобы вернуться в главное меню, нажмите кнопку ниже или введите /start."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton('🚪 Выйти из режима ИИ', callback_data='menu:main')]])

        await query.edit_message_text(chat_message, reply_markup=kb, parse_mode='Markdown')
        return

    if data == 'menu:main':
        uid = query.from_user.id
        # При выходе из ИИ-режима, очищаем его
        if uid in user_sessions and user_sessions[uid].get('mode') == 'ai_chat':
            user_sessions[uid].pop('mode') 
            if not user_sessions[uid]:
                 user_sessions.pop(uid)
                 
        await query.edit_message_text('Возвращаю в главное меню:', reply_markup=build_main_menu())
        return    
        # --- КНОПКА НАЗАД ---
        kb = InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='menu:main')]])
        
        await query.edit_message_text(about_text, reply_markup=kb, parse_mode='HTML')
        return

    if data == 'menu:main':
        await query.edit_message_text('Возвращаю в главное меню:', reply_markup=build_main_menu())
        return

    # --- 2. Обработка команд, связанных с текущим тестом ---

    if data.startswith('test:class_topic:'):
        parts = data.split(':')
        cls = parts[2]
        topic_index = int(parts[3])
        topic_list = list(CONTENT.get(cls, {}).keys())
        topic_name = topic_list[topic_index]

        uid = update.effective_user.id
        user_sessions[uid] = {
            'class': cls,
            'topic_index': topic_index,
        }

        qcount_buttons = [
            [InlineKeyboardButton('Начать тест', callback_data='test:qty:all')],
            [InlineKeyboardButton('⬅️ Назад к классам', callback_data=f'test:back_to_classes')],
        ]
        kb = InlineKeyboardMarkup(qcount_buttons)
        await query.edit_message_text(f'Выбрана тема: <b>{topic_name}</b>\nНажмите "Начать тест".', reply_markup=kb,
                                              parse_mode='HTML')
        return

    if data.startswith('test:qty:'):
        uid = update.effective_user.id
        session = user_sessions.get(uid)
        if not session:
             await query.edit_message_text('Сессия теста не найдена. Попробуйте заново.', reply_markup=build_main_menu())
             return
        cls = session['class']
        topic_index = session['topic_index']
        topic_list = list(CONTENT.get(cls, {}).keys())
        topic_name = topic_list[topic_index]
        questions = CONTENT[cls][topic_name]['questions']

        n = len(questions)

        qpool = questions.copy()
        random.shuffle(qpool)
        qlist = qpool[:n]

        user_sessions[uid].update({
            'questions': qlist,
            'q_index': 0,
            'score': 0,
            'answers': [],
        })
        await send_next_question(update, context, uid)
        return


    if data.startswith('answer:'):
        uid = update.effective_user.id
        await query.answer()
        parts_ans = data.split(':')
        chosen_index = int(parts_ans[1])
        session = user_sessions.get(uid)
        if not session:
            await query.edit_message_text('Тестовая сессия не найдена. Начните заново.', reply_markup=build_main_menu())
            return
        current_qi = session['q_index']
        qlist = session['questions']
        current_q = qlist[current_qi]
        correct_index = current_q['a']
        is_correct = (chosen_index == correct_index)
        if is_correct:
            session['score'] += 1
        session['answers'].append({'question': current_q['q'], 'chosen': chosen_index, 'correct': correct_index,
                                   'options': current_q['options']})
        session['q_index'] += 1

        if session['q_index'] < len(session['questions']):
            await send_next_question(update, context, uid)
            return
        else:
            await finish_test(update, context, uid)
            return

    if data == 'test:end':
        uid = update.effective_user.id
        session = user_sessions.get(uid)
        if not session:
            await query.edit_message_text('Тест не был запущен. Возвращаю в главное меню:',
                                          reply_markup=build_main_menu())
            return
        await finish_test(update, context, uid)
        return

    # --- 3. Обработка навигационных команд ---
    parts = data.split(':')

    if len(parts) == 2 and parts[1] == 'back_to_classes':
        prefix = parts[0]
        if prefix == 'study':
            await query.edit_message_text('Выберите класс для изучения:', reply_markup=build_class_keyboard('study'))
        elif prefix == 'test':
            await query.edit_message_text('Выберите класс для теста:', reply_markup=build_class_keyboard('test'))
        return

    if len(parts) >= 3:
        prefix = parts[0]
        action = parts[1]

        if action == 'class':
            cls = parts[2]
            if prefix == 'study':
                await query.edit_message_text(f'Класс {cls} — выберите тему:',
                                              reply_markup=build_topics_keyboard(cls, 'study'))
                return
            elif prefix == 'test':
                await query.edit_message_text(f'Класс {cls} — выберите тему для теста:',
                                              reply_markup=build_topics_keyboard(cls, 'test'))
                return

        if action == 'topic':
            cls = parts[2]
            topic_index = int(parts[3])
            topic_list = list(CONTENT.get(cls, {}).keys())
            if topic_index < 0 or topic_index >= len(topic_list):
                await query.answer('Тема не найдена', show_alert=True)
                return
            topic_name = topic_list[topic_index]
            topic = CONTENT[cls][topic_name] # CONTENT теперь импортирован

            if prefix == 'study':
                # --- Логика отображения темы с формулами ---
                formulas_latex_list = topic.get("formulas_urls", [])
                theory_text = topic.get("theory", "Нет теории")

                text = f'<b>{topic_name} — Класс {cls}</b>\n\n'
                text += f'<i>Теория:</i>\n{theory_text}\n\n'

                if formulas_latex_list:
                    text += '<b>Основные формулы:</b>\n\n'
                    for formula_latex in formulas_latex_list:
                        caption = FORMULA_CAPTIONS.get(formula_latex, "Формула (нет подписи):") # FORMULA_CAPTIONS теперь импортирован

                        simple_formula = convert_latex_to_simple_text(formula_latex)

                        text += f'{caption}\n'
                        text += f'<pre>{simple_formula}</pre>\n'

                # --- НОВАЯ НАВИГАЦИЯ ---
                kb_rows = []
                next_index = topic_index + 1

                # Кнопка "Следующая тема"
                if next_index < len(topic_list):
                    next_topic_name = topic_list[next_index]
                    kb_rows.append([InlineKeyboardButton(f'➡️ Следующая тема ({next_topic_name})',
                                                         callback_data=f'study:topic:{cls}:{next_index}')])

                # Кнопка "Пройти тест по этой теме"
                kb_rows.append([InlineKeyboardButton(f'📝 Пройти тест по "{topic_name}"',
                                                     callback_data=f'test:class_topic:{cls}:{topic_index}')])

                # Кнопки Назад
                kb_rows.append([InlineKeyboardButton('⬅️ Назад к классам', callback_data=f'study:back_to_classes')])
                kb_rows.append([InlineKeyboardButton('⬅️ Главное меню', callback_data='menu:main')])

                kb = InlineKeyboardMarkup(kb_rows)

                try:
                    await query.edit_message_text(text, reply_markup=kb, parse_mode='HTML')
                except BadRequest as e:
                    logger.warning(f"Error editing message: {e}. Sending new message instead.")
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=text,
                        reply_markup=kb,
                        parse_mode='HTML'
                    )
                return

            if prefix == 'test':
                uid = update.effective_user.id
                user_sessions[uid] = {
                    'class': cls,
                    'topic_index': topic_index,
                }
                qcount_buttons = [
                    [InlineKeyboardButton('Начать тест', callback_data='test:qty:all')],
                    [InlineKeyboardButton('⬅️ Назад к классам', callback_data=f'test:back_to_classes')],
                ]
                kb = InlineKeyboardMarkup(qcount_buttons)
                await query.edit_message_text(f'Выбрана тема: <b>{topic_name}</b>\nНажмите "Начать тест".', reply_markup=kb,
                                              parse_mode='HTML')
                return

    await query.answer('Неизвестная команда', show_alert=True)


async def send_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int):
    session = user_sessions[uid]
    qi = session['q_index']
    q = session['questions'][qi]
    text = f'<b>Вопрос {qi+1} из {len(session["questions"])}</b>\n\n{q["q"]}'
    kb = [[InlineKeyboardButton(opt, callback_data=f'answer:{i}')] for i, opt in enumerate(q['options'])]
    kb.append([InlineKeyboardButton('Сдаться и закончить', callback_data='test:end')])
    kb_markup = InlineKeyboardMarkup(kb)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb_markup, parse_mode='HTML')
    else:
        await context.bot.send_message(chat_id=uid, text=text, reply_markup=kb_markup, parse_mode='HTML')


async def finish_test(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int):
    session = user_sessions.get(uid)
    if not session:
        return
    total = len(session['questions'])
    score = session['score']
    percent = round(score / total * 100) if total > 0 else 0

    text = f'Тест завершён!\nРезультат: {score} из {total} ({percent}%)\n\nПодробности:\n'
    for i, ans in enumerate(session['answers'], start=1):
        correct = ans['correct']
        chosen = ans['chosen']
        qtext = ans['question']
        opts = ans['options']
        marker = '✅' if chosen == correct else '❌'
        text += f'{i}) {marker} {qtext}\n   Ваш ответ: {opts[chosen]}\n   Правильный: {opts[correct]}\n'

    stats = user_stats.setdefault(uid, {'tests_taken': 0, 'total_correct': 0, 'total_questions': 0})
    stats['tests_taken'] += 1
    stats['total_correct'] += score
    stats['total_questions'] += total

    save_stats()

    user_sessions.pop(uid, None)

    kb = InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Главное меню', callback_data='menu:main')]])

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await context.bot.send_message(chat_id=uid, text=text, reply_markup=kb)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Если нажата кнопка на клавиатуре
    if text == "🏠 Главное меню":
        return await start(update, context)

    # Регистрация (на случай, если пользователь сразу написал текст)
    if chat_id not in ALL_USERS_IDS:
        user_data = {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name if user.last_name else '',
            'username': user.username if user.username else '',
        }
        ALL_USERS_IDS[chat_id] = user_data
        save_user_ids()

    uid = update.effective_user.id
    
    # 1. Проверка режима AI Chat
    if uid in user_sessions and user_sessions[uid].get('mode') == 'ai_chat':
        await ai_query_handler(update, context)
        return

    # 2. Если не в режиме AI, показываем главное меню
    msg_text = "Отправьте /start для запуска бота или выберите одну из кнопок в меню."
    await update.message.reply_text(msg_text, reply_markup=build_main_menu())

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    stats = user_stats.get(uid)
    if not stats:
        await update.message.reply_text('Статистики пока нет. Пройдите хотя бы один тест.')
        return
    total = stats['total_questions']
    correct = stats['total_correct']
    tests = stats['tests_taken']
    pct = round(correct / total * 100) if total > 0 else 0
    text = f'Статистика:\nТестов пройдено: {tests}\nВсего вопросов: {total}\nПравильных ответов: {correct} ({pct}%)'
    await update.message.reply_text(text)


# ========================= ADMIN HANDLERS =========================

async def help_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет список всех доступных административных команд."""
    sender_id = update.effective_user.id

    if sender_id != OWNER_ID:
        await update.message.reply_text("⛔️ У вас нет прав на эту команду.")
        return

    help_text = (
        "⚙️ <b>Административные команды:</b>\n\n"
        "<b>/list_users</b> — Показать общее количество пользователей бота.\n\n"
        "<b>/broadcast &lt;текст&gt;</b> — Отправить сообщение всем активным пользователям бота.\n"
        "<i>Использование: /broadcast Внимание, бот обновлен!</i>\n\n"
        "<b>/send_to &lt;user_id&gt; &lt;текст&gt;</b> — Отправить личное сообщение конкретному пользователю по его Telegram ID.\n"
        "<i>Использование: /send_to 123456789 Привет от админа.</i>\n\n"
        "<b>/save_db</b> — Принудительно сохранить данные о пользователях и статистику в файлы JSON.\n\n"
        "<b>/help_admin</b> — Показать этот список команд."
    )

    await update.message.reply_text(help_text, parse_mode='HTML')


async def save_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Администраторская команда для принудительного сохранения всех данных."""
    sender_id = update.effective_user.id

    if sender_id != OWNER_ID:
        await update.message.reply_text("⛔️ У вас нет прав на эту команду.")
        return

    await update.message.reply_text("💾 Начинаю принудительное сохранение базы данных...")

    try:
        save_user_ids()
        save_stats()
        await update.message.reply_text("✅ База пользователей и статистика успешно сохранены.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при сохранении: {e}")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id

    # 1. Проверка администратора
    if sender_id != OWNER_ID:
        await update.message.reply_text("⛔️ У вас нет прав на рассылку.")
        return

    # 2. Получение текста/сообщения для рассылки
    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text("Отправьте команду /broadcast <текст> или ответьте ей на сообщение, которое нужно разослать.")
        return

    message_to_send = update.message.reply_to_message
    broadcast_text = " ".join(context.args) if not message_to_send else None

    if not message_to_send and not broadcast_text:
        await update.message.reply_text("Рассылаемый текст не может быть пустым.")
        return

    # 3. Запуск рассылки
    success_count = 0
    blocked_count = 0
    total_users = len(ALL_USERS_IDS)

    # Отправляем уведомление, что рассылка началась
    await update.message.reply_text(f"🚀 Начинаю рассылку для {total_users} пользователей...")

    users_to_check = list(ALL_USERS_IDS.keys())

    for chat_id in users_to_check:
        try:
            if message_to_send:
                # Пересылка сообщения (поддерживает медиа)
                await context.bot.forward_message(
                    chat_id=chat_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=message_to_send.message_id
                )
            elif broadcast_text:
                # Отправка текста
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=broadcast_text,
                    parse_mode='HTML'
                )
            success_count += 1
        except telegram.error.Unauthorized:
            # Пользователь заблокировал бота
            blocked_count += 1
            if chat_id in ALL_USERS_IDS:
                del ALL_USERS_IDS[chat_id]
        except Exception as e:
            # Игнорируем другие ошибки отправки
            logger.error(f"Ошибка отправки пользователю {chat_id}: {e}")
            pass

    # 4. Отчет о результате и сохранение
    report = (
        f"✅ Рассылка завершена!\n"
        f"Успешно доставлено: {success_count} сообщений\n"
        f"Пользователи заблокировали бота: {blocked_count}\n"
        f"Общее число активных пользователей: {len(ALL_USERS_IDS)}"
    )
    save_user_ids()
    await context.bot.send_message(sender_id, report)


async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выводит список пользователей с их именами и юзернеймами (только для админа)."""
    sender_id = update.effective_user.id

    if sender_id != OWNER_ID:
        await update.message.reply_text("⛔️ У вас нет прав на просмотр списка пользователей.")
        return

    # Заголовок отчета
    report = [f"📊 **ВСЕГО АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ**: {len(ALL_USERS_IDS)}\n"]

    sorted_users = sorted(ALL_USERS_IDS.values(), key=lambda x: x.get('first_name', 'zzzz'))

    for user_data in sorted_users:
        user_id = user_data['id']
        first_name = user_data.get('first_name', 'Нет Имени')
        last_name = user_data.get('last_name')
        username = user_data.get('username')

        full_name = f"{first_name} {last_name}".strip() if last_name else first_name

        link = f"<a href='tg://user?id={user_id}'>{full_name}</a>"

        username_str = f" (@{username})" if username else ""

        report.append(f"• {link}{username_str} (ID: <code>{user_id}</code>)")

    full_report = "\n".join(report)

    if len(full_report) > 4000:
        chunks = [full_report[i:i + 4000] for i in range(0, len(full_report), 4000)]
        for chunk in chunks:
            await context.bot.send_message(sender_id, chunk, parse_mode='HTML')
    else:
        await context.bot.send_message(sender_id, full_report, parse_mode='HTML')


async def send_to_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Администраторская команда для отправки личного сообщения пользователю по ID."""
    sender_id = update.effective_user.id

    if sender_id != OWNER_ID:
        await update.message.reply_text("⛔️ У вас нет прав на эту команду.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Использование: /send_to <user_id> <текст сообщения>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный ID пользователя. ID должен быть числом.")
        return

    message_text = " ".join(context.args[1:])

    if not message_text:
        await update.message.reply_text("Сообщение не может быть пустым.")
        return

    try:
        # Пытаемся отправить сообщение
        await context.bot.send_message(
            chat_id=target_id,
            text=f"✉️ **Сообщение от Администратора**:\n\n{message_text}",
            parse_mode='Markdown'
        )
        await update.message.reply_text(f"✅ Сообщение успешно отправлено пользователю с ID: {target_id}.")
    except telegram.error.Unauthorized:
        await update.message.reply_text(f"❌ Не удалось отправить. Пользователь {target_id} заблокировал бота.")
    except telegram.error.BadRequest as e:
        await update.message.reply_text(f"❌ Ошибка отправки пользователю {target_id}: {e}")
    except Exception as e:
        await update.message.reply_text(f"❌ Неизвестная ошибка: {e}")


async def unknown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text('Я не понимаю. Используйте меню.', reply_markup=build_main_menu())


# ========================= ERROR HANDLER =========================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет администратору уведомление о критической ошибке."""
    logger.error("Произошло исключение в обработчике:", exc_info=context.error)

    try:
        update_info = str(update.effective_message.text) if update and update.effective_message else "Нет информации о сообщении."

        error_message = (
            "🚨 **КРИТИЧЕСКАЯ ОШИБКА В БОТЕ!**\n\n"
            f"**Обновление:** {update_info[:100]}...\n"
            f"**Ошибка:** <code>{context.error.__class__.__name__}</code>\n"
            f"**Подробности:** <code>{context.error}</code>"
        )

        await context.bot.send_message(
            OWNER_ID,
            error_message,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.critical(f"Не удалось отправить уведомление администратору: {e}")


# ------------------------- APP RUN -------------------------

def main():
    if not TOKEN:
        return

    try:
        app = ApplicationBuilder().token(TOKEN).build()
    except InvalidToken:
        logger.exception('Provided token appears invalid during ApplicationBuilder construction.')
        print('\nОшибка: указанный токен недействителен. Проверьте токен и попробуйте снова.\n')
        return

    # --- Обработчики команд ---
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('stats', stats_command))
    
    # --- Регистрация команд администратора ---
    app.add_handler(CommandHandler('broadcast', broadcast_command))
    app.add_handler(CommandHandler('list_users', list_users_command))
    app.add_handler(CommandHandler('save_db', save_db_command))
    app.add_handler(CommandHandler('send_to', send_to_command))
    app.add_handler(CommandHandler('help_admin', help_admin_command)) # <-- НОВАЯ КОМАНДА

    # --- Основные обработчики ---
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_handler))

    # --- Обработчик ошибок ---
    app.add_error_handler(error_handler) 

    logger.info('Запуск бота...')
    try:
        app.run_polling()
    except InvalidToken:
        logger.exception('Invalid token detected while running. The token was rejected by Telegram API.')
        print('\nОшибка: токен был отклонён сервером Telegram. Проверьте, не истёк ли токен и правильно ли он введён.\n')


if __name__ == '__main__':

    main()



