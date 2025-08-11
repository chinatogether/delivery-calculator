from flask import Flask, render_template, request, jsonify
import psycopg2
from decimal import Decimal
import logging
import json
from datetime import datetime
import os
from functools import wraps
from dotenv import load_dotenv
import pytz
from notification_sender import send_order_notification
from google_form_sender import send_to_google_form  # ИСПРАВЛЕННЫЙ ИМПОРТ
import threading

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('delivery_calculator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
    'host': os.getenv('DB_HOST'),
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

# ФУНКЦИИ ДЛЯ РАБОТЫ С БАЗОЙ ДАННЫХ

@handle_db_errors
def init_purchase_orders_tables():
    """Создание таблиц для заявок если они не существуют"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        # Создаем схему если не существует
        cursor.execute("CREATE SCHEMA IF NOT EXISTS delivery_test")
        
        # Таблица заявок на выкуп и доставку (обновленная версия)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.purchase_requests (
                id SERIAL PRIMARY KEY,
                telegram_user_id INTEGER REFERENCES delivery_test.telegram_users(id),
                calculation_id INTEGER REFERENCES delivery_test.user_calculation(id),
                email VARCHAR(255) NOT NULL,
                telegram_contact VARCHAR(255) NOT NULL,
                supplier_link TEXT,
                order_amount VARCHAR(100),
                promo_code VARCHAR(100),
                additional_notes TEXT,
                terms_accepted BOOLEAN DEFAULT FALSE,
                status VARCHAR(50) DEFAULT 'new',
                manager_notes TEXT,
                google_form_submitted BOOLEAN DEFAULT FALSE,  -- НОВОЕ ПОЛЕ
                google_form_submission_time TIMESTAMP WITH TIME ZONE,  -- НОВОЕ ПОЛЕ
                created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow'),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow')
            )
        """)
        
        # Проверяем и добавляем новые поля если их нет
        cursor.execute("""
            DO $$ 
            BEGIN 
                BEGIN
                    ALTER TABLE delivery_test.purchase_requests 
                    ADD COLUMN google_form_submitted BOOLEAN DEFAULT FALSE;
                EXCEPTION
                    WHEN duplicate_column THEN 
                    -- Поле уже существует, ничего не делаем
                END;
                
                BEGIN
                    ALTER TABLE delivery_test.purchase_requests 
                    ADD COLUMN google_form_submission_time TIMESTAMP WITH TIME ZONE;
                EXCEPTION
                    WHEN duplicate_column THEN 
                    -- Поле уже существует, ничего не делаем  
                END;
            END $$;
        """)
        
        # Индексы для быстрого поиска
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_purchase_requests_telegram_user 
            ON delivery_test.purchase_requests (telegram_user_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_purchase_requests_status 
            ON delivery_test.purchase_requests (status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_purchase_requests_created 
            ON delivery_test.purchase_requests (created_at)
        """)
        
        # НОВЫЙ ИНДЕКС для Google Forms
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_purchase_requests_google_form 
            ON delivery_test.purchase_requests (google_form_submitted)
        """)
        
        conn.commit()
        logger.info("Таблицы для заявок успешно созданы/проверены")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка при создании таблиц заявок: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def save_telegram_user(telegram_id, username, first_name=None, last_name=None):
    """Сохранение или обновление пользователя Telegram"""
    if not telegram_id:
        return None
        
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        moscow_time = get_moscow_time()
        cursor.execute("""
            INSERT INTO delivery_test.telegram_users (telegram_id, username, first_name, last_name, created_at, last_activity)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE 
            SET username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_activity = %s
            RETURNING id
        """, (str(telegram_id), username, first_name, last_name, moscow_time, moscow_time, moscow_time))
        
        user_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"Пользователь Telegram сохранен/обновлен: ID={user_id}, telegram_id={telegram_id}")
        return user_id
        
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def save_user_action(telegram_id, action, details=None):
    """Сохранение действия пользователя"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        moscow_time = get_moscow_time()
        cursor.execute("""
            INSERT INTO delivery_test.user_actions (telegram_user_id, action, details, created_at)
            VALUES (%s, %s, %s, %s)
        """, (str(telegram_id), action, json.dumps(details) if details else None, moscow_time))
        
        conn.commit()
        logger.info(f"Действие пользователя сохранено: {telegram_id} -> {action}")
        
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def save_purchase_request(telegram_user_id, email, telegram_contact, supplier_link, order_amount, 
                         promo_code, additional_notes, terms_accepted, calculation_id=None):
    """Сохранение заявки на выкуп и доставку"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        moscow_time = get_moscow_time()
        cursor.execute("""
            INSERT INTO delivery_test.purchase_requests (
                telegram_user_id, calculation_id, email, telegram_contact, supplier_link,
                order_amount, promo_code, additional_notes, terms_accepted, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            telegram_user_id, calculation_id, email, telegram_contact, supplier_link,
            order_amount, promo_code, additional_notes, terms_accepted, moscow_time, moscow_time
        ))
        
        request_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"Заявка на выкуп создана: ID={request_id}, пользователь={telegram_user_id}")
        return request_id
        
    finally:
        cursor.close()
        conn.close()

# НОВАЯ ФУНКЦИЯ для обновления статуса Google Forms
@handle_db_errors
def update_google_form_status(request_id, submitted=True):
    """Обновление статуса отправки в Google Forms"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        moscow_time = get_moscow_time()
        cursor.execute("""
            UPDATE delivery_test.purchase_requests 
            SET google_form_submitted = %s, 
                google_form_submission_time = %s,
                updated_at = %s
            WHERE id = %s
            RETURNING id
        """, (submitted, moscow_time if submitted else None, moscow_time, request_id))
        
        result = cursor.fetchone()
        if result:
            conn.commit()
            logger.info(f"Статус Google Forms для заявки {request_id} обновлен: {submitted}")
            return request_id
        else:
            logger.warning(f"Заявка с ID {request_id} не найдена для обновления Google Forms статуса")
            return None
        
    finally:
        cursor.close()
        conn.close()

# ОСТАЛЬНЫЕ ФУНКЦИИ БД (get_user_requests, update_request_status, get_request_by_id)
# ... (остальной код БД остается такой же)

# МАРШРУТЫ ДЛЯ ORDER

def register_order_routes(app):
    """Регистрация маршрутов для заявок в Flask приложении"""
    
    @app.route('/order')
    def order_page():
        """Страница заказа доставки - возвращает HTML шаблон"""
        telegram_id = request.args.get('telegram_id')
        username = request.args.get('username')
        calculation_id = request.args.get('calculation_id')
        
        if telegram_id:
            save_user_action(telegram_id, 'page_opened', {
                'page': 'order', 
                'calculation_id': calculation_id
            })
        
        try:
            # Возвращаем HTML шаблон
            return render_template('order.html')
        except Exception as e:
            logger.error(f"Ошибка загрузки шаблона order.html: {e}")
            return jsonify({
                "error": "Template not found",
                "message": "Создайте файл templates/order.html",
                "telegram_id": telegram_id,
                "calculation_id": calculation_id
            }), 500

    @app.route('/submit_purchase_request', methods=['POST'])
    def submit_purchase_request():
        """Создание заявки на выкуп и доставку"""
        try:
            data = request.get_json()
            telegram_id = data.get('telegram_id')
            calculation_id = data.get('calculation_id')
            email = data.get('email', '').strip()
            telegram_contact = data.get('telegram_contact', '').strip()
            supplier_link = data.get('supplier_link', '').strip()
            order_amount = data.get('order_amount', '').strip()
            promo_code = data.get('promo_code', '').strip()
            additional_notes = data.get('additional_notes', '').strip()
            terms_accepted = data.get('terms_accepted', False)
            
            # Логируем получение заявки
            logger.info(f"📥 Получена заявка от пользователя {telegram_id}")
            
            # Извлекаем username из данных или создаем из telegram_contact
            username = data.get('username', '').strip()
            if not username and telegram_contact:
                if telegram_contact.startswith('@'):
                    username = telegram_contact[1:]  # убираем @
                elif 'https://t.me/' in telegram_contact:
                    username = telegram_contact.split('/')[-1]  # берем последнюю часть URL
                else:
                    username = f"user_{telegram_id}"  # fallback
            
            # Валидация обязательных полей
            if not all([telegram_id, telegram_contact]):
                return jsonify({"error": "Не все обязательные поля заполнены"}), 400
            
            if not terms_accepted:
                return jsonify({"error": "Необходимо согласиться с условиями работы"}), 400
            
            # Генерируем email из telegram_id если не указан
            if not email:
                email = f"{telegram_id}@telegram.user"
            
            # Валидация Telegram контакта
            if not (telegram_contact.startswith('@') or telegram_contact.startswith('https://t.me/')):
                return jsonify({"error": "Telegram контакт должен начинаться с @ или https://t.me/"}), 400
            
            # Получаем или создаем пользователя
            conn = connect_to_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM delivery_test.telegram_users WHERE telegram_id = %s", (str(telegram_id),))
            user_result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not user_result:
                logger.info(f"👤 Пользователь с telegram_id={telegram_id} не найден, создаем нового пользователя...")
                telegram_user_id = save_telegram_user(
                    telegram_id=telegram_id, 
                    username=username,
                    first_name=None,
                    last_name=None
                )
                
                if not telegram_user_id:
                    logger.error(f"❌ Не удалось создать пользователя с telegram_id={telegram_id}")
                    return jsonify({"error": "Ошибка при создании пользователя"}), 500
                
                logger.info(f"✅ Создан новый пользователь с ID={telegram_user_id}")
            else:
                telegram_user_id = user_result[0]
                logger.info(f"✅ Найден существующий пользователь с ID={telegram_user_id}")
            
            # Сохраняем заявку
            logger.info(f"💾 Сохранение заявки в БД...")
            request_id = save_purchase_request(
                telegram_user_id=telegram_user_id,
                calculation_id=calculation_id if calculation_id else None,
                email=email,
                telegram_contact=telegram_contact,
                supplier_link=supplier_link,
                order_amount=order_amount,
                promo_code=promo_code,
                additional_notes=additional_notes,
                terms_accepted=terms_accepted
            )
            
            if not request_id:
                logger.error("❌ Не удалось создать заявку - save_purchase_request вернул None")
                return jsonify({"error": "Ошибка при создании заявки"}), 500
            
            logger.info(f"✅ Заявка успешно создана с ID={request_id} для пользователя {telegram_user_id}")
            
            # Сохраняем действие
            save_user_action(telegram_id, 'purchase_request_submitted', {
                'request_id': request_id,
                'calculation_id': calculation_id,
                'email': email,
                'order_amount': order_amount,
                'telegram_contact': telegram_contact,
                'is_new_user': not bool(user_result)
            })
            
            # Подготавливаем данные для уведомлений и Google Forms
            notification_data = {
                'request_id': request_id,
                'telegram_contact': telegram_contact,
                'email': email,
                'order_amount': order_amount,
                'supplier_link': supplier_link,
                'promo_code': promo_code,
                'additional_notes': additional_notes,
                'calculation_id': calculation_id,
                'telegram_id': telegram_id,
                'username': username,
                'terms_accepted': terms_accepted
            }
            
            # 1. ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ В TELEGRAM
            notification_success = False
            try:
                notification_success = send_order_notification(notification_data)
                if notification_success:
                    logger.info(f"✅ Telegram уведомление для заявки #{request_id} отправлено")
                else:
                    logger.warning(f"⚠️ Telegram уведомление для заявки #{request_id} не отправлено")
            except Exception as e:
                logger.error(f"❌ Ошибка Telegram уведомления для заявки #{request_id}: {e}")
            
            # 2. ОТПРАВЛЯЕМ В GOOGLE FORMS  
            google_form_success = False
            try:
                google_form_success = send_to_google_form(notification_data)
                
                if google_form_success:
                    logger.info(f"✅ Google Form для заявки #{request_id} отправлена")
                    update_google_form_status(request_id, True)
                else:
                    logger.warning(f"⚠️ Google Form для заявки #{request_id} не отправлена")
                    update_google_form_status(request_id, False)
                    
            except Exception as e:
                logger.error(f"❌ Ошибка Google Form для заявки #{request_id}: {e}")
                update_google_form_status(request_id, False)
            
            # Возвращаем успешный ответ
            logger.info(f"🎉 Заявка #{request_id} успешно обработана")
            
            return jsonify({
                "success": True,
                "request_id": request_id,
                "message": "Заявка успешно отправлена! Менеджер свяжется с вами в рабочее время.",
                "telegram_notification_sent": notification_success,
                "google_form_sent": google_form_success
            })
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при создании заявки: {str(e)}")
            return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

    @app.route('/api/test-notification', methods=['POST'])
    def test_notification():
        """Тестирование систем уведомлений (Telegram + Google Forms)"""
        try:
            test_data = {
                'request_id': 999999,
                'telegram_contact': '@test_user',
                'email': 'test@example.com',
                'order_amount': '5000-10000 юаней',
                'supplier_link': 'https://example.com/product',
                'promo_code': 'TEST2024',
                'additional_notes': 'Это тестовое уведомление',
                'calculation_id': None,
                'telegram_id': 'test123',
                'username': 'test_user',
                'terms_accepted': True
            }
            
            # Тестируем Telegram уведомления
            telegram_success = False
            try:
                telegram_success = send_order_notification(test_data)
            except Exception as e:
                logger.error(f"Ошибка тестирования Telegram: {e}")
            
            # Тестируем Google Forms
            google_form_success = False
            try:
                google_form_success = send_to_google_form(test_data)
            except Exception as e:
                logger.error(f"Ошибка тестирования Google Forms: {e}")
            
            return jsonify({
                "success": True,
                "telegram_notification": {
                    "sent": telegram_success,
                    "message": "Тестовое уведомление в Telegram отправлено" if telegram_success else "Не удалось отправить в Telegram"
                },
                "google_form": {
                    "sent": google_form_success,
                    "message": "Тестовые данные в Google Form отправлены" if google_form_success else "Не удалось отправить в Google Form"
                }
            })
                
        except Exception as e:
            logger.error(f"Ошибка при тестировании уведомлений: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/health')
    def health_check():
        """Проверка работоспособности модуля заявок"""
        try:
            conn = connect_to_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_orders,
                    COUNT(*) FILTER (WHERE google_form_submitted = true) as google_form_submitted
                FROM delivery_test.purchase_requests
            """)
            result = cursor.fetchone()
            orders_count = result[0] if result else 0
            google_forms_count = result[1] if result else 0
            cursor.close()
            conn.close()
            
            # Проверяем статус модулей
            try:
                from notification_sender import get_notification_sender
                telegram_status = get_notification_sender().get_status()
            except:
                telegram_status = {"status": "unavailable"}
            
            try:
                from google_form_sender import get_google_forms_sender
                google_forms_status = get_google_forms_sender().get_status()
            except:
                google_forms_status = {"status": "unavailable"}
            
            return jsonify({
                "status": "healthy",
                "module": "orders_with_google_forms",
                "timestamp": get_moscow_time().isoformat(),
                "database": "connected",
                "total_orders": orders_count,
                "google_forms_submitted": google_forms_count,
                "telegram_notifications": telegram_status,
                "google_forms": google_forms_status,
                "version": "2.5-fixed-imports"
            })
        except Exception as e:
            return jsonify({
                "status": "unhealthy",
                "module": "orders_with_google_forms",
                "timestamp": get_moscow_time().isoformat(),
                "error": str(e)
            }), 500

# ЗАПУСК ПРИЛОЖЕНИЯ

if __name__ == '__main__':
    # Создание приложения Flask
    app = Flask(__name__, static_folder='static', template_folder='templates')
    
    # Настройка CORS
    from flask_cors import CORS
    CORS(app, origins=["https://telegram.org", "*"])
    
    logger.info("=== Запуск China Together Delivery Calculator - Orders Module v2.5 FIXED ===")
    
    # Инициализируем таблицы
    try:
        init_purchase_orders_tables()
        logger.info("✅ Таблицы заявок готовы")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации таблиц заявок: {str(e)}")
    
    # Регистрируем маршруты
    register_order_routes(app)
    logger.info("✅ Маршруты заявок зарегистрированы")
    
    # Проверяем доступность модулей
    try:
        from notification_sender import get_notification_sender
        telegram_sender = get_notification_sender()
        logger.info(f"✅ Telegram уведомления: {telegram_sender.get_status()}")
    except Exception as e:
        logger.warning(f"⚠️ Telegram уведомления недоступны: {e}")
    
    try:
        from google_form_sender import get_google_forms_sender
        google_sender = get_google_forms_sender()
        logger.info(f"✅ Google Forms: {google_sender.get_status()}")
    except Exception as e:
        logger.warning(f"⚠️ Google Forms недоступен: {e}")
    
    # Обработчики ошибок
    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith('/api/'):
            return jsonify({"error": "Endpoint не найден"}), 404
        return jsonify({"error": "Страница не найдена", "path": request.path}), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Внутренняя ошибка сервера: {str(error)}")
        if request.path.startswith('/api/'):
            return jsonify({"error": "Внутренняя ошибка сервера"}), 500
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

    @app.after_request
    def after_request(response):
        """Добавляем заголовки безопасности"""
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'ALLOWALL'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response
    
    # Запускаем сервер на отдельном порту
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('ORDERS_PORT', 8062)),
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        threaded=True
    )
