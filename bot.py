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
WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://china-together.ru')

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
    web_app_url = f"{WEB_APP_URL}/?telegram_id={user_id}&username={username}"
    order_app_url = f"{WEB_APP_URL}/order?telegram_id={user_id}&username={username}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📊 Рассчитать доставку", 
            web_app=WebAppInfo(url=web_app_url)
        )],
        [InlineKeyboardButton(
            text="🚚 Заказать доставку", 
            web_app=WebAppInfo(url=order_app_url)
        )],
        [InlineKeyboardButton(
            text="📂 Мои заявки", 
            callback_data="my_requests"
        )],
        [InlineKeyboardButton(
            text="📱 Больше опций", 
            callback_data="more_options"
        )]
    ])
    return keyboard

def get_more_options_menu(user_id, username):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💬 Связаться с менеджером", 
            callback_data="contact_manager"
        )],
        [InlineKeyboardButton(
            text="📋 История расчетов", 
            callback_data="calculation_history"
        )],
        [InlineKeyboardButton(
            text="📞 Поддержка", 
            callback_data="support"
        )],
        [InlineKeyboardButton(
            text="❓ Помощь", 
            callback_data="help"
        )],
        [InlineKeyboardButton(
            text="🔙 Назад", 
            callback_data="back_to_main"
        )]
    ])
    return keyboard

# Функция для умных ответов ИИ
def get_smart_response(message_text):
    text = message_text.lower()
    
    # Приветствия
    if any(word in text for word in ['привет', 'здравствуй', 'добро пожаловать', 'hi', 'hello']):
        return "👋 Привет! Я умный помощник China Together - ваш надежный партнер для доставки из Китая! Помогу рассчитать стоимость, оформить заказ и ответить на любые вопросы. Что вас интересует?"
    
    # Вопросы о доставке и расчетах
    elif any(word in text for word in ['доставка', 'расчет', 'стоимость', 'цена', 'тариф', 'калькулятор']):
        return ("📊 <b>Расчет стоимости доставки:</b>\n\n"
                "Для точного расчета нажмите '📊 Рассчитать доставку'. Вам нужно указать:\n"
                "• 📦 Категорию товара (обычные, текстиль, одежда, обувь)\n"
                "• ⚖️ Вес и размеры каждой коробки\n"
                "• 💰 Стоимость товара\n"
                "• 📦 Количество коробок\n\n"
                "У нас 3 варианта упаковки: мешок, картонные уголки, деревянный каркас.\n"
                "2 варианта доставки: быстрая (5-7 дней) и обычная (10-14 дней).")
    
    # Благодарности
    elif any(word in text for word in ['спасибо', 'благодар', 'thanks', 'отлично', 'хорошо']):
        return "😊 Пожалуйста! Рады помочь! China Together всегда к вашим услугам. Если есть еще вопросы - обращайтесь. Удачных покупок в Китае! 🇨🇳"
    
    # Общие вопросы
    else:
        return ("🤔 <b>Я готов помочь!</b>\n\n"
                "🎯 <b>Мои возможности:</b>\n"
                "📊 Расчет стоимости доставки\n"
                "🚚 Оформление заказов и выкуп товаров\n"
                "📂 Отслеживание статуса заказов\n"
                "💬 Связь с менеджерами\n"
                "❓ Ответы на вопросы о доставке\n\n"
                "Выберите нужную опцию в меню или задайте конкретный вопрос!")

