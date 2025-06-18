from flask import Flask, render_template, request, jsonify, redirect, send_file
import psycopg2
from decimal import Decimal, getcontext, InvalidOperation
from urllib.parse import unquote, quote
from flask_cors import CORS
import logging
import json
from datetime import datetime, timedelta
import os
from functools import wraps
import io
import csv

# Настройка точности для Decimal
getcontext().prec = 6

# Создание приложения Flask
app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app, origins=["https://telegram.org", "*"])  # Разрешаем запросы от Telegram

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

# Подключение к базе данных
def connect_to_db():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {str(e)}")
        raise

# Декоратор для обработки ошибок базы данных
def handle_db_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в функции {func.__name__}: {str(e)}")
            return None
    return wrapper

# Функция для безопасного преобразования значений в Decimal
def safe_decimal(value, default=Decimal('0')):
    """Преобразует значение в Decimal."""
    try:
        if value is None:
            return default
        return Decimal(str(value).replace(',', '.'))
    except (InvalidOperation, ValueError, TypeError):
        logger.warning(f"Ошибка при преобразовании значения '{value}' в Decimal")
        return default

# Создание таблиц, если их нет
def init_database():
    """Инициализирует структуру базы данных"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        # Создаем схему, если её нет
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

# Сохранение данных пользователя Telegram
@handle_db_errors
def save_telegram_user(telegram_id, username, first_name=None, last_name=None):
    if not telegram_id:
        logger.warning("telegram_id отсутствует")
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
        logger.info(f"Пользователь сохранен/обновлен: telegram_id={telegram_id}, id={user_id}")
        return user_id
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка при сохранении пользователя: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

# Сохранение действия пользователя
@handle_db_errors
def save_user_action(telegram_id, action, details=None):
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO delivery_test.user_actions (telegram_user_id, action, details, created_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """, (str(telegram_id), action, json.dumps(details) if details else None))
        
        conn.commit()
        logger.info(f"Действие пользователя сохранено: {action}")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка при сохранении действия: {str(e)}")
    finally:
        cursor.close()
        conn.close()

# Сохранение входных данных
@handle_db_errors
def save_user_input_to_db(category, weight, length, width, height, cost, quantity, telegram_user_id=None):
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
        logger.info(f"Входные данные сохранены: ID={input_id}")
        return input_id
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка при сохранении входных данных: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

# Сохранение результатов расчета
@handle_db_errors
def save_user_calculation(
    telegram_user_id, category, total_weight, density, product_cost, insurance_rate,
    insurance_amount, volume, box_count, bag_total_fast, bag_total_regular,
    corners_total_fast, corners_total_regular, frame_total_fast, frame_total_regular,
    input_id=None
):
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
        logger.info(f"Результаты расчета сохранены: ID={calculation_id}")
        return calculation_id
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка при сохранении расчета: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

