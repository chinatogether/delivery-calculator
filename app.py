from flask import Flask, request, redirect, send_from_directory, render_template_string, render_template, jsonify
import os
from datetime import datetime, timedelta
import psycopg2
import pandas as pd
from psycopg2.extras import RealDictCursor
import time
import glob
from pdf_generator import generate_tariffs_pdf, get_latest_pdf_info

app = Flask(__name__, template_folder='templates')
# Получаем директорию, где находится app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Папка для хранения файлов
UPLOAD_FOLDER = "/home/chinatogether/xlsx-files"
PDF_FOLDER = "/home/chinatogether/pdf-files"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# Файл для информации о последней загрузке
LAST_FILE_INFO = "/home/chinatogether/xlsx-files/last_file_info.txt"

# Единый стиль для всех страниц
UNIFIED_STYLE = '''
<style>
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }

    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        min-height: 100vh;
        color: #2c3e50;
        line-height: 1.6;
    }

    .container {
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
    }

    .header {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        padding: 30px;
        margin-bottom: 30px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        text-align: center;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }

    .logo {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        margin: 0 auto 15px;
        display: block;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
        border: 2px solid #fff;
    }

    .header h1 {
        font-size: 2rem;
        color: #2c3e50;
        margin-bottom: 10px;
        font-weight: 600;
    }

    .header p {
        color: #7f8c8d;
        font-size: 1rem;
    }

    .main-content {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        padding: 30px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.2);
        margin-bottom: 30px;
    }

    .content-section {
        margin-bottom: 30px;
    }

    .content-section h3 {
        color: #2c3e50;
        margin-bottom: 20px;
        font-size: 1.3rem;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 20px;
        margin-bottom: 30px;
    }

    .stat-card {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-left: 4px solid;
        text-align: center;
    }

    .stat-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
    }

    .stat-card.primary { border-left-color: #3498db; }
    .stat-card.success { border-left-color: #27ae60; }
    .stat-card.warning { border-left-color: #f39c12; }
    .stat-card.danger { border-left-color: #e74c3c; }
    .stat-card.info { border-left-color: #9b59b6; }

    .stat-icon {
        font-size: 2rem;
        margin-bottom: 10px;
        display: block;
    }

    .stat-number {
        font-size: 1.8rem;
        font-weight: bold;
        margin-bottom: 8px;
        color: #2c3e50;
    }

    .stat-label {
        color: #7f8c8d;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .buttons-container {
        display: flex;
        flex-direction: column;
        gap: 12px;
        margin-top: 25px;
    }

    .button {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        padding: 15px 25px;
        background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
        color: white;
        text-decoration: none;
        border-radius: 10px;
        font-weight: 500;
        font-size: 1rem;
        transition: all 0.3s ease;
        border: none;
        cursor: pointer;
        box-shadow: 0 4px 15px rgba(52, 152, 219, 0.3);
    }

    .button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(52, 152, 219, 0.4);
    }

    .button.secondary {
        background: linear-gradient(135deg, #95a5a6 0%, #7f8c8d 100%);
        box-shadow: 0 4px 15px rgba(149, 165, 166, 0.3);
    }

    .button.success {
        background: linear-gradient(135deg, #27ae60 0%, #229954 100%);
        box-shadow: 0 4px 15px rgba(39, 174, 96, 0.3);
    }

    .button.warning {
        background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);
        box-shadow: 0 4px 15px rgba(243, 156, 18, 0.3);
    }

    .button.danger {
        background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
        box-shadow: 0 4px 15px rgba(231, 76, 60, 0.3);
    }

    .file-info {
        background: rgba(52, 152, 219, 0.05);
        border-left: 4px solid #3498db;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 25px;
    }

    .file-info p {
        margin: 5px 0;
        color: #2c3e50;
    }

    .file-info strong {
        color: #2980b9;
    }

    .form-section {
        margin: 25px 0;
    }

    .form-section label {
        display: block;
        margin-bottom: 10px;
        font-weight: 500;
        color: #2c3e50;
    }

    .form-section input[type="file"] {
        width: 100%;
        padding: 12px;
        border: 2px dashed #bdc3c7;
        border-radius: 8px;
        background: #f8f9fa;
        margin-bottom: 15px;
        transition: all 0.3s ease;
    }

    .form-section input[type="file"]:hover {
        border-color: #3498db;
        background: #ecf0f1;
    }

    .alert {
        padding: 15px 20px;
        border-radius: 8px;
        margin: 20px 0;
        border-left: 4px solid;
    }

    .alert.success {
        background: rgba(39, 174, 96, 0.1);
        border-left-color: #27ae60;
        color: #27ae60;
    }

    .alert.error {
        background: rgba(231, 76, 60, 0.1);
        border-left-color: #e74c3c;
        color: #c0392b;
    }

    .alert.warning {
        background: rgba(243, 156, 18, 0.1);
        border-left-color: #f39c12;
        color: #d35400;
    }

    .chart-container {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 25px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.2);
        margin-bottom: 25px;
    }

    .chart-title {
        font-size: 1.2rem;
        font-weight: 600;
        margin-bottom: 20px;
        color: #2c3e50;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .table-container {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 25px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.2);
        overflow-x: auto;
        margin-bottom: 25px;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 10px;
    }

    th, td {
        padding: 12px 15px;
        text-align: left;
        border-bottom: 1px solid #ecf0f1;
    }

    th {
        background: rgba(52, 152, 219, 0.05);
        font-weight: 600;
        color: #2c3e50;
    }

    tr:hover {
        background-color: rgba(52, 152, 219, 0.03);
    }

    .funnel-container {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 15px;
        margin-top: 20px;
    }

    .funnel-step {
        text-align: center;
        padding: 20px;
        background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
        color: white;
        border-radius: 10px;
        position: relative;
        box-shadow: 0 4px 15px rgba(52, 152, 219, 0.3);
    }

    .funnel-number {
        font-size: 1.8rem;
        font-weight: bold;
        margin-bottom: 8px;
    }

    .funnel-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }

    .conversion-rate {
        font-size: 0.75rem;
        margin-top: 5px;
        background: rgba(255, 255, 255, 0.2);
        padding: 3px 8px;
        border-radius: 12px;
        display: inline-block;
    }

    @media (max-width: 768px) {
        .container {
            padding: 15px;
        }

        .header {
            padding: 20px;
        }

        .logo {
            width: 60px;
            height: 60px;
        }

        .header h1 {
            font-size: 1.6rem;
        }

        .main-content {
            padding: 20px;
        }

        .stats-grid {
            grid-template-columns: 1fr;
        }

        .buttons-container {
            gap: 10px;
        }

        .button {
            padding: 12px 20px;
            font-size: 0.95rem;
        }

        .funnel-container {
            grid-template-columns: 1fr;
        }
    }

    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .header, .main-content, .chart-container, .table-container {
        animation: fadeInUp 0.6s ease-out;
    }
</style>
'''

