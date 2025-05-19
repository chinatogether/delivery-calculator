from flask import Flask, render_template, request, jsonify, redirect
import psycopg2
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote, quote_plus
from flask_cors import CORS
import logging
<<<<<<< HEAD
from datetime import datetime

# Настройка Decimal
=======
import json

# Настройка точности для Decimal
from decimal import getcontext
>>>>>>> 9dd40b7 (Test CI/CD deployment)
getcontext().prec = 6

app = Flask(__name__)
CORS(app)

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
    'dbname': 'delivery_db',
    'user': 'chinatogether',
    'password': 'O99ri1@',
    'host': 'localhost',
    'port': '5432',
    'connect_timeout': 10
}

class DatabaseConnection:
    """Класс для управления подключением к базе данных"""
    def __init__(self):
        self.connection = None
    
    def __enter__(self):
        try:
            self.connection = psycopg2.connect(**DB_CONFIG)
            return self.connection
        except psycopg2.Error as e:
            logger.error(f"Ошибка подключения к базе данных: {e}")
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection:
            self.connection.close()

<<<<<<< HEAD
=======
# Функция для безопасного преобразования значений в Decimal
def safe_decimal(value, default=Decimal('0')):
    """
    Преобразует значение в Decimal.
    Если значение None или некорректное, возвращает значение по умолчанию (default).
    """
    try:
        if value is None:
            return default
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))  # Преобразуем через строку для точности
        if isinstance(value, str):
            return Decimal(value.replace(',', '.'))  # Заменяем запятые на точки
        raise ValueError(f"Неподдерживаемый тип данных: {type(value)}")
    except Exception as e:
        logger.warning(f"Ошибка при преобразовании значения '{value}' в Decimal: {str(e)}")
        return default

# Сохранение данных пользователя Telegram в базу данных
>>>>>>> 9dd40b7 (Test CI/CD deployment)
def save_telegram_user(telegram_id, username):
    """Сохранение пользователя Telegram в базу данных"""
    if not telegram_id or not username:
        logger.warning("Отсутствуют данные пользователя Telegram")
        return None
    
    try:
<<<<<<< HEAD
        with DatabaseConnection() as conn:
            with conn.cursor() as cursor:
                # Проверяем существование пользователя
                cursor.execute("""
                    SELECT id FROM delivery_test.telegram_users 
                    WHERE telegram_id = %s
                """, (telegram_id,))
                user = cursor.fetchone()

                if not user:
                    # Создаем нового пользователя
                    cursor.execute("""
                        INSERT INTO delivery_test.telegram_users (telegram_id, username)
                        VALUES (%s, %s)
                        RETURNING id
                    """, (telegram_id, username))
                    user_id = cursor.fetchone()[0]
                    conn.commit()
                    logger.info(f"Создан новый пользователь Telegram: {username} (ID: {telegram_id})")
                else:
                    # Пользователь уже существует
                    user_id = user[0]
                    logger.info(f"Найден существующий пользователь Telegram: ID {user_id}")
                
                return user_id
=======
        # Проверяем, существует ли пользователь с таким telegram_id
        cursor.execute("""
            SELECT id FROM delivery_test.telegram_users WHERE telegram_id = %s
        """, (telegram_id,))
        existing_user = cursor.fetchone()
        if existing_user:
            logger.info(f"Пользователь с telegram_id={telegram_id} уже существует.")
            return existing_user[0]

        # Если пользователя нет, добавляем нового
        cursor.execute("""
            INSERT INTO delivery_test.telegram_users (telegram_id, username)
            VALUES (%s, %s)
            RETURNING id
        """, (telegram_id, username))
        telegram_user_id = cursor.fetchone()[0]
        conn.commit()
        logger.info("Данные пользователя Telegram успешно сохранены.")
        return telegram_user_id
>>>>>>> 9dd40b7 (Test CI/CD deployment)
    except Exception as e:
        logger.error(f"Ошибка при работе с базой данных: {e}")
        return None

def save_calculation_to_db(input_data, results, telegram_user_id=None):
    """Сохранение данных расчета в базу данных"""
    try:
