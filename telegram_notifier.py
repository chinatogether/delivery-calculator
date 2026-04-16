import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BotCommand
from dotenv import load_dotenv
import os
import json
from datetime import datetime, timedelta
import pytz
import psycopg2
from decimal import Decimal
from functools import wraps
import threading
import queue
import time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('telegram_notifier.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Настройка московского времени
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def get_moscow_time():
    """Получение текущего времени в московской зоне"""
    return datetime.now(MOSCOW_TZ)

# Конфигурация базы данных
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'delivery_db'),
    'user': os.getenv('DB_USER'), 
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'connect_timeout': int(os.getenv('DB_TIMEOUT', '10'))
}

def connect_to_db():
    """Подключение к базе данных"""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {str(e)}")
        raise

def handle_db_errors(func):
    """Декоратор для обработки ошибок базы данных"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в функции {func.__name__}: {str(e)}")
            return None
    return wrapper

class TelegramNotifier:
    """Класс для отправки уведомлений в Telegram"""
    
    def __init__(self):
        self.token = os.getenv('API_ZAYAVKI_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_NOTIFICATIONS_CHAT_ID')
        self.admin_chat_ids = os.getenv('TELEGRAM_ADMIN_CHAT_IDS', '').split(',')
        
        if not self.token:
            raise ValueError("API_ZAYAVKI_TOKEN не найден в переменных окружения")
        
        if not self.chat_id:
            logger.warning("TELEGRAM_NOTIFICATIONS_CHAT_ID не найден в .env")
        
        self.bot = Bot(token=self.token)
        
        # Создаем очередь для сообщений
        self.message_queue = queue.Queue()
        self.worker_thread = None
        self.running = False
        
        # Запускаем worker thread
        self.start_worker()
        logger.info(f"TelegramNotifier инициализирован. Chat ID: {self.chat_id}")
    
    def start_worker(self):
        """Запуск worker thread для отправки сообщений"""
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.running = True
            self.worker_thread = threading.Thread(target=self._message_worker, daemon=True)
            self.worker_thread.start()
            logger.info("Message worker thread запущен")
    
    def _message_worker(self):
        """Worker thread для обработки очереди сообщений"""
        logger.info("Message worker начал работу")
        
        while self.running:
            try:
                # Получаем сообщение из очереди с таймаутом
                try:
                    message_data = self.message_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Создаем новый event loop для этого треда
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Отправляем сообщение
                    loop.run_until_complete(self._send_message_async(message_data))
                except Exception as e:
                    logger.error(f"Ошибка отправки сообщения: {e}")
                finally:
                    loop.close()
                    self.message_queue.task_done()
                    
            except Exception as e:
                logger.error(f"Ошибка в message worker: {e}")
                time.sleep(1)
        
        logger.info("Message worker завершил работу")
    
    async def _send_message_async(self, message_data):
        """Асинхронная отправка сообщения"""
        try:
            await self.bot.send_message(
                chat_id=message_data['chat_id'],
                text=message_data['text'],
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            logger.info(f"Сообщение отправлено в чат {message_data['chat_id']}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в {message_data['chat_id']}: {e}")
    
    def send_order_notification_sync(self, order_data):
        """Синхронная отправка уведомления о заявке через очередь"""
        try:
            moscow_time = get_moscow_time()
            
            # Форматируем сообщение о новой заявке
            message = (
                f"🆕 <b>НОВАЯ ЗАЯВКА НА ДОСТАВКУ</b>\n\n"
                f"📅 <b>Дата:</b> {moscow_time.strftime('%d.%m.%Y %H:%M')} (МСК)\n"
                f"🆔 <b>ID заявки:</b> #{order_data.get('request_id', 'N/A')}\n"
                f"👤 <b>Пользователь:</b> {order_data.get('telegram_contact', 'N/A')}\n"              
                f"👤 <b>e-mail::</b> {order_data.get('email', 'N/A')}\n"
                f"💰 <b>Сумма заказа:</b> {order_data.get('order_amount', 'Не указано')}\n"
                f"💰 <b>Промокод:</b> {order_data.get('promo_code', 'Не указано')}\n"
            )

            # Добавляем ссылку на товар если есть
            if order_data.get('supplier_link'):
                message += f"🔗 <b>Ссылка на товар:</b>\n{order_data['supplier_link'][:100]}{'...' if len(order_data['supplier_link']) > 100 else ''}\n\n"
            
            # Добавляем промокод если есть
            if order_data.get('promo_code'):
                message += f"🎫 <b>Промокод:</b> {order_data['promo_code']}\n\n"
            
            # Добавляем комментарии если есть
            if order_data.get('additional_notes'):
                notes = order_data['additional_notes'][:200]
                if len(order_data['additional_notes']) > 200:
                    notes += "..."
                message += f"💬 <b>Комментарии:</b>\n{notes}\n\n"
            
            # Добавляем информацию о расчете если есть
            if order_data.get('calculation_id'):
                message += f"📊 <b>Связанный расчет:</b> #{order_data['calculation_id']}\n\n"
            
            
            # Добавляем в очередь для отправки в группу
            if self.chat_id:
                self.message_queue.put({
                    'chat_id': self.chat_id,
                    'text': message
                })
                logger.info(f"Сообщение для группы {self.chat_id} добавлено в очередь")
            
            # Добавляем в очередь для отправки админам
            for admin_id in self.admin_chat_ids:
                if admin_id.strip():
                    self.message_queue.put({
                        'chat_id': admin_id.strip(),
                        'text': message
                    })
                    logger.info(f"Сообщение для админа {admin_id.strip()} добавлено в очередь")
            
            logger.info(f"Уведомление о заявке #{order_data.get('request_id')} добавлено в очередь отправки")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при подготовке уведомления о заявке: {e}")
            return False
    
    async def send_new_order_notification(self, order_data):
        """Асинхронная отправка уведомления о новой заявке"""
        try:
            moscow_time = get_moscow_time()
            
            # Форматируем сообщение о новой заявке
            message = (
                f"🆕 <b>НОВАЯ ЗАЯВКА НА ДОСТАВКУ</b>\n\n"
                f"📅 <b>Дата:</b> {moscow_time.strftime('%d.%m.%Y %H:%M')} (МСК)\n"
                f"🆔 <b>ID заявки:</b> #{order_data.get('request_id', 'N/A')}\n"
                f"👤 <b>Пользователь:</b> {order_data.get('telegram_contact', 'N/A')}\n" 
                f"👤 <b>e-mail::</b> {order_data.get('email', 'N/A')}\n"
                f"💰 <b>Сумма заказа:</b> {order_data.get('order_amount', 'Не указано')}\n"
            )
            
            # Добавляем ссылку на товар если есть
            if order_data.get('supplier_link'):
                message += f"🔗 <b>Ссылка на товар:</b>\n{order_data['supplier_link'][:100]}{'...' if len(order_data['supplier_link']) > 100 else ''}\n\n"
            
            # Добавляем промокод если есть
            if order_data.get('promo_code'):
                message += f"🎫 <b>Промокод:</b> {order_data['promo_code']}\n\n"
            
            # Добавляем комментарии если есть
            if order_data.get('additional_notes'):
                notes = order_data['additional_notes'][:200]
                if len(order_data['additional_notes']) > 200:
                    notes += "..."
                message += f"💬 <b>Комментарии:</b>\n{notes}\n\n"
            
            # Добавляем информацию о расчете если есть
            if order_data.get('calculation_id'):
                message += f"📊 <b>Связанный расчет:</b> #{order_data['calculation_id']}\n\n"
            
            
            # Отправляем в канал/группу
            if self.chat_id:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                logger.info(f"Уведомление о заявке #{order_data.get('request_id')} отправлено в канал")
            
            # Отправляем админам индивидуально
            for admin_id in self.admin_chat_ids:
                if admin_id.strip():
                    try:
                        await self.bot.send_message(
                            chat_id=admin_id.strip(),
                            text=message,
                            parse_mode='HTML',
                            disable_web_page_preview=True
                        )
                    except Exception as e:
                        logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о заявке: {e}")
            return False

    async def send_exchange_rate_update(self, rate_data):
        """Отправка уведомления об обновлении курса"""
        try:
            moscow_time = get_moscow_time()
            
            message = (
                f"💱 <b>ОБНОВЛЕНИЕ КУРСА ВАЛЮТ</b>\n\n"
                f"📅 <b>Дата:</b> {moscow_time.strftime('%d.%m.%Y %H:%M')} (МСК)\n"
                f"💴 <b>CNY/USD:</b> {rate_data['rate']} юаней за 1$\n"
                f"📈 <b>Источник:</b> {rate_data.get('source', 'Manual')}\n\n"
                f"ℹ️ <b>Новый курс применяется ко всем расчетам</b>"
            )
            
            # Отправляем в канал/группу
            if self.chat_id:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode='HTML'
                )
                logger.info(f"Уведомление об обновлении курса отправлено в канал")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о курсе: {e}")
            return False

# Глобальный экземпляр уведомителя
notifier = None

def get_notifier():
    """Получение экземпляра уведомителя"""
    global notifier
    if notifier is None:
        notifier = TelegramNotifier()
    return notifier

# Функции для работы с курсом валют
@handle_db_errors
def save_exchange_rate(rate, source="telegram_bot", notes=None):
    """Сохранение курса валют в БД"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        moscow_time = get_moscow_time()
        cursor.execute("""
            INSERT INTO delivery_test.exchange_rates (currency_pair, rate, recorded_at, source, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, ('CNY/USD', float(rate), moscow_time, source, notes))
        
        rate_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"Курс сохранен в БД: {rate} юаней за 1$ (ID: {rate_id})")
        return rate_id
        
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def get_current_exchange_rate():
    """Получение текущего курса из БД"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT rate, recorded_at, source 
            FROM delivery_test.exchange_rates 
            WHERE currency_pair = 'CNY/USD' 
            ORDER BY recorded_at DESC 
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        if result:
            return {
                'rate': float(result[0]),
                'recorded_at': result[1],
                'source': result[2]
            }
        return None
        
    finally:
        cursor.close()
        conn.close()

# Функции для асинхронных уведомлений
async def send_order_notification_async(order_data):
    """Асинхронная отправка уведомления о заявке"""
    try:
        notifier = get_notifier()
        return await notifier.send_new_order_notification(order_data)
    except Exception as e:
        logger.error(f"Ошибка при асинхронной отправке уведомления о заявке: {e}")
        return False

async def send_rate_notification_async(rate_data):
    """Асинхронная отправка уведомления о курсе"""
    try:
        notifier = get_notifier()
        return await notifier.send_exchange_rate_update(rate_data)
    except Exception as e:
        logger.error(f"Ошибка при асинхронной отправке уведомления о курсе: {e}")
        return False

# Синхронные обертки для использования в Flask
def send_order_notification(order_data):
    """Синхронная отправка уведомления о заявке через очередь"""
    try:
        notifier = get_notifier()
        return notifier.send_order_notification_sync(order_data)
    except Exception as e:
        logger.error(f"Ошибка при синхронной отправке уведомления о заявке: {e}")
        return False

def send_rate_notification(rate_data):
    """Синхронная отправка уведомления о курсе"""
    try:
        # Для курса валют оставляем старый способ, так как он вызывается из async контекста
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send_rate_notification_async(rate_data))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Ошибка при синхронной отправке уведомления о курсе: {e}")
        return False