# Конфигурация базы данных
DB_CONFIG = {
            'dbname': os.getenv('DB_NAME', 'delivery_db'),
            'user': os.getenv('DB_USER'), 
            'password': os.getenv('DB_PASSWORD'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'connect_timeout': int(os.getenv('DB_TIMEOUT', '10'))
}

# Подключение к базе данных
def connect_to_db():
    return psycopg2.connect(**DB_CONFIG)

# Удаление старых файлов
def remove_old_files():
    try:
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
        print("Очищаем таблицы...")
        cursor.execute("TRUNCATE TABLE delivery_test.weight;")
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

# Загрузка данных в БД с автоматической генерацией PDF
def load_data_to_db(file_path):
    try:
        start_time = time.time()
        print("Чтение данных из файла...")
        weight_data = pd.read_excel(file_path, sheet_name="weight", header=0)
        density_data = pd.read_excel(file_path, sheet_name="density", header=0)

        weight_data = weight_data.where(pd.notnull(weight_data), None)
        density_data = density_data.where(pd.notnull(density_data), None)
        print(f"Файл успешно прочитан за {time.time() - start_time:.2f} секунд.")

        required_columns_weight = [
            'Минимальный вес', 'Максимальный вес', 'Коэфициент мешок', 
            'Стоимость упаковки мешок', 'Стоимость разгрузки мешок', 'Коэфициент уголок',
            'Стоимость упаковки уголок', 'Стоимость разгрузки уголок',
            'Коэфициент каркас', 'Стоимость упаковки каркас',
            'Стоимость разгрузки каркас'
        ]
        required_columns_density = [
            'Категория', 'Минимальная плотность', 'Максимальная плотность',
            'Плотность', 'Быстрое авто ($/kg)', 'Обычное авто($/kg)'
        ]

        missing_columns_weight = [col for col in required_columns_weight if col not in weight_data.columns]
        if missing_columns_weight:
            return f"Ошибка: в листе 'weight' отсутствуют столбцы: {missing_columns_weight}"

        missing_columns_density = [col for col in required_columns_density if col not in density_data.columns]
        if missing_columns_density:
            return f"Ошибка: в листе 'density' отсутствуют столбцы: {missing_columns_density}"

    except Exception as e:
        return f"Ошибка при чтении файла: {str(e)}"

    try:
        conn = connect_to_db()
        cursor = conn.cursor()

        def convert_to_python_types(row):
            converted_row = []
            for value in row:
                if pd.isna(value):
                    converted_row.append(None)
                elif hasattr(value, 'item'):
                    converted_row.append(value.item())
                else:
                    converted_row.append(value)
            return tuple(converted_row)

        # Загрузка weight
        weight_data_tuples = [
            (row['Минимальный вес'], row['Максимальный вес'], row['Коэфициент мешок'],
             row['Стоимость упаковки мешок'], row['Стоимость разгрузки мешок'],
             row['Коэфициент уголок'], row['Стоимость упаковки уголок'],
             row['Стоимость разгрузки уголок'], row['Коэфициент каркас'], 
             row['Стоимость упаковки каркас'], row['Стоимость разгрузки каркас'])
            for _, row in weight_data.iterrows()
        ]
        weight_data_tuples = [convert_to_python_types(row) for row in weight_data_tuples]

        cursor.executemany("""
            INSERT INTO delivery_test.weight (
                min_weight, max_weight, coefficient_bag, bag_packing_cost, bag_unloading_cost,
                coefficient_corner,  corner_packing_cost, corner_unloading_cost,
                coefficient_frame,  frame_packing_cost, frame_unloading_cost
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, weight_data_tuples)

        # Загрузка density
        density_data_tuples = [
            (row['Категория'], row['Минимальная плотность'], row['Максимальная плотность'],
             row['Плотность'], row['Быстрое авто ($/kg)'], row['Обычное авто($/kg)'])
            for _, row in density_data.iterrows()
        ]
        density_data_tuples = [convert_to_python_types(row) for row in density_data_tuples]

        cursor.executemany("""
            INSERT INTO delivery_test.density (
                category, min_density, max_density, density_range,
                fast_delivery_cost, regular_delivery_cost
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, density_data_tuples)

        conn.commit()
        cursor.close()
        conn.close()
        
        # Генерируем PDF после успешной загрузки данных
        print("Начинаем генерацию PDF с тарифами...")
        try:
            pdf_success, pdf_message, pdf_path = generate_tariffs_pdf()
            
            if pdf_success:
                print(f"PDF успешно создан: {pdf_message}")
                return f"Данные успешно загружены в базу данных! PDF создан: {pdf_message}"
            else:
                print(f"Ошибка создания PDF: {pdf_message}")
                return f"Данные успешно загружены в базу данных! Ошибка PDF: {pdf_message}"
        except Exception as pdf_error:
            print(f"Критическая ошибка PDF: {str(pdf_error)}")
            return f"Данные успешно загружены в базу данных! Критическая ошибка PDF: {str(pdf_error)}"

    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return f"Ошибка при загрузке данных в БД: {str(e)}"

# Получение аналитики
def get_analytics_data():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT COUNT(*) as total FROM delivery_test.user_calculation")
        total_calculations = cursor.fetchone()['total']

        cursor.execute("""
            SELECT COUNT(*) as today 
            FROM delivery_test.user_calculation 
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        today_calculations = cursor.fetchone()['today']

        cursor.execute("SELECT AVG(total_weight) as avg_weight FROM delivery_test.user_calculation")
        avg_weight = cursor.fetchone()['avg_weight'] or 0

        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM delivery_test.user_calculation 
            GROUP BY category 
            ORDER BY count DESC 
            LIMIT 1
        """)
        popular_category_data = cursor.fetchone()
        popular_category = popular_category_data['category'] if popular_category_data else "Нет данных"

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
        return {
            'total_calculations': 0, 'today_calculations': 0,
            'avg_weight': 0.0, 'popular_category': 'Нет данных', 'active_users': 0
        }
    finally:
        cursor.close()
        conn.close()

# Получение данных для воронки
def get_funnel_data():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT COUNT(*) as visits FROM delivery_test.telegram_users")
        visits = cursor.fetchone()['visits']
        
        cursor.execute("SELECT COUNT(DISTINCT telegram_user_id) as started FROM delivery_test.user_inputs")
        started = cursor.fetchone()['started']
        
        cursor.execute("SELECT COUNT(DISTINCT telegram_user_id) as completed FROM delivery_test.user_calculation")
        completed = cursor.fetchone()['completed']
        
        cursor.execute("""
            SELECT COUNT(DISTINCT telegram_user_id) as saved 
            FROM delivery_test.user_actions 
            WHERE action LIKE '%save%' OR action LIKE '%download%'
        """)
        saved_result = cursor.fetchone()
        saved = saved_result['saved'] if saved_result else 0

        conversion_started = (started / visits * 100) if visits > 0 else 0
        conversion_completed = (completed / started * 100) if started > 0 else 0
        conversion_saved = (saved / completed * 100) if completed > 0 else 0

        return {
            'visits': visits, 'started': started, 'completed': completed, 'saved': saved,
            'conversion_started': conversion_started,
            'conversion_completed': conversion_completed,
            'conversion_saved': conversion_saved
        }
    except Exception as e:
        return {
            'visits': 0, 'started': 0, 'completed': 0, 'saved': 0,
            'conversion_started': 0, 'conversion_completed': 0, 'conversion_saved': 0
        }
    finally:
        cursor.close()
        conn.close()

# Функция для рендера ошибок
def render_error(message):
    return render_template_string('''
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Ошибка - China Together</title>
            ''' + UNIFIED_STYLE + '''
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <img src="https://raw.githubusercontent.com/EmilIskhakov/china-together-logo/main/photo_2024-05-27_15-00-14%20(2).jpg" 
                         alt="China Together Logo" class="logo" onerror="this.style.display='none'">
                    <h1>❌ Произошла ошибка</h1>
                    <p>Не удалось выполнить операцию</p>
                </div>

                <div class="main-content">
                    <div class="alert error">
                        <strong>Ошибка:</strong> {{ message }}
                    </div>

                    <div class="buttons-container">
                        <a href="/" class="button">
                            <span>🏠</span>
                            Вернуться на главную
                        </a>
                    </div>
                </div>
            </div>
        </body>
        </html>
    ''', message=message), 500

# МАРШРУТЫ
@app.route('/')
def index():
    if os.path.exists(LAST_FILE_INFO):
        with open(LAST_FILE_INFO, 'r', encoding='utf-8') as f:
            last_file_info = f.read()
    else:
        last_file_info = "Файл ещё не загружен."

    # Получаем информацию о PDF
    pdf_info = get_latest_pdf_info()

    return render_template_string('''
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>China Together - Система управления доставкой</title>
            ''' + UNIFIED_STYLE + '''
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <img src="https://raw.githubusercontent.com/EmilIskhakov/china-together-logo/main/photo_2024-05-27_15-00-14%20(2).jpg" 
                         alt="China Together Logo" class="logo" 
                         onerror="this.style.display='none'">
                    <h1>🚀 China Together</h1>
                    <p>Система управления расчетами доставки из Китая</p>
                </div>

                <div class="main-content">
                    <div class="file-info">
                        <p><strong>📁 Статус системы:</strong></p>
                        <p>{{ last_file_info }}</p>
                        
                        {% if pdf_info %}
                        <p><strong>📄 PDF с тарифами:</strong></p>
                        <p>{{ pdf_info.filename }} ({{ pdf_info.size_kb }} КБ, создан {{ pdf_info.created }})</p>
                        {% else %}
                        <p><strong>📄 PDF с тарифами:</strong> Не создан</p>
                        {% endif %}
                    </div>

                    <div class="form-section">
                        <form method="post" enctype="multipart/form-data" action="/upload">
                            <label for="file">
                                <strong>📊 Загрузка параметров доставки</strong><br>
                                <small>Выберите Excel файл с данными о весе и плотности товаров</small>
                            </label>
                            <input type="file" name="file" accept=".xlsx,.xls" required>
                            
                            <div class="buttons-container">
                                <button type="submit" class="button warning">
                                    <span>📤</span>
                                    Загрузить новый файл параметров
                                </button>
                            </div>
                        </form>
                    </div>

                    <div class="buttons-container">
                        <a href="/download" class="button success">
                            <span>💾</span>
                            Скачать текущий файл параметров
                        </a>
                        
                        {% if pdf_info %}
                        <a href="/download_pdf" class="button danger">
                            <span>📄</span>
                            Скачать PDF с тарифами
                        </a>
                        {% endif %}
                        
                        <a href="/dashboard" class="button">
                            <span>📊</span>
                            Открыть панель аналитики
                        </a>
                        
                        <form method="post" action="/generate_pdf" style="margin: 0;">
                            <button type="submit" class="button secondary">
                                <span>🔄</span>
                                Создать PDF заново
                            </button>
                        </form>
                        
                        <a href="#" onclick="checkSystem()" class="button secondary">
                            <span>🔍</span>
                            Проверить состояние системы
                        </a>
                    </div>
                </div>

                <div id="systemStatus" style="display: none;" class="main-content">
                    <h3>🔧 Состояние системы</h3>
                    <div id="statusContent">Проверка...</div>
                </div>
            </div>

            <script>
                function checkSystem() {
                    document.getElementById('systemStatus').style.display = 'block';
                    document.getElementById('statusContent').innerHTML = 'Проверка состояния системы...';
                    
                    Promise.all([
                        fetch('/api/system_info').then(r => r.json()),
                        fetch('/api/pdf_info').then(r => r.json())
                    ])
                    .then(([systemData, pdfData]) => {
                        let statusClass = systemData.system_status === 'OK' ? 'success' : 'warning';
                        document.getElementById('statusContent').innerHTML = `
                            <div class="alert ${statusClass}">
                                <strong>Статус системы:</strong> ${systemData.system_status}<br>
                                <strong>Записей в таблице weight:</strong> ${systemData.weight_records || 0}<br>
                                <strong>Записей в таблице density:</strong> ${systemData.density_records || 0}<br>
                                <strong>Файл Excel на сервере:</strong> ${systemData.file_exists ? 'Есть' : 'Отсутствует'}<br>
                                <strong>PDF файл:</strong> ${pdfData.exists ? `Есть (${pdfData.size_kb} КБ)` : 'Отсутствует'}
                            </div>
                        `;
                    })
                    .catch(error => {
                        document.getElementById('statusContent').innerHTML = `
                            <div class="alert error">Ошибка проверки: ${error.message}</div>
                        `;
                    });
                }
            </script>
        </body>
        </html>
    ''', last_file_info=last_file_info, pdf_info=pdf_info)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return render_error("Файл не найден")
    
    file = request.files['file']
    if file.filename == '':
        return render_error("Имя файла пустое")

    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        return render_error("Поддерживаются только файлы Excel (.xlsx, .xls)")

    try:
        remove_old_files()
        
        fixed_filename = "delivery_parameter.xlsx"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], fixed_filename)
        file.save(file_path)

        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        original_name = file.filename
        
        with open(LAST_FILE_INFO, 'w', encoding='utf-8') as f:
            f.write(f"{original_name} (загружен {timestamp})")

        if not clear_table():
            return render_error("Ошибка при очистке таблиц")
            
        result = load_data_to_db(file_path)

        return render_template_string('''
            <!DOCTYPE html>
            <html lang="ru">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Файл загружен - China Together</title>
                ''' + UNIFIED_STYLE + '''
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <img src="https://raw.githubusercontent.com/EmilIskhakov/china-together-logo/main/photo_2024-05-27_15-00-14%20(2).jpg" 
                             alt="China Together Logo" class="logo" onerror="this.style.display='none'">
                        <h1>✅ Файл успешно загружен!</h1>
                        <p>Данные обновлены в системе</p>
                    </div>

                    <div class="main-content">
                        <div class="alert success">
                            <strong>Результат:</strong> {{ result }}
                        </div>
                        
                        <div class="file-info">
                            <p><strong>Исходный файл:</strong> "{{ original_name }}"</p>
                            <p><strong>Сохранен как:</strong> "{{ fixed_filename }}"</p>
                            <p><strong>Время загрузки:</strong> {{ timestamp }}</p>
                        </div>

                        <div class="buttons-container">
                            <a href="/" class="button">
                                <span>🏠</span>
                                Вернуться на главную
                            </a>
                            <a href="/download_pdf" class="button success">
                                <span>📄</span>
                                Скачать PDF с тарифами
                            </a>
                            <a href="/dashboard" class="button success">
                                <span>📊</span>
                                Открыть панель аналитики
                            </a>
                        </div>
                    </div>
                </div>
            </body>
            </html>
        ''', result=result, original_name=original_name, 
             fixed_filename=fixed_filename, timestamp=timestamp)
        
    except Exception as e:
        return render_error(f"Ошибка при загрузке файла: {str(e)}")

