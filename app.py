from flask import Flask, request, jsonify
import psycopg2
from decimal import Decimal

app = Flask(__name__)

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

# Маршрут для расчетов
@app.route('/calculate', methods=['GET'])
def calculate():
    try:
        # Получаем параметры из запроса
        category = request.args.get('category', '').strip()
        weight_per_box = float(request.args.get('weight', 0))  # Вес одной коробки
        length = float(request.args.get('length', 0))
        width = float(request.args.get('width', 0))
        height = float(request.args.get('height', 0))
        cost = float(request.args.get('cost', 0))
        quantity = int(request.args.get('quantity', 1))  # Количество коробок

        # Проверяем, что все параметры указаны
        if not all([category, weight_per_box > 0, length > 0, width > 0, height > 0, cost > 0, quantity > 0]):
            return jsonify({"error": "Не все параметры указаны или имеют недопустимые значения"}), 400

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
        insurance = cost * float(insurance_rate)

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
            SELECT * FROM delivery_test.density
            WHERE category = %s AND min_density <= %s AND max_density > %s
        """, (category, density, density))
        result_row_density = cursor.fetchone()

        if not result_row_density:
            return jsonify({"error": "Плотность не попадает в диапазон для данной категории"}), 400

        # Извлекаем данные из найденной строки Density
        (_, _, _, _, fast_car_cost_per_kg, regular_car_cost_per_kg) = result_row_density

        # Вычисляем общую стоимость доставки
        delivery_cost_fast = round(fast_car_cost_per_kg * total_weight, 2)
        delivery_cost_regular = round(regular_car_cost_per_kg * total_weight, 2)

        # Вычисляем вес с упаковкой для каждого типа упаковки
        packed_weight_bag = (packing_factor_bag + total_weight)  # Вес с упаковкой (Мешок)
        packed_weight_corners = (additional_weight_corners + total_weight)  # Вес с упаковкой (Картонные уголки)
        packed_weight_frame = (additional_weight_frame + total_weight)  # Вес с упаковкой (Деревянный каркас)

        # Формируем результаты для каждой категории упаковки
        results = {
            "generalInformation": {
                "category": category,
                "weight": round(total_weight, 2),  # Общий вес
                "density": round(density, 2),
                "productCost": cost,
                "insuranceRate": f"{insurance_rate * 100:.0f}%",
                "insuranceAmount": round(insurance, 2),
                "volume": round(total_volume, 2),  # Общий объем
                "boxCount": quantity
            },
            "bag": {
                "packedWeight": round(packed_weight_bag, 2),  # Вес с упаковкой (Мешок)
                "packagingCost": round(packaging_cost_bag * quantity, 2),  # Стоимость упаковки
                "unloadCost": round(unload_cost_bag * quantity, 2),  # Стоимость разгрузки
                "insurance": round(insurance, 2),  # Страховка
                "deliveryCostFast": delivery_cost_fast,  # Стоимость быстрой доставки
                "deliveryCostRegular": delivery_cost_regular,  # Стоимость обычной доставки
                "totalFast": round(packaging_cost_bag * quantity + unload_cost_bag * quantity + insurance + delivery_cost_fast, 2),
                "totalRegular": round(packaging_cost_bag * quantity + unload_cost_bag * quantity + insurance + delivery_cost_regular, 2)
            },
            "corners": {
                "packedWeight": round(packed_weight_corners, 2),  # Вес с упаковкой (Картонные уголки)
                "packagingCost": round(packaging_cost_corners * quantity, 2),  # Стоимость упаковки
                "unloadCost": round(unload_cost_corners * quantity, 2),  # Стоимость разгрузки
                "insurance": round(insurance, 2),  # Страховка
                "deliveryCostFast": delivery_cost_fast,  # Стоимость быстрой доставки
                "deliveryCostRegular": delivery_cost_regular,  # Стоимость обычной доставки
                "totalFast": round(packaging_cost_corners * quantity + unload_cost_corners * quantity + insurance + delivery_cost_fast, 2),
                "totalRegular": round(packaging_cost_corners * quantity + unload_cost_corners * quantity + insurance + delivery_cost_regular, 2)
            },
            "frame": {
                "packedWeight": round(packed_weight_frame, 2),  # Вес с упаковкой (Деревянный каркас)
                "packagingCost": round(packaging_cost_frame * quantity, 2),  # Стоимость упаковки
                "unloadCost": round(unload_cost_frame * quantity, 2),  # Стоимость разгрузки
                "insurance": round(insurance, 2),  # Страховка
                "deliveryCostFast": delivery_cost_fast,  # Стоимость быстрой доставки
                "deliveryCostRegular": delivery_cost_regular,  # Стоимость обычной доставки
                "totalFast": round(packaging_cost_frame * quantity + unload_cost_frame * quantity + insurance + delivery_cost_fast, 2),
                "totalRegular": round(packaging_cost_frame * quantity + unload_cost_frame * quantity + insurance + delivery_cost_regular, 2)
            }
        }

        # Закрываем соединение с базой данных
        cursor.close()
        conn.close()

        # Возвращаем JSON-ответ
        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8061)