# Получение статистики
@handle_db_errors
def get_analytics_data():
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        # Общее количество расчетов
        cursor.execute("SELECT COUNT(*) FROM delivery_test.user_calculation")
        total_calculations = cursor.fetchone()[0]
        
        # Расчеты сегодня
        cursor.execute("""
            SELECT COUNT(*) FROM delivery_test.user_calculation 
            WHERE created_at >= CURRENT_DATE
        """)
        today_calculations = cursor.fetchone()[0]
        
        # Средний вес
        cursor.execute("SELECT AVG(total_weight) FROM delivery_test.user_calculation")
        avg_weight = cursor.fetchone()[0] or 0
        
        # Популярная категория
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM delivery_test.user_calculation 
            GROUP BY category 
            ORDER BY count DESC 
            LIMIT 1
        """)
        popular_category_data = cursor.fetchone()
        popular_category = popular_category_data[0] if popular_category_data else "Нет данных"
        
        # Активные пользователи за последние 7 дней
        cursor.execute("""
            SELECT COUNT(DISTINCT telegram_user_id) 
            FROM delivery_test.user_calculation 
            WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
        """)
        active_users = cursor.fetchone()[0]
        
        return {
            'total_calculations': total_calculations,
            'today_calculations': today_calculations,
            'avg_weight': float(avg_weight) if avg_weight else 0,
            'popular_category': popular_category,
            'active_users': active_users
        }
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

# Главная страница
@app.route('/')
def index():
    # Получаем параметры из URL (для Telegram Web App)
    telegram_id = request.args.get('telegram_id')
    username = request.args.get('username')
    
    # Сохраняем действие открытия страницы
    if telegram_id:
        save_user_action(telegram_id, 'page_opened', {'page': 'index'})
    
    return render_template('index.html')

# API для статистики (можно использовать для внешнего дашборда)
@app.route('/api/stats')
def get_stats():
    try:
        # Проверка токена для API
        api_token = request.headers.get('Authorization')
        expected_token = os.getenv('API_STATS_TOKEN', None)
        
        if expected_token and api_token != f"Bearer {expected_token}":
            return jsonify({"error": "Unauthorized"}), 401
            
        stats = get_analytics_data()
        if stats is None:
            return jsonify({"error": "Ошибка получения статистики"}), 500
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Ошибка в /api/stats: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Страница результатов
@app.route('/result')
def result():
    results_param = request.args.get('results', None)
    telegram_id = request.args.get('telegram_id')
    
    try:
        results = json.loads(unquote(results_param)) if results_param else {}
        
        # Сохраняем действие просмотра результатов
        if telegram_id:
            save_user_action(telegram_id, 'view_results', {'has_results': bool(results)})
        
        if not all(key in results for key in ["generalInformation", "bag", "corners", "frame"]):
            return render_template('result.html', error="Некорректная структура данных.")

        return render_template('result.html', results=results)
    except Exception as e:
        logger.error(f"Ошибка на странице результатов: {str(e)}")
        return render_template('result.html', error="Произошла ошибка при обработке данных.")

# Основной маршрут расчета
@app.route('/calculate', methods=['GET', 'POST'])
def calculate():
    try:
        # Получаем параметры
        if request.method == 'POST':
            data = request.get_json()
        else:
            data = request.args
        
        # Декодирование параметров
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
            logger.warning("Некорректные параметры для расчета")
            return jsonify({"error": "Не все параметры указаны корректно"}), 400

        # Сохраняем пользователя
        telegram_user_id = None
        if telegram_id and telegram_id != 'test_user':
            telegram_user_id = save_telegram_user(telegram_id, username)

        # Расчеты
        volume_per_box = (length / Decimal(100)) * (width / Decimal(100)) * (height / Decimal(100))
        total_volume = volume_per_box * quantity
        density = weight_per_box / volume_per_box if volume_per_box > 0 else Decimal('0')
        total_weight = weight_per_box * quantity
        cost_per_kg = cost / total_weight if total_weight > 0 else Decimal('0')

        # Определяем процент страхования
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
            SELECT min_weight, max_weight, coefficient_bag, bag, bag_packing_cost, bag_unloading_cost,
                   coefficient_corner, cardboard_corners, corner_packing_cost, corner_unloading_cost,
                   coefficient_frame, wooden_frame, frame_packing_cost, frame_unloading_cost
            FROM delivery_test.weight
            WHERE min_weight <= %s AND max_weight > %s
        """, (total_weight, total_weight))
        
        result_row_weight = cursor.fetchone()
        
        if not result_row_weight:
            cursor.close()
            conn.close()
            return jsonify({"error": f"Вес {total_weight} кг вне диапазона тарифов"}), 400

        # Преобразуем данные
        (
            min_weight, max_weight, packing_factor_bag, _, packaging_cost_bag, unload_cost_bag,
            additional_weight_corners, _, packaging_cost_corners, unload_cost_corners,
            additional_weight_frame, _, packaging_cost_frame, unload_cost_frame
        ) = [safe_decimal(value) for value in result_row_weight]

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

        (
            category_db, min_density, max_density, fast_car_cost_per_kg, regular_car_cost_per_kg
        ) = [safe_decimal(value) if isinstance(value, (int, float)) else value for value in result_row_density]

        cursor.close()
        conn.close()

        # Расчеты стоимости
        packed_weight_bag = packing_factor_bag + total_weight
        packed_weight_corners = additional_weight_corners + total_weight
        packed_weight_frame = additional_weight_frame + total_weight

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
                "packagingCost": float((packaging_cost_bag).quantize(Decimal('0.01'))),
                "unloadCost": float((unload_cost_bag).quantize(Decimal('0.01'))),
                "insurance": float(insurance.quantize(Decimal('0.01'))),
                "deliveryCostFast": float(delivery_cost_fast_bag),
                "deliveryCostRegular": float(delivery_cost_regular_bag),
                "totalFast": float(
                    (packaging_cost_bag + unload_cost_bag + insurance + delivery_cost_fast_bag).quantize(Decimal('0.01'))
                ),
                "totalRegular": float(
                    (packaging_cost_bag + unload_cost_bag + insurance + delivery_cost_regular_bag).quantize(Decimal('0.01'))
                )
            },
            "corners": {
                "packedWeight": float(packed_weight_corners.quantize(Decimal('0.01'))),
                "packagingCost": float((packaging_cost_corners).quantize(Decimal('0.01'))),
                "unloadCost": float((unload_cost_corners).quantize(Decimal('0.01'))),
                "insurance": float(insurance.quantize(Decimal('0.01'))),
                "deliveryCostFast": float(delivery_cost_fast_corners),
                "deliveryCostRegular": float(delivery_cost_regular_corners),
                "totalFast": float(
                    (packaging_cost_corners + unload_cost_corners + insurance + delivery_cost_fast_corners).quantize(Decimal('0.01'))
                ),
                "totalRegular": float(
                    (packaging_cost_corners + unload_cost_corners + insurance + delivery_cost_regular_corners).quantize(Decimal('0.01'))
                )
            },
            "frame": {
                "packedWeight": float(packed_weight_frame.quantize(Decimal('0.01'))),
                "packagingCost": float((packaging_cost_frame).quantize(Decimal('0.01'))),
                "unloadCost": float((unload_cost_frame).quantize(Decimal('0.01'))),
                "insurance": float(insurance.quantize(Decimal('0.01'))),
                "deliveryCostFast": float(delivery_cost_fast_frame),
                "deliveryCostRegular": float(delivery_cost_regular_frame),
                "totalFast": float(
                    (packaging_cost_frame + unload_cost_frame + insurance + delivery_cost_fast_frame).quantize(Decimal('0.01'))
                ),
                "totalRegular": float(
                    (packaging_cost_frame + unload_cost_frame + insurance + delivery_cost_regular_frame).quantize(Decimal('0.01'))
                )
            }
        }

        # Сохраняем данные
        input_id = save_user_input_to_db(
            category=category,
            weight=float(weight_per_box),
            length=float(length),
            width=float(width),
            height=float(height),
            cost=float(cost),
            quantity=quantity,
            telegram_user_id=telegram_user_id
        )

        # Сохраняем расчет
        calculation_id = save_user_calculation(
            telegram_user_id=telegram_user_id,
            category=category,
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

        logger.info(f"Расчет выполнен для пользователя {username} (ID: {telegram_id})")

        # Возвращаем результат
        if request.method == 'POST':
            return jsonify(results)
        else:
            # Перенаправляем на страницу результатов
            results_url = f"/result?results={quote(json.dumps(results))}"
            if telegram_id:
                results_url += f"&telegram_id={telegram_id}"
            return redirect(results_url)

    except Exception as e:
        logger.error(f"Ошибка в calculate: {str(e)}")
        return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

# Генерация CSV файла
@app.route('/generate_csv', methods=['POST'])
def generate_csv():
    try:
        data = request.get_json()
        telegram_id = data.get('telegram_id')
        results = data.get('results')
        
        if not results:
            return jsonify({"error": "Нет данных для экспорта"}), 400
        
        # Создаем CSV в памяти
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Заголовок
        writer.writerow(['China Together - Расчет доставки'])
        writer.writerow(['Дата расчета:', datetime.now().strftime('%d.%m.%Y %H:%M')])
        writer.writerow([])
        
        # Общая информация
        writer.writerow(['ОБЩАЯ ИНФОРМАЦИЯ'])
        info = results.get('generalInformation', {})
        writer.writerow(['Категория:', info.get('category', '')])
        writer.writerow(['Общий вес (кг):', info.get('weight', '')])
        writer.writerow(['Плотность (кг/м³):', info.get('density', '')])
        writer.writerow(['Стоимость товара ($):', info.get('productCost', '')])
        writer.writerow(['Страховка:', f"{info.get('insuranceRate', '')} (${info.get('insuranceAmount', '')})"])
        writer.writerow(['Объем (м³):', info.get('volume', '')])
        writer.writerow(['Количество коробок:', info.get('boxCount', '')])
        writer.writerow([])
        
        # Сравнение вариантов
        writer.writerow(['СРАВНЕНИЕ ВАРИАНТОВ ДОСТАВКИ'])
        writer.writerow(['Тип упаковки', 'Быстрая доставка ($)', 'Обычная доставка ($)'])
        writer.writerow(['Мешок', results['bag']['totalFast'], results['bag']['totalRegular']])
        writer.writerow(['Картонные уголки', results['corners']['totalFast'], results['corners']['totalRegular']])
        writer.writerow(['Деревянный каркас', results['frame']['totalFast'], results['frame']['totalRegular']])
        writer.writerow([])
        
        # Детальная разбивка
        for pack_type, pack_name in [('bag', 'МЕШОК'), ('corners', 'КАРТОННЫЕ УГОЛКИ'), ('frame', 'ДЕРЕВЯННЫЙ КАРКАС')]:
            writer.writerow([f'ДЕТАЛИ - {pack_name}'])
            pack_data = results.get(pack_type, {})
            writer.writerow(['Вес с упаковкой (кг):', pack_data.get('packedWeight', '')])
            writer.writerow(['Стоимость упаковки ($):', pack_data.get('packagingCost', '')])
            writer.writerow(['Стоимость разгрузки ($):', pack_data.get('unloadCost', '')])
            writer.writerow(['Доставка быстрая ($):', pack_data.get('deliveryCostFast', '')])
            writer.writerow(['Доставка обычная ($):', pack_data.get('deliveryCostRegular', '')])
            writer.writerow(['Итого быстрая ($):', pack_data.get('totalFast', '')])
            writer.writerow(['Итого обычная ($):', pack_data.get('totalRegular', '')])
            writer.writerow([])
        
        # Сохраняем действие
        if telegram_id:
            save_user_action(telegram_id, 'csv_exported', {'timestamp': datetime.now().isoformat()})
        
        # Конвертируем в байты
        output.seek(0)
        csv_bytes = io.BytesIO(output.getvalue().encode('utf-8-sig'))  # utf-8-sig для корректного отображения в Excel
        
        return send_file(
            csv_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'china_together_calculation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
        
    except Exception as e:
        logger.error(f"Ошибка при генерации CSV: {str(e)}")
        return jsonify({"error": "Ошибка при создании файла"}), 500

# История расчетов пользователя
@app.route('/api/user_history/<telegram_id>')
def get_user_history(telegram_id):
    try:
        conn = connect_to_db()
        cursor = conn.cursor()
        
        # Получаем историю расчетов
        cursor.execute("""
            SELECT 
                c.id,
                c.category,
                c.total_weight,
                c.product_cost,
                c.bag_total_fast,
                c.bag_total_regular,
                c.corners_total_fast,
                c.corners_total_regular,
                c.frame_total_fast,
                c.frame_total_regular,
                c.created_at,
                i.quantity
            FROM delivery_test.user_calculation c
            LEFT JOIN delivery_test.user_inputs i ON c.user_input_id = i.id
            JOIN delivery_test.telegram_users u ON c.telegram_user_id = u.id
            WHERE u.telegram_id = %s
            ORDER BY c.created_at DESC
            LIMIT 50
        """, (str(telegram_id),))
        
        columns = [desc[0] for desc in cursor.description]
        history = []
        
        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            # Конвертируем datetime в строку
            record['created_at'] = record['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            history.append(record)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'history': history,
            'count': len(history)
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения истории: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Проверка здоровья приложения
@app.route('/health')
def health_check():
    try:
        # Проверяем подключение к БД
        conn = connect_to_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": "connected",
            "version": "2.0"
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }), 500

# Webhook для Telegram (если понадобится в будущем)
@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    try:
        data = request.get_json()
        logger.info(f"Получен webhook от Telegram: {data}")
        
        # Здесь можно обрабатывать данные от Telegram
        # Например, когда пользователь закрывает Web App
        
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Ошибка в webhook: {str(e)}")
        return jsonify({"ok": False, "error": str(e)}), 500

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

# Middleware для логирования запросов
@app.before_request
def log_request():
    logger.info(f"{request.method} {request.path} - IP: {request.remote_addr}")
    if request.args:
        logger.info(f"Query params: {dict(request.args)}")

# Middleware для CORS и безопасности
@app.after_request
def after_request(response):
    # CORS заголовки для Telegram Web App
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    
    # Заголовки безопасности
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'ALLOWALL'  # Для работы в Telegram
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    return response

# Функция для очистки старых данных (можно запускать по крону)
def cleanup_old_data(days=90):
    """Удаляет данные старше указанного количества дней"""
    try:
        conn = connect_to_db()
        cursor = conn.cursor()
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Удаляем старые действия
        cursor.execute("""
            DELETE FROM delivery_test.user_actions 
            WHERE created_at < %s
        """, (cutoff_date,))
        
        deleted_actions = cursor.rowcount
        
        # Удаляем старые расчеты (но оставляем пользователей)
        cursor.execute("""
            DELETE FROM delivery_test.user_calculation 
            WHERE created_at < %s
        """, (cutoff_date,))
        
        deleted_calculations = cursor.rowcount
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Очистка завершена: удалено {deleted_actions} действий и {deleted_calculations} расчетов")
        
    except Exception as e:
        logger.error(f"Ошибка при очистке данных: {str(e)}")

# CLI команды для управления
@app.cli.command()
def init_db():
    """Инициализировать базу данных"""
    init_database()
    print("База данных инициализирована")

@app.cli.command()
def cleanup():
    """Очистить старые данные"""
    cleanup_old_data()
    print("Старые данные очищены")

if __name__ == '__main__':
    logger.info("=== Запуск China Together Delivery Calculator API v2.0 ===")
    
    # Инициализируем БД при первом запуске
    try:
        init_database()
        logger.info("✅ База данных готова к работе")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {str(e)}")
    
    # Проверяем подключение
    try:
        conn = connect_to_db()
        conn.close()
        logger.info("✅ Подключение к базе данных успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к БД: {str(e)}")
        logger.warning("⚠️ Приложение может работать нестабильно!")
    
    # Запускаем сервер
    app.run(
        host='0.0.0.0',
        port=8061,
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        threaded=True
    )
