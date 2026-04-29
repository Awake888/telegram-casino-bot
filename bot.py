import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

logging.basicConfig(level=logging.INFO)

TOKEN = "8648883883:AAF-Js6d3ZKgYBGdroYOXuK2PpSDz9wejHc"
APP_URL = "https://awake888.github.io/telegram-casino-bot/"

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="🎰 Открыть Казино",
        web_app=types.WebAppInfo(url=APP_URL)
    ))
    await message.answer(
        f"Добро пожаловать, {message.from_user.first_name}!\n\n"
        "Нажми кнопку ниже, чтобы зайти в казино. "
        "Игра идет на виртуальные монеты.",
        reply_markup=keyboard
    )

if __name__ == "__main__":
    print("Бот запущен и готов к работе!")
    executor.start_polling(dp, skip_updates=True)
