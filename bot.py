import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()
API_TOKEN = os.getenv('API_TOKEN')

# Инициализация бота и хранилища состояний
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Удаление webhook (если он был установлен)
async def delete_webhook():
    await bot.delete_webhook()

# Создание кнопки для открытия веб-приложения
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    web_app_url = f"https://chinatogether.github.io/delivery-calculator/index.html?telegram_id={user_id}&username={username}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Открыть форму",
            web_app=types.WebAppInfo(url=web_app_url)
        )]
    ])
    await message.reply("Нажмите кнопку, чтобы открыть форму:", reply_markup=keyboard)

# Запуск бота
async def main():
    # Удаляем webhook, если он активен
    await delete_webhook()
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
