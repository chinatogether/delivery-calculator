import requests
import logging
from urllib.parse import urlencode
import time
from datetime import datetime
import pytz
import concurrent.futures
from typing import Dict, Optional

# Настройка логирования
logger = logging.getLogger(__name__)

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def get_moscow_time():
    return datetime.now(MOSCOW_TZ)

class GoogleFormsSender:
    """Класс для отправки данных в Google Forms"""
    
    def __init__(self):
        # URL для отправки данных в Google Form
        self.form_url = "https://docs.google.com/forms/d/e/1FAIpQLSfONB0hP9sCKurPmcyuHyAj_ffmF2tmLrum9kKlyMSWqDGm_w/formResponse"
        
        # ТОЧНЫЙ маппинг полей формы (из FB_PUBLIC_LOAD_DATA_)
        self.field_mapping = {
            # Email поле - Google Forms собирает email автоматически
            'email': 'emailAddress',
            # Данные из FB_PUBLIC_LOAD_DATA_:
            'telegram_contact': 'entry.1244169801',    # [848184379] "Ссылка на ваш личный телеграм"
            'supplier_link': 'entry.1332237779',       # [1776711643] "Ссылка на поставщика на 1688"  
            'order_amount': 'entry.1319459294',        # [423871719] "На какую сумму вы планируете сделать заказ?"
            'promo_code': 'entry.211960837',           # [833179138] "Промокод"
            'terms_accepted': 'entry.363561279'        # [1814089819] "Отправляя заявку, Вы соглашаетесь" (CHECKBOX!)
        }
        
        # Альтернативные варианты для email (если основной не работает)
        self.email_alternatives = [
            'emailAddress',
            'email', 
            'entry.email',
            'emailReceipt',
        ]
        
        # Executor для неблокирующих запросов
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, 
            thread_name_prefix="google_forms"
        )
        
        # Настройки для HTTP запросов
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded'
        })
        
        logger.info("GoogleFormsSender инициализирован с обновленным маппингом")
    
    def send_form_data(self, order_data: Dict) -> bool:
        """Отправка данных в Google Form (неблокирующая)"""
        try:
            logger.info(f"📝 Подготовка отправки в Google Form для заявки #{order_data.get('request_id')}")
            
            # Запускаем отправку в executor
            future = self.executor.submit(self._send_form_worker, order_data)
            
            # НЕ ждем результат - это делает функцию неблокирующей
            logger.info(f"📝 Задача отправки в Google Form для заявки #{order_data.get('request_id')} поставлена в очередь")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при постановке задачи Google Form в очередь: {e}")
            return False
    
    def _send_form_worker(self, order_data: Dict) -> bool:
        """Worker для отправки данных в Google Form в отдельном потоке"""
        try:
            logger.info(f"📝 Начало отправки в Google Form для заявки #{order_data.get('request_id')}")
            
            # Подготавливаем данные для отправки
            form_data = self._prepare_form_data(order_data)
            
            if not form_data:
                logger.error(f"❌ Не удалось подготовить данные для Google Form")
                return False
            
            # Отправляем данные с retry логикой
            success = self._submit_to_google_form(form_data, max_retries=3)
            
            if success:
                logger.info(f"✅ Данные успешно отправлены в Google Form для заявки #{order_data.get('request_id')}")
            else:
                logger.error(f"❌ Не удалось отправить данные в Google Form для заявки #{order_data.get('request_id')}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в Google Forms worker: {e}")
            return False
    
    def _prepare_form_data(self, order_data: Dict) -> Optional[Dict]:
        """Подготовка данных для отправки в Google Form"""
        try:
            # Из анализа FB_PUBLIC_LOAD_DATA_ видно, что "На какую сумму заказа" - это текстовое поле
            # НЕ select, поэтому передаем значение как есть
            order_amount = order_data.get('order_amount', '')
            
            # Подготавливаем базовые данные для формы
            form_data = {}
            
            # Email - пробуем разные варианты
            email = order_data.get('email', '')
            if email and not email.endswith('@telegram.user'):
                form_data[self.field_mapping['email']] = email
            
            # Остальные поля - точно по маппингу из FB_PUBLIC_LOAD_DATA_
            form_data.update({
                self.field_mapping['telegram_contact']: order_data.get('telegram_contact', ''),
                self.field_mapping['supplier_link']: order_data.get('supplier_link', ''),
                self.field_mapping['order_amount']: order_amount,  # Передаем как есть
                self.field_mapping['promo_code']: order_data.get('promo_code', ''),
            })
            
            # Обработка согласия с условиями - это CHECKBOX поле!
            if order_data.get('terms_accepted'):
                # Для checkbox в Google Forms нужно передать точное значение опции
                # Из FB_PUBLIC_LOAD_DATA_: "Я подтверждаю, что ознакомлен(а)..."
                form_data[self.field_mapping['terms_accepted']] = 'Я подтверждаю, что ознакомлен(а) с условиями и правилами работы и выражаю свое согласие с ними.'
            
            # Добавляем дополнительные комментарии к ссылке на поставщика если есть
            additional_notes = order_data.get('additional_notes', '').strip()
            if additional_notes:
                current_supplier = form_data.get(self.field_mapping['supplier_link'], '')
                if current_supplier:
                    form_data[self.field_mapping['supplier_link']] = f"{current_supplier}\n\nДополнительные комментарии:\n{additional_notes}"
                else:
                    form_data[self.field_mapping['supplier_link']] = f"Дополнительные комментарии:\n{additional_notes}"
            
            # Убираем пустые значения
            form_data = {k: v for k, v in form_data.items() if v}
            
            logger.info(f"📝 Данные для Google Form подготовлены: {len(form_data)} полей")
            logger.debug(f"📝 Поля формы: {list(form_data.keys())}")
            
            return form_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка при подготовке данных для Google Form: {e}")
            return None
    
    def _submit_to_google_form(self, form_data: Dict, max_retries: int = 3) -> bool:
        """Отправка данных в Google Form с retry логикой"""
        for attempt in range(max_retries):
            try:
                logger.info(f"📝 Попытка {attempt + 1}/{max_retries} отправки в Google Form")
                logger.debug(f"📝 Отправляемые данные: {form_data}")
                
                # Отправляем POST запрос
                response = self.session.post(
                    self.form_url,
                    data=form_data,
                    timeout=30,
                    allow_redirects=True
                )
                
                logger.info(f"📝 Ответ от Google Forms: статус {response.status_code}, URL: {response.url}")
                
                # Google Forms может возвращать разные коды
                if response.status_code in [200, 302]:
                    # Проверяем URL перенаправления для подтверждения успеха
                    if any(keyword in response.url.lower() for keyword in ['formresponse', 'thanks', 'submitted']):
                        logger.info(f"✅ Google Form успешно отправлена (попытка {attempt + 1})")
                        return True
                    elif 'viewform' in response.url.lower():
                        logger.warning(f"⚠️ Форма вернулась к viewform - возможно, ошибка валидации")
                    else:
                        logger.info(f"✅ Форма отправлена, URL ответа: {response.url}")
                        return True
                else:
                    logger.warning(f"⚠️ Неуспешный ответ от Google Form: статус {response.status_code}")
                
            except requests.exceptions.Timeout:
                logger.warning(f"⏰ Таймаут при отправке в Google Form (попытка {attempt + 1})")
            except requests.exceptions.RequestException as e:
                logger.warning(f"🌐 Ошибка сети при отправке в Google Form (попытка {attempt + 1}): {e}")
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка при отправке в Google Form (попытка {attempt + 1}): {e}")
            
            # Пауза между попытками
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Экспоненциальная задержка
        
        logger.error(f"❌ Все {max_retries} попытки отправки в Google Form неуспешны")
        return False
    
    def test_form_submission(self):
        """Тестирование отправки формы с отладочной информацией"""
        test_data = {
            'request_id': 999999,
            'email': 'test@example.com',
            'telegram_contact': '@test_user',
            'supplier_link': 'https://example.com/test-product',
            'order_amount': '5000-10000 юаней',
            'promo_code': 'TEST123',
            'additional_notes': 'Это тестовые данные для проверки интеграции',
            'terms_accepted': True
        }
        
        logger.info("🧪 Запуск тестирования Google Form с отладкой")
        
        # Синхронная отправка для получения детального лога
        form_data = self._prepare_form_data(test_data)
        if form_data:
            logger.info(f"📋 Подготовленные данные:")
            for field, value in form_data.items():
                logger.info(f"   {field}: {value}")
            
            success = self._submit_to_google_form(form_data, max_retries=1)
            return success
        else:
            logger.error("❌ Не удалось подготовить тестовые данные")
            return False
    
    def create_prefilled_url(self, test_data):
        """Создает предзаполненную ссылку для тестирования маппинга"""
        try:
            view_url = self.form_url.replace('/formResponse', '/viewform')
            
            params = []
            form_data = self._prepare_form_data(test_data)
            if form_data:
                for field, value in form_data.items():
                    if value:
                        params.append(f"{field}={requests.utils.quote(str(value))}")
            
            prefilled_url = f"{view_url}?" + "&".join(params)
            
            logger.info(f"🔗 Предзаполненная ссылка создана: {len(prefilled_url)} символов")
            return prefilled_url
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания предзаполненной ссылки: {e}")
            return None
    
    def send_form_data_sync(self, order_data: Dict) -> bool:
        """Синхронная отправка данных в Google Form (для критических случаев)"""
        try:
            logger.info(f"🔄 Синхронная отправка в Google Form для заявки #{order_data.get('request_id')}")
            
            future = self.executor.submit(self._send_form_worker, order_data)
            result = future.result(timeout=15)  # Ждем максимум 15 секунд
            
            if result:
                logger.info(f"✅ Синхронная отправка в Google Form успешна для заявки #{order_data.get('request_id')}")
            else:
                logger.error(f"❌ Синхронная отправка в Google Form неуспешна для заявки #{order_data.get('request_id')}")
            
            return result
            
        except concurrent.futures.TimeoutError:
            logger.error(f"⏰ Таймаут синхронной отправки в Google Form для заявки #{order_data.get('request_id')}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка синхронной отправки в Google Form: {e}")
            return False
    
    def update_field_mapping(self, new_mapping: Dict[str, str]):
        """Обновление маппинга полей"""
        self.field_mapping.update(new_mapping)
        logger.info(f"📝 Маппинг полей обновлен: {new_mapping}")
    
    def get_status(self) -> Dict:
        """Получить статус Google Forms отправителя"""
        return {
            "form_url": self.form_url,
            "fields_mapped": len(self.field_mapping),
            "executor_active": not self.executor._shutdown if hasattr(self.executor, '_shutdown') else True,
            "field_mapping": self.field_mapping,
            "email_alternatives": self.email_alternatives
        }
    
    def __del__(self):
        """Корректное закрытие ресурсов при удалении объекта"""
        try:
            if hasattr(self, 'session') and self.session:
                self.session.close()
            if hasattr(self, 'executor') and self.executor:
                self.executor.shutdown(wait=False)
        except Exception as e:
            logger.warning(f"Проблема при закрытии Google Forms ресурсов: {e}")

