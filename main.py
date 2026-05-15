import logging
import os
from typing import Dict, Any, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from data import CONTENT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not found. Add it to Railway Variables.")


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📚 Теория", callback_data="menu_theory")],
            [InlineKeyboardButton("📝 Тесты", callback_data="menu_tests")],
        ]
    )


def class_menu(mode: str) -> InlineKeyboardMarkup:
    keyboard = []
    for cls in CONTENT.keys():
        keyboard.append([InlineKeyboardButton(f"{cls} класс", callback_data=f"class_{mode}_{cls}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)


def topics_menu(mode: str, cls: str) -> InlineKeyboardMarkup:
    keyboard = []
    topics = list(CONTENT.get(cls, {}).keys())
    for i, topic in enumerate(topics):
        keyboard.append([InlineKeyboardButton(topic, callback_data=f"topic_{mode}_{cls}_{i}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"menu_{mode}")])
    return InlineKeyboardMarkup(keyboard)


def question_keyboard(cls: str, topic_index: int, q_index: int, options: List[str]) -> InlineKeyboardMarkup:
    keyboard = []
    for idx, option in enumerate(options):
        keyboard.append([InlineKeyboardButton(option, callback_data=f"ans_{cls}_{topic_index}_{q_index}_{idx}")])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)


def get_topics(cls: str) -> List[str]:
    return list(CONTENT[cls].keys())


def get_topic_data(cls: str, topic_index: int) -> Dict[str, Any]:
    topics = get_topics(cls)
    if topic_index < 0 or topic_index >= len(topics):
        raise IndexError("topic_index out of range")
    topic_name = topics[topic_index]
    return CONTENT[cls][topic_name]


def start_test(context: ContextTypes.DEFAULT_TYPE, cls: str, topic_index: int) -> None:
    context.user_data["test"] = {
        "cls": cls,
        "topic_index": topic_index,
        "q_index": 0,
        "score": 0,
        "wrong": 0,
    }


def clear_test(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("test", None)


def result_text(score: int, wrong: int) -> str:
    total = score + wrong
    percent = round(score / total * 100) if total else 0
    return (
        "🎉 Тест завершён!\n\n"
        f"✅ Правильных ответов: {score}\n"
        f"❌ Ошибок: {wrong}\n"
        f"📊 Результат: {percent}%"
    )


async def show_question(query, context: ContextTypes.DEFAULT_TYPE, cls: str, topic_index: int, q_index: int):
    topic = get_topic_data(cls, topic_index)
    questions = topic["questions"]

    if q_index >= len(questions):
        state = context.user_data.get("test", {})
        text = result_text(state.get("score", 0), state.get("wrong", 0))
        clear_test(context)
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")],
                    [InlineKeyboardButton("🔁 Пройти ещё раз", callback_data=f"starttest_{cls}_{topic_index}")],
                ]
            ),
        )
        return

    question = questions[q_index]
    text = f"📝 Вопрос {q_index + 1}/5\n\n{question['q']}"
    await query.edit_message_text(
        text,
        reply_markup=question_keyboard(cls, topic_index, q_index, question["options"]),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_test(context)
    user = update.effective_user
    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Выбери раздел ниже:\n"
        "• Теория\n"
        "• Тесты"
    )
    await update.message.reply_text(text, reply_markup=main_menu())


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    try:
        if data == "menu":
            clear_test(context)
            await query.edit_message_text("🏠 Главное меню", reply_markup=main_menu())
            return

        if data == "menu_theory":
            clear_test(context)
            await query.edit_message_text("📚 Выбери класс для теории:", reply_markup=class_menu("theory"))
            return

        if data == "menu_tests":
            clear_test(context)
            await query.edit_message_text("📝 Выбери класс для тестов:", reply_markup=class_menu("test"))
            return

        if data.startswith("menu_"):
            clear_test(context)
            mode = data.split("_", 1)[1]
            title = "📚 Выбери класс для теории:" if mode == "theory" else "📝 Выбери класс для тестов:"
            await query.edit_message_text(title, reply_markup=class_menu(mode))
            return

        if data.startswith("class_"):
            clear_test(context)
            _, mode, cls = data.split("_", 2)
            title = f"{'📚' if mode == 'theory' else '📝'} Темы {cls} класса:"
            await query.edit_message_text(title, reply_markup=topics_menu(mode, cls))
            return

        if data.startswith("topic_"):
            clear_test(context)
            _, mode, cls, topic_index_str = data.split("_", 3)
            topic_index = int(topic_index_str)
            topic_name = get_topics(cls)[topic_index]
            topic = CONTENT[cls][topic_name]

            text = f"📖 {topic_name}\n\n{topic['theory']}"
            buttons = [
                [InlineKeyboardButton("📝 Пройти тест по теме", callback_data=f"starttest_{cls}_{topic_index}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data=f"class_{mode}_{cls}")],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            return

        if data.startswith("starttest_"):
            _, cls, topic_index_str = data.split("_", 2)
            topic_index = int(topic_index_str)
            start_test(context, cls, topic_index)
            await show_question(query, context, cls, topic_index, 0)
            return

        if data.startswith("ans_"):
            state = context.user_data.get("test")
            if not state:
                await query.edit_message_text("Тест не найден. Нажми /start и выбери тему заново.", reply_markup=main_menu())
                return

            _, cls, topic_index_str, q_index_str, selected_str = data.split("_", 4)
            topic_index = int(topic_index_str)
            q_index = int(q_index_str)
            selected = int(selected_str)

            topic = get_topic_data(cls, topic_index)
            questions = topic["questions"]
            if q_index >= len(questions):
                await query.edit_message_text("Тест уже завершён.", reply_markup=main_menu())
                clear_test(context)
                return

            question = questions[q_index]
            if selected == question["a"]:
                state["score"] += 1
            else:
                state["wrong"] += 1

            state["q_index"] = q_index + 1

            if state["q_index"] >= len(questions):
                await show_question(query, context, cls, topic_index, state["q_index"])
            else:
                await show_question(query, context, cls, topic_index, state["q_index"])
            return

        await query.edit_message_text("Неизвестная команда.", reply_markup=main_menu())

    except Exception:
        logger.exception("Callback error")
        await query.edit_message_text(
            "Произошла ошибка. Нажми /start и попробуй ещё раз.",
            reply_markup=main_menu(),
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled error: %s", context.error)


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_error_handler(error_handler)

    print("BOT STARTED")
    app.run_polling()


if __name__ == "__main__":
    main()
