from flask import Flask, request, redirect, send_from_directory, render_template_string, render_template, jsonify
import os
from datetime import datetime, timedelta
import psycopg2
import pandas as pd
from psycopg2.extras import RealDictCursor
import time
import glob

app = Flask(__name__, template_folder='templates')

# Папка для хранения файлов
UPLOAD_FOLDER = "/home/chinatogether/xlsx-files"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Файл для информации о последней загрузке
LAST_FILE_INFO = "/home/chinatogether/xlsx-files/last_file_info.txt"

# Стили для страницы (используется только в index)
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
    a.button {
        display: inline-block;
        padding: 10px 20px;
        margin-top: 10px;
        background-color: red;
        color: white;
        text-decoration: none;
        border-radius: 5px;
    }
    a.button:hover {
        background-color: darkred;
    }
    .file-info {
        margin-top: 20px;
        background: #fff;
        padding: 15px;
        border-radius: 6px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.1);
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
        connect_timeout=10
    )

# Удаление старых файлов
def remove_old_files():
    """Удаляет все Excel файлы из папки загрузки"""
    try:
        # Ищем все Excel файлы
        excel_files = glob.glob(os.path.join(app.config['UPLOAD_FOLDER'], "*.xlsx"))
        excel_files.extend(glob.glob(os.path.join(app.config['UPLOAD_FOLDER'], "*.xls")))
        
        for file_path in excel_files:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Удален старый файл: {file_path}")
                
        return True
    except Exception as e:
        print(f"Ошибка при удалении старых файлов: {str(e)}")
        return False

# Очистка таблиц перед загрузкой
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
        return True
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при очистке таблиц: {str(e)}")
        return False
    finally:
        cursor.close()
        conn.close()

# Загрузка данных в БД (на основе вашего рабочего кода)
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
            return f"Ошибка: в листе 'weight' отсутствуют следующие столбцы: {missing_columns_weight}"

        missing_columns_density = [col for col in required_columns_density if col not in density_data.columns]
        if missing_columns_density:
            print(f"Ошибка: в листе 'density' отсутствуют следующие столбцы: {missing_columns_density}")
            return f"Ошибка: в листе 'density' отсутствуют следующие столбцы: {missing_columns_density}"

        # Отладка: Вывод содержимого DataFrame
        print("Первые 5 строк из листа 'weight':")
        print(weight_data.head())
        print("Первые 5 строк из листа 'density':")
        print(density_data.head())

    except Exception as e:
        print(f"Ошибка при чтении файла: {str(e)}")
        return f"Ошибка при чтении файла: {str(e)}"

    try:
        conn = connect_to_db()
        cursor = conn.cursor()

        # Проверка подключения к базе данных
        cursor.execute("SELECT 1;")
        result = cursor.fetchone()
        print(f"Тестовое подключение к базе данных: {result}")

        # Функция конвертации типов данных (из вашего рабочего кода)
        def convert_to_python_types(row):
            converted_row = []
            for value in row:
                if pd.isna(value):
                    converted_row.append(None)
                elif isinstance(value, (pd.Timestamp, pd._libs.tslibs.timestamps.Timestamp)):
                    converted_row.append(value.to_pydatetime())
                elif hasattr(value, 'item'):  # numpy types
                    converted_row.append(value.item())
                else:
                    converted_row.append(value)
            return tuple(converted_row)

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
        for row in weight_data_tuples[:3]:  # Выводим первые 3 строки для проверки
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
        for row in density_data_tuples[:3]:  # Выводим первые 3 строки для проверки
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
        if 'conn' in locals():
            conn.rollback()
        print(f"Ошибка при загрузке данных в базу данных: {str(e)}")
        return f"Ошибка при загрузке данных в базу данных: {str(e)}"