# Глобальный экземпляр
google_forms_sender = None

def get_google_forms_sender():
    """Получить экземпляр отправителя Google Forms"""
    global google_forms_sender
    if google_forms_sender is None:
        google_forms_sender = GoogleFormsSender()
    return google_forms_sender

def send_to_google_form(order_data: Dict) -> bool:
    """Функция для отправки данных в Google Form"""
    try:
        sender = get_google_forms_sender()
        
        logger.info(f"📝 Запуск отправки в Google Form для заявки #{order_data.get('request_id')}")
        
        return sender.send_form_data(order_data)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка отправки в Google Form: {e}")
        return False

def send_to_google_form_sync(order_data: Dict) -> bool:
    """Синхронная версия отправки в Google Form"""
    try:
        sender = get_google_forms_sender()
        return sender.send_form_data_sync(order_data)
    except Exception as e:
        logger.error(f"❌ Ошибка синхронной отправки в Google Form: {e}")
        return False

def test_google_form():
    """Расширенное тестирование отправки в Google Form"""
    test_data = {
        'request_id': 999999,
        'email': 'test@example.com',
        'telegram_contact': '@test_user',
        'supplier_link': 'https://example.com/product',
        'order_amount': '5000-10000 юаней',
        'promo_code': 'TEST2024',
        'additional_notes': 'Это тестовые данные',
        'terms_accepted': True
    }
    
    logger.info("🧪 Запуск расширенного тестирования Google Form")
    
    sender = get_google_forms_sender()
    
    # 1. Показываем статус
    status = sender.get_status()
    logger.info(f"📊 Статус отправителя: {status}")
    
    # 2. Создаем предзаполненную ссылку для ручной проверки
    prefilled_url = sender.create_prefilled_url(test_data)
    if prefilled_url:
        print(f"\n🔗 ПРЕДЗАПОЛНЕННАЯ ССЫЛКА ДЛЯ ПРОВЕРКИ:")
        print("=" * 60)
        print(prefilled_url)
        print("\nОткройте эту ссылку в браузере для проверки маппинга!")
    
    # 3. Тестируем отправку
    result = sender.test_form_submission()
    
    print(f"\n🎯 Результат тестирования: {'✅ Успех' if result else '❌ Неудача'}")
    
    if not result:
        print(f"\n💡 ЕСЛИ ТЕСТ НЕ ПРОШЕЛ:")
        print("1. Проверьте, что entry ID правильные")
        print("2. Особенно проверьте поле email")
        print("3. Запустите: python find_email_field.py")
        print("4. Обновите field_mapping с правильными ID")
    
    return result

if __name__ == '__main__':
    # Показываем текущий маппинг
    sender = get_google_forms_sender()
    print("📋 ТЕКУЩИЙ МАППИНГ ПОЛЕЙ:")
    print("=" * 40)
    for field, entry in sender.field_mapping.items():
        print(f"   {field:15} → {entry}")
    
    print(f"\n📝 НАЙДЕННЫЕ ENTRY ID:")
    print("   entry.1244169801 → Telegram contact")
    print("   entry.1332237779 → Supplier link") 
    print("   entry.1319459294 → Order amount")
    print("   entry.211960837  → Promo code")
    print("   entry.363561279  → Terms accepted")
    
    print(f"\n⚠️  ВНИМАНИЕ: EMAIL ПОЛЕ")
    print("   Текущий маппинг использует 'emailAddress'")
    print("   Если не работает, запустите: python find_email_field.py")
    
    # Тестируем
    test_google_form()
    time.sleep(5)  # Ждем завершения
    logger.info("🏁 Тестирование Google Form завершено")