@app.route('/download')
def download_file():
    fixed_filename = "delivery_parameter.xlsx"
    path = os.path.join(app.config['UPLOAD_FOLDER'], fixed_filename)
    if not os.path.exists(path):
        return render_error("Файл не найден. Возможно, он еще не был загружен.")
    return send_from_directory(app.config['UPLOAD_FOLDER'], fixed_filename, as_attachment=True)

@app.route('/download_pdf')
def download_pdf():
    """Скачивание последнего созданного PDF файла"""
    try:
        # Получаем информацию о PDF через прямой поиск файлов
        import glob
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pdf_folder = os.path.join(base_dir, "pdf-files")
        
        pdf_files = glob.glob(os.path.join(pdf_folder, "*.pdf"))
        
        if not pdf_files:
            return render_error("PDF файл не найден. Возможно, он еще не был создан.")
        
        # Берем самый новый файл
        latest_file = max(pdf_files, key=os.path.getctime)
        
        if not os.path.exists(latest_file):
            return render_error("PDF файл не найден на сервере.")
        
        filename = os.path.basename(latest_file)
        directory = os.path.dirname(latest_file)
        
        return send_from_directory(
            directory, 
            filename, 
            as_attachment=True,
            download_name=f"china_together_tariffs_{datetime.now().strftime('%Y%m%d')}.pdf"
        )
        
    except Exception as e:
        print(f"Ошибка download_pdf: {str(e)}")
        return render_error(f"Ошибка при скачивании PDF: {str(e)}")

