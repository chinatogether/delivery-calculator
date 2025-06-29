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
from dotenv import load_dotenv
import re
import pytz
import threading

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

def get_current_exchange_rate():
    """Получение текущего курса CNY/USD из БД (сколько юаней за 1 доллар)"""
    try:
        conn = connect_to_db()
        cursor = conn.cursor()
        
        # Получаем последний курс из БД
        cursor.execute("""
            SELECT rate, recorded_at, source 
            FROM delivery_test.exchange_rates 
            WHERE currency_pair = 'CNY/USD' 
            ORDER BY recorded_at DESC 
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            rate, recorded_at, source = result
            logger.info(f"Получен курс CNY/USD из БД: {rate} юаней за 1$ (обновлен: {recorded_at}, источник: {source})")
            return safe_decimal(rate)
        else:
            # Если курса нет в БД, возвращаем фиксированный курс и записываем его
            logger.warning("Курс не найден в БД, устанавливаем фиксированный курс 7.20 юаней за 1$")
            default_rate = Decimal('7.20')
            
            # Записываем фиксированный курс в БД
            try:
                conn = connect_to_db()
                cursor = conn.cursor()
                moscow_time = get_moscow_time()
                cursor.execute("""
                    INSERT INTO delivery_test.exchange_rates (currency_pair, rate, recorded_at, source, notes)
                    VALUES (%s, %s, %s, %s, %s)
                """, ('CNY/USD', float(default_rate), moscow_time, 'system_default', 'Автоматически установленный курс по умолчанию'))
                conn.commit()
                cursor.close()
                conn.close()
                logger.info("Фиксированный курс 7.20 записан в БД")
            except Exception as e:
                logger.error(f"Ошибка при записи фиксированного курса: {e}")
            
            return default_rate
        
    except Exception as e:
        logger.error(f"Ошибка при получении курса валют из БД: {str(e)}")
        # Возвращаем фиксированный курс как fallback (сколько юаней за 1 доллар)
        logger.warning("Используем резервный курс 7.20 юаней за 1$ из-за ошибки БД")
        return Decimal('7.20')


def convert_cny_to_usd(amount_cny):
    """Конвертация из юаней в доллары (делим на курс, так как курс показывает сколько юаней за 1$)"""
    rate = get_current_exchange_rate()  # Сколько юаней за 1 доллар
    return amount_cny / rate  # Делим юани на курс

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
                created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow'),
                last_activity TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow')
            )
        """)
        
        # Таблица курсов валют
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.exchange_rates (
                id SERIAL PRIMARY KEY,
                currency_pair VARCHAR(10) NOT NULL,
                rate DECIMAL(10,4) NOT NULL,
                recorded_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow'),
                source VARCHAR(255),
                notes TEXT
            )
        """)
        
        # Создаем индекс для быстрого поиска
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_exchange_rates_pair_date 
            ON delivery_test.exchange_rates (currency_pair, recorded_at DESC)
        """)
        
        # Таблица входных данных пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.user_inputs (
                id SERIAL PRIMARY KEY,
                telegram_user_id INTEGER REFERENCES delivery_test.telegram_users(id),
                category VARCHAR(255),
                total_weight DECIMAL(10,2),
                cost_cny DECIMAL(10,2),
                cost_usd DECIMAL(10,2),
                exchange_rate DECIMAL(10,4),
                volume DECIMAL(10,4),
                use_box_dimensions BOOLEAN DEFAULT FALSE,
                quantity INTEGER,
                weight_per_box DECIMAL(10,2),
                length DECIMAL(10,2),
                width DECIMAL(10,2),
                height DECIMAL(10,2),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow')
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
                product_cost_cny DECIMAL(10,2),
                product_cost_usd DECIMAL(10,2),
                exchange_rate DECIMAL(10,4),
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
                created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow')
            )
        """)
        
        # Таблица действий пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.user_actions (
                id SERIAL PRIMARY KEY,
                telegram_user_id VARCHAR(255),
                action VARCHAR(255),
                details JSON,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow')
            )
        """)
        
        # Инициализируем курсы валют если их нет
        cursor.execute("""
            SELECT COUNT(*) FROM delivery_test.exchange_rates 
            WHERE currency_pair = 'CNY/USD'
        """)
        
        count = cursor.fetchone()[0]
        
        if count == 0:
            # Добавляем первоначальный курс валют (7.20 юаней за 1 доллар)
            moscow_time = get_moscow_time()
            cursor.execute("""
                INSERT INTO delivery_test.exchange_rates (currency_pair, rate, recorded_at, source, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, ('CNY/USD', 7.20, moscow_time, 'initial_setup', 'Курс: сколько юаней за 1 доллар'))
            
            logger.info("✅ Добавлен начальный курс: 7.20 юаней за 1$")
        
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
        
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def save_user_input_to_db(category, total_weight, cost_cny, cost_usd, exchange_rate, volume=None, 
                         use_box_dimensions=False, quantity=None, weight_per_box=None,
                         length=None, width=None, height=None, telegram_user_id=None):
    """Сохранение входных данных пользователя с улучшенным логированием"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        moscow_time = get_moscow_time()
        
        # Логируем что пытаемся сохранить
        logger.info(f"💾 Попытка сохранения user_input: category={category}, weight={total_weight}, cost_cny={cost_cny}")
        logger.info(f"📊 Параметры: volume={volume}, use_box_dimensions={use_box_dimensions}, telegram_user_id={telegram_user_id}")
        
        cursor.execute("""
            INSERT INTO delivery_test.user_inputs (
                category, total_weight, cost_cny, cost_usd, exchange_rate, volume, use_box_dimensions, 
                quantity, weight_per_box, length, width, height, telegram_user_id, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (category, total_weight, cost_cny, cost_usd, exchange_rate, volume, use_box_dimensions, 
              quantity, weight_per_box, length, width, height, telegram_user_id, moscow_time))
        
        input_id = cursor.fetchone()[0]
        conn.commit()
        
        logger.info(f"✅ user_input успешно сохранен с ID={input_id}")
        return input_id
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Ошибка сохранения user_input: {str(e)}")
        logger.error(f"📋 Данные которые пытались сохранить: category={category}, total_weight={total_weight}")
        raise  # Перебрасываем исключение чтобы handle_db_errors его обработал
    finally:
        cursor.close()
        conn.close()

@handle_db_errors
def save_user_calculation(telegram_user_id, category, total_weight, density, product_cost_cny, 
                         product_cost_usd, exchange_rate, insurance_rate, insurance_amount, 
                         volume, box_count, bag_total_fast, bag_total_regular, corners_total_fast, 
                         corners_total_regular, frame_total_fast, frame_total_regular, input_id=None):
    """Сохранение результатов расчета"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        moscow_time = get_moscow_time()
        cursor.execute("""
            INSERT INTO delivery_test.user_calculation (
                telegram_user_id, category, total_weight, density, product_cost_cny, product_cost_usd,
                exchange_rate, insurance_rate, insurance_amount, volume, box_count, bag_total_fast, 
                bag_total_regular, corners_total_fast, corners_total_regular, frame_total_fast, 
                frame_total_regular, user_input_id, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            telegram_user_id, category, total_weight, density, product_cost_cny, product_cost_usd,
            exchange_rate, insurance_rate, insurance_amount, volume, box_count, bag_total_fast, 
            bag_total_regular, corners_total_fast, corners_total_regular, frame_total_fast, 
            frame_total_regular, input_id, moscow_time
        ))
        
        calculation_id = cursor.fetchone()[0]
        conn.commit()
        return calculation_id
        
    finally:
        cursor.close()
        conn.close()

# МАРШРУТЫ ДЛЯ РАСЧЕТОВ

@app.route('/')
def homepage():
    """Главная страница сайта"""
    try:
        return render_template('homepage.html')
    except:
        return jsonify({
            "status": "ok",
            "message": "China Together Delivery Calculator - Homepage",
            "version": "2.3"
        })

@app.route('/calculate')
def index():
    """Страница калькулятора для Telegram бота"""
    telegram_id = request.args.get('telegram_id')
    username = request.args.get('username')
    
    if telegram_id:
        save_user_action(telegram_id, 'page_opened', {'page': 'calculator'})
    
    try:
        return render_template('index.html')
    except:
        return jsonify({
            "page": "calculator",
            "telegram_id": telegram_id,
            "message": "Template not found, showing JSON response"
        })

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
            try:
                return render_template('result.html', error="Некорректные данные для отображения.")
            except:
                return jsonify({"error": "Некорректные данные для отображения."})

        try:
            return render_template('result.html', results=results, calculation_id=calculation_id)
        except:
            return jsonify({"results": results, "calculation_id": calculation_id})
        
    except Exception as e:
        logger.error(f"Ошибка на странице результатов: {str(e)}")
        try:
            return render_template('result.html', error="Произошла ошибка при обработке данных.")
        except:
            return jsonify({"error": "Произошла ошибка при обработке данных."})

@app.route('/calculate-old', methods=['GET', 'POST'])
def calculate():
    """Основной расчет доставки с улучшенной отладкой"""
    try:
        # Получаем данные
        if request.method == 'POST':
            data = request.get_json()
            logger.info(f"📥 POST запрос на расчет: {data}")
        else:
            data = request.args
            logger.info(f"📥 GET запрос на расчет: {dict(data)}")
        
        # Извлекаем параметры
        category = unquote(str(data.get('category', ''))).strip()
        cost_cny = safe_decimal(data.get('cost', 0))  # Теперь в юанях
        use_box_dimensions = data.get('useBoxDimensions', 'false').lower() == 'true'
        telegram_id = data.get('telegram_id')
        username = data.get('username')

        logger.info(f"🔍 Извлеченные параметры: category={category}, cost_cny={cost_cny}, use_box_dimensions={use_box_dimensions}")

        # Получаем текущий курс и конвертируем стоимость
        exchange_rate = get_current_exchange_rate()
        cost_usd = convert_cny_to_usd(cost_cny)

        logger.info(f"💱 Курс: {exchange_rate}, cost_usd: {cost_usd}")

        # Обработка веса и объема в зависимости от режима
        if use_box_dimensions:
            # Режим коробок: используем вес одной коробки
            quantity = int(data.get('quantity', 1))
            weight_per_box = safe_decimal(data.get('weightPerBox', 0))
            length = safe_decimal(data.get('length', 0))
            width = safe_decimal(data.get('width', 0))
            height = safe_decimal(data.get('height', 0))
            
            # Рассчитываем общий вес из веса коробок
            total_weight = weight_per_box * quantity
            
            logger.info(f"📦 Режим коробок: quantity={quantity}, weight_per_box={weight_per_box}, total_weight={total_weight}")
            
            # Валидация размеров
            if not all([quantity > 0, weight_per_box > 0, length > 0, width > 0, height > 0]):
                logger.error(f"❌ Валидация не прошла: quantity={quantity}, weight_per_box={weight_per_box}, размеры=[{length}, {width}, {height}]")
                return jsonify({"error": "Все параметры коробок должны быть больше 0"}), 400
            
            # Рассчитываем объем одной коробки в м³
            volume_per_box = (length / Decimal(100)) * (width / Decimal(100)) * (height / Decimal(100))
            total_volume = volume_per_box * quantity
            
            logger.info(f"📐 Рассчитанный объем: volume_per_box={volume_per_box}, total_volume={total_volume}")
            
            # ИСПРАВЛЕНИЕ: Для режима коробок сохраняем рассчитанный объем, а не None
            volume_to_save = float(total_volume)
        else:
            # Режим прямого ввода
            total_weight = safe_decimal(data.get('totalWeight', 0))
            total_volume = safe_decimal(data.get('volume', 0))
            quantity = 1  # Для совместимости
            weight_per_box = None
            length = width = height = None
            
            logger.info(f"📊 Режим прямого ввода: total_weight={total_weight}, total_volume={total_volume}")
            
            # Для режима прямого ввода объема сохраняем введенное значение
            volume_to_save = float(total_volume)

        # Валидация основных параметров
        if not all([category, total_weight > 0, cost_cny > 0, total_volume > 0]):
            logger.error(f"❌ Основная валидация не прошла: category={bool(category)}, total_weight={total_weight > 0}, cost_cny={cost_cny > 0}, total_volume={total_volume > 0}")
            return jsonify({"error": "Не все параметры указаны корректно"}), 400

        logger.info(f"✅ Валидация прошла успешно")

        # Сохраняем пользователя
        telegram_user_id = None
        if telegram_id and telegram_id != 'test_user':
            logger.info(f"👤 Сохранение пользователя Telegram: {telegram_id}")
            telegram_user_id = save_telegram_user(telegram_id, username)
            logger.info(f"👤 ID пользователя: {telegram_user_id}")
        else:
            logger.info(f"👤 Запрос без telegram_id или тестовый")

        # Рассчитываем плотность на основе общего веса и общего объема
        density = total_weight / total_volume if total_volume > 0 else Decimal('0')

        logger.info(f"📊 Плотность: {density}")

        # Определяем процент страхования (теперь на основе стоимости в долларах)
        cost_per_kg_usd = cost_usd / total_weight if total_weight > 0 else Decimal('0')
        if cost_per_kg_usd < 20:
            insurance_rate = Decimal('0.01')
        else:
            insurance_rate = Decimal('0.02')
        insurance = cost_usd * insurance_rate

        logger.info(f"💰 Страхование: rate={insurance_rate}, amount={insurance}")

        # Получаем тарифы из БД
        conn = connect_to_db()
        cursor = conn.cursor()

        logger.info(f"🔍 Поиск тарифов для веса: {total_weight}")

        # Тарифы по весу
        cursor.execute("""
            SELECT min_weight, max_weight, coefficient_bag, bag_packing_cost, bag_unloading_cost,
                   coefficient_corner, corner_packing_cost, corner_unloading_cost,
                   coefficient_frame, frame_packing_cost, frame_unloading_cost
            FROM delivery_test.weight
            WHERE min_weight <= %s AND max_weight > %s
        """, (total_weight, total_weight))
        
        result_row_weight = cursor.fetchone()
        if not result_row_weight:
            cursor.close()
            conn.close()
            logger.error(f"❌ Тарифы по весу не найдены для {total_weight} кг")
            return jsonify({"error": f"Вес {total_weight} кг вне диапазона тарифов"}), 400

        logger.info(f"✅ Тарифы по весу найдены")

        (min_weight, max_weight, packing_factor_bag, packaging_cost_bag, unload_cost_bag,
         additional_weight_corners, packaging_cost_corners, unload_cost_corners,
         additional_weight_frame, packaging_cost_frame, unload_cost_frame) = [safe_decimal(value) for value in result_row_weight]

        logger.info(f"🔍 Поиск тарифов для плотности: {density}, категория: {category}")

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
            logger.error(f"❌ Тарифы по плотности не найдены для плотности {density} кг/м³, категория '{category}'")
            return jsonify({"error": f"Плотность {density} кг/м³ вне диапазона для '{category}'"}), 400

        logger.info(f"✅ Тарифы по плотности найдены")

        (category_db, min_density, max_density, fast_car_cost_per_kg, regular_car_cost_per_kg) = [
            safe_decimal(value) if isinstance(value, (int, float)) else value for value in result_row_density]

        cursor.close()
        conn.close()

        # Расчеты стоимости для каждого типа упаковки
        packed_weight_bag = packing_factor_bag + total_weight
        packed_weight_corners = additional_weight_corners + total_weight
        packed_weight_frame = additional_weight_frame + total_weight

        logger.info(f"📦 Упакованные веса: bag={packed_weight_bag}, corners={packed_weight_corners}, frame={packed_weight_frame}")

        # Расчет страховки для каждого типа (на основе USD)
        cost_per_bag = cost_usd / packed_weight_bag if packed_weight_bag > 0 else Decimal('0')
        cost_per_corners = cost_usd / packed_weight_corners if packed_weight_corners > 0 else Decimal('0')
        cost_per_frame = cost_usd / packed_weight_frame if packed_weight_frame > 0 else Decimal('0')

        insurance_bag = cost_usd * (Decimal('0.01') if cost_per_bag < 20 else Decimal('0.02'))
        insurance_corners = cost_usd * (Decimal('0.01') if cost_per_corners < 20 else Decimal('0.02'))
        insurance_frame = cost_usd * (Decimal('0.01') if cost_per_frame < 20 else Decimal('0.02'))

        # Расчет доставки
        delivery_cost_fast_bag = (fast_car_cost_per_kg * packed_weight_bag).quantize(Decimal('0.01'))
        delivery_cost_regular_bag = (regular_car_cost_per_kg * packed_weight_bag).quantize(Decimal('0.01'))
        delivery_cost_fast_corners = (fast_car_cost_per_kg * packed_weight_corners).quantize(Decimal('0.01'))
        delivery_cost_regular_corners = (regular_car_cost_per_kg * packed_weight_corners).quantize(Decimal('0.01'))
        delivery_cost_fast_frame = (fast_car_cost_per_kg * packed_weight_frame).quantize(Decimal('0.01'))
        delivery_cost_regular_frame = (regular_car_cost_per_kg * packed_weight_frame).quantize(Decimal('0.01'))

        logger.info(f"💰 Расчеты завершены, начинаем сохранение в БД")

        # ИСПРАВЛЕНИЕ: Логируем данные перед сохранением
        logger.info(f"💾 Данные для сохранения user_input:")
        logger.info(f"   category={category}")
        logger.info(f"   total_weight={float(total_weight)}")
        logger.info(f"   cost_cny={float(cost_cny)}")
        logger.info(f"   cost_usd={float(cost_usd)}")
        logger.info(f"   exchange_rate={float(exchange_rate)}")
        logger.info(f"   volume_to_save={volume_to_save}")
        logger.info(f"   use_box_dimensions={use_box_dimensions}")
        logger.info(f"   quantity={quantity if use_box_dimensions else None}")
        logger.info(f"   weight_per_box={float(weight_per_box) if weight_per_box is not None else None}")
        logger.info(f"   length={float(length) if length is not None else None}")
        logger.info(f"   width={float(width) if width is not None else None}")
        logger.info(f"   height={float(height) if height is not None else None}")
        logger.info(f"   telegram_user_id={telegram_user_id}")

        # Сохраняем данные в БД
        input_id = save_user_input_to_db(
            category=category,
            total_weight=float(total_weight),
            cost_cny=float(cost_cny),
            cost_usd=float(cost_usd),
            exchange_rate=float(exchange_rate),
            volume=volume_to_save,  # Теперь всегда float
            use_box_dimensions=use_box_dimensions,
            quantity=quantity if use_box_dimensions else None,
            weight_per_box=float(weight_per_box) if weight_per_box is not None else None,
            length=float(length) if length is not None else None,
            width=float(width) if width is not None else None,
            height=float(height) if height is not None else None,
            telegram_user_id=telegram_user_id
        )

        if input_id:
            logger.info(f"✅ user_input сохранен с ID={input_id}")
        else:
            logger.error(f"❌ save_user_input_to_db вернул None")

        # Формируем результаты
        results = {
            "generalInformation": {
                "category": category,
                "fast_car_cost_per_kg": float(fast_car_cost_per_kg.quantize(Decimal('0.01'))),
                "regular_car_cost_per_kg": float(regular_car_cost_per_kg.quantize(Decimal('0.01'))),
                "weight": float(total_weight.quantize(Decimal('0.01'))),
                "density": float(density.quantize(Decimal('0.01'))),
                "productCostCNY": float(cost_cny),
                "productCostUSD": float(cost_usd.quantize(Decimal('0.01'))),
                "exchangeRate": float(exchange_rate.quantize(Decimal('0.0001'))),
                "exchangeRateNote": f"{exchange_rate} юаней за 1$",
                "insuranceRate": f"{insurance_rate * Decimal('100'):.0f}%",
                "insuranceAmount": float(insurance.quantize(Decimal('0.01'))),
                "volume": float(total_volume.quantize(Decimal('0.01'))),
                "boxCount": quantity if use_box_dimensions else 1,
                "weightPerBox": float(weight_per_box) if weight_per_box else None
            },
            "bag": {
                "packedWeight": float(packed_weight_bag.quantize(Decimal('0.01'))),
                "packagingCost": float(packaging_cost_bag.quantize(Decimal('0.01'))),
                "unloadCost": float(unload_cost_bag.quantize(Decimal('0.01'))),
                "insurance": float(insurance_bag.quantize(Decimal('0.01'))),
                "insuranceRate": f"{(insurance_bag/cost_usd * Decimal('100')).quantize(Decimal('1')):.0f}%",
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
                "insuranceRate": f"{(insurance_corners/cost_usd * Decimal('100')).quantize(Decimal('1')):.0f}%",
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
                "insuranceRate": f"{(insurance_frame/cost_usd * Decimal('100')).quantize(Decimal('1')):.0f}%",
                "deliveryCostFast": float(delivery_cost_fast_frame),
                "deliveryCostRegular": float(delivery_cost_regular_frame),
                "totalFast": float((packaging_cost_frame + unload_cost_frame + insurance_frame + delivery_cost_fast_frame).quantize(Decimal('0.01'))),
                "totalRegular": float((packaging_cost_frame + unload_cost_frame + insurance_frame + delivery_cost_regular_frame).quantize(Decimal('0.01')))
            }
        }

        logger.info(f"💾 Сохранение расчета...")

        calculation_id = save_user_calculation(
            telegram_user_id=telegram_user_id,
            category=category,
            total_weight=float(total_weight.quantize(Decimal('0.01'))),
            density=float(density.quantize(Decimal('0.01'))),
            product_cost_cny=float(cost_cny),
            product_cost_usd=float(cost_usd.quantize(Decimal('0.01'))),
            exchange_rate=float(exchange_rate),
            insurance_rate=float(insurance_rate * Decimal('100')),
            insurance_amount=float(insurance.quantize(Decimal('0.01'))),
            volume=float(total_volume.quantize(Decimal('0.01'))),
            box_count=quantity if use_box_dimensions else 1,
            bag_total_fast=float(results["bag"]["totalFast"]),
            bag_total_regular=float(results["bag"]["totalRegular"]),
            corners_total_fast=float(results["corners"]["totalFast"]),
            corners_total_regular=float(results["corners"]["totalRegular"]),
            frame_total_fast=float(results["frame"]["totalFast"]),
            frame_total_regular=float(results["frame"]["totalRegular"]),
            input_id=input_id
        )

        if calculation_id:
            logger.info(f"✅ Расчет сохранен с ID={calculation_id}")
        else:
            logger.error(f"❌ save_user_calculation вернул None")

        # Сохраняем действие
        if telegram_id:
            save_user_action(telegram_id, 'calculation_completed', {
                'calculation_id': calculation_id,
                'input_id': input_id,
                'category': category,
                'total_weight': float(total_weight),
                'cost_cny': float(cost_cny),
                'cost_usd': float(cost_usd),
                'exchange_rate': float(exchange_rate),
                'use_box_dimensions': use_box_dimensions
            })

        logger.info(f"🎉 Расчет завершен успешно")

        # Возвращаем результат
        if request.method == 'POST':
            return jsonify(results)
        else:
            results_url = f"/result?results={quote(json.dumps(results))}&calculation_id={calculation_id}"
            if telegram_id:
                results_url += f"&telegram_id={telegram_id}"
            return redirect(results_url)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в calculate: {str(e)}")
        logger.error(f"📍 Место ошибки: {e.__class__.__name__}")
        import traceback
        logger.error(f"🔍 Полный traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

# ДОПОЛНИТЕЛЬНО: endpoint для проверки таблицы user_inputs
@app.route('/api/debug/user-inputs', methods=['GET'])
def debug_user_inputs():
    """Отладочный endpoint для проверки таблицы user_inputs"""
    try:
        conn = connect_to_db()
        cursor = conn.cursor()
        
        # Получаем последние 10 записей
        cursor.execute("""
            SELECT id, category, total_weight, cost_cny, cost_usd, volume, 
                   use_box_dimensions, quantity, telegram_user_id, created_at
            FROM delivery_test.user_inputs 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        
        results = cursor.fetchall()
        
        # Получаем общее количество
        cursor.execute("SELECT COUNT(*) FROM delivery_test.user_inputs")
        total_count = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        # Форматируем результаты
        user_inputs = []
        for row in results:
            user_inputs.append({
                'id': row[0],
                'category': row[1],
                'total_weight': float(row[2]) if row[2] else None,
                'cost_cny': float(row[3]) if row[3] else None,
                'cost_usd': float(row[4]) if row[4] else None,
                'volume': float(row[5]) if row[5] else None,
                'use_box_dimensions': row[6],
                'quantity': row[7],
                'telegram_user_id': row[8],
                'created_at': row[9].isoformat() if row[9] else None
            })
        
        return jsonify({
            "success": True,
            "total_count": total_count,
            "last_10_records": user_inputs,
            "timestamp": get_moscow_time().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Ошибка в debug_user_inputs: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/calculate', methods=['POST'])
def api_calculate():
    """API для расчета доставки с главной страницы"""
    try:
        data = request.get_json()
        
        # Извлекаем параметры (используем формат с весом одной коробки)
        category = data.get('category', '').strip()
        quantity = int(data.get('quantity', 1))
        weight_per_box = safe_decimal(data.get('weight', 0))
        cost_cny = safe_decimal(data.get('cost', 0))  # Теперь в юанях
        length = safe_decimal(data.get('length', 0))
        width = safe_decimal(data.get('width', 0))
        height = safe_decimal(data.get('height', 0))
        
        # Валидация
        if not all([category, weight_per_box > 0, length > 0, width > 0, height > 0, cost_cny > 0, quantity > 0]):
            return jsonify({"error": "Не все параметры указаны корректно"}), 400
        
        # Получаем курс и конвертируем
        exchange_rate = get_current_exchange_rate()
        cost_usd = convert_cny_to_usd(cost_cny)
        
        # Рассчитываем общие параметры
        total_weight = weight_per_box * quantity
        volume_per_box = (length / Decimal(100)) * (width / Decimal(100)) * (height / Decimal(100))
        total_volume = volume_per_box 
        density = total_weight / total_volume if total_volume > 0 else Decimal('0')
        
        # Определяем процент страхования (на основе USD)
        cost_per_kg_usd = cost_usd / total_weight if total_weight > 0 else Decimal('0')
        insurance_rate = Decimal('0.01') if cost_per_kg_usd < 20 else Decimal('0.02')
        insurance = cost_usd * insurance_rate
        
        # Получаем тарифы из БД (такая же логика как в основном calculate)
        conn = connect_to_db()
        cursor = conn.cursor()

        # Тарифы по весу
        cursor.execute("""
            SELECT min_weight, max_weight, coefficient_bag, bag_packing_cost, bag_unloading_cost,
                   coefficient_corner, corner_packing_cost, corner_unloading_cost,
                   coefficient_frame, frame_packing_cost, frame_unloading_cost
            FROM delivery_test.weight
            WHERE min_weight <= %s AND max_weight > %s
        """, (total_weight, total_weight))
        
        result_row_weight = cursor.fetchone()
        if not result_row_weight:
            cursor.close()
            conn.close()
            return jsonify({"error": f"Вес {total_weight} кг вне диапазона тарифов"}), 400

        (min_weight, max_weight, packing_factor_bag, packaging_cost_bag, unload_cost_bag,
         additional_weight_corners, packaging_cost_corners, unload_cost_corners,
         additional_weight_frame, packaging_cost_frame, unload_cost_frame) = [safe_decimal(value) for value in result_row_weight]

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
        
        # Расчеты стоимости (такая же логика как в основном calculate)
        packed_weight_bag = packing_factor_bag + total_weight
        packed_weight_corners = additional_weight_corners + total_weight
        packed_weight_frame = additional_weight_frame + total_weight

        # Расчет страховки для каждого типа (на основе USD)
        cost_per_bag = cost_usd / packed_weight_bag if packed_weight_bag > 0 else Decimal('0')
        cost_per_corners = cost_usd / packed_weight_corners if packed_weight_corners > 0 else Decimal('0')
        cost_per_frame = cost_usd / packed_weight_frame if packed_weight_frame > 0 else Decimal('0')

        insurance_bag = cost_usd * (Decimal('0.01') if cost_per_bag < 20 else Decimal('0.02'))
        insurance_corners = cost_usd * (Decimal('0.01') if cost_per_corners < 20 else Decimal('0.02'))
        insurance_frame = cost_usd * (Decimal('0.01') if cost_per_frame < 20 else Decimal('0.02'))

        # Расчет доставки
        delivery_cost_fast_bag = (fast_car_cost_per_kg * packed_weight_bag).quantize(Decimal('0.01'))
        delivery_cost_regular_bag = (regular_car_cost_per_kg * packed_weight_bag).quantize(Decimal('0.01'))
        delivery_cost_fast_corners = (fast_car_cost_per_kg * packed_weight_corners).quantize(Decimal('0.01'))
        delivery_cost_regular_corners = (regular_car_cost_per_kg * packed_weight_corners).quantize(Decimal('0.01'))
        delivery_cost_fast_frame = (fast_car_cost_per_kg * packed_weight_frame).quantize(Decimal('0.01'))
        delivery_cost_regular_frame = (regular_car_cost_per_kg * packed_weight_frame).quantize(Decimal('0.01'))

        # Сохраняем данные (как формат с использованием размеров коробок)
        input_id = save_user_input_to_db(
            category=category,
            total_weight=float(total_weight),
            cost_cny=float(cost_cny),
            cost_usd=float(cost_usd),
            exchange_rate=float(exchange_rate),
            volume=None,  # Будет рассчитан триггером
            use_box_dimensions=True,
            quantity=quantity,
            weight_per_box=float(weight_per_box),
            length=float(length),
            width=float(width),
            height=float(height),
            telegram_user_id=None  # Это запрос с сайта, не из Telegram
        )

        # Формируем ответ
        return jsonify({
            "success": True,
            "total_cost_bag_fast": float((packaging_cost_bag + unload_cost_bag + insurance_bag + delivery_cost_fast_bag).quantize(Decimal('0.01'))),
            "total_cost_bag_regular": float((packaging_cost_bag + unload_cost_bag + insurance_bag + delivery_cost_regular_bag).quantize(Decimal('0.01'))),
            "total_cost_corners_fast": float((packaging_cost_corners + unload_cost_corners + insurance_corners + delivery_cost_fast_corners).quantize(Decimal('0.01'))),
            "total_cost_corners_regular": float((packaging_cost_corners + unload_cost_corners + insurance_corners + delivery_cost_regular_corners).quantize(Decimal('0.01'))),
            "total_cost_frame_fast": float((packaging_cost_frame + unload_cost_frame + insurance_frame + delivery_cost_fast_frame).quantize(Decimal('0.01'))),
            "total_cost_frame_regular": float((packaging_cost_frame + unload_cost_frame + insurance_frame + delivery_cost_regular_frame).quantize(Decimal('0.01'))),
            "total_weight": float(total_weight.quantize(Decimal('0.01'))),
            "total_volume": float(total_volume.quantize(Decimal('0.001'))),
            "density": float(density.quantize(Decimal('0.01'))),
            "cost_cny": float(cost_cny),
            "cost_usd": float(cost_usd.quantize(Decimal('0.01'))),
            "exchange_rate": float(exchange_rate.quantize(Decimal('0.0001'))),
            "exchange_rate_note": f"{exchange_rate} юаней за 1$",
            "insurance_rate": f"{insurance_rate * Decimal('100'):.0f}%"
        })
        
    except Exception as e:
        logger.error(f"Ошибка в api_calculate: {str(e)}")
        return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

@app.route('/api/exchange-rate', methods=['GET'])
def api_get_exchange_rate():
    """API для получения текущего курса валют"""
    try:
        # Получаем курс из БД
        conn = connect_to_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT rate, recorded_at, source, notes, id
            FROM delivery_test.exchange_rates 
            WHERE currency_pair = 'CNY/USD' 
            ORDER BY recorded_at DESC 
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            rate, recorded_at, source, notes, rate_id = result
            
            response_data = {
                "success": True,
                "currency_pair": "CNY/USD",
                "rate": float(rate),
                "rate_description": f"{rate} юаней за 1 доллар",
                "rate_id": rate_id,
                "last_updated": recorded_at.isoformat() if recorded_at else None,
                "source": source,
                "notes": notes,
                "timestamp": get_moscow_time().isoformat()
            }
        else:
            # Курса нет в БД
            response_data = {
                "success": False,
                "error": "Курс не найден в базе данных",
                "currency_pair": "CNY/USD",
                "timestamp": get_moscow_time().isoformat()
            }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Ошибка при получении курса через API: {str(e)}")
        return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500

@app.route('/api/exchange-rate/update', methods=['POST'])
def api_manual_update_exchange_rate():
    """API для ручного обновления курса валют (принимает курс: сколько юаней за 1$)"""
    try:
        data = request.get_json()
        
        if not data or 'rate' not in data:
            return jsonify({"error": "Необходимо указать курс валют (сколько юаней за 1$)"}), 400
        
        rate = safe_decimal(data['rate'])
        source = data.get('source', 'api_manual_update')
        notes = data.get('notes', 'Ручное обновление курса через API')
        
        if rate <= 0:
            return jsonify({"error": "Курс должен быть больше 0"}), 400
        
        if rate > 20:
            return jsonify({"error": "Курс выглядит слишком большим (больше 20)"}), 400
        
        # Сохраняем курс в БД
        conn = connect_to_db()
        cursor = conn.cursor()
        
        moscow_time = get_moscow_time()
        cursor.execute("""
            INSERT INTO delivery_test.exchange_rates (currency_pair, rate, recorded_at, source, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, ('CNY/USD', float(rate), moscow_time, source, notes))
        
        rate_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Курс обновлен через API: {rate} юаней за 1$ (ID: {rate_id}, источник: {source})")
        
        # Отправляем уведомление (если доступно)
        try:
            from telegram_notifier import send_rate_notification
            rate_data = {
                'rate': float(rate),
                'source': source
            }
            
            def send_notification():
                try:
                    send_rate_notification(rate_data)
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление о курсе: {e}")
            
            notification_thread = threading.Thread(target=send_notification)
            notification_thread.daemon = True
            notification_thread.start()
            
        except ImportError:
            logger.info("Модуль telegram_notifier недоступен, уведомление не отправлено")
        except Exception as e:
            logger.warning(f"Ошибка при отправке уведомления о курсе: {e}")
        
        return jsonify({
            "success": True,
            "rate_id": rate_id,
            "currency_pair": "CNY/USD",
            "rate": float(rate),
            "rate_description": f"{rate} юаней за 1 доллар",
            "message": "Курс валют успешно обновлен",
            "timestamp": moscow_time.isoformat(),
            "source": source
        })
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении курса через API: {str(e)}")
        return jsonify({"error": f"Внутренняя ошибка: {str(e)}"}), 500
@app.route('/api/exchange-rate/history', methods=['GET'])
def api_get_exchange_rate_history():
    """API для получения истории курсов валют"""
    try:
        limit = int(request.args.get('limit', 10))
        limit = min(limit, 100)  # Максимум 100 записей
        
        conn = connect_to_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT rate, recorded_at, source, notes, id
            FROM delivery_test.exchange_rates 
            WHERE currency_pair = 'CNY/USD' 
            ORDER BY recorded_at DESC 
            LIMIT %s
        """, (limit,))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        history = []
        for rate, recorded_at, source, notes, rate_id in results:
            history.append({
                "id": rate_id,
                "rate": float(rate),
                "recorded_at": recorded_at.isoformat() if recorded_at else None,
                "source": source,
                "notes": notes
            })
        
        return jsonify({
            "success": True,
            "currency_pair": "CNY/USD",
            "history": history,
            "total_records": len(history),
            "timestamp": get_moscow_time().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении истории курсов: {str(e)}")
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
        
        # Проверяем актуальность курса валют
        rate = get_current_exchange_rate()
        
        return jsonify({
            "status": "healthy",
            "timestamp": get_moscow_time().isoformat(),
            "database": "connected",
            "exchange_rate": float(rate),
            "version": "2.3-calculations"
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "timestamp": get_moscow_time().isoformat(),
            "error": str(e)
        }), 500

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

if __name__ == '__main__':
    logger.info("=== Запуск China Together Delivery Calculator v2.3 (Calculations Only) ===")
    
    # Инициализируем БД
    try:
        init_database()
        logger.info("✅ База данных готова")
        
        # Получаем актуальный курс при старте
        rate = get_current_exchange_rate()
        logger.info(f"✅ Курс CNY/USD: {rate} юаней за 1$")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {str(e)}")
    
    # Запускаем сервер
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 8061)),
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        threaded=True
    )
