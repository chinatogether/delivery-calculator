import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Вставьте сюда токен вашего бота
BOT_TOKEN = os.getenv('API_ZAYAVKI_TOKEN') or "ВСТАВЬТЕ_ТОКЕН_СЮДА"

if BOT_TOKEN == "ВСТАВЬТЕ_ТОКЕН_СЮДА":
    print("❌ Пожалуйста, вставьте токен бота в переменную BOT_TOKEN")
    exit(1)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Команда /start"""
    chat_info = (
        f"🤖 <b>Chat ID Bot</b>\n\n"
        f"👤 <b>Ваши данные:</b>\n"
        f"🆔 <b>User ID:</b> <code>{message.from_user.id}</code>\n"
        f"👤 <b>Имя:</b> {message.from_user.first_name or 'Не указано'}\n"
        f"📱 <b>Username:</b> @{message.from_user.username or 'Не указан'}\n\n"
        f"💬 <b>Данные чата:</b>\n"
        f"🆔 <b>Chat ID:</b> <code>{message.chat.id}</code>\n"
        f"📋 <b>Тип чата:</b> {message.chat.type}\n"
    )
    
    if message.chat.type in ['group', 'supergroup']:
        chat_info += f"🏷️ <b>Название группы:</b> {message.chat.title or 'Не указано'}\n"
        chat_info += f"👥 <b>Участников:</b> {message.chat.member_count or 'Неизвестно'}\n"
    
    chat_info += (
        f"\n💡 <b>Инструкция:</b>\n"
        f"1. Добавьте этого бота в вашу группу\n"
        f"2. Отправьте /chatid в группе\n"
        f"3. Скопируйте Chat ID для .env файла\n\n"
        f"📋 <b>Команды:</b>\n"
        f"/chatid - Получить Chat ID\n"
        f"/info - Подробная информация\n"
        f"/help - Справка"
    )
    
    await message.answer(chat_info, parse_mode='HTML')

@dp.message(Command("chatid"))
async def chatid_command(message: types.Message):
    """Команда для получения Chat ID"""
    chat_type_emoji = {
        'private': '👤',
        'group': '👥',
        'supergroup': '👥',
        'channel': '📢'
    }
    
    emoji = chat_type_emoji.get(message.chat.type, '💬')
    
    response = (
        f"{emoji} <b>Chat ID Information</b>\n\n"
        f"🆔 <b>Chat ID:</b> <code>{message.chat.id}</code>\n"
        f"📋 <b>Тип:</b> {message.chat.type}\n"
    )
    
    if message.chat.type in ['group', 'supergroup']:
        response += f"🏷️ <b>Название:</b> {message.chat.title or 'Без названия'}\n"
        response += f"\n✅ <b>Для .env файла используйте:</b>\n"
        response += f"<code>TELEGRAM_NOTIFICATIONS_CHAT_ID={message.chat.id}</code>\n"
    elif message.chat.type == 'private':
        response += f"👤 <b>Имя:</b> {message.from_user.first_name or 'Не указано'}\n"
        response += f"📱 <b>Username:</b> @{message.from_user.username or 'Не указан'}\n"
        response += f"\n✅ <b>Для .env файла используйте:</b>\n"
        response += f"<code>TELEGRAM_ADMIN_CHAT_IDS={message.from_user.id}</code>\n"
    
    response += f"\n📋 <b>Скопируйте Chat ID выше ⬆️</b>"
    
    await message.answer(response, parse_mode='HTML')

@dp.message(Command("info"))
async def info_command(message: types.Message):
    """Подробная информация о чате"""
    info = (
        f"📊 <b>Полная информация о чате</b>\n\n"
        f"🆔 <b>Chat ID:</b> <code>{message.chat.id}</code>\n"
        f"📋 <b>Тип чата:</b> {message.chat.type}\n"
    )
    
    # Информация о чате
    if message.chat.title:
        info += f"🏷️ <b>Название:</b> {message.chat.title}\n"
    if message.chat.description:
        info += f"📝 <b>Описание:</b> {message.chat.description[:100]}...\n"
    if message.chat.username:
        info += f"🔗 <b>Username:</b> @{message.chat.username}\n"
    
    # Информация о пользователе
    info += f"\n👤 <b>Отправитель:</b>\n"
    info += f"🆔 <b>User ID:</b> <code>{message.from_user.id}</code>\n"
    info += f"👤 <b>Имя:</b> {message.from_user.first_name or 'Не указано'}\n"
    if message.from_user.last_name:
        info += f"👤 <b>Фамилия:</b> {message.from_user.last_name}\n"
    if message.from_user.username:
        info += f"📱 <b>Username:</b> @{message.from_user.username}\n"
    
    # Информация о сообщении
    info += f"\n📨 <b>Сообщение:</b>\n"
    info += f"🆔 <b>Message ID:</b> {message.message_id}\n"
    info += f"📅 <b>Дата:</b> {message.date.strftime('%d.%m.%Y %H:%M:%S')}\n"
    
    await message.answer(info, parse_mode='HTML')

@dp.message(Command("help"))
async def help_command(message: types.Message):
    """Справка по командам"""
    help_text = (
        f"❓ <b>Справка по Chat ID Bot</b>\n\n"
        f"🎯 <b>Назначение:</b>\n"
        f"Этот бот помогает получить Chat ID для настройки уведомлений в China Together.\n\n"
        f"📋 <b>Команды:</b>\n"
        f"/start - Приветствие и основная информация\n"
        f"/chatid - Получить Chat ID текущего чата\n"
        f"/info - Подробная информация о чате\n"
        f"/help - Эта справка\n\n"
        f"📱 <b>Как использовать:</b>\n"
        f"1. <b>Для личных уведомлений:</b>\n"
        f"   • Отправьте /chatid боту в личных сообщениях\n"
        f"   • Скопируйте ваш User ID\n\n"
        f"2. <b>Для групповых уведомлений:</b>\n"
        f"   • Добавьте бота в группу\n"
        f"   • Отправьте /chatid в группе\n"
        f"   • Скопируйте Chat ID группы\n\n"
        f"⚙️ <b>Настройка .env:</b>\n"
        f"<code>API_ZAYAVKI_TOKEN=токен_бота</code>\n"
        f"<code>TELEGRAM_NOTIFICATIONS_CHAT_ID=ID_группы</code>\n"
        f"<code>TELEGRAM_ADMIN_CHAT_IDS=ваш_ID</code>\n\n"
        f"💡 <b>Совет:</b> Chat ID группы начинается с -100"
    )
    
    await message.answer(help_text, parse_mode='HTML')

@dp.message()
async def any_message(message: types.Message):
    """Обработка любого сообщения"""
    response = (
        f"📨 <b>Сообщение получено!</b>\n\n"
        f"🆔 <b>Chat ID:</b> <code>{message.chat.id}</code>\n"
        f"👤 <b>От:</b> {message.from_user.first_name or 'Аноним'}\n"
        f"📋 <b>Тип чата:</b> {message.chat.type}\n\n"
        f"💡 Используйте /chatid для получения Chat ID"
    )
    
    await message.answer(response, parse_mode='HTML')

async def main():
    """Главная функция"""
    try:
        # Получаем информацию о боте
        bot_info = await bot.get_me()
        print(f"🤖 Бот запущен: @{bot_info.username}")
        print(f"🆔 Bot ID: {bot_info.id}")
        print(f"📋 Токен: {BOT_TOKEN[:10]}...")
        print(f"✅ Готов к работе!")
        print(f"\n💡 Добавьте бота в группу и отправьте /chatid")
        
        # Запускаем polling
        await dp.start_polling(bot)
        
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    asyncio.run(main())