# Главная страница
@app.route('/')
def index():
    # Чтение информации о последнем файле
    if os.path.exists(LAST_FILE_INFO):
        with open(LAST_FILE_INFO, 'r', encoding='utf-8') as f:
            last_file_info = f.read()
    else:
        last_file_info = "Файл ещё не загружен."

    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head><title>Главная страница</title>''' + PAGE_STYLE + '''</head>
        <body>
            <h1>Главная страница системы доставки</h1>
            <div class="file-info">
                <p><strong>Последний загруженный файл:</strong><br>{{ last_file_info }}</p>
            </div>
            <form method="post" enctype="multipart/form-data" action="/upload">
                <label for="file">Выберите Excel файл для загрузки:</label><br>
                <input type="file" name="file" accept=".xlsx,.xls" required>
                <input type="submit" value="Загрузить новый файл">
            </form>
            <br>
            <a href="/download" class="button">Скачать текущий файл</a>
            <br><br>
            <a href="/dashboard" class="button">📊 Перейти к дашборду</a>
        </body></html>
    ''', last_file_info=last_file_info)

# Маршрут загрузки файла
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "Ошибка: файл не найден", 400
    file = request.files['file']
    if file.filename == '':
        return "Ошибка: имя файла пустое", 400

    # Проверяем расширение файла
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        return "Ошибка: поддерживаются только файлы Excel (.xlsx, .xls)", 400

    try:
        # Удаляем старые файлы
        remove_old_files()
        
        # Сохраняем новый файл
        fixed_filename = "delivery_parameter.xlsx"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], fixed_filename)
        file.save(file_path)

        # Записываем информацию о файле
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        original_name = file.filename
        
        with open(LAST_FILE_INFO, 'w', encoding='utf-8') as f:
            f.write(f"{original_name} (загружен {timestamp})")

        # Очищаем таблицы
        if not clear_table():
            return "Ошибка при очистке таблиц", 500
            
        # Загружаем данные в БД
        result = load_data_to_db(file_path)

        return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Файл загружен</title>
                {PAGE_STYLE}
            </head>
            <body>
                <h1>✅ Файл успешно загружен!</h1>
                <div class="file-info">
                    <p><strong>Исходный файл:</strong> "{original_name}"</p>
                    <p><strong>Сохранен как:</strong> "{fixed_filename}"</p>
                    <p><strong>Время загрузки:</strong> {timestamp}</p>
                    <p><strong>Результат загрузки в БД:</strong> {result}</p>
                </div>
                <br>
                <a href="/" class="button">← На главную</a>
                <a href="/dashboard" class="button">📊 К дашборду</a>
            </body>
            </html>
        '''
        
    except Exception as e:
        return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Ошибка загрузки</title>
                {PAGE_STYLE}
            </head>
            <body>
                <h1>❌ Ошибка при загрузке файла</h1>
                <p>Детали ошибки: {str(e)}</p>
                <a href="/" class="button">← На главную</a>
            </body>
            </html>
        ''', 500

# Маршрут скачивания файла
@app.route('/download')
def download_file():
    fixed_filename = "delivery_parameter.xlsx"
    path = os.path.join(app.config['UPLOAD_FOLDER'], fixed_filename)
    if not os.path.exists(path):
        return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Ошибка</title>
                {PAGE_STYLE}
            </head>
            <body>
                <h1>❌ Ошибка</h1>
                <p>Файл не найден. Возможно, он еще не был загружен.</p>
                <a href="/" class="button">← На главную</a>
            </body>
            </html>
        ''', 404
    return send_from_directory(app.config['UPLOAD_FOLDER'], fixed_filename, as_attachment=True)

