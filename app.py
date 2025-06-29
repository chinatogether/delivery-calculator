from flask import Flask, request, redirect, send_from_directory, render_template, jsonify, session, flash, url_for
import os
from datetime import datetime, timedelta
import psycopg2
import pandas as pd
from psycopg2.extras import RealDictCursor
import time
import glob
from pdf_generator import generate_tariffs_pdf, get_latest_pdf_info
from dotenv import load_dotenv
import json
from functools import wraps
import secrets
from decimal import Decimal
import hashlib
import xlsxwriter
from io import BytesIO

app = Flask(__name__, template_folder='templates')
app.secret_key = secrets.token_hex(16)

# Получаем директорию, где находится app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Папка для хранения файлов
UPLOAD_FOLDER = "/home/chinatogether/xlsx-files"
PDF_FOLDER = "/home/chinatogether/pdf-files"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Файл для информации о последней загрузке
LAST_FILE_INFO = "/home/chinatogether/xlsx-files/last_file_info.txt"

load_dotenv()

# Конфигурация базы данных
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'delivery_db'),
    'user': os.getenv('DB_USER'), 
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'connect_timeout': int(os.getenv('DB_TIMEOUT', '10'))
}

# Авторизованные пользователи (временно, потом заменим на БД)
AUTHORIZED_USERS = {
    'director@chinatogether.ru': {
        'name': 'Директор',
        'role': 'director',
        'permissions': ['all']
    },
    'manager1@chinatogether.ru': {
        'name': 'Менеджер 1',
        'role': 'manager', 
        'permissions': ['orders', 'users', 'calculations']
    },
    'manager2@chinatogether.ru': {
        'name': 'Менеджер 2',
        'role': 'manager',
        'permissions': ['orders', 'users', 'calculations']
    }
}

# Подключение к базе данных
def connect_to_db():
    return psycopg2.connect(**DB_CONFIG)

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def require_permission(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_email' not in session:
                return redirect(url_for('login'))
            
            user = AUTHORIZED_USERS.get(session['user_email'])
            if not user:
                flash('Доступ запрещен', 'error')
                return redirect(url_for('dashboard'))
            
            if 'all' not in user['permissions'] and permission not in user['permissions']:
                flash('Недостаточно прав доступа', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Инициализация таблиц для новой функциональности
def init_management_tables():
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        # Создаем схему если не существует
        cursor.execute("CREATE SCHEMA IF NOT EXISTS delivery_test")
        
        # Обновляем таблицу purchase_requests с новыми статусами
        cursor.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_schema='delivery_test' 
                              AND table_name='purchase_requests' 
                              AND column_name='manager_email') THEN
                    ALTER TABLE delivery_test.purchase_requests 
                    ADD COLUMN manager_email VARCHAR(255),
                    ADD COLUMN status_history JSONB DEFAULT '[]',
                    ADD COLUMN updated_by VARCHAR(255);
                END IF;
            END $$;
        """)
        
        # Таблица действий менеджеров
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.manager_actions (
                id SERIAL PRIMARY KEY,
                manager_email VARCHAR(255) NOT NULL,
                action_type VARCHAR(100) NOT NULL,
                target_id INTEGER,
                target_type VARCHAR(50),
                description TEXT,
                details JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow')
            )
        """)
        
        # Таблица пользователей с расширенной информацией
        cursor.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_schema='delivery_test' 
                              AND table_name='telegram_users' 
                              AND column_name='company') THEN
                    ALTER TABLE delivery_test.telegram_users 
                    ADD COLUMN company VARCHAR(255),
                    ADD COLUMN phone VARCHAR(50),
                    ADD COLUMN email VARCHAR(255),
                    ADD COLUMN full_name VARCHAR(255);
                END IF;
            END $$;
        """)
        
        # Таблица счет-фактур
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.invoices (
                id SERIAL PRIMARY KEY,
                invoice_number VARCHAR(100) UNIQUE NOT NULL,
                telegram_user_id INTEGER REFERENCES delivery_test.telegram_users(id),
                calculation_id INTEGER REFERENCES delivery_test.user_calculation(id),
                from_address TEXT,
                to_address TEXT,
                product_description TEXT,
                weight DECIMAL(10,2),
                volume DECIMAL(10,4),
                packaging_type VARCHAR(50),
                product_cost DECIMAL(10,2),
                delivery_cost DECIMAL(10,2),
                delivery_type VARCHAR(50),
                packaging_cost DECIMAL(10,2),
                unloading_cost DECIMAL(10,2),
                total_amount DECIMAL(10,2),
                status VARCHAR(50) DEFAULT 'draft',
                created_by VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow'),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow')
            )
        """)
        
        conn.commit()
        print("Таблицы управления успешно созданы/обновлены")
        
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при создании таблиц управления: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