# Команда /start
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    first_name = message.from_user.first_name or ""
    
    save_user_action(user_id, "start_command", {
        "username": username,
        "first_name": first_name
    })
    
    keyboard = get_main_keyboard(user_id, username)
    
    await message.reply(
        f"🚀 <b>Добро пожаловать, {first_name}!</b>\n\n"
        "Я умный помощник China Together - помогу рассчитать доставку из Китая и оформить заказ!\n\n"
        "🎯 <b>Что я умею:</b>\n"
        "• 📊 Точный расчет стоимости доставки\n"
        "• 🚚 Оформление заявок на выкуп товаров\n"
        "• 📂 Отслеживание статуса заказов\n"
        "• 💬 Ответы на ваши вопросы\n"
        "• 👨‍💼 Связь с менеджерами\n\n"
        "💡 <b>Просто напишите мне сообщение или выберите действие:</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# Обработка текстовых сообщений
@dp.message(F.text)
async def handle_text_message(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    text = message.text
    
    save_user_action(user_id, "text_message", {"text": text})
    
    smart_response = get_smart_response(text)
    keyboard = get_main_keyboard(user_id, username)
    
    # Если пользователь спрашивает о менеджере
    if any(word in text.lower() for word in ['менеджер', 'поддержка', 'помощь']):
        keyboard = get_more_options_menu(user_id, username)
    
    await message.reply(
        smart_response,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# Обработка данных от веб-приложения
@dp.message(F.web_app_data)
async def handle_web_app_data(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
        user_id = message.from_user.id
        username = message.from_user.username or f"user_{user_id}"
        action = data.get('action', '')
        
        save_user_action(user_id, f"webapp_{action}", data)
        
        if action == 'calculation_completed':
            await handle_calculation_completed(message, data, user_id, username)
        elif action == 'purchase_request_submitted':
            await handle_purchase_request_submitted(message, data, user_id, username)
        else:
            await message.reply("✅ Данные получены и обработаны!")
            
    except Exception as e:
        logger.error(f"Ошибка обработки данных веб-приложения: {e}")
        await message.reply("❌ Произошла ошибка при обработке данных.")

# Обработка завершенного расчета
async def handle_calculation_completed(message, data, user_id, username):
    await message.reply(
        "✅ <b>Расчет успешно выполнен!</b>\n\n"
        f"📊 Категория: {data.get('category', 'Не указано')}\n"
        f"⚖️ Общий вес: {data.get('totalWeight', 0)} кг\n"
        f"💰 Стоимость товара: ${data.get('productCost', 0)}\n\n"
        "Что хотите сделать дальше?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🚚 Заказать доставку", 
                web_app=WebAppInfo(url=f"{WEB_APP_URL}/order?telegram_id={user_id}&username={username}")
            )],
            [InlineKeyboardButton(text="🔄 Новый расчет", callback_data="new_calculation")]
        ]),
        parse_mode="HTML"
    )

# Обработка отправленной заявки
async def handle_purchase_request_submitted(message, data, user_id, username):
    await message.reply(
        "✅ <b>Заявка успешно отправлена!</b>\n\n"
        f"💰 Сумма заказа: {data.get('order_amount', '')}\n"
        f"📱 Telegram: {data.get('telegram_contact', '')}\n\n"
        "🕐 <b>Менеджер свяжется с вами в рабочее время:</b>\n"
        "ПН–ПТ с 10:00 до 18:00 по московскому времени",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 Мои заявки", callback_data="my_requests")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ]),
        parse_mode="HTML"
    )

