from flask import Flask, request, jsonify
import psycopg2
from decimal import Decimal, getcontext
import urllib.parse
from flask_cors import CORS
import logging

# Устанавливаем точность для Decimal
getcontext().prec = 6

app = Flask(__name__)
CORS(app)  # Включение CORS для всех маршрутов

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Подключение к базе данных
def connect_to_db():
    return psycopg2.connect(
        dbname="delivery_db",
        user="chinatogether",
        password="O99ri1@",
        host="localhost",
        port="5432",
        connect_timeout=10
    )

# Сохранение данных пользователя Telegram в базу данных (необязательно)
def save_telegram_user(telegram_id, username):
    if not telegram_id or not username:
        logger.warning("Данные пользователя Telegram отсутствуют. Пропуск сохранения.")
        return None
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        # Проверяем, существует ли пользователь в таблице telegram_users
        cursor.execute("""
            SELECT id FROM delivery_test.telegram_users WHERE telegram_id = %s
        """, (telegram_id,))
        user = cursor.fetchone()

        if not user:
            # Если пользователь не существует, создаем новую запись
            cursor.execute("""
                INSERT INTO delivery_test.telegram_users (telegram_id, username)
                VALUES (%s, %s)
                RETURNING id
            """, (telegram_id, username))
            user_id = cursor.fetchone()[0]
        else:
            # Если пользователь существует, используем его ID
            user_id = user[0]

        conn.commit()
        logger.info(f"Пользователь Telegram с ID {telegram_id} успешно сохранен.")
        return user_id
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка при сохранении данных пользователя Telegram: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

