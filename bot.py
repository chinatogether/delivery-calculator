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
    # Передаем параметры пользователя в URL веб-приложения
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
    first_name = message.from_user.first_name or ""
    
    # Сохраняем действие пользователя
    save_user_action(user_id, "start_command", {
        "username": username,
        "first_name": first_name
    })
    
    keyboard = get_main_keyboard(user_id, username)
    
    await message.reply(
        "🚀 <b>Добро пожаловать в China Together!</b>\n\n"
        "📦 Рассчитайте стоимость доставки из Китая и оформите заказ за несколько секунд.\n\n"
        "🎯 <b>Что вы можете сделать:</b>\n"
        "• 📊 Рассчитать точную стоимость доставки\n"
        "• 🚚 Оформить заявку на выкуп и доставку\n"
        "• 📂 Посмотреть свои заявки\n"
        "• ❓ Получить помощь\n\n"
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
        username = message.from_user.username or f"user_{user_id}"
        action = data.get('action', '')
        
        # Сохраняем действие
        save_user_action(user_id, f"webapp_{action}", data)
        
        # Обрабатываем разные типы действий
        if action == 'calculation_completed':
            await handle_calculation_completed(message, data, user_id, username)
        elif action == 'purchase_request_submitted':
            await handle_purchase_request_submitted(message, data, user_id, username)
        elif action == 'delivery_ordered':
            await handle_delivery_ordered(message, data, user_id, username)
        elif action == 'share_calculation':
            await handle_share_calculation(message, data, user_id, username)
        else:
            await message.reply("✅ Данные получены и обработаны!")
            
    except Exception as e:
        logger.error(f"Ошибка обработки данных веб-приложения: {e}")
        await message.reply("❌ Произошла ошибка при обработке данных.")

# Обработка завершенного расчета
async def handle_calculation_completed(message, data, user_id, username):
    """Обработка завершенного расчета"""
    await message.reply(
        "✅ <b>Расчет успешно выполнен!</b>\n\n"
        f"📊 Категория: {data.get('category', 'Не указано')}\n"
        f"⚖️ Общий вес: {data.get('totalWeight', 0)} кг\n"
        f"💰 Стоимость товара: ${data.get('productCost', 0)}\n\n"
        f"💸 <b>Лучшие варианты доставки:</b>\n"
        f"📦 Мешок: ${data.get('bagTotalRegular', 0):.2f} / ${data.get('bagTotalFast', 0):.2f}\n"
        f"📐 Уголки: ${data.get('cornersTotalRegular', 0):.2f} / ${data.get('cornersTotalFast', 0):.2f}\n"
        f"🪵 Каркас: ${data.get('frameTotalRegular', 0):.2f} / ${data.get('frameTotalFast', 0):.2f}\n\n"
        "Что вы хотите сделать дальше?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🚚 Заказать доставку", 
                web_app=WebAppInfo(url=f"{WEB_APP_URL}/order?telegram_id={user_id}&username={username}")
            )],
            [InlineKeyboardButton(text="🔄 Новый расчет", callback_data="new_calculation")],
            [InlineKeyboardButton(text="📤 Поделиться", callback_data="share_last_calculation")]
        ]),
        parse_mode="HTML"
    )

# Обработка отправленной заявки на выкуп
async def handle_purchase_request_submitted(message, data, user_id, username):
    """Обработка отправленной заявки на выкуп"""
    await message.reply(
        "✅ <b>Заявка успешно отправлена!</b>\n\n"
        f"📧 Email: {data.get('email', '')}\n"
        f"💰 Сумма заказа: {data.get('order_amount', '')}\n"
        f"📱 Telegram: {data.get('telegram_contact', '')}\n\n"
        "🕐 <b>Менеджер свяжется с вами в рабочее время:</b>\n"
        "ПН–ПТ с 10:00 до 18:00 по московскому времени\n\n"
        "📞 Если у вас срочные вопросы, можете написать нашему менеджеру: @manager_username",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 Мои заявки", callback_data="my_requests")],
            [InlineKeyboardButton(text="🔄 Новая заявка", callback_data="new_order")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]),
        parse_mode="HTML"
    )

