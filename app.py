from flask import Flask, request, redirect, send_from_directory, render_template_string, render_template
import os
from datetime import datetime
import psycopg2

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
        port="5432"
    )

# Очистка таблиц перед загрузкой
def clear_table():
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("TRUNCATE TABLE delivery_test.weight;")
        cursor.execute("TRUNCATE TABLE delivery_test.density;")
        conn.commit()
        print("Таблицы успешно очищены.")
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при очистке таблиц: {str(e)}")
    finally:
        cursor.close()
        conn.close()

# Загрузка данных в БД
def load_data_to_db(file_path):
    try:
        weight_data = pd.read_excel(file_path, sheet_name="weight", header=0)
        density_data = pd.read_excel(file_path, sheet_name="density", header=0)

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

        missing_weight = [col for col in required_columns_weight if col not in weight_data.columns]
        missing_density = [col for col in required_columns_density if col not in density_data.columns]

        if missing_weight or missing_density:
            raise ValueError(f"Недостающие столбцы: {missing_weight + missing_density}")

        conn = connect_to_db()
        cursor = conn.cursor()

        weight_rows = [
            tuple(row[col] for col in required_columns_weight)
            for _, row in weight_data.iterrows()
        ]
        cursor.executemany("""
            INSERT INTO delivery_test.weight (
                min_weight, max_weight, coefficient_bag, bag, 
                bag_packing_cost, bag_unloading_cost,
                coefficient_corner, cardboard_corners, 
                corner_packing_cost, corner_unloading_cost,
                coefficient_frame, wooden_frame, 
                frame_packing_cost, frame_unloading_cost
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, weight_rows)

        density_rows = [
            tuple(row[col] for col in required_columns_density)
            for _, row in density_data.iterrows()
        ]
        cursor.executemany("""
            INSERT INTO delivery_test.density (
                category, min_density, max_density, 
                density_range, fast_delivery_cost, regular_delivery_cost
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, density_rows)

        conn.commit()
        cursor.close()
        conn.close()
        return "Данные успешно загружены!"
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при загрузке данных: {str(e)}")
        return f"Ошибка при загрузке данных: {str(e)}"

# Главная страница
@app.route('/')
def index():
    if os.path.exists(LAST_FILE_INFO):
        with open(LAST_FILE_INFO, 'r') as f:
            last_file_info = f.read()
    else:
        last_file_info = "Файл ещё не загружен."

    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head><title>Главная</title>''' + PAGE_STYLE + '''</head>
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

    fixed_filename = "delivery_parameter.xlsx"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fixed_filename))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    original_name = file.filename
    with open(LAST_FILE_INFO, 'w') as f:
        f.write(f"{original_name} (загружен {timestamp})")

    clear_table()
    result = load_data_to_db(os.path.join(app.config['UPLOAD_FOLDER'], fixed_filename))

    return f'''
        <html><head><title>Файл загружен</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>Файл успешно загружен!</h1>
            <p>Файл "{original_name}" сохранён как "{fixed_filename}".</p>
            <p>{result}</p>
            <a href="/" class="button">На главную</a>
        </body></html>
    '''

# Маршрут скачивания файла
@app.route('/download')
def download_file():
    fixed_filename = "delivery_parameter.xlsx"
    path = os.path.join(app.config['UPLOAD_FOLDER'], fixed_filename)
    if not os.path.exists(path):
        return f'''
            <html><head><title>Ошибка</title></head>
            <body style="font-family: Arial; padding: 20px;">
                <h1>Ошибка</h1>
                <p>Файл не найден.</p>
                <a href="/" class="button">На главную</a>
            </body></html>
        ''', 404
    return send_from_directory(app.config['UPLOAD_FOLDER'], fixed_filename, as_attachment=True)

# Получение данных из таблицы weight
def get_weight_data():
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM delivery_test.weight ORDER BY id ASC LIMIT 100")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return {"columns": columns, "rows": rows}
    finally:
        cursor.close()
        conn.close()

# Получение данных из таблицы density
def get_density_data():
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM delivery_test.density ORDER BY id ASC LIMIT 100")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return {"columns": columns, "rows": rows}
    finally:
        cursor.close()
        conn.close()

# Получение аналитики по расчетам
def get_analytics_data():
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM delivery_test.user_calculation")
        total_calculations = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM delivery_test.user_calculation WHERE created_at >= CURRENT_DATE")
        today_calculations = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(total_weight) FROM delivery_test.user_calculation")
        avg_weight = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM delivery_test.user_calculation 
            GROUP BY category 
            ORDER BY count DESC 
            LIMIT 1
        """)
        popular_category_data = cursor.fetchone()
        popular_category = popular_category_data[0] if popular_category_data else "Нет данных"

        cursor.execute("""
            SELECT COUNT(DISTINCT telegram_user_id) 
            FROM delivery_test.user_calculation 
            WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
        """)
        active_users = cursor.fetchone()[0]

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

# Дашборд с данными из weight и density + графики
@app.route('/dashboard')
def dashboard():
    conn = connect_to_db()
    cursor = conn.cursor()

    try:
        # Расчеты по дням
        cursor.execute("""
            SELECT DATE(created_at) AS date, COUNT(*) AS count
            FROM delivery_test.user_calculation
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            LIMIT 30
        """)
        calculations_by_day = cursor.fetchall()

        # Топ пользователей по количеству расчетов
        cursor.execute("""
            SELECT u.username, COUNT(c.id) AS calculation_count
            FROM delivery_test.telegram_users u
            JOIN delivery_test.user_calculation c ON u.id = c.telegram_user_id
            GROUP BY u.username
            ORDER BY calculation_count DESC
            LIMIT 5
        """)
        calculations_per_user = cursor.fetchall()

        # Последние расчеты за неделю
        cursor.execute("""
            SELECT u.username, c.category, c.created_at
            FROM delivery_test.user_calculation c
            LEFT JOIN delivery_test.telegram_users u ON c.telegram_user_id = u.id
            WHERE c.created_at >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY c.created_at DESC
            LIMIT 50
        """)
        recent_calculations = cursor.fetchall()

    except Exception as e:
        print(f"Ошибка при загрузке дашборда: {str(e)}")
        return "Ошибка при загрузке данных", 500
    finally:
        cursor.close()
        conn.close()

    return render_template('dashboard.html',
                           calculations_by_day=calculations_by_day,
                           calculations_per_user=calculations_per_user,
                           recent_calculations=recent_calculations)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8060)
