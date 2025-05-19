from flask import Flask, request, jsonify
import psycopg2
from decimal import Decimal, getcontext
from urllib.parse import unquote
from flask_cors import CORS
import logging
from datetime import datetime

# Настройка Decimal
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

def safe_decimal(value, default=Decimal('0')):
    """Безопасное преобразование значения в Decimal"""
    try:
        if value is None:
            return default
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except:
        return default

def save_telegram_user(telegram_id, username):
    """Сохранение пользователя Telegram в базу данных"""
    if not telegram_id or not username:
        logger.warning("Отсутствуют данные пользователя Telegram")
        return None
    
    try:
        with DatabaseConnection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id FROM delivery_test.telegram_users 
                    WHERE telegram_id = %s
                """, (telegram_id,))
                user = cursor.fetchone()

                if not user:
                    cursor.execute("""
                        INSERT INTO delivery_test.telegram_users (telegram_id, username)
                        VALUES (%s, %s)
                        RETURNING id
                    """, (telegram_id, username))
                    user_id = cursor.fetchone()[0]
                    conn.commit()
                    logger.info(f"Создан новый пользователь Telegram: {username} (ID: {telegram_id})")
                else:
                    user_id = user[0]
                    logger.info(f"Найден существующий пользователь Telegram: ID {user_id}")
                
                return user_id
    except Exception as e:
        logger.error(f"Ошибка при работе с базой данных: {e}")
        return None

def save_calculation_to_db(input_data, results, telegram_user_id=None):
    """Сохранение данных расчета в базу данных"""
    try:
        with DatabaseConnection() as conn:
            with conn.cursor() as cursor:
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
        category = unquote(request.args.get('category', '').strip())
        weight_per_box = safe_decimal(request.args.get('weight', 0))
        length = safe_decimal(request.args.get('length', 0))
        width = safe_decimal(request.args.get('width', 0))
        height = safe_decimal(request.args.get('height', 0))
        cost = safe_decimal(request.args.get('cost', 0))
        quantity = int(request.args.get('quantity', 1))
        telegram_id = request.args.get('telegram_id')
        username = request.args.get('username')

        # Валидация входных данных
        if not all([category, weight_per_box > 0, length > 0, width > 0, height > 0, cost > 0, quantity > 0]):
            error_msg = "Не все параметры указаны или имеют недопустимые значения"
            logger.warning(error_msg)
            return jsonify({"error": error_msg}), 400

        # Сохраняем пользователя Telegram
        telegram_user_id = None
        if telegram_id and username:
            telegram_user_id = save_telegram_user(telegram_id, username)

        # Расчет основных параметров
        volume_per_box = (length / Decimal(100)) * (width / Decimal(100)) * (height / Decimal(100))
        total_volume = volume_per_box * quantity
        total_weight = weight_per_box * quantity
        density = total_weight / total_volume if total_volume > 0 else Decimal('0')

        # Расчет страховки
        cost_per_kg = cost / total_weight if total_weight > 0 else Decimal('0')
        if cost_per_kg < 20:
            insurance_rate = Decimal('0.01')
        elif 20 <= cost_per_kg < 30:
            insurance_rate = Decimal('0.02')
        else:
            insurance_rate = Decimal('0.03')
        
        insurance = cost * insurance_rate

        # Получаем данные из базы
        try:
            with DatabaseConnection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            coefficient_bag, bag_packing_cost, bag_unloading_cost,
                            coefficient_corner, corner_packing_cost, corner_unloading_cost,
                            coefficient_frame, frame_packing_cost, frame_unloading_cost
                        FROM delivery_test.weight
                        WHERE min_weight <= %s AND max_weight > %s
                    """, (float(total_weight), float(total_weight)))
                    weight_data = cursor.fetchone()

                    if not weight_data:
                        error_msg = f"Не найден подходящий диапазон веса для {total_weight} кг"
                        logger.warning(error_msg)
                        return jsonify({"error": error_msg}), 400

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
        packed_weight_bag = (Decimal(packing_factor_bag) + total_weight)
        packed_weight_corners = (Decimal(additional_weight_corners) + total_weight)
        packed_weight_frame = (Decimal(additional_weight_frame) + total_weight)

        # Формируем результаты
        def format_result(value):
            return float(Decimal(value).quantize(Decimal('0.01')))

        results = {
            "generalInformation": {
                "category": category,
                "weight": format_result(total_weight),
                "density": format_result(density),
                "productCost": format_result(cost),
                "insuranceRate": f"{insurance_rate * 100:.0f}%",
                "insuranceAmount": format_result(insurance),
                "volume": format_result(total_volume),
                "boxCount": quantity
            },
            "bag": {
                "packedWeight": format_result(packed_weight_bag),
                "packagingCost": format_result(packaging_cost_bag * quantity),
                "unloadCost": format_result(unload_cost_bag * quantity),
                "insurance": format_result(insurance),
                "deliveryCostFast": delivery_cost_fast,
                "deliveryCostRegular": delivery_cost_regular,
                "totalFast": format_result(packaging_cost_bag * quantity + unload_cost_bag * quantity + insurance + delivery_cost_fast),
                "totalRegular": format_result(packaging_cost_bag * quantity + unload_cost_bag * quantity + insurance + delivery_cost_regular)
            },
            "corners": {
                "packedWeight": format_result(packed_weight_corners),
                "packagingCost": format_result(packaging_cost_corners * quantity),
                "unloadCost": format_result(unload_cost_corners * quantity),
                "insurance": format_result(insurance),
                "deliveryCostFast": delivery_cost_fast,
                "deliveryCostRegular": delivery_cost_regular,
                "totalFast": format_result(packaging_cost_corners * quantity + unload_cost_corners * quantity + insurance + delivery_cost_fast),
                "totalRegular": format_result(packaging_cost_corners * quantity + unload_cost_corners * quantity + insurance + delivery_cost_regular)
            },
            "frame": {
                "packedWeight": format_result(packed_weight_frame),
                "packagingCost": format_result(packaging_cost_frame * quantity),
                "unloadCost": format_result(unload_cost_frame * quantity),
                "insurance": format_result(insurance),
                "deliveryCostFast": delivery_cost_fast,
                "deliveryCostRegular": delivery_cost_regular,
                "totalFast": format_result(packaging_cost_frame * quantity + unload_cost_frame * quantity + insurance + delivery_cost_fast),
                "totalRegular": format_result(packaging_cost_frame * quantity + unload_cost_frame * quantity + insurance + delivery_cost_regular)
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

    except Exception as e:
        logger.error(f"Ошибка при расчете: {str(e)}", exc_info=True)
        return jsonify({"error": f"Внутренняя ошибка сервера: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8061)