@app.route('/generate_pdf', methods=['POST'])
def force_generate_pdf():
    """Принудительная генерация PDF из текущих данных БД"""
    try:
        print("Запущена принудительная генерация PDF...")
        pdf_success, pdf_message, pdf_path = generate_tariffs_pdf()
        
        if pdf_success:
            return render_template_string('''
                <!DOCTYPE html>
                <html lang="ru">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>PDF создан - China Together</title>
                    ''' + UNIFIED_STYLE + '''
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <img src="https://raw.githubusercontent.com/EmilIskhakov/china-together-logo/main/photo_2024-05-27_15-00-14%20(2).jpg" 
                                 alt="China Together Logo" class="logo" onerror="this.style.display='none'">
                            <h1>✅ PDF успешно создан!</h1>
                            <p>Файл с тарифами сгенерирован</p>
                        </div>

                        <div class="main-content">
                            <div class="alert success">
                                <strong>Результат:</strong> {{ pdf_message }}
                            </div>

                            <div class="buttons-container">
                                <a href="/download_pdf" class="button success">
                                    <span>📄</span>
                                    Скачать PDF файл
                                </a>
                                <a href="/" class="button">
                                    <span>🏠</span>
                                    Вернуться на главную
                                </a>
                                <a href="/dashboard" class="button">
                                    <span>📊</span>
                                    Открыть панель аналитики
                                </a>
                            </div>
                        </div>
                    </div>
                </body>
                </html>
            ''', pdf_message=pdf_message)
        else:
            return render_error(f"Ошибка при создании PDF: {pdf_message}")
            
    except Exception as e:
        return render_error(f"Ошибка при создании PDF: {str(e)}")

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

        # Топ пользователей
        cursor.execute("""
            SELECT u.username, COUNT(c.id) AS calculation_count
            FROM delivery_test.telegram_users u
            JOIN delivery_test.user_calculation c ON u.id = c.telegram_user_id
            GROUP BY u.username
            ORDER BY calculation_count DESC
            LIMIT 5
        """)
        calculations_per_user = [(row['username'] or 'Аноним', row['calculation_count']) for row in cursor.fetchall()]

        # Последние расчеты
        cursor.execute("""
            SELECT u.username, c.category, c.total_weight, c.product_cost, c.created_at
            FROM delivery_test.user_calculation c
            LEFT JOIN delivery_test.telegram_users u ON c.telegram_user_id = u.id
            WHERE c.created_at >= NOW() - INTERVAL '24 hours'
            ORDER BY c.created_at DESC
            LIMIT 50
        """)
        recent_calculations = cursor.fetchall()

        # Аналитика пользователей
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
        return render_error("Ошибка при загрузке данных дашборда")
    finally:
        cursor.close()
        conn.close()

    analytics = get_analytics_data()
    funnel_data = get_funnel_data()

    return render_template_string('''
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Панель аналитики - China Together</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            ''' + UNIFIED_STYLE + '''
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <img src="https://raw.githubusercontent.com/EmilIskhakov/china-together-logo/main/photo_2024-05-27_15-00-14%20(2).jpg" 
                         alt="China Together Logo" class="logo" onerror="this.style.display='none'">
                    <h1>📊 Панель аналитики</h1>
                    <p>Статистика и анализ расчетов доставки</p>
                </div>

                <!-- Основная статистика -->
                <div class="main-content">
                    <div class="content-section">
                        <h3>📈 Основная статистика</h3>
                        <div class="stats-grid">
                            <div class="stat-card primary">
                                <span class="stat-icon">📊</span>
                                <div class="stat-number">{{ analytics.total_calculations }}</div>
                                <div class="stat-label">Всего расчетов</div>
                            </div>
                            <div class="stat-card success">
                                <span class="stat-icon">🔥</span>
                                <div class="stat-number">{{ analytics.today_calculations }}</div>
                                <div class="stat-label">Расчетов сегодня</div>
                            </div>
                            <div class="stat-card warning">
                                <span class="stat-icon">⚖️</span>
                                <div class="stat-number">{{ "%.1f"|format(analytics.avg_weight) }} кг</div>
                                <div class="stat-label">Средний вес груза</div>
                            </div>
                            <div class="stat-card info">
                                <span class="stat-icon">👥</span>
                                <div class="stat-number">{{ analytics.active_users }}</div>
                                <div class="stat-label">Активных пользователей</div>
                            </div>
                            <div class="stat-card danger">
                                <span class="stat-icon">📦</span>
                                <div class="stat-number">{{ analytics.popular_category }}</div>
                                <div class="stat-label">Популярная категория</div>
                            </div>
                        </div>
                    </div>

                    <div class="buttons-container">
                        <a href="/" class="button secondary">
                            <span>🏠</span>
                            Вернуться на главную
                        </a>
                        <a href="#" onclick="refreshData()" class="button">
                            <span>🔄</span>
                            Обновить данные
                        </a>
                    </div>
                </div>

                <!-- Воронка пользователей -->
                <div class="main-content">
                    <div class="content-section">
                        <h3>🎯 Воронка пользователей</h3>
                        <div class="funnel-container">
                            <div class="funnel-step">
                                <div class="funnel-number">{{ funnel_data.visits }}</div>
                                <div class="funnel-label">Всего пользователей</div>
                            </div>
                            <div class="funnel-step">
                                <div class="funnel-number">{{ funnel_data.started }}</div>
                                <div class="funnel-label">Начали расчет</div>
                                <div class="conversion-rate">{{ "%.1f"|format(funnel_data.conversion_started) }}%</div>
                            </div>
                            <div class="funnel-step">
                                <div class="funnel-number">{{ funnel_data.completed }}</div>
                                <div class="funnel-label">Завершили расчет</div>
                                <div class="conversion-rate">{{ "%.1f"|format(funnel_data.conversion_completed) }}%</div>
                            </div>
                            <div class="funnel-step">
                                <div class="funnel-number">{{ funnel_data.saved }}</div>
                                <div class="funnel-label">Сохранили результат</div>
                                <div class="conversion-rate">{{ "%.1f"|format(funnel_data.conversion_saved) }}%</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Графики -->
                <div class="chart-container">
                    <h3 class="chart-title">📈 Расчеты по дням</h3>
                    <canvas id="calculationsByDayChart"></canvas>
                </div>

                <div class="chart-container">
                    <h3 class="chart-title">👑 Топ пользователей</h3>
                    <canvas id="userCalculationsChart"></canvas>
                </div>

                <!-- Таблицы -->
                <div class="table-container">
                    <h3 class="chart-title">🔥 Последние расчеты (24 часа)</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Пользователь</th>
                                <th>Категория</th>
                                <th>Вес (кг)</th>
                                <th>Стоимость ($)</th>
                                <th>Время</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for calc in recent_calculations %}
                            <tr>
                                <td>{{ calc.username or 'Аноним' }}</td>
                                <td>{{ calc.category or '-' }}</td>
                                <td>{{ "%.2f"|format(calc.total_weight or 0) }}</td>
                                <td>{{ "%.2f"|format(calc.product_cost or 0) }}</td>
                                <td>{{ calc.created_at.strftime('%d.%m %H:%M') if calc.created_at else '-' }}</td>
                            </tr>
                            {% endfor %}
                            {% if not recent_calculations %}
                            <tr>
                                <td colspan="5" style="text-align: center; color: #7f8c8d; padding: 20px;">
                                    Нет расчетов за последние 24 часа
                                </td>
                            </tr>
                            {% endif %}
                        </tbody>
                    </table>
                </div>

                <div class="table-container">
                    <h3 class="chart-title">📊 Детальная аналитика по пользователям</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Пользователь</th>
                                <th>Расчетов</th>
                                <th>Общий вес (кг)</th>
                                <th>Общая стоимость ($)</th>
                                <th>Последний расчет</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for user in user_analytics %}
                            <tr>
                                <td>{{ user.username or 'Аноним' }}</td>
                                <td>{{ user.calculation_count }}</td>
                                <td>{{ "%.2f"|format(user.total_weight or 0) }}</td>
                                <td>{{ "%.2f"|format(user.total_cost or 0) }}</td>
                                <td>{{ user.last_calculation.strftime('%d.%m.%Y %H:%M') if user.last_calculation else '-' }}</td>
                            </tr>
                            {% endfor %}
                            {% if not user_analytics %}
                            <tr>
                                <td colspan="5" style="text-align: center; color: #7f8c8d; padding: 20px;">
                                    Нет данных по пользователям
                                </td>
                            </tr>
                            {% endif %}
                        </tbody>
                    </table>
                </div>
            </div>

            <script>
                // График расчетов по дням
                const ctx1 = document.getElementById('calculationsByDayChart').getContext('2d');
                new Chart(ctx1, {
                    type: 'line',
                    data: {
                        labels: [{% for row in calculations_by_day %}"{{ row[0] }}",{% endfor %}],
                        datasets: [{
                            label: 'Количество расчетов',
                            data: [{% for row in calculations_by_day %}{{ row[1] }},{% endfor %}],
                            backgroundColor: 'rgba(52, 152, 219, 0.1)',
                            borderColor: 'rgba(52, 152, 219, 1)',
                            borderWidth: 3,
                            fill: true,
                            tension: 0.4
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.1)' } },
                            x: { grid: { color: 'rgba(0,0,0,0.1)' } }
                        }
                    }
                });

                // График топ пользователей
                const ctx2 = document.getElementById('userCalculationsChart').getContext('2d');
                new Chart(ctx2, {
                    type: 'bar',
                    data: {
                        labels: [{% for user, count in calculations_per_user %}"{{ (user[:15] + '...') if user|length > 15 else user }}",{% endfor %}],
                        datasets: [{
                            label: 'Расчетов',
                            data: [{% for user, count in calculations_per_user %}{{ count }},{% endfor %}],
                            backgroundColor: 'rgba(39, 174, 96, 0.8)',
                            borderColor: 'rgba(39, 174, 96, 1)',
                            borderWidth: 1,
                            borderRadius: 5
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.1)' } },
                            x: { grid: { display: false } }
                        }
                    }
                });

                function refreshData() {
                    window.location.reload();
                }
            </script>
        </body>
        </html>
    ''', calculations_by_day=calculations_by_day,
         calculations_per_user=calculations_per_user,
         recent_calculations=recent_calculations,
         user_analytics=user_analytics,
         analytics=analytics,
         funnel_data=funnel_data)