<<<<<<< HEAD
        with DatabaseConnection() as conn:
            with conn.cursor() as cursor:
                # Сохраняем входные данные
                cursor.execute("""
                    INSERT INTO delivery_test.calculations (
                        category, weight, length, width, height, 
                        cost, quantity, telegram_user_id,
                        total_weight, density, volume, 
                        insurance_rate, insurance_amount,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    input_data['category'],
                    float(input_data['weight']),
                    float(input_data['length']),
                    float(input_data['width']),
                    float(input_data['height']),
                    float(input_data['cost']),
                    int(input_data['quantity']),
                    telegram_user_id,
                    float(results['generalInformation']['weight']),
                    float(results['generalInformation']['density']),
                    float(results['generalInformation']['volume']),
                    float(results['generalInformation']['insuranceRate'].strip('%')) / 100,
                    float(results['generalInformation']['insuranceAmount']),
                    datetime.now()
                ))
                calculation_id = cursor.fetchone()[0]
                
                # Сохраняем результаты для каждого типа упаковки
                for package_type in ['bag', 'corners', 'frame']:
                    cursor.execute("""
                        INSERT INTO delivery_test.calculation_results (
                            calculation_id, package_type,
                            packed_weight, packaging_cost,
                            unload_cost, delivery_cost_fast,
                            delivery_cost_regular, total_fast,
                            total_regular
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        calculation_id, package_type,
                        float(results[package_type]['packedWeight']),
                        float(results[package_type]['packagingCost']),
                        float(results[package_type]['unloadCost']),
                        float(results[package_type]['deliveryCostFast']),
                        float(results[package_type]['deliveryCostRegular']),
                        float(results[package_type]['totalFast']),
                        float(results[package_type]['totalRegular'])
                    ))
                
                conn.commit()
                logger.info(f"Успешно сохранен расчет ID {calculation_id}")
                return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении расчета: {e}")
        return False

@app.route('/calculate', methods=['GET'])
def calculate():
    try:
        logger.info("Получен запрос на расчет доставки")
        
        # Получаем и валидируем параметры
        category = urllib.parse.unquote(request.args.get('category', '').strip())
        weight_per_box = Decimal(request.args.get('weight', 0))
        length = Decimal(request.args.get('length', 0))
        width = Decimal(request.args.get('width', 0))
        height = Decimal(request.args.get('height', 0))
        cost = Decimal(request.args.get('cost', 0))
        quantity = int(request.args.get('quantity', 1))
        telegram_id = request.args.get('telegram_id')
        username = request.args.get('username')

        # Валидация входных данных
