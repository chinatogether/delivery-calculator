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
import concurrent.futures

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def get_moscow_time():
    return datetime.now(MOSCOW_TZ)

class NotificationSender:
    """Улучшенный отправитель уведомлений"""
    
    def __init__(self):
        self.token = os.getenv('API_ZAYAVKI_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_NOTIFICATIONS_CHAT_ID')
        self.admin_chat_ids = [id.strip() for id in os.getenv('TELEGRAM_ADMIN_CHAT_IDS', '').split(',') if id.strip()]
        
        if not self.token:
            logger.error("API_ZAYAVKI_TOKEN не найден")
            return
        
        # Используем executor для избежания блокировок
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="notification")
        
        logger.info(f"NotificationSender создан. Chat ID: {self.chat_id}, Admin IDs: {self.admin_chat_ids}")
    
    def send_order_notification(self, order_data):
        """Отправка уведомления о заявке (неблокирующая)"""
        try:
            logger.info(f"Подготовка уведомления для заявки #{order_data.get('request_id')}")
            
            # Запускаем отправку в executor
            future = self.executor.submit(self._send_notification_worker, order_data)
            
            # НЕ ждем результат - это делает функцию неблокирующей
            logger.info(f"Задача отправки уведомления для заявки #{order_data.get('request_id')} поставлена в очередь")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при постановке задачи уведомления в очередь: {e}")
            return False
    
    def _send_notification_worker(self, order_data):
        """Worker для отправки уведомления в отдельном потоке"""
        try:
            moscow_time = get_moscow_time()
            
            # Форматируем сообщение
            message = self._format_order_message(order_data, moscow_time)
            
            # Создаем новый event loop для этого потока
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Устанавливаем таймаут для всей операции
                result = asyncio.wait_for(
                    self._send_messages_async(message), 
                    timeout=30.0  # 30 секунд максимум
                )
                loop.run_until_complete(result)
                
                logger.info(f"✅ Уведомление о заявке #{order_data.get('request_id')} успешно отправлено")
                return True
                
            except asyncio.TimeoutError:
                logger.error(f"⏰ Таймаут при отправке уведомления для заявки #{order_data.get('request_id')}")
                return False
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке уведомления для заявки #{order_data.get('request_id')}: {e}")
                return False
            finally:
                try:
                    # Правильно закрываем loop
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception as e:
                    logger.warning(f"Проблема при закрытии event loop: {e}")
                finally:
                    loop.close()
                    
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в notification worker: {e}")
            return False
    
    def _format_order_message(self, order_data, moscow_time):
        """Форматирование сообщения о заявке"""
        message = (
            f"🆕 <b>НОВАЯ ЗАЯВКА НА ДОСТАВКУ</b>\n\n"
            f"📅 <b>Дата:</b> {moscow_time.strftime('%d.%m.%Y %H:%M')} (МСК)\n"
            f"🆔 <b>ID заявки:</b> #{order_data.get('request_id', 'N/A')}\n"
            f"👤 <b>Пользователь:</b> {order_data.get('telegram_contact', 'N/A')}\n"              
            f"👤 <b>e-mail::</b> {order_data.get('email', 'N/A')}\n"
            f"💰 <b>Сумма заказа:</b> {order_data.get('order_amount', 'Не указано')}\n"
        )
        
        # Дополнительная информация
        if order_data.get('supplier_link'):
            supplier_link = order_data['supplier_link'][:100]
            if len(order_data['supplier_link']) > 100:
                supplier_link += "..."
            message += f"🔗 <b>Ссылка на товар:</b>\n{supplier_link}\n\n"
        
        if order_data.get('promo_code'):
            message += f"🎫 <b>Промокод:</b> {order_data['promo_code']}\n\n"
        
        if order_data.get('additional_notes'):
            notes = order_data['additional_notes'][:200]
            if len(order_data['additional_notes']) > 200:
                notes += "..."
            message += f"💬 <b>Комментарии:</b>\n{notes}\n\n"
        
        if order_data.get('calculation_id'):
            message += f"📊 <b>Связанный расчет:</b> #{order_data['calculation_id']}\n\n"
        
        
        return message
    
    async def _send_messages_async(self, message):
        """Асинхронная отправка сообщений с retry логикой"""
        bot = Bot(token=self.token)
        
        try:
            success_count = 0
            total_attempts = 0
            
            # Отправляем в группу
            if self.chat_id:
                total_attempts += 1
                try:
                    await bot.send_message(
                        chat_id=self.chat_id,
                        text=message,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                    success_count += 1
                    logger.info(f"✅ Сообщение отправлено в группу {self.chat_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки в группу {self.chat_id}: {e}")
            
            # Отправляем админам
            for admin_id in self.admin_chat_ids:
                if admin_id:
                    total_attempts += 1
                    try:
                        await bot.send_message(
                            chat_id=admin_id,
                            text=message,
                            parse_mode='HTML',
                            disable_web_page_preview=True
                        )
                        success_count += 1
                        logger.info(f"✅ Сообщение отправлено админу {admin_id}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки админу {admin_id}: {e}")
            
            logger.info(f"📊 Статистика отправки: {success_count}/{total_attempts} успешно")
            
            # Возвращаем True если хотя бы одно сообщение отправлено
            return success_count > 0
            
        finally:
            # Правильно закрываем сессию бота
            try:
                await bot.session.close()
            except Exception as e:
                logger.warning(f"Проблема при закрытии сессии бота: {e}")
    
    def send_order_notification_sync_fallback(self, order_data):
        """Синхронная fallback версия для критических случаев"""
        try:
            logger.info(f"🔄 Попытка синхронной отправки для заявки #{order_data.get('request_id')}")
            
            future = self.executor.submit(self._send_notification_worker, order_data)
            # Ждем максимум 10 секунд
            result = future.result(timeout=10)
            
            if result:
                logger.info(f"✅ Синхронная отправка успешна для заявки #{order_data.get('request_id')}")
            else:
                logger.error(f"❌ Синхронная отправка неуспешна для заявки #{order_data.get('request_id')}")
            
            return result
            
        except concurrent.futures.TimeoutError:
            logger.error(f"⏰ Таймаут синхронной отправки для заявки #{order_data.get('request_id')}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка синхронной отправки: {e}")
            return False
    
    def get_status(self):
        """Получить статус отправителя уведомлений"""
        return {
            "token_configured": bool(self.token),
            "chat_id_configured": bool(self.chat_id),
            "admin_ids_count": len(self.admin_chat_ids),
            "executor_active": not self.executor._shutdown,
            "admin_ids": self.admin_chat_ids
        }
    
    def __del__(self):
        """Корректное закрытие executor при удалении объекта"""
        try:
            if hasattr(self, 'executor') and self.executor:
                self.executor.shutdown(wait=False)
        except Exception as e:
            logger.warning(f"Проблема при закрытии executor: {e}")

# Глобальный экземпляр
notification_sender = None

def get_notification_sender():
    """Получить экземпляр отправителя уведомлений"""
    global notification_sender
    if notification_sender is None:
        notification_sender = NotificationSender()
    return notification_sender

def send_order_notification(order_data):
    """Функция для отправки уведомления о заявке"""
    try:
        sender = get_notification_sender()
        
        # Проверяем конфигурацию
        status = sender.get_status()
        if not status["token_configured"]:
            logger.error("❌ Токен бота не настроен")
            return False
        
        if not status["chat_id_configured"] and not status["admin_ids_count"]:
            logger.error("❌ Ни chat_id, ни admin_ids не настроены")
            return False
        
        logger.info(f"🚀 Запуск отправки уведомления для заявки #{order_data.get('request_id')}")
        logger.info(f"📋 Конфигурация: chat_id={bool(sender.chat_id)}, admin_count={len(sender.admin_chat_ids)}")
        
        return sender.send_order_notification(order_data)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка отправки уведомления: {e}")
        return False

def send_order_notification_sync(order_data):
    """Синхронная версия отправки уведомления (для критических случаев)"""
    try:
        sender = get_notification_sender()
        return sender.send_order_notification_sync_fallback(order_data)
    except Exception as e:
        logger.error(f"❌ Ошибка синхронной отправки уведомления: {e}")
        return False

def test_notification_system():
    """Тестирование системы уведомлений"""
    test_data = {
        'request_id': 999999,
        'telegram_contact': '@test_user',
        'email': 'test@example.com',
        'order_amount': '5000-10000 юаней',
        'supplier_link': 'https://example.com/product',
        'promo_code': 'TEST2024',
        'additional_notes': 'Это тестовое уведомление',
        'calculation_id': 12345,
        'telegram_id': 'test123',
        'username': 'test_user'
    }
    
    logger.info("🧪 Запуск тестирования системы уведомлений")
    result = send_order_notification(test_data)
    logger.info(f"🧪 Результат теста: {'✅ Успех' if result else '❌ Неудача'}")
    return result

if __name__ == '__main__':
    # Тестирование
    test_notification_system()
    time.sleep(5)  # Ждем завершения
    logger.info("🏁 Тестирование завершено")
