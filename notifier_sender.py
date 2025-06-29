import requests
import logging
import threading
from dotenv import load_dotenv
import os
from datetime import datetime
import pytz
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def get_moscow_time():
    return datetime.now(MOSCOW_TZ)

class TelegramHTTPSender:
    """HTTP отправитель уведомлений в Telegram"""
    
    def __init__(self):
        self.token = os.getenv('API_ZAYAVKI_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_NOTIFICATIONS_CHAT_ID')
        self.admin_chat_ids = [id.strip() for id in os.getenv('TELEGRAM_ADMIN_CHAT_IDS', '').split(',') if id.strip()]
        
        if not self.token:
            logger.error("API_ZAYAVKI_TOKEN не найден")
            return
        
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        logger.info(f"TelegramHTTPSender создан. Chat ID: {self.chat_id}")
    
    def send_message_http(self, chat_id, text):
        """Отправка сообщения через HTTP API"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"✅ Сообщение отправлено в чат {chat_id}")
                return True
            else:
                logger.error(f"❌ Ошибка отправки в {chat_id}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ HTTP ошибка отправки в {chat_id}: {e}")
            return False
    
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
            
            # Отправляем в отдельном потоке
            def send_notifications():
                success_count = 0
                
                # Отправляем в группу
                if self.chat_id:
                    if self.send_message_http(self.chat_id, message):
                        success_count += 1
                
                # Отправляем админам
                for admin_id in self.admin_chat_ids:
                    if admin_id:
                        if self.send_message_http(admin_id, message):
                            success_count += 1
                
                logger.info(f"📊 Уведомление о заявке #{order_data.get('request_id')}: отправлено {success_count} сообщений")
                return success_count > 0
            
            # Запускаем в отдельном потоке
            thread = threading.Thread(target=send_notifications, daemon=True)
            thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка подготовки уведомления: {e}")
            return False

# Глобальный экземпляр
http_sender = None

def get_http_sender():
    global http_sender
    if http_sender is None:
        http_sender = TelegramHTTPSender()
    return http_sender

def send_order_notification(order_data):
    """Функция для отправки уведомления о заявке"""
    try:
        sender = get_http_sender()
        return sender.send_order_notification(order_data)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")
        return False
