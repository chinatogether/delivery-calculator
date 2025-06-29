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
from telegram_notifier import send_order_notification
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
                created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow'),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow')
            )
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

@handle_db_errors
def get_user_requests(telegram_user_id, limit=10):
    """Получение заявок пользователя"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT pr.id, pr.calculation_id, pr.email, pr.telegram_contact, 
                   pr.supplier_link, pr.order_amount, pr.promo_code, 
                   pr.additional_notes, pr.status, pr.created_at, pr.updated_at
            FROM delivery_test.purchase_requests pr
            WHERE pr.telegram_user_id = %s
            ORDER BY pr.created_at DESC
            LIMIT %s
        """, (telegram_user_id, limit))
        
        requests = cursor.fetchall()
        
        # Преобразуем в словари
        result = []
        for req in requests:
            result.append({
                'id': req[0],
                'calculation_id': req[1],
                'email': req[2],
                'telegram_contact': req[3],
                'supplier_link': req[4],
                'order_amount': req[5],
                'promo_code': req[6],
                'additional_notes': req[7],
                'status': req[8],
                'created_at': req[9].isoformat() if req[9] else None,
                'updated_at': req[10].isoformat() if req[10] else None
            })
        
        return result
        
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def update_request_status(request_id, status, manager_notes=None):
    """Обновление статуса заявки"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        moscow_time = get_moscow_time()
        cursor.execute("""
            UPDATE delivery_test.purchase_requests 
            SET status = %s, manager_notes = %s, updated_at = %s
            WHERE id = %s
            RETURNING id
        """, (status, manager_notes, moscow_time, request_id))
        
        result = cursor.fetchone()
        if result:
            conn.commit()
            logger.info(f"Статус заявки {request_id} обновлен на '{status}'")
            return request_id
        else:
            logger.warning(f"Заявка с ID {request_id} не найдена")
            return None
        
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def get_request_by_id(request_id):
    """Получение заявки по ID"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT pr.id, pr.telegram_user_id, pr.calculation_id, pr.email, 
                   pr.telegram_contact, pr.supplier_link, pr.order_amount, 
                   pr.promo_code, pr.additional_notes, pr.terms_accepted,
                   pr.status, pr.manager_notes, pr.created_at, pr.updated_at,
                   tu.telegram_id, tu.username, tu.first_name, tu.last_name
            FROM delivery_test.purchase_requests pr
            LEFT JOIN delivery_test.telegram_users tu ON pr.telegram_user_id = tu.id
            WHERE pr.id = %s
        """, (request_id,))
        
        result = cursor.fetchone()
        if result:
            return {
                'id': result[0],
                'telegram_user_id': result[1],
                'calculation_id': result[2],
                'email': result[3],
                'telegram_contact': result[4],
                'supplier_link': result[5],
                'order_amount': result[6],
                'promo_code': result[7],
                'additional_notes': result[8],
                'terms_accepted': result[9],
                'status': result[10],
                'manager_notes': result[11],
                'created_at': result[12].isoformat() if result[12] else None,
                'updated_at': result[13].isoformat() if result[13] else None,
                'user': {
                    'telegram_id': result[14],
                    'username': result[15],
                    'first_name': result[16],
                    'last_name': result[17]
                }
            }
        return None
        
    finally:
        cursor.close()
        conn.close()

# МАРШРУТЫ ДЛЯ ORDER

def register_order_routes(app):
    """Регистрация маршрутов для заявок в Flask приложении"""
    
    @app.route('/order')
    def order_page():
        """Страница заказа доставки"""
        telegram_id = request.args.get('telegram_id')
        username = request.args.get('username')
        calculation_id = request.args.get('calculation_id')
        
        if telegram_id:
            save_user_action(telegram_id, 'page_opened', {
                'page': 'order', 
                'calculation_id': calculation_id
            })
        
        try:
            return render_template('order.html')
        except:
            return jsonify({
                "page": "order",
                "telegram_id": telegram_id,
                "calculation_id": calculation_id,
                "message": "Order page - Template not found, showing JSON response"
            })

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
                logger.info(f"Пользователь с telegram_id={telegram_id} не найден, создаем нового пользователя...")
                # Создаем нового пользователя
                telegram_user_id = save_telegram_user(
                    telegram_id=telegram_id, 
                    username=username,
                    first_name=None,  # Не знаем имя, оставляем пустым
                    last_name=None    # Не знаем фамилию, оставляем пустым
                )
                
                if not telegram_user_id:
                    logger.error(f"Не удалось создать пользователя с telegram_id={telegram_id}")
                    return jsonify({"error": "Ошибка при создании пользователя"}), 500
                
                logger.info(f"Создан новый пользователь с ID={telegram_user_id}")
            else:
                telegram_user_id = user_result[0]
                logger.info(f"Найден существующий пользователь с ID={telegram_user_id}")
            
            # Сохраняем заявку
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
            
            if request_id:
                # Сохраняем действие
                save_user_action(telegram_id, 'purchase_request_submitted', {
                    'request_id': request_id,
                    'calculation_id': calculation_id,
                    'email': email,
                    'order_amount': order_amount,
                    'telegram_contact': telegram_contact,
                    'is_new_user': not bool(user_result)
                })
                
                logger.info(f"Заявка успешно создана с ID={request_id} для пользователя {telegram_user_id}")
                
                # НОВОЕ: Отправляем уведомление в Telegram
                def send_notification():
                    """Отправка уведомления в отдельном потоке"""
                    try:
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
                            'username': username
                        }
                        
                        success = send_order_notification(notification_data)
                        if success:
                            logger.info(f"Уведомление о заявке #{request_id} успешно отправлено в Telegram")
                        else:
                            logger.warning(f"Не удалось отправить уведомление о заявке #{request_id}")
                            
                    except Exception as e:
                        logger.error(f"Ошибка при отправке уведомления о заявке #{request_id}: {e}")
                
                # Запускаем отправку уведомления в отдельном потоке
                try:
                    notification_thread = threading.Thread(target=send_notification)
                    notification_thread.daemon = True
                    notification_thread.start()
                    logger.info(f"Поток уведомления для заявки #{request_id} запущен")
                except Exception as e:
                    logger.error(f"Ошибка при запуске потока уведомления: {e}")
                
                return jsonify({
                    "success": True,
                    "request_id": request_id,
                    "message": "Заявка успешно отправлена! Менеджер свяжется с вами в рабочее время."
                })
            else:
                logger.error("Не удалось создать заявку - save_purchase_request вернул None")
                return jsonify({"error": "Ошибка при создании заявки"}), 500
                
        except Exception as e:
            logger.error(f"Ошибка при создании заявки: {str(e)}")
            return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

    # 3. Также добавьте эту функцию для тестирования уведомлений (опционально):

    @app.route('/api/test-notification', methods=['POST'])
    def test_notification():
        """Тестирование системы уведомлений (только для разработки)"""
        try:
            data = request.get_json()
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
                'username': 'test_user'
            }
            
            success = send_order_notification(test_data)
            
            if success:
                return jsonify({
                    "success": True,
                    "message": "Тестовое уведомление отправлено"
                })
            else:
                return jsonify({
                    "success": False,
                    "message": "Не удалось отправить тестовое уведомление"
                })
                
        except Exception as e:
            logger.error(f"Ошибка при тестировании уведомлений: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/orders', methods=['GET'])
    def api_get_orders():
        """API для получения списка заявок"""
        try:
            telegram_id = request.args.get('telegram_id')
            limit = int(request.args.get('limit', 10))
            
            if not telegram_id:
                return jsonify({"error": "Не указан telegram_id"}), 400
            
            # Получаем ID пользователя
            conn = connect_to_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM delivery_test.telegram_users WHERE telegram_id = %s", (str(telegram_id),))
            user_result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not user_result:
                return jsonify({"orders": [], "message": "Пользователь не найден"})
            
            telegram_user_id = user_result[0]
            orders = get_user_requests(telegram_user_id, limit)
            
            return jsonify({
                "success": True,
                "orders": orders,
                "total": len(orders)
            })
            
        except Exception as e:
            logger.error(f"Ошибка при получении заявок: {str(e)}")
            return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

    @app.route('/api/orders/<int:request_id>/status', methods=['PUT'])
    def api_update_order_status(request_id):
        """API для обновления статуса заявки"""
        try:
            data = request.get_json()
            
            if not data or 'status' not in data:
                return jsonify({"error": "Необходимо указать статус"}), 400
            
            new_status = data.get('status', '').strip()
            manager_notes = data.get('manager_notes', '').strip()
            
            # Валидируем статус
            valid_statuses = ['new', 'in_progress', 'completed', 'cancelled', 'on_hold']
            if new_status not in valid_statuses:
                return jsonify({"error": f"Недопустимый статус. Доступные: {', '.join(valid_statuses)}"}), 400
            
            # Обновляем статус
            updated_id = update_request_status(request_id, new_status, manager_notes)
            
            if updated_id:
                return jsonify({
                    "success": True,
                    "request_id": updated_id,
                    "new_status": new_status,
                    "message": "Статус заявки обновлен"
                })
            else:
                return jsonify({"error": "Заявка не найдена"}), 404
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса заявки: {str(e)}")
            return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

    @app.route('/api/orders/<int:request_id>', methods=['GET'])
    def api_get_order_details(request_id):
        """API для получения детальной информации о заявке"""
        try:
            order = get_request_by_id(request_id)
            
            if order:
                return jsonify({
                    "success": True,
                    "order": order
                })
            else:
                return jsonify({"error": "Заявка не найдена"}), 404
                
        except Exception as e:
            logger.error(f"Ошибка при получении заявки: {str(e)}")
            return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

    @app.route('/api/orders/stats', methods=['GET'])
    def api_get_orders_stats():
        """API для получения статистики заявок"""
        try:
            conn = connect_to_db()
            cursor = conn.cursor()
            
            # Общая статистика
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_orders,
                    COUNT(*) FILTER (WHERE status = 'new') as new_orders,
                    COUNT(*) FILTER (WHERE status = 'in_progress') as in_progress_orders,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed_orders,
                    COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled_orders,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') as orders_last_24h,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') as orders_last_week
                FROM delivery_test.purchase_requests
            """)
            
            stats = cursor.fetchone()
            
            # Статистика по дням (последние 7 дней)
            cursor.execute("""
                SELECT 
                    DATE(created_at AT TIME ZONE 'Europe/Moscow') as order_date,
                    COUNT(*) as orders_count
                FROM delivery_test.purchase_requests
                WHERE created_at >= NOW() - INTERVAL '7 days'
                GROUP BY DATE(created_at AT TIME ZONE 'Europe/Moscow')
                ORDER BY order_date DESC
            """)
            
            daily_stats = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return jsonify({
                "success": True,
                "stats": {
                    "total_orders": stats[0],
                    "new_orders": stats[1],
                    "in_progress_orders": stats[2],
                    "completed_orders": stats[3],
                    "cancelled_orders": stats[4],
                    "orders_last_24h": stats[5],
                    "orders_last_week": stats[6]
                },
                "daily_stats": [
                    {"date": str(day[0]), "orders": day[1]} 
                    for day in daily_stats
                ]
            })
            
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {str(e)}")
            return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

    @app.route('/admin/orders')
    def admin_orders_page():
        """Административная панель для управления заявками"""
        try:
            return render_template('admin_orders.html')
        except:
            return jsonify({
                "page": "admin_orders",
                "message": "Admin orders page - Template not found, showing JSON response",
                "endpoints": [
                    "GET /api/orders/stats - статистика заявок",
                    "GET /api/orders?telegram_id=XXX - заявки пользователя",
                    "PUT /api/orders/{id}/status - обновление статуса",
                    "GET /api/orders/{id} - детали заявки"
                ]
            })

    @app.route('/health')
    def health_check():
        """Проверка работоспособности модуля заявок"""
        try:
            conn = connect_to_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM delivery_test.purchase_requests")
            orders_count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            
            return jsonify({
                "status": "healthy",
                "module": "orders",
                "timestamp": get_moscow_time().isoformat(),
                "database": "connected",
                "total_orders": orders_count,
                "version": "2.3-orders"
            })
        except Exception as e:
            return jsonify({
                "status": "unhealthy",
                "module": "orders",
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
    
    logger.info("=== Запуск China Together Delivery Calculator - Orders Module v2.3 ===")
    
    # Инициализируем таблицы
    try:
        init_purchase_orders_tables()
        logger.info("✅ Таблицы заявок готовы")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации таблиц заявок: {str(e)}")
    
    # Регистрируем маршруты
    register_order_routes(app)
    logger.info("✅ Маршруты заявок зарегистрированы")
    
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
