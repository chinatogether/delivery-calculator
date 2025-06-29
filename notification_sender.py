import asyncio
import logging
from aiogram import Bot
import threading
import queue
import time
from dotenv import load_dotenv
import os
from datetime import datetime
import pytz

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def get_moscow_time():
    return datetime.now(MOSCOW_TZ)

class NotificationSender:
    """Простой отправитель уведомлений без конфликтов"""
    
    def __init__(self):
        self.token = os.getenv('API_ZAYAVKI_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_NOTIFICATIONS_CHAT_ID')
        self.admin_chat_ids = [id.strip() for id in os.getenv('TELEGRAM_ADMIN_CHAT_IDS', '').split(',') if id.strip()]
        
        if not self.token:
            logger.error("API_ZAYAVKI_TOKEN не найден")
            return
        
        self.bot = Bot(token=self.token)
        logger.info(f"NotificationSender создан. Chat ID: {self.chat_id}")
    
    def send_order_notification(self, order_data):
        """Отправка уведомления о заявке"""
        try:
            moscow_time = get_moscow_time()
            
            # Форматируем сообщение
            message = (
                f"🆕 <b>НОВАЯ ЗАЯВКА НА ДОСТАВКУ</b>\n\n"
                f"📅 <b>Дата:</b> {moscow_time.strftime('%d.%m.%Y %H:%M')} (МСК)\n"
                f"🆔 <b>ID заявки:</b> #{order_data.get('request_id', 'N/A')}\n"
                f"👤 <b>Пользователь:</b> {order_data.get('telegram_contact', 'N/A')}\n"
                f"💰 <b>Сумма заказа:</b> {order_data.get('order_amount', 'Не указано')}\n"
            )
            
            # Дополнительная информация
            if order_data.get('supplier_link'):
                message += f"🔗 <b>Ссылка на товар:</b>\n{order_data['supplier_link'][:100]}{'...' if len(order_data['supplier_link']) > 100 else ''}\n\n"
            
            if order_data.get('promo_code'):
                message += f"🎫 <b>Промокод:</b> {order_data['promo_code']}\n\n"
            
            if order_data.get('additional_notes'):
                notes = order_data['additional_notes'][:200]
                if len(order_data['additional_notes']) > 200:
                    notes += "..."
                message += f"💬 <b>Комментарии:</b>\n{notes}\n\n"
            
            if order_data.get('calculation_id'):
                message += f"📊 <b>Связанный расчет:</b> #{order_data['calculation_id']}\n\n"
            
            # Отправляем через новый event loop
            def send_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._send_messages(message))
                    logger.info(f"Уведомление о заявке #{order_data.get('request_id')} отправлено")
                    return True
                except Exception as e:
                    logger.error(f"Ошибка отправки: {e}")
                    return False
                finally:
                    loop.close()
            
            # Запускаем в отдельном потоке
            thread = threading.Thread(target=send_async, daemon=True)
            thread.start()
            thread.join(timeout=10)  # Ждем максимум 10 секунд
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка подготовки уведомления: {e}")
            return False
    
    async def _send_messages(self, message):
        """Асинхронная отправка сообщений"""
        # Отправляем в группу
        if self.chat_id:
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                logger.info(f"Сообщение отправлено в группу {self.chat_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки в группу: {e}")
        
        # Отправляем админам
        for admin_id in self.admin_chat_ids:
            if admin_id:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                    logger.info(f"Сообщение отправлено админу {admin_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки админу {admin_id}: {e}")

# Глобальный экземпляр
notification_sender = None

def get_notification_sender():
    global notification_sender
    if notification_sender is None:
        notification_sender = NotificationSender()
    return notification_sender

def send_order_notification(order_data):
    """Функция для отправки уведомления о заявке"""
    try:
        sender = get_notification_sender()
        return sender.send_order_notification(order_data)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")
        return False