# Обработка callback-запросов
@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or f"user_{user_id}"
    
    # Больше опций
    if callback.data == "more_options":
        keyboard = get_more_options_menu(user_id, username)
        await callback.message.edit_text(
            "📱 <b>Дополнительные опции:</b>\n\n"
            "💬 <b>Связаться с менеджером</b> - прямая связь с нашим специалистом\n"
            "📋 <b>История расчетов</b> - ваши предыдущие расчеты\n"
            "📞 <b>Поддержка</b> - контакты и рабочее время\n"
            "❓ <b>Помощь</b> - подробная инструкция\n\n"
            "Выберите нужную опцию:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        save_user_action(user_id, "more_options_opened")
    
    # Назад к главному меню
    elif callback.data == "back_to_main":
        keyboard = get_main_keyboard(user_id, username)
        await callback.message.edit_text(
            "🏠 <b>Главное меню</b>\n\n"
            "Выберите действие или просто напишите мне сообщение!",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        save_user_action(user_id, "back_to_main")
    
    # Связь с менеджером
    elif callback.data == "contact_manager":
        manager_text = (
            "👨‍💼 <b>Связь с менеджером</b>\n\n"
            "Наши специалисты готовы помочь вам:\n\n"
            "🎯 <b>Главный менеджер:</b> @manager_username\n"
            "💬 <b>Общий чат поддержки:</b> @china_together_support\n"
            "📧 <b>Email:</b> manager@china-together.com\n\n"
            "🕐 <b>Рабочее время:</b>\n"
            "ПН–ПТ с 10:00 до 18:00 (МСК)\n"
            "🇨🇳 В Китае: 15:00 до 23:00\n\n"
            "⚡ <b>Для быстрой связи напишите:</b> @manager_username"
        )
        await callback.message.answer(manager_text, parse_mode="HTML")
        save_user_action(user_id, "manager_contact_viewed")
    
    # Мои заявки
    elif callback.data == "my_requests":
        requests = get_user_purchase_requests(user_id)
        if requests:
            requests_text = "<b>📂 Ваши заявки на выкуп:</b>\n\n"
            for i, req in enumerate(requests[:5], 1):
                status_emoji = {
                    'new': '🆕', 'in_review': '👀', 'approved': '✅',
                    'rejected': '❌', 'completed': '🎉'
                }.get(req['status'], '❓')
                
                requests_text += (
                    f"{i}. {status_emoji} {req['created_at'][:16]}\n"
                    f"   💰 Сумма: {req['order_amount']}\n"
                    f"   📧 Email: {req['email']}\n\n"
                )
            await callback.message.answer(requests_text, parse_mode="HTML")
        else:
            await callback.message.answer(
                "📭 У вас пока нет заявок на выкуп.\n\n"
                "Хотите оформить заявку?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🚚 Заказать доставку", 
                        web_app=WebAppInfo(url=f"{WEB_APP_URL}/order?telegram_id={user_id}&username={username}")
                    )]
                ])
            )
        save_user_action(user_id, "view_requests")
    
    # Поддержка
    elif callback.data == "support":
        support_text = (
            "📞 <b>Поддержка China Together</b>\n\n"
            "Наши менеджеры готовы помочь вам:\n\n"
            "📞 <b>Менеджер:</b> @manager_username\n"
            "💬 <b>Группа поддержки:</b> @china_together_support\n"
            "📧 <b>Email:</b> support@china-together.com\n\n"
            "🕐 <b>Время работы:</b>\n"
            "ПН–ПТ с 10:00 до 18:00 (МСК)\n\n"
            "⚡ <b>Быстрая связь:</b> напишите @manager_username"
        )
        await callback.message.answer(support_text, parse_mode="HTML")
        save_user_action(user_id, "support_contacted")
    
    # Помощь
    elif callback.data == "help":
        help_text = (
            "<b>❓ Как пользоваться сервисом:</b>\n\n"
            "<b>📊 Расчет доставки:</b>\n"
            "1️⃣ Нажмите «Рассчитать доставку»\n"
            "2️⃣ Заполните все поля формы\n"
            "3️⃣ Получите детальный расчет\n\n"
            "<b>🚚 Заказ доставки:</b>\n"
            "1️⃣ Нажмите «Заказать доставку»\n"
            "2️⃣ Заполните заявку\n"
            "3️⃣ Менеджер свяжется с вами\n\n"
            "<b>📞 Поддержка:</b> @manager_username"
        )
        await callback.message.answer(help_text, parse_mode="HTML")
        save_user_action(user_id, "view_help")
    
    # Новый расчет
    elif callback.data == "new_calculation":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📊 Открыть калькулятор", 
                web_app=WebAppInfo(url=f"{WEB_APP_URL}/?telegram_id={user_id}&username={username}")
            )]
        ])
        await callback.message.answer(
            "🔄 Начните новый расчет доставки:",
            reply_markup=keyboard
        )
        save_user_action(user_id, "new_calculation")
    
    await callback.answer()

# Функция получения заявок пользователя на выкуп
def get_user_purchase_requests(telegram_id):
    conn = connect_to_db()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pr.*, u.telegram_id
            FROM delivery_test.purchase_requests pr
            JOIN delivery_test.telegram_users u ON pr.telegram_user_id = u.id
            WHERE u.telegram_id = %s
            ORDER BY pr.created_at DESC
            LIMIT 10
        """, (str(telegram_id),))
        
        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            record['created_at'] = record['created_at'].strftime('%Y-%m-%d %H:%M')
            results.append(record)
        
        cursor.close()
        return results
    except Exception as e:
        logger.error(f"Ошибка получения заявок: {e}")
        return []
    finally:
        conn.close()

# Удаление webhook
async def delete_webhook():
    await bot.delete_webhook()

# Запуск бота
async def main():
    await delete_webhook()
    logger.info("🤖 China Together Bot запущен!")
    logger.info(f"🌐 Web App URL: {WEB_APP_URL}")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
