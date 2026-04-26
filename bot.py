import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder

logging.basicConfig(level=logging.INFO)

# Твой токен
TOKEN = "8648883883:AAF-Js6d3ZKgYBGdroYOXuK2PpSDz9wejHc"
# Твоя ссылка на GitHub Pages (уже вставлена корректно)
APP_URL = "https://awake888.github.io/telegram-casino-bot/"

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(
        text="Открыть Казино 🎰",
        web_app=types.WebAppInfo(url=APP_URL)
    ))

    await message.answer(
        f"Добро пожаловать, {message.from_user.first_name}!\n\n"
        "Нажми кнопку ниже, чтобы зайти в Mini App. "
        "Игра идет на виртуальные монеты.",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

async def main():
    print("Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
