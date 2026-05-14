import os
                "⬅️ В меню",
                callback_data="menu"
            )
        ])

        text = (
            f"📝 Вопрос {q_index + 1}/{len(questions)}\n\n"
            f"{question['q']}"
        )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ================= ANSWER =================

    if data.startswith("answer_"):

        parts = data.split("_")

        cls = parts[1]
        topic_index = int(parts[2])
        q_index = int(parts[3])
        selected = int(parts[4])

        topic_name = list(CONTENT[cls].keys())[topic_index]
        topic_data = CONTENT[cls][topic_name]

        question = topic_data['questions'][q_index]

        user_id = str(query.from_user.id)

        if selected == question['a']:
            USERS[user_id]['correct'] += 1
            result = "✅ Правильно!"
        else:
            USERS[user_id]['wrong'] += 1
            correct_answer = question['options'][question['a']]
            result = f"❌ Неправильно!\nПравильный ответ: {correct_answer}"

        save_users(USERS)

        keyboard = [
            [InlineKeyboardButton(
                "➡️ Следующий вопрос",
                callback_data=f"starttest_{cls}_{topic_index}_{q_index + 1}"
            )],
            [InlineKeyboardButton(
                "🏠 Главное меню",
                callback_data="menu"
            )]
        ]

        await query.edit_message_text(
            result,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return


# ================= ERROR HANDLER =================


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)


# ================= MAIN =================


def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))

    app.add_error_handler(error_handler)

    print("✅ BOT STARTED")

    app.run_polling()


if __name__ == "__main__":
    main()