# API маршруты
@app.route('/api/stats')
def api_stats():
    analytics = get_analytics_data()
    return jsonify(analytics)

@app.route('/api/pdf_info')
def api_pdf_info():
    """API для получения информации о PDF файле"""
    try:
        pdf_info = get_latest_pdf_info()
        
        if pdf_info:
            return jsonify({
                'exists': True,
                'filename': pdf_info['filename'],
                'size_kb': pdf_info['size_kb'],
                'created': pdf_info['created'],
                'modified': pdf_info['modified']
            })
        else:
            return jsonify({
                'exists': False,
                'message': 'PDF файл не найден'
            })
            
    except Exception as e:
        return jsonify({'error': f'Ошибка получения информации о PDF: {str(e)}'}), 500

@app.route('/api/system_info')
def api_system_info():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("SELECT COUNT(*) as count FROM delivery_test.weight")
        weight_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM delivery_test.density")
        density_count = cursor.fetchone()['count']
        
        file_exists = os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], "delivery_parameter.xlsx"))
        
        last_file_info = "Нет данных"
        if os.path.exists(LAST_FILE_INFO):
            with open(LAST_FILE_INFO, 'r', encoding='utf-8') as f:
                last_file_info = f.read()
        
        return jsonify({
            'weight_records': weight_count,
            'density_records': density_count,
            'file_exists': file_exists,
            'last_file_info': last_file_info,
            'system_status': 'OK' if weight_count > 0 and density_count > 0 else 'WARNING'
        })
        
    except Exception as e:
        return jsonify({'error': f'Ошибка получения системной информации: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()

# Обработка ошибок
@app.errorhandler(404)
def not_found(error):
    return render_error("Страница не найдена"), 404

@app.errorhandler(500)
def server_error(error):
    return render_error("Внутренняя ошибка сервера"), 500

if __name__ == '__main__':
    # Создаем необходимые директории
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(PDF_FOLDER, exist_ok=True)
    
    print("Запуск приложения China Together Delivery System")
    print(f"Excel файлы: {UPLOAD_FOLDER}")
    print(f"PDF файлы: {PDF_FOLDER}")
    
    try:
        app.run(host='0.0.0.0', port=8060, debug=True)
    except Exception as e:
        print(f"Ошибка запуска приложения: {str(e)}")
        raise
