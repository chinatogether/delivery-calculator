from flask import Flask, request, redirect, send_from_directory, render_template_string
import os
from datetime import datetime
import pandas as pd
import psycopg2
import time

app = Flask(__name__)

# Папка для хранения файлов
UPLOAD_FOLDER = "/home/chinatogether/xlsx-files"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Файл для хранения информации о последней загрузке
LAST_FILE_INFO = "/home/chinatogether/xlsx-files/last_file_info.txt"

# Стили для страницы
PAGE_STYLE = '''
<style>
    body {
        font-family: Arial, sans-serif;
        background-color: #f4f4f9;
        margin: 20px;
    }
    h1 {
        color: #333;
    }
    p {
        color: #555;
    }
    a.button {
        display: inline-block;
        padding: 10px 20px;
        margin: 10px 0;
        background-color: red; /* Кнопки красного цвета */
        color: white;
        text-decoration: none;
        border-radius: 5px;
    }
    a.button:hover {
        background-color: darkred;
    }
    form {
        margin-top: 20px;
    }
    input[type="submit"] {
        background-color: red;
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 5px;
        cursor: pointer;
    }
    input[type="submit"]:hover {
        background-color: darkred;
    }
</style>
'''

# Подключение к базе данных
def connect_to_db():
    return psycopg2.connect(
        dbname="delivery_db",
        user="chinatogether",
        password="O99ri1@",
        host="localhost",
        port="5432",
        connect_timeout=10  # Увеличиваем таймаут подключения
    )

# Очистка таблиц перед загрузкой данных
def clear_table():
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        print("Очищаем таблицу weight...")
        cursor.execute("TRUNCATE TABLE delivery_test.weight;")
        print("Очищаем таблицу density...")
        cursor.execute("TRUNCATE TABLE delivery_test.density;")
        conn.commit()
        print("Таблицы успешно очищены.")
    except Exception as e:
        conn.rollback()  # Откатываем изменения в случае ошибки
        print(f"Ошибка при очистке таблиц: {str(e)}")
        return f"Ошибка при очистке таблиц: {str(e)}", 500
    finally:
        cursor.close()
        conn.close()