# Сохранение входных данных пользователя в базу данных
def save_user_input_to_db(category, weight, length, width, height, cost, quantity, telegram_user_id=None):
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        # Сохраняем входные данные пользователя с привязкой к telegram_user_id (если он есть)
        cursor.execute("""
            INSERT INTO delivery_test.user_inputs (
                category, weight, length, width, height, cost, quantity, telegram_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (category, weight, length, width, height, cost, quantity, telegram_user_id))
        conn.commit()
        logger.info("Входные данные успешно записаны в базу данных.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка при записи входных данных: {str(e)}")
        return f"Ошибка при записи входных данных: {str(e)}", 500
    finally:
        cursor.close()
        conn.close()

# Маршрут для расчетов
@app.route('/calculate', methods=['GET'])
def calculate():
    try:
        # Декодирование параметров запроса (для корректной обработки кириллицы)
        category = urllib.parse.unquote(request.args.get('category', '').strip())
        weight_per_box = Decimal(request.args.get('weight', 0))  # Вес одной коробки
        length = Decimal(request.args.get('length', 0))
        width = Decimal(request.args.get('width', 0))
        height = Decimal(request.args.get('height', 0))
        cost = Decimal(request.args.get('cost', 0))
        quantity = int(request.args.get('quantity', 1))  # Количество коробок
        telegram_id = request.args.get('telegram_id', None)  # ID пользователя Telegram
        username = request.args.get('username', None)  # Никнейм пользователя Telegram

        # Проверяем, что все основные параметры указаны
        if not all([category, weight_per_box > 0, length > 0, width > 0, height > 0, cost > 0, quantity > 0]):
            return jsonify({"error": "Не все основные параметры указаны или имеют недопустимые значения"}), 400

        # Сохраняем данные пользователя Telegram (если они есть)
        telegram_user_id = None
        if telegram_id and username:
            telegram_user_id = save_telegram_user(telegram_id, username)
            if not telegram_user_id:
                logger.warning("Ошибка при сохранении данных пользователя Telegram. Продолжаем без них.")

        # Расчет объема и плотности
        volume_per_box = (length / 100) * (width / 100) * (height / 100)  # Объем одной коробки в м³
        total_volume = volume_per_box * quantity  # Общий объем
        if volume_per_box == 0:
            return jsonify({"error": "Объем не может быть равен нулю"}), 400
        density = weight_per_box / volume_per_box  # Плотность одной коробки

        # Рассчитываем общий вес (вес одной коробки × количество коробок)
        total_weight = weight_per_box * quantity

        # Рассчитываем стоимость товара за кг
        cost_per_kg = cost / total_weight

        # Определяем процент страхования
        if cost_per_kg < 20:
            insurance_rate = Decimal('0.01')  # 1%
        elif 20 <= cost_per_kg < 30:
            insurance_rate = Decimal('0.02')  # 2%
        else:
            insurance_rate = Decimal('0.03')  # 3%

        # Рассчитываем сумму страхового платежа
        insurance = cost * insurance_rate

        # Подключаемся к базе данных
        conn = connect_to_db()
        cursor = conn.cursor()

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

        # Извлекаем данные из найденной строки Weight
        (
            _, _, packing_factor_bag, _, packaging_cost_bag, unload_cost_bag,
            additional_weight_corners, _, packaging_cost_corners, unload_cost_corners,
            additional_weight_frame, _, packaging_cost_frame, unload_cost_frame
        ) = result_row_weight

        # Находим строку с подходящей плотностью на листе Density
        cursor.execute("""
            SELECT category, min_density, max_density, density_range, fast_delivery_cost, regular_delivery_cost
            FROM delivery_test.density 
            WHERE category = %s AND min_density <= %s AND max_density > %s
        """, (category, density, density))
        result_row_density = cursor.fetchone()

        if not result_row_density:
            return jsonify({"error": "Плотность не попадает в диапазон для данной категории"}), 400

        # Извлекаем данные из найденной строки Density
        (_, _, _, _, fast_car_cost_per_kg, regular_car_cost_per_kg) = result_row_density

        # Вычисляем общую стоимость доставки
        delivery_cost_fast = round(float(fast_car_cost_per_kg) * float(total_weight), 2)
        delivery_cost_regular = round(float(regular_car_cost_per_kg) * float(total_weight), 2)

        # Вычисляем вес с упаковкой для каждого типа упаковки
        packed_weight_bag = (packing_factor_bag + total_weight)  # Вес с упаковкой (Мешок)
        packed_weight_corners = (additional_weight_corners + total_weight)  # Вес с упаковкой (Картонные уголки)
        packed_weight_frame = (additional_weight_frame + total_weight)  # Вес с упаковкой (Деревянный каркас)

        # Формируем результаты для каждой категории упаковки
        results = {
            "generalInformation": {
                "category": category,
                "weight": round(float(total_weight), 2),  # Общий вес
                "density": round(float(density), 2),
                "productCost": float(cost),
                "insuranceRate": f"{insurance_rate * 100:.0f}%",
                "insuranceAmount": float(round(insurance, 2)),
                "volume": float(round(total_volume, 2)),  # Общий объем
                "boxCount": quantity
            },
            "bag": {
                "packedWeight": float(round(packed_weight_bag, 2)),  # Вес с упаковкой (Мешок)
                "packagingCost": float(round(packaging_cost_bag * quantity, 2)),  # Стоимость упаковки
                "unloadCost": float(round(unload_cost_bag * quantity, 2)),  # Стоимость разгрузки
                "insurance": float(round(insurance, 2)),  # Страховка
                "deliveryCostFast": float(delivery_cost_fast),  # Стоимость быстрой доставки
                "deliveryCostRegular": float(delivery_cost_regular),  # Стоимость обычной доставки
                "totalFast": float(round(packaging_cost_bag * quantity + unload_cost_bag * quantity + insurance + delivery_cost_fast, 2)),
                "totalRegular": float(round(packaging_cost_bag * quantity + unload_cost_bag * quantity + insurance + delivery_cost_regular, 2))
            },
            "corners": {
                "packedWeight": float(round(packed_weight_corners, 2)),  # Вес с упаковкой (Картонные уголки)
                "packagingCost": float(round(packaging_cost_corners * quantity, 2)),  # Стоимость упаковки
                "unloadCost": float(round(unload_cost_corners * quantity, 2)),  # Стоимость разгрузки
                "insurance": float(round(insurance, 2)),  # Страховка
                "deliveryCostFast": float(delivery_cost_fast),  # Стоимость быстрой доставки
                "deliveryCostRegular": float(delivery_cost_regular),  # Стоимость обычной доставки
                "totalFast": float(round(packaging_cost_corners * quantity + unload_cost_corners * quantity + insurance + delivery_cost_fast, 2)),
                "totalRegular": float(round(packaging_cost_corners * quantity + unload_cost_corners * quantity + insurance + delivery_cost_regular, 2))
            },
            "frame": {
                "packedWeight": float(round(packed_weight_frame, 2)),  # Вес с упаковкой (Деревянный каркас)
                "packagingCost": float(round(packaging_cost_frame * quantity, 2)),  # Стоимость упаковки
                "unloadCost": float(round(unload_cost_frame * quantity, 2)),  # Стоимость разгрузки
                "insurance": float(round(insurance, 2)),  # Страховка
                "deliveryCostFast": float(delivery_cost_fast),  # Стоимость быстрой доставки
                "deliveryCostRegular": float(delivery_cost_regular),  # Стоимость обычной доставки
                "totalFast": float(round(packaging_cost_frame * quantity + unload_cost_frame * quantity + insurance + delivery_cost_fast, 2)),
                "totalRegular": float(round(packaging_cost_frame * quantity + unload_cost_frame * quantity + insurance + delivery_cost_regular, 2))
            }
        }

        # Запись входных данных в базу данных
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

        # Закрываем соединение с базой данных
        cursor.close()
        conn.close()

        # Возвращаем JSON-ответ
        return jsonify(results)

    except Exception as e:
        logger.error(f"Произошла ошибка: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8061)