=======
        cursor.execute("""
            INSERT INTO delivery_test.user_inputs (
                category, weight, length, width, height, cost, quantity, telegram_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (category, weight, length, width, height, cost, quantity, telegram_user_id))
        conn.commit()
        logger.info("Входные данные успешно записаны в таблицу user_inputs.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка при записи входных данных: {str(e)}")
    finally:
        cursor.close()
        conn.close()

# Сохранение результатов расчета пользователя в базу данных
def save_user_calculation(
    telegram_user_id, category, total_weight, density, product_cost, insurance_rate,
    insurance_amount, volume, box_count, bag_total_fast, bag_total_regular,
    corners_total_fast, corners_total_regular, frame_total_fast, frame_total_regular
):
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO delivery_test.user_calculations (
                telegram_user_id, category, total_weight, density, product_cost, insurance_rate,
                insurance_amount, volume, box_count, bag_total_fast, bag_total_regular,
                corners_total_fast, corners_total_regular, frame_total_fast, frame_total_regular
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            telegram_user_id, category, total_weight, density, product_cost, insurance_rate,
            insurance_amount, volume, box_count, bag_total_fast, bag_total_regular,
            corners_total_fast, corners_total_regular, frame_total_fast, frame_total_regular
        ))
        conn.commit()
        logger.info("Результаты расчета успешно записаны в таблицу user_calculations.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка при записи результатов расчета: {str(e)}")
    finally:
        cursor.close()
        conn.close()

# Маршрут для главной страницы (index.html)
@app.route('/')
def index():
    return render_template('index.html')

# Маршрут для страницы с результатами (result.html)
@app.route('/result', methods=['GET', 'POST'])
def result():
    if request.method == 'POST':
        try:
            # Получение данных из тела запроса
            results = request.json

            # Проверка структуры данных
            if not all(key in results for key in ["generalInformation", "bag", "corners", "frame"]):
                return render_template('result.html', error="Некорректная структура данных.")

            # Передача данных в шаблон
            return render_template('result.html', results=results)

        except Exception as e:
            logger.error(f"Произошла ошибка: {str(e)}")
            return render_template('result.html', error="Произошла внутренняя ошибка.")
    else:
        return render_template('result.html', error="Данные для отображения отсутствуют.")
    

# Маршрут для расчетов
@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        # Получение данных из тела запроса
        data = request.json

        # Извлечение параметров
        category = data.get('category', '').strip()  # Убираем unquote
        weight_per_box = safe_decimal(data.get('weight', 0))
        length = safe_decimal(data.get('length', 0))
        width = safe_decimal(data.get('width', 0))
        height = safe_decimal(data.get('height', 0))
        cost = safe_decimal(data.get('cost', 0))
        quantity = int(data.get('quantity', 1))
        telegram_id = data.get('telegram_id', None)
        username = data.get('username', None)

        # Проверка обязательных параметров
>>>>>>> 9dd40b7 (Test CI/CD deployment)
        if not all([category, weight_per_box > 0, length > 0, width > 0, height > 0, cost > 0, quantity > 0]):
            error_msg = "Не все параметры указаны или имеют недопустимые значения"
            logger.warning(error_msg)
            return jsonify({"error": error_msg}), 400

        # Сохраняем пользователя Telegram (если данные предоставлены)
        telegram_user_id = None
        if telegram_id and username:
            telegram_user_id = save_telegram_user(telegram_id, username)

<<<<<<< HEAD
        # Расчет основных параметров
        volume_per_box = (length / 100) * (width / 100) * (height / 100)  # м³
        total_volume = volume_per_box * quantity
=======
        # Расчет объема и плотности
        volume_per_box = (length / Decimal(100)) * (width / Decimal(100)) * (height / Decimal(100))
        total_volume = volume_per_box * quantity
        if volume_per_box == 0:
            return jsonify({"error": "Объем не может быть равен нулю"}), 400
        density = weight_per_box / volume_per_box

        # Рассчитываем общий вес (вес одной коробки × количество коробок)
>>>>>>> 9dd40b7 (Test CI/CD deployment)
        total_weight = weight_per_box * quantity
        density = total_weight / total_volume if total_volume > 0 else Decimal('0')

        # Расчет страховки
        cost_per_kg = cost / total_weight if total_weight > 0 else Decimal('0')
        if cost_per_kg < 20:
            insurance_rate = Decimal('0.01')  # 1%
        elif 20 <= cost_per_kg < 30:
            insurance_rate = Decimal('0.02')  # 2%
        else:
            insurance_rate = Decimal('0.03')  # 3%
        
        insurance = cost * insurance_rate

        # Получаем данные из базы
        try:
            with DatabaseConnection() as conn:
                with conn.cursor() as cursor:
                    # Получаем коэффициенты для веса
                    cursor.execute("""
                        SELECT 
                            coefficient_bag, bag_packing_cost, bag_unloading_cost,
                            coefficient_corner, corner_packing_cost, corner_unloading_cost,
                            coefficient_frame, frame_packing_cost, frame_unloading_cost
                        FROM delivery_test.weight
                        WHERE min_weight <= %s AND max_weight > %s
                    """, (float(total_weight), float(total_weight)))
                    weight_data = cursor.fetchone()

<<<<<<< HEAD
                    if not weight_data:
                        error_msg = f"Не найден подходящий диапазон веса для {total_weight} кг"
                        logger.warning(error_msg)
                        return jsonify({"error": error_msg}), 400

                    # Получаем стоимость доставки по плотности
                    cursor.execute("""
                        SELECT fast_delivery_cost, regular_delivery_cost
                        FROM delivery_test.density
                        WHERE category = %s AND min_density <= %s AND max_density > %s
                    """, (category, float(density), float(density)))
                    density_data = cursor.fetchone()

                    if not density_data:
                        error_msg = f"Не найден подходящий диапазон плотности для {density} кг/м³"
                        logger.warning(error_msg)
                        return jsonify({"error": error_msg}), 400

        except psycopg2.Error as e:
            logger.error(f"Ошибка базы данных: {e}")
            return jsonify({"error": "Ошибка при работе с базой данных"}), 500

        # Распаковываем данные
        (packing_factor_bag, packaging_cost_bag, unload_cost_bag,
         additional_weight_corners, packaging_cost_corners, unload_cost_corners,
         additional_weight_frame, packaging_cost_frame, unload_cost_frame) = weight_data

        fast_car_cost_per_kg, regular_car_cost_per_kg = density_data

        # Рассчитываем стоимости доставки
        delivery_cost_fast = round(float(fast_car_cost_per_kg) * float(total_weight), 2)
        delivery_cost_regular = round(float(regular_car_cost_per_kg) * float(total_weight), 2)

        # Рассчитываем упакованные веса
        packed_weight_bag = (packing_factor_bag + total_weight)
        packed_weight_corners = (additional_weight_corners + total_weight)
        packed_weight_frame = (additional_weight_frame + total_weight)
=======
        # Находим строку с подходящим диапазоном общего веса
        cursor.execute("""
            SELECT min_weight, max_weight, coefficient_bag, bag, bag_packing_cost, bag_unloading_cost,
                   coefficient_corner, cardboard_corners, corner_packing_cost, corner_unloading_cost,
                   coefficient_frame, wooden_frame, frame_packing_cost, frame_unloading_cost
            FROM delivery_test.weight
            WHERE min_weight <= %s AND max_weight > %s
        """, (total_weight, total_weight))
        result_row_weight = cursor.fetchone()
        if not result_row_weight:
            return jsonify({"error": "Общий вес не попадает в диапазон"}), 400

        # Преобразуем данные из найденной строки Weight в Decimal
        (
            min_weight, max_weight, packing_factor_bag, _, packaging_cost_bag, unload_cost_bag,
            additional_weight_corners, _, packaging_cost_corners, unload_cost_corners,
            additional_weight_frame, _, packaging_cost_frame, unload_cost_frame
        ) = [safe_decimal(value) for value in result_row_weight]

        # Находим строку с подходящей плотностью на листе Density
        cursor.execute("""
            SELECT category, min_density, max_density, fast_delivery_cost, regular_delivery_cost
            FROM delivery_test.density 
            WHERE category = %s AND min_density <= %s AND max_density > %s
        """, (category, density, density))
        result_row_density = cursor.fetchone()
        if not result_row_density:
            return jsonify({"error": "Плотность не попадает в диапазон для данной категории"}), 400

        # Преобразуем данные из найденной строки Density в Decimal
        (
            category_db, min_density, max_density, fast_car_cost_per_kg, regular_car_cost_per_kg
        ) = [safe_decimal(value) for value in result_row_density]

        # Вычисляем вес с упаковкой для каждого типа упаковки
        packed_weight_bag = safe_decimal(packing_factor_bag) + total_weight
        packed_weight_corners = safe_decimal(additional_weight_corners) + total_weight
        packed_weight_frame = safe_decimal(additional_weight_frame) + total_weight

        # Вычисляем общую стоимость доставки
        delivery_cost_fast = (fast_car_cost_per_kg * total_weight).quantize(Decimal('0.01'))
        delivery_cost_regular = (regular_car_cost_per_kg * total_weight).quantize(Decimal('0.01'))

>>>>>>> 9dd40b7 (Test CI/CD deployment)

        # Формируем результаты
        results = {
            "generalInformation": {
                "category": category,
<<<<<<< HEAD
                "weight": float(round(total_weight, 2)),
                "density": float(round(density, 2)),
                "productCost": float(cost),
                "insuranceRate": f"{insurance_rate * 100:.0f}%",
                "insuranceAmount": float(round(insurance, 2)),
                "volume": float(round(total_volume, 2)),
                "boxCount": quantity
            },
            "bag": {
                "packedWeight": float(round(packed_weight_bag, 2)),
                "packagingCost": float(round(packaging_cost_bag * quantity, 2)),
                "unloadCost": float(round(unload_cost_bag * quantity, 2)),
                "insurance": float(round(insurance, 2)),
                "deliveryCostFast": delivery_cost_fast,
                "deliveryCostRegular": delivery_cost_regular,
                "totalFast": float(round(packaging_cost_bag * quantity + unload_cost_bag * quantity + insurance + delivery_cost_fast, 2)),
                "totalRegular": float(round(packaging_cost_bag * quantity + unload_cost_bag * quantity + insurance + delivery_cost_regular, 2))
            },
            "corners": {
                "packedWeight": float(round(packed_weight_corners, 2)),
                "packagingCost": float(round(packaging_cost_corners * quantity, 2)),
                "unloadCost": float(round(unload_cost_corners * quantity, 2)),
                "insurance": float(round(insurance, 2)),
                "deliveryCostFast": delivery_cost_fast,
                "deliveryCostRegular": delivery_cost_regular,
                "totalFast": float(round(packaging_cost_corners * quantity + unload_cost_corners * quantity + insurance + delivery_cost_fast, 2)),
                "totalRegular": float(round(packaging_cost_corners * quantity + unload_cost_corners * quantity + insurance + delivery_cost_regular, 2))
            },
            "frame": {
                "packedWeight": float(round(packed_weight_frame, 2)),
                "packagingCost": float(round(packaging_cost_frame * quantity, 2)),
                "unloadCost": float(round(unload_cost_frame * quantity, 2)),
                "insurance": float(round(insurance, 2)),
                "deliveryCostFast": delivery_cost_fast,
                "deliveryCostRegular": delivery_cost_regular,
                "totalFast": float(round(packaging_cost_frame * quantity + unload_cost_frame * quantity + insurance + delivery_cost_fast, 2)),
                "totalRegular": float(round(packaging_cost_frame * quantity + unload_cost_frame * quantity + insurance + delivery_cost_regular, 2))
            }
        }

        # Сохраняем расчет в базу данных
        input_data = {
            'category': category,
            'weight': weight_per_box,
            'length': length,
            'width': width,
            'height': height,
            'cost': cost,
            'quantity': quantity
        }
        save_calculation_to_db(input_data, results, telegram_user_id)

        logger.info("Расчет успешно завершен")
        return jsonify(results)
=======
                "weight": float(total_weight.quantize(Decimal('0.01'))),  # Общий вес
                "density": float(density.quantize(Decimal('0.01'))),  # Плотность
                "productCost": float(cost),  # Стоимость товара
                "insuranceRate": f"{insurance_rate * Decimal('100'):.0f}%",  # Процент страхования
                "insuranceAmount": float(insurance.quantize(Decimal('0.01'))),  # Сумма страхового платежа
                "volume": float(total_volume.quantize(Decimal('0.01'))),  # Общий объем
                "boxCount": quantity  # Количество коробок
            },
            "bag": {
                "packedWeight": float(packed_weight_bag.quantize(Decimal('0.01'))),  # Вес с упаковкой (Мешок)
                "packagingCost": float((packaging_cost_bag * quantity).quantize(Decimal('0.01'))),  # Стоимость упаковки
                "unloadCost": float((unload_cost_bag * quantity).quantize(Decimal('0.01'))),  # Стоимость разгрузки
                "insurance": float(insurance.quantize(Decimal('0.01'))),  # Страховка
                "deliveryCostFast": float(delivery_cost_fast),  # Стоимость быстрой доставки
                "deliveryCostRegular": float(delivery_cost_regular),  # Стоимость обычной доставки
                "totalFast": float(
                    (packaging_cost_bag * quantity + unload_cost_bag * quantity + insurance + delivery_cost_fast).quantize(Decimal('0.01'))
                ),  # Итоговая стоимость (быстрая доставка)
                "totalRegular": float(
                    (packaging_cost_bag * quantity + unload_cost_bag * quantity + insurance + delivery_cost_regular).quantize(Decimal('0.01'))
                )  # Итоговая стоимость (обычная доставка)
            },
            "corners": {
                "packedWeight": float(packed_weight_corners.quantize(Decimal('0.01'))),  # Вес с упаковкой (Картонные уголки)
                "packagingCost": float((packaging_cost_corners * quantity).quantize(Decimal('0.01'))),  # Стоимость упаковки
                "unloadCost": float((unload_cost_corners * quantity).quantize(Decimal('0.01'))),  # Стоимость разгрузки
                "insurance": float(insurance.quantize(Decimal('0.01'))),  # Страховка
                "deliveryCostFast": float(delivery_cost_fast),  # Стоимость быстрой доставки
                "deliveryCostRegular": float(delivery_cost_regular),  # Стоимость обычной доставки
                "totalFast": float(
                    (packaging_cost_corners * quantity + unload_cost_corners * quantity + insurance + delivery_cost_fast).quantize(Decimal('0.01'))
                ),  # Итоговая стоимость (быстрая доставка)
                "totalRegular": float(
                    (packaging_cost_corners * quantity + unload_cost_corners * quantity + insurance + delivery_cost_regular).quantize(Decimal('0.01'))
                )  # Итоговая стоимость (обычная доставка)
            },
            "frame": {
                "packedWeight": float(packed_weight_frame.quantize(Decimal('0.01'))),  # Вес с упаковкой (Деревянный каркас)
                "packagingCost": float((packaging_cost_frame * quantity).quantize(Decimal('0.01'))),  # Стоимость упаковки
                "unloadCost": float((unload_cost_frame * quantity).quantize(Decimal('0.01'))),  # Стоимость разгрузки
                "insurance": float(insurance.quantize(Decimal('0.01'))),  # Страховка
                "deliveryCostFast": float(delivery_cost_fast),  # Стоимость быстрой доставки
                "deliveryCostRegular": float(delivery_cost_regular),  # Стоимость обычной доставки
                "totalFast": float(
                    (packaging_cost_frame * quantity + unload_cost_frame * quantity + insurance + delivery_cost_fast).quantize(Decimal('0.01'))
                ),  # Итоговая стоимость (быстрая доставка)
                "totalRegular": float(
                    (packaging_cost_frame * quantity + unload_cost_frame * quantity + insurance + delivery_cost_regular).quantize(Decimal('0.01'))
                )  # Итоговая стоимость (обычная доставка)
            }
        }

        # Сохраняем входные данные пользователя в базу данных
        save_user_input_to_db(
            category=category,
            weight=float(weight_per_box),
            length=float(length),
            width=float(width),
            height=float(height),
            cost=float(cost),
            quantity=quantity,
            telegram_user_id=telegram_user_id
        )

        # Сохраняем результаты расчета пользователя в базу данных
        save_user_calculation(
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
            frame_total_regular=float(results["frame"]["totalRegular"])
        )


        # Закрываем соединение с базой данных
        cursor.close()
        conn.close()

         # Логируем данные
        logger.info(f"Сформированные результаты: {json.dumps(results, ensure_ascii=False, indent=4)}")

        # Перенаправляем пользователя на страницу результатов
        # Перенаправляем пользователя на страницу результатов
        # encoded_results = quote_plus(json.dumps(results))
        # redirect_url = f"/result?results={encoded_results}"
        # return redirect(redirect_url)
        return render_template('result.html', results=results)

>>>>>>> 9dd40b7 (Test CI/CD deployment)

    except Exception as e:
        logger.error(f"Ошибка при расчете: {str(e)}", exc_info=True)
        return jsonify({"error": f"Внутренняя ошибка сервера: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8061, debug=True)