# Загрузка данных из файла в базу данных
def load_data_to_db(file_path):
    try:
        start_time = time.time()
        print("Чтение данных из файла...")
        weight_data = pd.read_excel(file_path, sheet_name="weight", header=0)
        density_data = pd.read_excel(file_path, sheet_name="density", header=0)

        # Замена NaN на None
        weight_data = weight_data.where(pd.notnull(weight_data), None)
        density_data = density_data.where(pd.notnull(density_data), None)
        print(f"Файл успешно прочитан за {time.time() - start_time:.2f} секунд.")

        # Отладка: Вывод названий столбцов
        print("Названия столбцов в листе 'weight':")
        print(weight_data.columns)
        print("Названия столбцов в листе 'density':")
        print(density_data.columns)

        # Проверка наличия необходимых столбцов
        required_columns_weight = [
            'Минимальный вес', 'Максимальный вес', 'Коэфициент мешок', 'Мешок',
            'Стоимость упаковки мешок', 'Стоимость разгрузки мешок', 'Коэфициент уголок',
            'Картонные уголки', 'Стоимость упаковки уголок', 'Стоимость разгрузки уголок',
            'Коэфициент каркас', 'Деревянный каркас', 'Стоимость упаковки каркас',
            'Стоимость разгрузки каркас'
        ]
        required_columns_density = [
            'Категория', 'Минимальная плотность', 'Максимальная плотность',
            'Плотность', 'Быстрое авто ($/kg)', 'Обычное авто($/kg)'
        ]

        missing_columns_weight = [col for col in required_columns_weight if col not in weight_data.columns]
        if missing_columns_weight:
            print(f"Ошибка: в листе 'weight' отсутствуют следующие столбцы: {missing_columns_weight}")
            return f"Ошибка: в листе 'weight' отсутствуют следующие столбцы: {missing_columns_weight}", 400

        missing_columns_density = [col for col in required_columns_density if col not in density_data.columns]
        if missing_columns_density:
            print(f"Ошибка: в листе 'density' отсутствуют следующие столбцы: {missing_columns_density}")
            return f"Ошибка: в листе 'density' отсутствуют следующие столбцы: {missing_columns_density}", 400

        # Отладка: Вывод содержимого DataFrame
        print("Первые 5 строк из листа 'weight':")
        print(weight_data.head())
        print("Первые 5 строк из листа 'density':")
        print(density_data.head())

    except Exception as e:
        print(f"Ошибка при чтении файла: {str(e)}")
        return f"Ошибка при чтении файла: {str(e)}", 400

    try:
        conn = connect_to_db()
        cursor = conn.cursor()

        # Проверка подключения к базе данных
        cursor.execute("SELECT 1;")
        result = cursor.fetchone()
        print(f"Тестовое подключение к базе данных: {result}")

        # Преобразование данных в Python-типы
        def convert_to_python_types(row):
            return tuple(float(value) if isinstance(value, (float, int)) else value for value in row)

        # Пакетная вставка данных в таблицу weight
        start_time = time.time()
        print("Начало загрузки данных в таблицу weight...")
        weight_data_tuples = [
            (
                row['Минимальный вес'],
                row['Максимальный вес'],
                row['Коэфициент мешок'],
                row['Мешок'],
                row['Стоимость упаковки мешок'],
                row['Стоимость разгрузки мешок'],
                row['Коэфициент уголок'],
                row['Картонные уголки'],
                row['Стоимость упаковки уголок'],
                row['Стоимость разгрузки уголок'],
                row['Коэфициент каркас'],
                row['Деревянный каркас'],
                row['Стоимость упаковки каркас'],
                row['Стоимость разгрузки каркас']
            )
            for _, row in weight_data.iterrows()
        ]
        weight_data_tuples = [convert_to_python_types(row) for row in weight_data_tuples]
        print(f"Подготовлено {len(weight_data_tuples)} строк для вставки в таблицу weight.")
        print("Пример подготовленных данных для таблицы weight:")
        for row in weight_data_tuples[:5]:  # Выводим первые 5 строк для проверки
            print(row)

        cursor.executemany("""
            INSERT INTO delivery_test.weight (
                min_weight, max_weight, coefficient_bag, bag, bag_packing_cost, bag_unloading_cost,
                coefficient_corner, cardboard_corners, corner_packing_cost, corner_unloading_cost,
                coefficient_frame, wooden_frame, frame_packing_cost, frame_unloading_cost
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, weight_data_tuples)
        print(f"Данные успешно загружены в таблицу weight за {time.time() - start_time:.2f} секунд.")

        # Пакетная вставка данных в таблицу density
        start_time = time.time()
        print("Начало загрузки данных в таблицу density...")
        density_data_tuples = [
            (
                row['Категория'],
                row['Минимальная плотность'],
                row['Максимальная плотность'],
                row['Плотность'],
                row['Быстрое авто ($/kg)'],
                row['Обычное авто($/kg)']
            )
            for _, row in density_data.iterrows()
        ]
        density_data_tuples = [convert_to_python_types(row) for row in density_data_tuples]
        print(f"Подготовлено {len(density_data_tuples)} строк для вставки в таблицу density.")
        print("Пример подготовленных данных для таблицы density:")
        for row in density_data_tuples[:5]:  # Выводим первые 5 строк для проверки
            print(row)

        cursor.executemany("""
            INSERT INTO delivery_test.density (
                category, min_density, max_density, density_range,
                fast_delivery_cost, regular_delivery_cost
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, density_data_tuples)
        print(f"Данные успешно загружены в таблицу density за {time.time() - start_time:.2f} секунд.")

        conn.commit()
        cursor.close()
        conn.close()
        return "Данные успешно загружены в базу данных!"

    except Exception as e:
        conn.rollback()  # Откатываем изменения в случае ошибки
        print(f"Ошибка при загрузке данных в базу данных: {str(e)}")
        return f"Ошибка при загрузке данных в базу данных: {str(e)}", 500

# Главная страница
@app.route('/')
def index():
    # Чтение информации о последнем файле
    if os.path.exists(LAST_FILE_INFO):
        with open(LAST_FILE_INFO, 'r') as f:
            last_file_info = f.read()
    else:
        last_file_info = "Файл ещё не загружен."

    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Главная страница</title>
            ''' + PAGE_STYLE + '''
        </head>
        <body>
            <h1>Главная страница</h1>
            <p><strong>Последний загруженный файл:</strong> {{ last_file_info }}</p>
            <form method="post" enctype="multipart/form-data" action="/upload">
                <input type="file" name="file">
                <input type="submit" value="Загрузить новый файл">
            </form>
            <br>
            <a href="/download" class="button">Скачать последний файл</a>
            <br><br>
            <a href="/" class="button">На главную</a>
        </body>
        </html>
    ''', last_file_info=last_file_info)

# Маршрут для загрузки файла
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "Ошибка: файл не найден", 400
    file = request.files['file']
    if file.filename == '':
        return "Ошибка: имя файла пустое", 400

    # Сохраняем файл под фиксированным именем
    fixed_filename = "delivery_parameter.xlsx"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fixed_filename))

    # Записываем информацию о последнем файле
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    original_filename = file.filename
    with open(LAST_FILE_INFO, 'w') as f:
        f.write(f"{original_filename} (загружен {timestamp})")

    # Очищаем таблицы перед загрузкой данных
    clear_table()

    # Загружаем данные в базу данных
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], fixed_filename)
    result = load_data_to_db(file_path)

    return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Файл загружен</title>
            ''' + PAGE_STYLE + '''
        </head>
        <body>
            <h1>Файл успешно загружен!</h1>
            <p>Файл '{original_filename}' сохранён как 'delivery_parameter.xlsx'.</p>
            <p>{result}</p>
            <a href="/" class="button">На главную</a>
        </body>
        </html>
    '''

# Маршрут для скачивания файла
@app.route('/download', methods=['GET'])
def download_file():
    # Фиксированное имя файла
    fixed_filename = "delivery_parameter.xlsx"

    # Проверяем, существует ли файл
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], fixed_filename)
    if not os.path.exists(file_path):
        return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Ошибка</title>
                ''' + PAGE_STYLE + '''
            </head>
            <body>
                <h1>Ошибка</h1>
                <p>Файл не найден.</p>
                <a href="/" class="button">На главную</a>
            </body>
            </html>
        ''', 404

    return send_from_directory(app.config['UPLOAD_FOLDER'], fixed_filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8060)
