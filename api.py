from flask import Flask, render_template, request, jsonify, redirect
import psycopg2
from decimal import Decimal, getcontext, InvalidOperation
from urllib.parse import unquote, quote
from flask_cors import CORS
import logging
import json
from datetime import datetime, timedelta
import os
from functools import wraps
import re

# Настройка точности для Decimal
getcontext().prec = 6

# Создание приложения Flask
app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app, origins=["https://telegram.org", "*"])

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

# Конфигурация базы данных
DB_CONFIG = {
    "dbname": "delivery_db",
    "user": "chinatogether",
    "password": "O99ri1@",
    "host": "localhost",
    "port": "5432",
    "connect_timeout": 10
}

def connect_to_db():
    """Подключение к базе данных"""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {str(e)}")
        raise

def safe_decimal(value, default=Decimal('0')):
    """Безопасное преобразование в Decimal"""
    try:
        if value is None:
            return default
        return Decimal(str(value).replace(',', '.'))
    except (InvalidOperation, ValueError, TypeError):
        logger.warning(f"Ошибка при преобразовании значения '{value}' в Decimal")
        return default

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

def init_database():
    """Создание таблиц в базе данных"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        # Создаем схему
        cursor.execute("CREATE SCHEMA IF NOT EXISTS delivery_test")
        
        # Таблица пользователей Telegram
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.telegram_users (
                id SERIAL PRIMARY KEY,
                telegram_id VARCHAR(255) UNIQUE NOT NULL,
                username VARCHAR(255),
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица входных данных
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.user_inputs (
                id SERIAL PRIMARY KEY,
                telegram_user_id INTEGER REFERENCES delivery_test.telegram_users(id),
                category VARCHAR(255),
                weight DECIMAL(10,2),
                length DECIMAL(10,2),
                width DECIMAL(10,2),
                height DECIMAL(10,2),
                cost DECIMAL(10,2),
                quantity INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица расчетов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.user_calculation (
                id SERIAL PRIMARY KEY,
                telegram_user_id INTEGER REFERENCES delivery_test.telegram_users(id),
                user_input_id INTEGER REFERENCES delivery_test.user_inputs(id),
                category VARCHAR(255),
                total_weight DECIMAL(10,2),
                density DECIMAL(10,2),
                product_cost DECIMAL(10,2),
                insurance_rate DECIMAL(5,2),
                insurance_amount DECIMAL(10,2),
                volume DECIMAL(10,4),
                box_count INTEGER,
                bag_total_fast DECIMAL(10,2),
                bag_total_regular DECIMAL(10,2),
                corners_total_fast DECIMAL(10,2),
                corners_total_regular DECIMAL(10,2),
                frame_total_fast DECIMAL(10,2),
                frame_total_regular DECIMAL(10,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица заявок на выкуп и доставку
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица действий пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.user_actions (
                id SERIAL PRIMARY KEY,
                telegram_user_id VARCHAR(255),
                action VARCHAR(255),
                details JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        logger.info("База данных успешно инициализирована")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка при инициализации базы данных: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def save_telegram_user(telegram_id, username, first_name=None, last_name=None):
    """Сохранение пользователя Telegram"""
    if not telegram_id:
        return None
        
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO delivery_test.telegram_users (telegram_id, username, first_name, last_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE 
            SET username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_activity = CURRENT_TIMESTAMP
            RETURNING id
        """, (str(telegram_id), username, first_name, last_name))
        
        user_id = cursor.fetchone()[0]
        conn.commit()
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
        cursor.execute("""
            INSERT INTO delivery_test.user_actions (telegram_user_id, action, details, created_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """, (str(telegram_id), action, json.dumps(details) if details else None))
        
        conn.commit()
        
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def save_user_input_to_db(category, weight, length, width, height, cost, quantity, telegram_user_id=None):
    """Сохранение входных данных пользователя"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO delivery_test.user_inputs (
                category, weight, length, width, height, cost, quantity, telegram_user_id, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING id
        """, (category, weight, length, width, height, cost, quantity, telegram_user_id))
        
        input_id = cursor.fetchone()[0]
        conn.commit()
        return input_id
        
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def save_user_calculation(telegram_user_id, category, total_weight, density, product_cost, 
                         insurance_rate, insurance_amount, volume, box_count, bag_total_fast, 
                         bag_total_regular, corners_total_fast, corners_total_regular, 
                         frame_total_fast, frame_total_regular, input_id=None):
    """Сохранение результатов расчета"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO delivery_test.user_calculation (
                telegram_user_id, category, total_weight, density, product_cost, insurance_rate,
                insurance_amount, volume, box_count, bag_total_fast, bag_total_regular,
                corners_total_fast, corners_total_regular, frame_total_fast, frame_total_regular,
                user_input_id, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING id
        """, (
            telegram_user_id, category, total_weight, density, product_cost, insurance_rate,
            insurance_amount, volume, box_count, bag_total_fast, bag_total_regular,
            corners_total_fast, corners_total_regular, frame_total_fast, frame_total_regular,
            input_id
        ))
        
        calculation_id = cursor.fetchone()[0]
        conn.commit()
        return calculation_id
        
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def save_purchase_request(telegram_user_id, email, telegram_contact, supplier_link, order_amount, 
                         promo_code, additional_notes, terms_accepted, calculation_id=None):
    """Сохранение заявки на выкуп"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO delivery_test.purchase_requests (
                telegram_user_id, calculation_id, email, telegram_contact, supplier_link,
                order_amount, promo_code, additional_notes, terms_accepted, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """, (
            telegram_user_id, calculation_id, email, telegram_contact, supplier_link,
            order_amount, promo_code, additional_notes, terms_accepted
        ))
        
        request_id = cursor.fetchone()[0]
        conn.commit()
        return request_id
        
    finally:
        cursor.close()
        conn.close()

