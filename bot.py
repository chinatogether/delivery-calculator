import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, CallbackQuery
from aiogram.types.web_app_data import WebAppData
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import os
import json
import logging
import psycopg2
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
API_TOKEN = os.getenv('API_TOKEN')
WEB_APP_URL = os.getenv('WEB_APP_URL', 'http://84.201.187.187:8061')

# Инициализация бота и хранилища состояний
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Подключение к базе данных
def connect_to_db():
    try:
        return psycopg2.connect(
            dbname="delivery_db",
            user="chinatogether",
            password="O99ri1@",
            host="localhost",
            port="5432"
        )
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return None

# Функция для сохранения действий пользователя
def save_user_action(telegram_id, action, details=None):
    conn = connect_to_db()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO delivery_test.user_actions (telegram_user_id, action, details, created_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """, (telegram_id, action, json.dumps(details) if details else None))
        conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"Ошибка сохранения действия: {e}")
    finally:
        conn.close()

# Создание главного меню
def get_main_keyboard(user_id, username):
    # Передаем параметры пользователя в URL веб-приложения
    web_app_url = f"{WEB_APP_URL}/?telegram_id={user_id}&username={username}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📊 Открыть калькулятор", 
            web_app=WebAppInfo(url=web_app_url)
        )],
        [InlineKeyboardButton(
            text="📂 История расчетов", 
            callback_data="history"
        )],
        [InlineKeyboardButton(
            text="❓ Помощь", 
            callback_data="help"
        )]
    ])
    return keyboard

# Команда /start
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    # Сохраняем действие пользователя
    save_user_action(user_id, "start_command", {"username": username})
    
    keyboard = get_main_keyboard(user_id, username)
    
    await message.reply(
        "🚀 <b>Добро пожаловать в China Together!</b>\n\n"
        "📦 Рассчитайте стоимость доставки из Китая за несколько секунд.\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# Обработка данных от веб-приложения
@dp.message(F.web_app_data)
async def handle_web_app_data(message: types.Message):
    """Обработка данных, полученных от веб-приложения"""
    try:
        # Парсим данные от веб-приложения
        data = json.loads(message.web_app_data.data)
        user_id = message.from_user.id
        
        # Сохраняем действие
        save_user_action(user_id, "calculation_completed", data)
        
        # Отправляем подтверждение пользователю
        await message.reply(
            "✅ <b>Расчет успешно выполнен!</b>\n\n"
            f"📊 Категория: {data.get('category', 'Не указано')}\n"
            f"⚖️ Общий вес: {data.get('totalWeight', 0)} кг\n"
            f"💰 Стоимость товара: ${data.get('productCost', 0)}\n\n"
            "Что вы хотите сделать дальше?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💾 Сохранить в CSV", callback_data=f"save_csv:{message.web_app_data.data}")],
                [InlineKeyboardButton(text="🔄 Новый расчет", callback_data="new_calculation")],
                [InlineKeyboardButton(text="📋 История расчетов", callback_data="history")]
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка обработки данных веб-приложения: {e}")
        await message.reply("❌ Произошла ошибка при обработке данных.")

# Обработка callback-запросов
@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or f"user_{user_id}"
    
    # Сохранение в CSV
    if callback.data.startswith("save_csv:"):
        try:
            # Извлекаем данные
            data_json = callback.data.replace("save_csv:", "")
            data = json.loads(data_json)
            
            # Генерируем CSV
            csv_content = generate_csv(data)
            
            # Отправляем файл
            from io import BytesIO
            csv_file = BytesIO(csv_content.encode('utf-8'))
            csv_file.name = f"calculation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            await callback.message.answer_document(
                document=types.BufferedInputFile(
                    file=csv_file.getvalue(),
                    filename=csv_file.name
                ),
                caption="📄 Ваш расчет сохранен в CSV файле."
            )
            
            # Сохраняем действие
            save_user_action(user_id, "csv_saved", {"filename": csv_file.name})
            
        except Exception as e:
            logger.error(f"Ошибка сохранения CSV: {e}")
            await callback.answer("❌ Ошибка при сохранении файла", show_alert=True)
    
    # История расчетов
    elif callback.data == "history":
        history = get_user_history(user_id)
        if history:
            history_text = "<b>📋 История ваших расчетов:</b>\n\n"
            for i, calc in enumerate(history[:10], 1):  # Показываем последние 10
                history_text += (
                    f"{i}. {calc['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
                    f"   Категория: {calc['category']}\n"
                    f"   Вес: {calc['total_weight']} кг\n"
                    f"   Мешок (быстро): ${calc['bag_total_fast']}\n\n"
                )
            await callback.message.answer(history_text, parse_mode="HTML")
        else:
            await callback.message.answer("📭 У вас пока нет сохраненных расчетов.")
        
        save_user_action(user_id, "view_history")
    
    # Новый расчет
    elif callback.data == "new_calculation":
        keyboard = get_main_keyboard(user_id, username)
        await callback.message.answer(
            "🔄 Начните новый расчет:",
            reply_markup=keyboard
        )
        save_user_action(user_id, "new_calculation")
    
    # Помощь
    elif callback.data == "help":
        help_text = (
            "<b>❓ Как пользоваться калькулятором:</b>\n\n"
            "1️⃣ Нажмите «Открыть калькулятор»\n"
            "2️⃣ Заполните все поля формы\n"
            "3️⃣ Нажмите «Рассчитать»\n"
            "4️⃣ Получите детальный расчет\n"
            "5️⃣ Сохраните результат в CSV\n\n"
            "<b>📞 Поддержка:</b> @support_username"
        )
        await callback.message.answer(help_text, parse_mode="HTML")
        save_user_action(user_id, "view_help")
    
    await callback.answer()

# Функция генерации CSV
def generate_csv(data):
    """Генерирует CSV файл из данных расчета"""
    csv_lines = [
        "Параметр,Значение",
        f"Категория,{data.get('category', '')}",
        f"Общий вес (кг),{data.get('totalWeight', '')}",
        f"Плотность (кг/м³),{data.get('density', '')}",
        f"Стоимость товара ($),{data.get('productCost', '')}",
        f"Страховка (%),{data.get('insuranceRate', '')}",
        f"Сумма страховки ($),{data.get('insuranceAmount', '')}",
        f"Объем (м³),{data.get('volume', '')}",
        f"Количество коробок,{data.get('boxCount', '')}",
        "",
        "Тип упаковки,Быстрая доставка ($),Обычная доставка ($)",
        f"Мешок,{data.get('bagTotalFast', '')},{data.get('bagTotalRegular', '')}",
        f"Картонные уголки,{data.get('cornersTotalFast', '')},{data.get('cornersTotalRegular', '')}",
        f"Деревянный каркас,{data.get('frameTotalFast', '')},{data.get('frameTotalRegular', '')}"
    ]
    
    return "\n".join(csv_lines)

# Функция получения истории пользователя
def get_user_history(telegram_id):
    """Получает историю расчетов пользователя из БД"""
    conn = connect_to_db()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, u.telegram_id
            FROM delivery_test.user_calculations c
            JOIN delivery_test.telegram_users u ON c.telegram_user_id = u.id
            WHERE u.telegram_id = %s
            ORDER BY c.created_at DESC
            LIMIT 10
        """, (str(telegram_id),))
        
        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        cursor.close()
        return results
    except Exception as e:
        logger.error(f"Ошибка получения истории: {e}")
        return []
    finally:
        conn.close()

# Удаление webhook
async def delete_webhook():
    await bot.delete_webhook()

# Запуск бота
async def main():
    # Удаляем webhook, если он активен
    await delete_webhook()
    
    logger.info("Бот запущен!")
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
