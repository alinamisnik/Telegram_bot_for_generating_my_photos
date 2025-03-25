import logging
import pathlib
import random
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from replicate.client import Client
from decouple import config


REPO_DIR = pathlib.Path().resolve()
DATA_DIR = REPO_DIR / "data"
GENERATED_DIR = DATA_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True, parents=True)
REFERENCES_DIR = DATA_DIR / "references"
REFERENCES_DIR.mkdir(exist_ok=True, parents=True)


API_TOKEN = config("API_TOKEN")
MODEL = config("MODEL")
MODEL_VERSION = config("MODEL_VERSION")
client = Client(api_token=API_TOKEN)
model = f"{MODEL}:{MODEL_VERSION}"


ASK_REFERENCE, RECEIVE_REFERENCE, RECEIVE_PROMPT = range(3)
user_data_temp = {}
logging.basicConfig(level=logging.INFO)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Так", "Ні"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привіт! Я вмію створювати фотографії. Хочеш використати референсне зображення?", reply_markup=reply_markup)
    return ASK_REFERENCE


async def ask_reference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.lower()
    user_id = update.message.from_user.id
    user_data_temp[user_id] = {}

    if answer == "так":
        await update.message.reply_text("Надішли, будь ласка, зображення.")
        return RECEIVE_REFERENCE
    elif answer == "ні":
        await update.message.reply_text("Добре. Тоді введи текстовий опис.")
        return RECEIVE_PROMPT
    else:
        await update.message.reply_text("Будь ласка, виберіть 'Так' або 'Ні'.")
        return ASK_REFERENCE


async def receive_reference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    photo = update.message.photo[-1]
    photo_file = await photo.get_file()
    ref_path = REFERENCES_DIR / f"reference_{user_id}.jpg"
    await photo_file.download_to_drive(str(ref_path))

    user_data_temp[user_id]["reference_path"] = ref_path
    await update.message.reply_text("Отримано! Тепер введи опис зображення, яке хочеш отримати.")
    return RECEIVE_PROMPT


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    prompt = update.message.text
    ref_path = user_data_temp[user_id].get("reference_path", None)

    await update.message.reply_text("Генерую зображення... Це займе кілька секунд.")

    inputs = {
        "prompt": f"a photo of TOK adult woman {prompt}",
        "num_outputs": 2,
        "output_format": "jpg",
        "model": "dev"
    }

    if ref_path:
        image = open(ref_path, "rb")
        inputs["image"] = image

    responses = client.run(model, input=inputs)
    session_id = random.randint(1000, 9999)

    for i, output in enumerate(responses):
        fname = f"{i}-{session_id}.jpg"
        outpath = GENERATED_DIR / fname
        with open(outpath, "wb") as f:
            f.write(output.read())
        await update.message.reply_photo(photo=open(outpath, "rb"))

    if ref_path:
        image.close()

    await update.message.reply_text("Готово! Щоб згенерувати ще — надішли /start.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Генерацію скасовано. Надішли /start, щоб почати знову.")
    return ConversationHandler.END


def main():
    telegram_token = config("BOT_TOKEN")
    app = ApplicationBuilder().token(telegram_token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_REFERENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_reference)],
            RECEIVE_REFERENCE: [MessageHandler(filters.PHOTO, receive_reference)],
            RECEIVE_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prompt)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