# Получение аналитики по расчетам
def get_analytics_data():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Общее количество расчетов
        cursor.execute("SELECT COUNT(*) as total FROM delivery_test.user_calculation")
        total_calculations = cursor.fetchone()['total']

        # Расчеты за сегодня
        cursor.execute("""
            SELECT COUNT(*) as today 
            FROM delivery_test.user_calculation 
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        today_calculations = cursor.fetchone()['today']

        # Средний вес
        cursor.execute("SELECT AVG(total_weight) as avg_weight FROM delivery_test.user_calculation")
        avg_weight = cursor.fetchone()['avg_weight'] or 0

        # Популярная категория
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM delivery_test.user_calculation 
            GROUP BY category 
            ORDER BY count DESC 
            LIMIT 1
        """)
        popular_category_data = cursor.fetchone()
        popular_category = popular_category_data['category'] if popular_category_data else "Нет данных"

        # Активные пользователи за неделю
        cursor.execute("""
            SELECT COUNT(DISTINCT telegram_user_id) as active_users
            FROM delivery_test.user_calculation 
            WHERE created_at >= NOW() - INTERVAL '7 days'
        """)
        active_users = cursor.fetchone()['active_users']

        return {
            'total_calculations': total_calculations,
            'today_calculations': today_calculations,
            'avg_weight': float(avg_weight),
            'popular_category': popular_category,
            'active_users': active_users
        }
    except Exception as e:
        print(f"Ошибка при получении статистики: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

# Получение данных для воронки
def get_funnel_data():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Общее количество пользователей
        cursor.execute("SELECT COUNT(*) as visits FROM delivery_test.telegram_users")
        visits = cursor.fetchone()['visits']
        
        # Пользователи, которые начали расчет
        cursor.execute("""
            SELECT COUNT(DISTINCT telegram_user_id) as started 
            FROM delivery_test.user_inputs
        """)
        started = cursor.fetchone()['started']
        
        # Пользователи, которые завершили расчет
        cursor.execute("""
            SELECT COUNT(DISTINCT telegram_user_id) as completed 
            FROM delivery_test.user_calculation
        """)
        completed = cursor.fetchone()['completed']
        
        # Пользователи, которые сохранили результат
        cursor.execute("""
            SELECT COUNT(DISTINCT telegram_user_id) as saved 
            FROM delivery_test.user_actions 
            WHERE action LIKE '%save%' OR action LIKE '%download%'
        """)
        saved_result = cursor.fetchone()
        saved = saved_result['saved'] if saved_result else 0

        # Расчет конверсий
        conversion_started = (started / visits * 100) if visits > 0 else 0
        conversion_completed = (completed / started * 100) if started > 0 else 0
        conversion_saved = (saved / completed * 100) if completed > 0 else 0

        return {
            'visits': visits,
            'started': started,
            'completed': completed,
            'saved': saved,
            'conversion_started': conversion_started,
            'conversion_completed': conversion_completed,
            'conversion_saved': conversion_saved
        }
    except Exception as e:
        print(f"Ошибка при получении данных воронки: {str(e)}")
        return {
            'visits': 0, 'started': 0, 'completed': 0, 'saved': 0,
            'conversion_started': 0, 'conversion_completed': 0, 'conversion_saved': 0
        }
    finally:
        cursor.close()
        conn.close()

# API для получения статистики
@app.route('/api/stats')
def api_stats():
    analytics = get_analytics_data()
    if analytics:
        return jsonify(analytics)
    else:
        return jsonify({'error': 'Ошибка получения статистики'}), 500

# Дашборд
@app.route('/dashboard')
def dashboard():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Расчеты по дням
        cursor.execute("""
            SELECT DATE(created_at) AS date, COUNT(*) AS count
            FROM delivery_test.user_calculation
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            LIMIT 30
        """)
        calculations_by_day = [(row['date'].strftime('%d.%m'), row['count']) for row in cursor.fetchall()]

        # Топ пользователей по количеству расчетов
        cursor.execute("""
            SELECT u.username, COUNT(c.id) AS calculation_count
            FROM delivery_test.telegram_users u
            JOIN delivery_test.user_calculation c ON u.id = c.telegram_user_id
            GROUP BY u.username
            ORDER BY calculation_count DESC
            LIMIT 5
        """)
        calculations_per_user = [(row['username'] or 'Аноним', row['calculation_count']) for row in cursor.fetchall()]

        # Последние расчеты за 24 часа
        cursor.execute("""
            SELECT u.username, c.category, c.total_weight, c.product_cost, c.created_at
            FROM delivery_test.user_calculation c
            LEFT JOIN delivery_test.telegram_users u ON c.telegram_user_id = u.id
            WHERE c.created_at >= NOW() - INTERVAL '24 hours'
            ORDER BY c.created_at DESC
            LIMIT 50
        """)
        recent_calculations = cursor.fetchall()

        # Детальная аналитика по пользователям
        cursor.execute("""
            SELECT u.username,
                   COUNT(c.id) as calculation_count,
                   SUM(c.total_weight) as total_weight,
                   SUM(c.product_cost) as total_cost,
                   MAX(c.created_at) as last_calculation
            FROM delivery_test.telegram_users u
            LEFT JOIN delivery_test.user_calculation c ON u.id = c.telegram_user_id
            GROUP BY u.id, u.username
            HAVING COUNT(c.id) > 0
            ORDER BY calculation_count DESC
            LIMIT 20
        """)
        user_analytics = cursor.fetchall()

    except Exception as e:
        print(f"Ошибка при загрузке дашборда: {str(e)}")
        return "Ошибка при загрузке данных", 500
    finally:
        cursor.close()
        conn.close()

    # Получаем аналитику и данные воронки
    analytics = get_analytics_data() or {}
    funnel_data = get_funnel_data()

    return render_template('dashboard.html',
                           calculations_by_day=calculations_by_day,
                           calculations_per_user=calculations_per_user,
                           recent_calculations=recent_calculations,
                           user_analytics=user_analytics,
                           analytics=analytics,
                           funnel_data=funnel_data)

if __name__ == '__main__':
    # Убеждаемся, что папка для загрузки существует
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(host='0.0.0.0', port=8060, debug=True)