# МАРШРУТЫ

@app.route('/')
def index():
    """Главная страница"""
    telegram_id = request.args.get('telegram_id')
    username = request.args.get('username')
    
    if telegram_id:
        save_user_action(telegram_id, 'page_opened', {'page': 'index'})
    
    return render_template('index.html')

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
    
    return render_template('order.html')

@app.route('/result')
def result():
    """Страница результатов"""
    results_param = request.args.get('results', None)
    telegram_id = request.args.get('telegram_id')
    calculation_id = request.args.get('calculation_id')
    
    try:
        results = json.loads(unquote(results_param)) if results_param else {}
        
        if telegram_id:
            save_user_action(telegram_id, 'view_results', {
                'has_results': bool(results),
                'calculation_id': calculation_id
            })
        
        if not results or not all(key in results for key in ["generalInformation", "bag", "corners", "frame"]):
            return render_template('result.html', error="Некорректные данные для отображения.")

        return render_template('result.html', results=results, calculation_id=calculation_id)
        
    except Exception as e:
        logger.error(f"Ошибка на странице результатов: {str(e)}")
        return render_template('result.html', error="Произошла ошибка при обработке данных.")

@app.route('/calculate', methods=['GET', 'POST'])
def calculate():
    """Основной расчет доставки"""
    try:
        # Получаем данные
        if request.method == 'POST':
            data = request.get_json()
        else:
            data = request.args
        
        # Извлекаем параметры
        category = unquote(str(data.get('category', ''))).strip()
        weight_per_box = safe_decimal(data.get('weight', 0))
        length = safe_decimal(data.get('length', 0))
        width = safe_decimal(data.get('width', 0))
        height = safe_decimal(data.get('height', 0))
        cost = safe_decimal(data.get('cost', 0))
        quantity = int(data.get('quantity', 1))
        telegram_id = data.get('telegram_id')
        username = data.get('username')

        # Валидация
        if not all([category, weight_per_box > 0, length > 0, width > 0, height > 0, cost > 0, quantity > 0]):
            return jsonify({"error": "Не все параметры указаны корректно"}), 400

        # Сохраняем пользователя
        telegram_user_id = None
        if telegram_id and telegram_id != 'test_user':
            telegram_user_id = save_telegram_user(telegram_id, username)

        # Выполняем расчеты
        volume_per_box = (length / Decimal(100)) * (width / Decimal(100)) * (height / Decimal(100))
        total_volume = volume_per_box * quantity
        density = weight_per_box / volume_per_box if volume_per_box > 0 else Decimal('0')
        total_weight = weight_per_box * quantity

        # Определяем процент страхования
        cost_per_kg = cost / total_weight if total_weight > 0 else Decimal('0')
        if cost_per_kg < 20:
            insurance_rate = Decimal('0.01')
        else:
            insurance_rate = Decimal('0.02')
        insurance = cost * insurance_rate

        # Получаем тарифы из БД
        conn = connect_to_db()
        cursor = conn.cursor()

        # Тарифы по весу
        cursor.execute("""
            SELECT min_weight, max_weight, coefficient_bag,  bag_packing_cost, bag_unloading_cost,
                   coefficient_corner,  corner_packing_cost, corner_unloading_cost,
                   coefficient_frame,frame_packing_cost, frame_unloading_cost
            FROM delivery_test.weight
            WHERE min_weight <= %s AND max_weight > %s
        """, (total_weight, total_weight))
        
        result_row_weight = cursor.fetchone()
        if not result_row_weight:
            cursor.close()
            conn.close()
            return jsonify({"error": f"Вес {total_weight} кг вне диапазона тарифов"}), 400

        (min_weight, max_weight, packing_factor_bag,  packaging_cost_bag, unload_cost_bag,
         additional_weight_corners,  packaging_cost_corners, unload_cost_corners,
         additional_weight_frame,  packaging_cost_frame, unload_cost_frame) = [safe_decimal(value) for value in result_row_weight]

        # Тарифы по плотности
        cursor.execute("""
            SELECT category, min_density, max_density, fast_delivery_cost, regular_delivery_cost
            FROM delivery_test.density 
            WHERE category = %s AND min_density <= %s AND max_density > %s
        """, (category, density, density))
        
        result_row_density = cursor.fetchone()
        if not result_row_density:
            cursor.close()
            conn.close()
            return jsonify({"error": f"Плотность {density} кг/м³ вне диапазона для '{category}'"}), 400

        (category_db, min_density, max_density, fast_car_cost_per_kg, regular_car_cost_per_kg) = [
            safe_decimal(value) if isinstance(value, (int, float)) else value for value in result_row_density]

        cursor.close()
        conn.close()

        # Расчеты стоимости для каждого типа упаковки
        packed_weight_bag = packing_factor_bag + total_weight
        packed_weight_corners = additional_weight_corners + total_weight
        packed_weight_frame = additional_weight_frame + total_weight

        # Расчет страховки для каждого типа
        cost_per_bag = cost / packed_weight_bag if packed_weight_bag > 0 else Decimal('0')
        cost_per_corners = cost / packed_weight_corners if packed_weight_corners > 0 else Decimal('0')
        cost_per_frame = cost / packed_weight_frame if packed_weight_frame > 0 else Decimal('0')

        insurance_bag = cost * (Decimal('0.01') if cost_per_bag < 20 else Decimal('0.02'))
        insurance_corners = cost * (Decimal('0.01') if cost_per_corners < 20 else Decimal('0.02'))
        insurance_frame = cost * (Decimal('0.01') if cost_per_frame < 20 else Decimal('0.02'))

        # Расчет доставки
        delivery_cost_fast_bag = (fast_car_cost_per_kg * packed_weight_bag).quantize(Decimal('0.01'))
        delivery_cost_regular_bag = (regular_car_cost_per_kg * packed_weight_bag).quantize(Decimal('0.01'))
        delivery_cost_fast_corners = (fast_car_cost_per_kg * packed_weight_corners).quantize(Decimal('0.01'))
        delivery_cost_regular_corners = (regular_car_cost_per_kg * packed_weight_corners).quantize(Decimal('0.01'))
        delivery_cost_fast_frame = (fast_car_cost_per_kg * packed_weight_frame).quantize(Decimal('0.01'))
        delivery_cost_regular_frame = (regular_car_cost_per_kg * packed_weight_frame).quantize(Decimal('0.01'))

        # Формируем результаты
        results = {
            "generalInformation": {
                "category": category,
                "fast_car_cost_per_kg":float(fast_car_cost_per_kg.quantize(Decimal('0.01'))),
                "regular_car_cost_per_kg":float(regular_car_cost_per_kg.quantize(Decimal('0.01'))),
                "weight": float(total_weight.quantize(Decimal('0.01'))),
                "density": float(density.quantize(Decimal('0.01'))),
                "productCost": float(cost),
                "insuranceRate": f"{insurance_rate * Decimal('100'):.0f}%",
                "insuranceAmount": float(insurance.quantize(Decimal('0.01'))),
                "volume": float(total_volume.quantize(Decimal('0.01'))),
                "boxCount": quantity
            },
            "bag": {
                "packedWeight": float(packed_weight_bag.quantize(Decimal('0.01'))),
                "packagingCost": float(packaging_cost_bag.quantize(Decimal('0.01'))),
                "unloadCost": float(unload_cost_bag.quantize(Decimal('0.01'))),
                "insurance": float(insurance_bag.quantize(Decimal('0.01'))),
                "insuranceRate": f"{(insurance_bag/cost * Decimal('100')).quantize(Decimal('1')):.0f}%",
                "deliveryCostFast": float(delivery_cost_fast_bag),
                "deliveryCostRegular": float(delivery_cost_regular_bag),
                "totalFast": float((packaging_cost_bag + unload_cost_bag + insurance_bag + delivery_cost_fast_bag).quantize(Decimal('0.01'))),
                "totalRegular": float((packaging_cost_bag + unload_cost_bag + insurance_bag + delivery_cost_regular_bag).quantize(Decimal('0.01')))
            },
            "corners": {
                "packedWeight": float(packed_weight_corners.quantize(Decimal('0.01'))),
                "packagingCost": float(packaging_cost_corners.quantize(Decimal('0.01'))),
                "unloadCost": float(unload_cost_corners.quantize(Decimal('0.01'))),
                "insurance": float(insurance_corners.quantize(Decimal('0.01'))),
                "insuranceRate": f"{(insurance_corners/cost * Decimal('100')).quantize(Decimal('1')):.0f}%",
                "deliveryCostFast": float(delivery_cost_fast_corners),
                "deliveryCostRegular": float(delivery_cost_regular_corners),
                "totalFast": float((packaging_cost_corners + unload_cost_corners + insurance_corners + delivery_cost_fast_corners).quantize(Decimal('0.01'))),
                "totalRegular": float((packaging_cost_corners + unload_cost_corners + insurance_corners + delivery_cost_regular_corners).quantize(Decimal('0.01')))
            },
            "frame": {
                "packedWeight": float(packed_weight_frame.quantize(Decimal('0.01'))),
                "packagingCost": float(packaging_cost_frame.quantize(Decimal('0.01'))),
                "unloadCost": float(unload_cost_frame.quantize(Decimal('0.01'))),
                "insurance": float(insurance_frame.quantize(Decimal('0.01'))),
                "insuranceRate": f"{(insurance_frame/cost * Decimal('100')).quantize(Decimal('1')):.0f}%",
                "deliveryCostFast": float(delivery_cost_fast_frame),
                "deliveryCostRegular": float(delivery_cost_regular_frame),
                "totalFast": float((packaging_cost_frame + unload_cost_frame + insurance_frame + delivery_cost_fast_frame).quantize(Decimal('0.01'))),
                "totalRegular": float((packaging_cost_frame + unload_cost_frame + insurance_frame + delivery_cost_regular_frame).quantize(Decimal('0.01')))
            }
        }

        # Сохраняем данные в БД
        input_id = save_user_input_to_db(
            category=category, weight=float(weight_per_box), length=float(length),
            width=float(width), height=float(height), cost=float(cost),
            quantity=quantity, telegram_user_id=telegram_user_id
        )

        calculation_id = save_user_calculation(
            telegram_user_id=telegram_user_id, category=category,
            total_weight=float(total_weight.quantize(Decimal('0.01'))),
            density=float(density.quantize(Decimal('0.01'))),
            product_cost=float(cost),
            insurance_rate=float(insurance_rate * Decimal('100')),
            insurance_amount=float(insurance.quantize(Decimal('0.01'))),
            volume=float(total_volume.quantize(Decimal('0.01'))),
            box_count=quantity,
            bag_total_fast=float(results["bag"]["totalFast"]),
            bag_total_regular=float(results["bag"]["totalRegular"]),
            corners_total_fast=float(results["corners"]["totalFast"]),
            corners_total_regular=float(results["corners"]["totalRegular"]),
            frame_total_fast=float(results["frame"]["totalFast"]),
            frame_total_regular=float(results["frame"]["totalRegular"]),
            input_id=input_id
        )

        # Сохраняем действие
        if telegram_id:
            save_user_action(telegram_id, 'calculation_completed', {
                'calculation_id': calculation_id,
                'category': category,
                'total_weight': float(total_weight)
            })

        # Возвращаем результат
        if request.method == 'POST':
            return jsonify(results)
        else:
            results_url = f"/result?results={quote(json.dumps(results))}&calculation_id={calculation_id}"
            if telegram_id:
                results_url += f"&telegram_id={telegram_id}"
            return redirect(results_url)

    except Exception as e:
        logger.error(f"Ошибка в calculate: {str(e)}")
        return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

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
        
        # Валидация
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
        
        # Получаем telegram_user_id
        conn = connect_to_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM delivery_test.telegram_users WHERE telegram_id = %s", (str(telegram_id),))
        user_result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user_result:
            return jsonify({"error": "Пользователь не найден"}), 404
        
        telegram_user_id = user_result[0]
        
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
                'order_amount': order_amount
            })
            
            return jsonify({
                "success": True,
                "request_id": request_id,
                "message": "Заявка успешно отправлена! Менеджер свяжется с вами в рабочее время."
            })
        else:
            return jsonify({"error": "Ошибка при создании заявки"}), 500
            
    except Exception as e:
        logger.error(f"Ошибка при создании заявки: {str(e)}")
        return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

@app.route('/health')
def health_check():
    """Проверка работоспособности приложения"""
    try:
        conn = connect_to_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": "connected",
            "version": "2.1"
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }), 500

@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        return jsonify({"error": "Endpoint не найден"}), 404
    return render_template('error.html', error="Страница не найдена"), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Внутренняя ошибка сервера: {str(error)}")
    if request.path.startswith('/api/'):
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500
    return render_template('error.html', error="Внутренняя ошибка сервера"), 500

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

if __name__ == '__main__':
    logger.info("=== Запуск China Together Delivery Calculator ===")
    
    # Инициализируем БД
    try:
        init_database()
        logger.info("✅ База данных готова")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {str(e)}")
    
    # Запускаем сервер
    app.run(
        host='0.0.0.0',
        port=8061,
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        threaded=True
    )