# Функции для работы с заявками
def get_all_orders(filters=None):
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        base_query = """
            SELECT pr.id, pr.email, pr.telegram_contact, pr.supplier_link,
                   pr.order_amount, pr.promo_code, pr.additional_notes,
                   pr.status, pr.manager_email, pr.created_at, pr.updated_at,
                   tu.username, tu.first_name, tu.company, tu.phone,
                   uc.category, uc.total_weight, uc.product_cost_usd
            FROM delivery_test.purchase_requests pr
            LEFT JOIN delivery_test.telegram_users tu ON pr.telegram_user_id = tu.id
            LEFT JOIN delivery_test.user_calculation uc ON pr.calculation_id = uc.id
        """
        
        conditions = []
        params = []
        
        if filters:
            if filters.get('status'):
                conditions.append("pr.status = %s")
                params.append(filters['status'])
            if filters.get('manager_email'):
                conditions.append("pr.manager_email = %s")
                params.append(filters['manager_email'])
            if filters.get('date_from'):
                conditions.append("pr.created_at >= %s")
                params.append(filters['date_from'])
            if filters.get('date_to'):
                conditions.append("pr.created_at <= %s")
                params.append(filters['date_to'])
        
        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)
        
        base_query += " ORDER BY pr.created_at DESC"
        
        cursor.execute(base_query, params)
        return cursor.fetchall()
        
    finally:
        cursor.close()
        conn.close()

def update_order_status(order_id, new_status, manager_email, notes=None):
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        # Получаем текущий статус
        cursor.execute("SELECT status, status_history FROM delivery_test.purchase_requests WHERE id = %s", (order_id,))
        current_data = cursor.fetchone()
        
        if not current_data:
            return False
        
        current_status, status_history = current_data
        if status_history is None:
            status_history = []
        
        # Добавляем новую запись в историю
        status_entry = {
            'status': new_status,
            'changed_by': manager_email,
            'changed_at': datetime.now().isoformat(),
            'notes': notes
        }
        status_history.append(status_entry)
        
        # Обновляем заявку
        cursor.execute("""
            UPDATE delivery_test.purchase_requests 
            SET status = %s, manager_email = %s, status_history = %s, 
                updated_at = NOW(), updated_by = %s
            WHERE id = %s
        """, (new_status, manager_email, json.dumps(status_history), manager_email, order_id))
        
        # Записываем действие менеджера
        cursor.execute("""
            INSERT INTO delivery_test.manager_actions 
            (manager_email, action_type, target_id, target_type, description, details)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (manager_email, 'status_change', order_id, 'order', 
              f'Изменен статус на {new_status}', 
              json.dumps({'old_status': current_status, 'new_status': new_status, 'notes': notes})))
        
        conn.commit()
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"Ошибка обновления статуса: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def log_manager_action(manager_email, action_type, target_id=None, target_type=None, description=None, details=None):
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO delivery_test.manager_actions 
            (manager_email, action_type, target_id, target_type, description, details)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (manager_email, action_type, target_id, target_type, description, json.dumps(details) if details else None))
        conn.commit()
    except Exception as e:
        print(f"Ошибка логирования действия: {e}")
    finally:
        cursor.close()
        conn.close()

# Функции для работы с курсом валют
def get_current_exchange_rate():
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT rate, recorded_at, source 
            FROM delivery_test.exchange_rates 
            WHERE currency_pair = 'CNY/USD' 
            ORDER BY recorded_at DESC 
            LIMIT 1
        """)
        result = cursor.fetchone()
        if result:
            return {'rate': float(result[0]), 'recorded_at': result[1], 'source': result[2]}
        return {'rate': 7.20, 'recorded_at': datetime.now(), 'source': 'default'}
    finally:
        cursor.close()
        conn.close()