# Обработка заказа доставки
async def handle_delivery_ordered(message, data, user_id, username):
    """Обработка заказа доставки"""
    package_names = {
        'bag': '📦 Мешок',
        'corners': '📐 Картонные уголки', 
        'frame': '🪵 Деревянный каркас'
    }
    delivery_names = {
        'fast': '🚀 Быстрая (5-7 дней)',
        'regular': '🚢 Обычная (10-14 дней)'
    }
    
    package_name = package_names.get(data.get('package_type', ''), 'Не указано')
    delivery_name = delivery_names.get(data.get('delivery_type', ''), 'Не указано')
    
    await message.reply(
        "✅ <b>Заказ доставки оформлен!</b>\n\n"
        f"📦 Упаковка: {package_name}\n"
        f"🚚 Доставка: {delivery_name}\n"
        f"💰 Стоимость: ${data.get('total_cost', 0):.2f}\n"
        f"⚖️ Вес: {data.get('weight', 0)} кг\n"
        f"📊 Категория: {data.get('category', '')}\n\n"
        "🕐 Менеджер свяжется с вами для подтверждения заказа в рабочее время.\n\n"
        "📞 Вопросы? Пишите: @manager_username",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 Мои заказы", callback_data="my_orders")],
            [InlineKeyboardButton(text="🔄 Новый расчет", callback_data="new_calculation")]
        ]),
        parse_mode="HTML"
    )

# Обработка поделиться расчетом
async def handle_share_calculation(message, data, user_id, username):
    """Обработка функции поделиться расчетом"""
    share_text = data.get('text', '')
    await message.reply(
        f"📤 <b>Поделиться расчетом:</b>\n\n{share_text}",
        parse_mode="HTML"
    )

# Обработка callback-запросов
@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or f"user_{user_id}"
    
    # Мои заявки
    if callback.data == "my_requests":
        requests = get_user_purchase_requests(user_id)
        if requests:
            requests_text = "<b>📂 Ваши заявки на выкуп:</b>\n\n"
            for i, req in enumerate(requests[:5], 1):  # Показываем последние 5
                status_emoji = {
                    'new': '🆕',
                    'in_review': '👀', 
                    'approved': '✅',
                    'rejected': '❌',
                    'completed': '🎉'
                }.get(req['status'], '❓')
                
                requests_text += (
                    f"{i}. {status_emoji} {req['created_at'][:16]}\n"
                    f"   💰 Сумма: {req['order_amount']}\n"
                    f"   📧 Email: {req['email']}\n"
                    f"   📊 Статус: {req['status']}\n\n"
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
    
    # Мои заказы (доставки)
    elif callback.data == "my_orders":
        orders = get_user_delivery_orders(user_id)
        if orders:
            orders_text = "<b>📦 Ваши заказы доставки:</b>\n\n"
            for i, order in enumerate(orders[:5], 1):  # Показываем последние 5
                status_emoji = {
                    'pending': '⏳',
                    'confirmed': '✅',
                    'in_progress': '🚛',
                    'delivered': '🎉',
                    'cancelled': '❌'
                }.get(order['status'], '❓')
                
                orders_text += (
                    f"{i}. {status_emoji} {order['created_at'][:16]}\n"
                    f"   💰 Стоимость: ${order['total_cost']}\n"
                    f"   📦 Упаковка: {order['selected_package_type']}\n"
                    f"   🚚 Доставка: {order['selected_delivery_type']}\n\n"
                )
            await callback.message.answer(orders_text, parse_mode="HTML")
        else:
            await callback.message.answer("📭 У вас пока нет заказов доставки.")
        
        save_user_action(user_id, "view_orders")
    
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
    
    # Новая заявка
    elif callback.data == "new_order":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🚚 Заказать доставку", 
                web_app=WebAppInfo(url=f"{WEB_APP_URL}/order?telegram_id={user_id}&username={username}")
            )]
        ])
        await callback.message.answer(
            "🚚 Оформите новую заявку на доставку:",
            reply_markup=keyboard
        )
        save_user_action(user_id, "new_order")
    
    # Главное меню
    elif callback.data == "main_menu":
        keyboard = get_main_keyboard(user_id, username)
        await callback.message.answer(
            "🏠 <b>Главное меню</b>\n\nВыберите действие:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        save_user_action(user_id, "main_menu")
    
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
            "<b>🕐 График работы:</b>\n"
            "ПН–ПТ с 10:00 до 18:00 (МСК)\n\n"
            "<b>📞 Поддержка:</b> @manager_username\n"
            "<b>💬 Группа:</b> @china_together_group"
        )
        await callback.message.answer(help_text, parse_mode="HTML")
        save_user_action(user_id, "view_help")
    
    await callback.answer()

# Функция получения заявок пользователя на выкуп
def get_user_purchase_requests(telegram_id):
    """Получает заявки пользователя на выкуп из БД"""
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

# Функция получения заказов доставки пользователя
def get_user_delivery_orders(telegram_id):
    """Получает заказы доставки пользователя из БД"""
    conn = connect_to_db()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT do.*, u.telegram_id
            FROM delivery_test.delivery_orders do
            JOIN delivery_test.telegram_users u ON do.telegram_user_id = u.id
            WHERE u.telegram_id = %s
            ORDER BY do.created_at DESC
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
        logger.error(f"Ошибка получения заказов доставки: {e}")
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
    
    logger.info("🤖 China Together Bot запущен!")
    logger.info(f"🌐 Web App URL: {WEB_APP_URL}")
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