# Бот для управления курсом валют
class ExchangeRateBot:
    """Бот для управления курсом валют"""
    
    def __init__(self):
        self.token = os.getenv('API_ZAYAVKI_TOKEN')
        self.admin_chat_ids = [id.strip() for id in os.getenv('TELEGRAM_ADMIN_CHAT_IDS', '').split(',') if id.strip()]
        
        if not self.token:
            raise ValueError("API_ZAYAVKI_TOKEN не найден в переменных окружения")
        
        self.bot = Bot(token=self.token)
        self.dp = Dispatcher()
        
        # Регистрируем обработчики
        self.register_handlers()
        logger.info("ExchangeRateBot инициализирован")
    
    def is_admin(self, user_id):
        """Проверка является ли пользователь админом"""
        return str(user_id) in self.admin_chat_ids
    
    def register_handlers(self):
        """Регистрация обработчиков команд"""
        
        @self.dp.message(Command("start"))
        async def start_command(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.reply("❌ У вас нет доступа к этому боту.")
                return
            
            await message.reply(
                "🤖 <b>Бот управления курсом валют China Together</b>\n\n"
                "📋 <b>Доступные команды:</b>\n"
                "/rate - Текущий курс CNY/USD\n"
                "/setrate 7.20 - Установить новый курс\n"
                "/history - История изменений курса\n"
                "/status - Статус системы\n\n"
                "💡 <b>Формат курса:</b> сколько юаней за 1 доллар",
                parse_mode='HTML'
            )
        
        @self.dp.message(Command("rate"))
        async def get_rate_command(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.reply("❌ У вас нет доступа к этому боту.")
                return
            
            current_rate = get_current_exchange_rate()
            if current_rate:
                moscow_time = current_rate['recorded_at'].astimezone(MOSCOW_TZ)
                await message.reply(
                    f"💱 <b>Текущий курс CNY/USD</b>\n\n"
                    f"💴 <b>Курс:</b> {current_rate['rate']} юаней за 1$\n"
                    f"📅 <b>Обновлен:</b> {moscow_time.strftime('%d.%m.%Y %H:%M')} МСК\n"
                    f"📈 <b>Источник:</b> {current_rate['source']}",
                    parse_mode='HTML'
                )
            else:
                await message.reply("❌ Курс не найден в базе данных.")
        
        @self.dp.message(Command("setrate"))
        async def set_rate_command(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.reply("❌ У вас нет доступа к этому боту.")
                return
            
            try:
                # Извлекаем курс из команды
                args = message.text.split()
                if len(args) < 2:
                    await message.reply(
                        "❌ <b>Неверный формат команды</b>\n\n"
                        "📝 <b>Правильный формат:</b>\n"
                        "/setrate 7.20\n\n"
                        "💡 Укажите сколько юаней за 1 доллар",
                        parse_mode='HTML'
                    )
                    return
                
                new_rate = float(args[1])
                
                if new_rate <= 0 or new_rate > 20:
                    await message.reply("❌ Курс должен быть положительным числом от 0 до 20.")
                    return
                
                # Сохраняем курс
                rate_id = save_exchange_rate(
                    rate=new_rate,
                    source=f"telegram_admin_{message.from_user.id}",
                    notes=f"Обновлено администратором {message.from_user.first_name or message.from_user.username}"
                )
                
                if rate_id:
                    # Отправляем уведомление
                    rate_data = {
                        'rate': new_rate,
                        'source': 'Telegram Admin'
                    }
                    await send_rate_notification_async(rate_data)
                    
                    await message.reply(
                        f"✅ <b>Курс успешно обновлен</b>\n\n"
                        f"💴 <b>Новый курс:</b> {new_rate} юаней за 1$\n"
                        f"🆔 <b>ID записи:</b> #{rate_id}\n"
                        f"📅 <b>Время:</b> {get_moscow_time().strftime('%d.%m.%Y %H:%M')} МСК\n\n"
                        f"ℹ️ Уведомление отправлено в канал",
                        parse_mode='HTML'
                    )
                else:
                    await message.reply("❌ Ошибка при сохранении курса в базу данных.")
                
            except ValueError:
                await message.reply("❌ Неверный формат курса. Используйте число (например: 7.20)")
            except Exception as e:
                logger.error(f"Ошибка при установке курса: {e}")
                await message.reply(f"❌ Произошла ошибка: {str(e)}")
        
        @self.dp.message(Command("history"))
        async def history_command(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.reply("❌ У вас нет доступа к этому боту.")
                return
            
            try:
                conn = connect_to_db()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT rate, recorded_at, source
                    FROM delivery_test.exchange_rates 
                    WHERE currency_pair = 'CNY/USD' 
                    ORDER BY recorded_at DESC 
                    LIMIT 10
                """)
                
                results = cursor.fetchall()
                cursor.close()
                conn.close()
                
                if results:
                    history_text = "📊 <b>История курса CNY/USD (последние 10 записей)</b>\n\n"
                    for i, (rate, recorded_at, source) in enumerate(results, 1):
                        moscow_time = recorded_at.astimezone(MOSCOW_TZ)
                        history_text += (
                            f"{i}. <b>{rate}</b> юаней за 1$ "
                            f"({moscow_time.strftime('%d.%m %H:%M')})\n"
                            f"   📈 {source}\n\n"
                        )
                    
                    await message.reply(history_text, parse_mode='HTML')
                else:
                    await message.reply("📭 История курса пуста.")
                
            except Exception as e:
                logger.error(f"Ошибка при получении истории: {e}")
                await message.reply(f"❌ Ошибка при получении истории: {str(e)}")
        
        @self.dp.message(Command("status"))
        async def status_command(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.reply("❌ У вас нет доступа к этому боту.")
                return
            
            try:
                # Проверяем подключение к БД
                conn = connect_to_db()
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.close()
                db_status = "✅ Подключена"
                
                # Получаем текущий курс
                current_rate = get_current_exchange_rate()
                
                # Считаем количество заявок за сегодня
                conn = connect_to_db()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM delivery_test.purchase_requests 
                    WHERE DATE(created_at AT TIME ZONE 'Europe/Moscow') = CURRENT_DATE
                """)
                today_orders = cursor.fetchone()[0]
                cursor.close()
                conn.close()
                
                status_text = (
                    f"🤖 <b>Статус системы China Together</b>\n\n"
                    f"🗄️ <b>База данных:</b> {db_status}\n"
                    f"💱 <b>Курс CNY/USD:</b> {current_rate['rate'] if current_rate else 'Не установлен'}\n"
                    f"📋 <b>Заявок сегодня:</b> {today_orders}\n"
                    f"🕐 <b>Время сервера:</b> {get_moscow_time().strftime('%d.%m.%Y %H:%M')} МСК\n\n"
                    f"✅ Система работает нормально"
                )
                
                await message.reply(status_text, parse_mode='HTML')
                
            except Exception as e:
                logger.error(f"Ошибка при получении статуса: {e}")
                await message.reply(f"❌ Ошибка системы: {str(e)}")
    
    async def start_polling(self):
        """Запуск бота в режиме polling"""
        try:
            # Устанавливаем команды бота
            commands = [
                BotCommand(command="start", description="🚀 Запуск бота"),
                BotCommand(command="rate", description="💱 Текущий курс CNY/USD"),
                BotCommand(command="setrate", description="📝 Установить новый курс"),
                BotCommand(command="history", description="📊 История изменений курса"),
                BotCommand(command="status", description="🔧 Статус системы")
            ]
            await self.bot.set_my_commands(commands)
            
            logger.info("🤖 Exchange Rate Bot запущен!")
            await self.dp.start_polling(self.bot)
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
            raise

# Функция для запуска бота
async def run_exchange_rate_bot():
    """Запуск бота управления курсом валют"""
    bot = ExchangeRateBot()
    await bot.start_polling()

if __name__ == '__main__':
    # Запуск бота управления курсом валют
    asyncio.run(run_exchange_rate_bot())