def update_exchange_rate(rate, manager_email):
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO delivery_test.exchange_rates (currency_pair, rate, recorded_at, source, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, ('CNY/USD', rate, datetime.now(), f'manual_by_{manager_email}', f'Обновлен менеджером {manager_email}'))
        
        log_manager_action(manager_email, 'exchange_rate_update', None, 'system', 
                          f'Обновлен курс валют на {rate}', {'rate': rate})
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка обновления курса: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# МАРШРУТЫ

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        
        if email in AUTHORIZED_USERS:
            session['user_email'] = email
            session['user_name'] = AUTHORIZED_USERS[email]['name']
            session['user_role'] = AUTHORIZED_USERS[email]['role']
            flash(f'Добро пожаловать, {AUTHORIZED_USERS[email]["name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Доступ запрещен. Обратитесь к администратору.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('login'))

@app.route('/')
@require_auth
def dashboard():
    # Получаем статистику для дашборда
    analytics = get_analytics_data()
    funnel_data = get_funnel_data()
    
    # Получаем данные для графиков
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Расчеты по дням
        cursor.execute("""
            SELECT DATE(created_at) AS date, COUNT(*) AS count
            FROM delivery_test.user_calculation
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """)
        calculations_by_day = cursor.fetchall()
        
        # Заявки по статусам
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM delivery_test.purchase_requests
            GROUP BY status
        """)
        orders_by_status = cursor.fetchall()
        
        # Активность менеджеров (если пользователь директор)
        manager_stats = []
        if session.get('user_role') == 'director':
            cursor.execute("""
                SELECT pr.manager_email, COUNT(*) as orders_count,
                       COUNT(CASE WHEN pr.status = 'completed' THEN 1 END) as completed_count
                FROM delivery_test.purchase_requests pr
                WHERE pr.manager_email IS NOT NULL
                GROUP BY pr.manager_email
            """)
            manager_stats = cursor.fetchall()
    
    finally:
        cursor.close()
        conn.close()
    
    return render_template('dashboard.html', 
                         analytics=analytics,
                         funnel_data=funnel_data,
                         calculations_by_day=calculations_by_day,
                         orders_by_status=orders_by_status,
                         manager_stats=manager_stats)

@app.route('/orders')
@require_permission('orders')
def orders_page():
    # Получаем фильтры из запроса
    filters = {}
    if request.args.get('status'):
        filters['status'] = request.args.get('status')
    if request.args.get('manager'):
        filters['manager_email'] = request.args.get('manager')
    if request.args.get('date_from'):
        filters['date_from'] = request.args.get('date_from')
    if request.args.get('date_to'):
        filters['date_to'] = request.args.get('date_to')
    
    orders = get_all_orders(filters)
    
    # Получаем список статусов и менеджеров для фильтров
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DISTINCT status FROM delivery_test.purchase_requests WHERE status IS NOT NULL")
        statuses = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT manager_email FROM delivery_test.purchase_requests WHERE manager_email IS NOT NULL")
        managers = [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()
    
    return render_template('orders.html', orders=orders, statuses=statuses, managers=managers, filters=filters)

@app.route('/users')
@require_permission('users')
def users_page():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("""
            SELECT tu.id, tu.telegram_id, tu.username, tu.first_name, tu.last_name,
                   tu.company, tu.phone, tu.email, tu.full_name, tu.created_at,
                   COUNT(uc.id) as calculations_count,
                   COUNT(pr.id) as orders_count,
                   MAX(tu.last_activity) as last_activity
            FROM delivery_test.telegram_users tu
            LEFT JOIN delivery_test.user_calculation uc ON tu.id = uc.telegram_user_id
            LEFT JOIN delivery_test.purchase_requests pr ON tu.id = pr.telegram_user_id
            GROUP BY tu.id
            ORDER BY tu.last_activity DESC NULLS LAST
        """)
        users = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    
    return render_template('users.html', users=users)

@app.route('/exchange-rate')
@require_permission('all')  # Только директор
def exchange_rate_page():
    current_rate = get_current_exchange_rate()
    
    # Получаем историю курсов
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("""
            SELECT rate, recorded_at, source, notes
            FROM delivery_test.exchange_rates
            WHERE currency_pair = 'CNY/USD'
            ORDER BY recorded_at DESC
            LIMIT 20
        """)
        rate_history = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    
    return render_template('exchange_rate.html', current_rate=current_rate, rate_history=rate_history)

@app.route('/settings')
@require_permission('all')  # Только директор
def settings_page():
    if os.path.exists(LAST_FILE_INFO):
        with open(LAST_FILE_INFO, 'r', encoding='utf-8') as f:
            last_file_info = f.read()
    else:
        last_file_info = "Файл ещё не загружен."
    
    pdf_info = get_latest_pdf_info()
    
    return render_template('settings.html', last_file_info=last_file_info, pdf_info=pdf_info)

# API МАРШРУТЫ

@app.route('/api/orders/<int:order_id>/status', methods=['POST'])
@require_permission('orders')
def update_order_status_api(order_id):
    data = request.get_json()
    new_status = data.get('status')
    notes = data.get('notes', '')
    
    if not new_status:
        return jsonify({'error': 'Статус не указан'}), 400
    
    success = update_order_status(order_id, new_status, session['user_email'], notes)
    
    if success:
        return jsonify({'success': True, 'message': 'Статус обновлен'})
    else:
        return jsonify({'error': 'Ошибка обновления статуса'}), 500

@app.route('/api/exchange-rate', methods=['POST'])
@require_permission('all')
def update_exchange_rate_api():
    data = request.get_json()
    rate = data.get('rate')
    
    if not rate or rate <= 0:
        return jsonify({'error': 'Некорректный курс'}), 400
    
    success = update_exchange_rate(rate, session['user_email'])
    
    if success:
        return jsonify({'success': True, 'message': 'Курс обновлен'})
    else:
        return jsonify({'error': 'Ошибка обновления курса'}), 500

@app.route('/api/export/orders')
@require_permission('orders')
def export_orders():
    # Получаем заявки для экспорта
    orders = get_all_orders()
    
    # Создаем Excel файл в памяти
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Заявки')
    
    # Заголовки
    headers = ['ID', 'Email', 'Telegram', 'Сумма заказа', 'Статус', 'Менеджер', 'Дата создания']
    for col, header in enumerate(headers):
        worksheet.write(0, col, header)
    
    # Данные
    for row, order in enumerate(orders, 1):
        worksheet.write(row, 0, order['id'])
        worksheet.write(row, 1, order['email'] or '')
        worksheet.write(row, 2, order['telegram_contact'] or '')
        worksheet.write(row, 3, order['order_amount'] or '')
        worksheet.write(row, 4, order['status'] or '')
        worksheet.write(row, 5, order['manager_email'] or '')
        worksheet.write(row, 6, order['created_at'].strftime('%d.%m.%Y %H:%M') if order['created_at'] else '')
    
    workbook.close()
    output.seek(0)
    
    # Логируем действие
    log_manager_action(session['user_email'], 'export', None, 'orders', 'Экспорт заявок в Excel')
    
    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename=orders_{datetime.now().strftime("%Y%m%d")}.xlsx'}
    )

@app.route('/api/export/users')
@require_permission('users')
def export_users():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("""
            SELECT tu.id, tu.telegram_id, tu.username, tu.first_name, tu.last_name,
                   tu.company, tu.phone, tu.email, tu.full_name, tu.created_at,
                   COUNT(uc.id) as calculations_count,
                   COUNT(pr.id) as orders_count
            FROM delivery_test.telegram_users tu
            LEFT JOIN delivery_test.user_calculation uc ON tu.id = uc.telegram_user_id
            LEFT JOIN delivery_test.purchase_requests pr ON tu.id = pr.telegram_user_id
            GROUP BY tu.id
            ORDER BY tu.created_at DESC
        """)
        users = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    
    # Создаем Excel файл
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Пользователи')
    
    # Заголовки
    headers = ['ID', 'Telegram ID', 'Username', 'Имя', 'Фамилия', 'Компания', 'Телефон', 'Email', 'Расчеты', 'Заявки', 'Дата регистрации']
    for col, header in enumerate(headers):
        worksheet.write(0, col, header)
    
    # Данные
    for row, user in enumerate(users, 1):
        worksheet.write(row, 0, user['id'])
        worksheet.write(row, 1, user['telegram_id'] or '')
        worksheet.write(row, 2, user['username'] or '')
        worksheet.write(row, 3, user['first_name'] or '')
        worksheet.write(row, 4, user['last_name'] or '')
        worksheet.write(row, 5, user['company'] or '')
        worksheet.write(row, 6, user['phone'] or '')
        worksheet.write(row, 7, user['email'] or '')
        worksheet.write(row, 8, user['calculations_count'])
        worksheet.write(row, 9, user['orders_count'])
        worksheet.write(row, 10, user['created_at'].strftime('%d.%m.%Y %H:%M') if user['created_at'] else '')
    
    workbook.close()
    output.seek(0)
    
    # Логируем действие
    log_manager_action(session['user_email'], 'export', None, 'users', 'Экспорт пользователей в Excel')
    
    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename=users_{datetime.now().strftime("%Y%m%d")}.xlsx'}
    )

# Остальные функции из оригинального app.py...
# (get_analytics_data, get_funnel_data, remove_old_files, clear_table, load_data_to_db, etc.)

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
        
        cursor.execute("SELECT COUNT(*) as orders FROM delivery_test.purchase_requests")
        orders = cursor.fetchone()['orders']

        conversion_started = (started / visits * 100) if visits > 0 else 0
        conversion_completed = (completed / started * 100) if started > 0 else 0
        conversion_orders = (orders / completed * 100) if completed > 0 else 0

        return {
            'visits': visits, 'started': started, 'completed': completed, 'orders': orders,
            'conversion_started': conversion_started,
            'conversion_completed': conversion_completed,
            'conversion_orders': conversion_orders
        }
    except Exception as e:
        return {
            'visits': 0, 'started': 0, 'completed': 0, 'orders': 0,
            'conversion_started': 0, 'conversion_completed': 0, 'conversion_orders': 0
        }
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    # Создаем необходимые директории
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(PDF_FOLDER, exist_ok=True)
    
    # Инициализируем таблицы управления
    try:
        init_management_tables()
        print("✅ Таблицы управления инициализированы")
    except Exception as e:
        print(f"❌ Ошибка инициализации таблиц: {e}")
    
    print("Запуск приложения China Together Management System")
    print(f"Excel файлы: {UPLOAD_FOLDER}")
    print(f"PDF файлы: {PDF_FOLDER}")
    
    try:
        app.run(host='0.0.0.0', port=8060, debug=True)
    except Exception as e:
        print(f"Ошибка запуска приложения: {str(e)}")
        raise
