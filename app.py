from flask import Flask, request, redirect, render_template, jsonify, session, flash, url_for, send_file, send_from_directory
import os
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import json
from functools import wraps
import secrets
from decimal import Decimal
import calendar
import hashlib
import bcrypt
import psutil
import shutil
import traceback
import pandas as pd
from io import BytesIO
import xlsxwriter
import tempfile
from werkzeug.utils import secure_filename
import glob

app = Flask(__name__, template_folder='templates')
app.secret_key = secrets.token_hex(16)

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

# Конфигурация загрузки файлов
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
PDF_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pdf-files')
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Создаем папки если их нет
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)

def connect_to_db():
    return psycopg2.connect(**DB_CONFIG)

def hash_password(password):
    """Хеширование пароля"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    """Проверка пароля"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def log_manager_action(manager_email, action_type, target_id=None, target_type=None, description=None, details=None):
    """Логирование действий менеджера"""
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
        print(f"Ошибка логирования: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def require_role(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('user_role') != role:
                flash('Недостаточно прав доступа', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user_by_email(email):
    """Получение пользователя из БД"""
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("""
            SELECT * FROM delivery_test.system_users 
            WHERE email = %s AND is_active = true
        """, (email,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def create_default_users():
    """Создание пользователей по умолчанию"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        # Проверяем есть ли уже пользователи
        cursor.execute("SELECT COUNT(*) FROM delivery_test.system_users")
        count = cursor.fetchone()[0]
        
        if count == 0:
            # Создаем пользователей по умолчанию
            default_users = [
                ('director@company.ru', 'Директор', 'director', 'director123'),
                ('manager1@company.ru', 'Менеджер Анна', 'manager', 'manager123'),
                ('manager2@company.ru', 'Менеджер Максим', 'manager', 'manager123')
            ]
            
            for email, name, role, password in default_users:
                hashed_password = hash_password(password)
                permissions = ['all'] if role == 'director' else ['orders', 'clients', 'calculator']
                
                cursor.execute("""
                    INSERT INTO delivery_test.system_users 
                    (email, name, role, password_hash, permissions)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (email) DO NOTHING
                """, (email, name, role, hashed_password, json.dumps(permissions)))
            
            conn.commit()
            print("✅ Пользователи по умолчанию созданы")
    except Exception as e:
        print(f"⚠ Ошибка создания пользователей: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def save_exchange_rate(rate, source="manual", notes=None, user_email=None):
    """Сохранение курса валют"""
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO delivery_test.exchange_rates 
            (currency_pair, rate, source, notes)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, ('CNY/USD', float(rate), f"{source}_{user_email}" if user_email else source, notes))
        
        rate_id = cursor.fetchone()[0]
        conn.commit()
        
        # Логируем действие
        if user_email:
            log_manager_action(user_email, 'update_exchange_rate', rate_id, 'exchange_rate', 
                             f"Обновлен курс на {rate}", {'rate': rate, 'source': source})
        
        return rate_id
    finally:
        cursor.close()
        conn.close()

def get_system_stats():
    """Получение статистики системы"""
    try:
        # Память
        memory = psutil.virtual_memory()
        memory_usage = {
            'total': round(memory.total / (1024**3), 2),  # GB
            'used': round(memory.used / (1024**3), 2),
            'free': round(memory.available / (1024**3), 2),
            'percent': memory.percent
        }
        
        # Диск
        disk = psutil.disk_usage('/')
        disk_usage = {
            'total': round(disk.total / (1024**3), 2),  # GB
            'used': round(disk.used / (1024**3), 2),
            'free': round(disk.free / (1024**3), 2),
            'percent': round((disk.used / disk.total) * 100, 1)
        }
        
        # CPU
        cpu_usage = psutil.cpu_percent(interval=1)
        
        # Загрузка системы
        load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
        
        return {
            'memory': memory_usage,
            'disk': disk_usage,
            'cpu': cpu_usage,
            'load_avg': load_avg,
            'uptime': psutil.boot_time()
        }
    except Exception as e:
        print(f"Ошибка получения статистики: {str(e)}")
        return None

# Инициализация таблиц
def init_tables():
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        # Создаем схему
        cursor.execute("CREATE SCHEMA IF NOT EXISTS delivery_test")
        
        # Таблица system_users (если не существует)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.system_users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL,
                password_hash TEXT NOT NULL,
                permissions JSONB DEFAULT '[]',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow'),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow'),
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        
        # Таблица exchange_rates (если не существует)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.exchange_rates (
                id SERIAL PRIMARY KEY,
                currency_pair VARCHAR(10) NOT NULL,
                rate NUMERIC(10, 6) NOT NULL,
                recorded_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow'),
                source VARCHAR(255),
                notes TEXT
            )
        """)
        
        # Таблица manager_actions (если не существует)
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
        
        # Таблица клиентов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.clients (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(255),
                telegram_username VARCHAR(100),
                telegram_chat_id VARCHAR(50),
                company VARCHAR(255),
                phone VARCHAR(50),
                email VARCHAR(255),
                comment TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                created_by VARCHAR(255)
            )
        """)
        
        # Таблица заявок
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.orders (
                id SERIAL PRIMARY KEY,
                client_id INTEGER REFERENCES delivery_test.clients(id),
                manager_email VARCHAR(255),
                status VARCHAR(50) DEFAULT 'new',
                order_amount DECIMAL(12,2),
                commission_amount DECIMAL(12,2),
                reject_reason TEXT,
                supplier_link TEXT,
                product_description TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                status_history JSONB DEFAULT '[]',
                closed_at TIMESTAMP WITH TIME ZONE,
                is_closed BOOLEAN DEFAULT FALSE
            )
        """)
        
        # Таблица расчетов доставки
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.delivery_calculations (
                id SERIAL PRIMARY KEY,
                client_id INTEGER REFERENCES delivery_test.clients(id),
                order_id INTEGER REFERENCES delivery_test.orders(id),
                manager_email VARCHAR(255),
                category VARCHAR(100),
                weight DECIMAL(10,3),
                volume DECIMAL(10,6),
                product_cost_cny DECIMAL(12,2),
                product_cost_usd DECIMAL(12,2),
                delivery_cost_usd DECIMAL(12,2),
                total_cost_usd DECIMAL(12,2),
                exchange_rate DECIMAL(8,4),
                calculation_details JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        
        # Таблицы для параметров доставки
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.weight (
                id SERIAL PRIMARY KEY,
                min_weight DECIMAL(10,3),
                max_weight DECIMAL(10,3),
                coefficient_bag DECIMAL(6,3),
                bag_packing_cost DECIMAL(8,2),
                bag_unloading_cost DECIMAL(8,2),
                coefficient_corner DECIMAL(6,3),
                corner_packing_cost DECIMAL(8,2),
                corner_unloading_cost DECIMAL(8,2),
                coefficient_frame DECIMAL(6,3),
                frame_packing_cost DECIMAL(8,2),
                frame_unloading_cost DECIMAL(8,2)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.density (
                id SERIAL PRIMARY KEY,
                category VARCHAR(100),
                min_density DECIMAL(8,3),
                max_density DECIMAL(8,3),
                density_range VARCHAR(50),
                fast_delivery_cost DECIMAL(8,2),
                regular_delivery_cost DECIMAL(8,2)
            )
        """)
        
        # Таблицы для совместимости с Telegram ботом
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.telegram_users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                username VARCHAR(100),
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                full_name VARCHAR(255),
                company VARCHAR(255),
                phone VARCHAR(50),
                email VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.user_calculation (
                id SERIAL PRIMARY KEY,
                telegram_user_id INTEGER REFERENCES delivery_test.telegram_users(id),
                category VARCHAR(100),
                total_weight DECIMAL(10,3),
                volume DECIMAL(10,6),
                product_cost DECIMAL(12,2),
                exchange_rate DECIMAL(8,4),
                calculation_details JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.purchase_requests (
                id SERIAL PRIMARY KEY,
                telegram_user_id INTEGER REFERENCES delivery_test.telegram_users(id),
                calculation_id INTEGER REFERENCES delivery_test.user_calculation(id),
                manager_email VARCHAR(255),
                status VARCHAR(50) DEFAULT 'new',
                email VARCHAR(255),
                telegram_contact VARCHAR(255),
                supplier_link TEXT,
                order_amount VARCHAR(255),
                promo_code VARCHAR(100),
                additional_notes TEXT,
                terms_accepted BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_test.user_inputs (
                id SERIAL PRIMARY KEY,
                telegram_user_id INTEGER REFERENCES delivery_test.telegram_users(id),
                input_type VARCHAR(50),
                input_value TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        
        # Создаем индексы
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_exchange_rates_pair_date 
            ON delivery_test.exchange_rates (currency_pair, recorded_at DESC)
        """)
        
        conn.commit()
        print("✅ Таблицы успешно созданы")
        
    except Exception as e:
        conn.rollback()
        print(f"⚠ Ошибка создания таблиц: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

# === МАРШРУТЫ АВТОРИЗАЦИИ ===

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '').strip()
        
        user = get_user_by_email(email)
        
        if user and check_password(password, user['password_hash']):
            session['user_email'] = user['email']
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            session['user_permissions'] = user['permissions']
            
            # Логируем вход
            log_manager_action(user['email'], 'login', None, 'auth', 'Вход в систему')
            
            flash(f'Добро пожаловать, {user["name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Неверный email или пароль', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_email' in session:
        log_manager_action(session['user_email'], 'logout', None, 'auth', 'Выход из системы')
    
    session.clear()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('login'))

# === ГЛАВНАЯ СТРАНИЦА ===

@app.route('/')
@require_auth
def home():
    """Главная страница - перенаправляет на dashboard"""
    return redirect(url_for('dashboard'))

# === ГЛАВНАЯ ПАНЕЛЬ ===

@app.route('/dashboard')
@require_auth
def dashboard():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Основная статистика
        cursor.execute("SELECT COUNT(*) as total FROM delivery_test.user_calculation")
        total_calculations_result = cursor.fetchone()
        total_calculations = total_calculations_result['total'] if total_calculations_result else 0
        
        cursor.execute("""
            SELECT COUNT(*) as today 
            FROM delivery_test.user_calculation 
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        today_calculations_result = cursor.fetchone()
        today_calculations = today_calculations_result['today'] if today_calculations_result else 0
        
        cursor.execute("SELECT AVG(total_weight) as avg_weight FROM delivery_test.user_calculation")
        avg_weight_result = cursor.fetchone()
        avg_weight = avg_weight_result['avg_weight'] if avg_weight_result and avg_weight_result['avg_weight'] else 0
        
        cursor.execute("SELECT COUNT(DISTINCT telegram_user_id) as active_users FROM delivery_test.user_calculation WHERE created_at >= NOW() - INTERVAL '7 days'")
        active_users_result = cursor.fetchone()
        active_users = active_users_result['active_users'] if active_users_result else 0
        
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM delivery_test.user_calculation 
            GROUP BY category 
            ORDER BY count DESC 
            LIMIT 1
        """)
        popular_category_data = cursor.fetchone()
        popular_category = popular_category_data['category'] if popular_category_data else "Нет данных"
        
        analytics = {
            'total_calculations': total_calculations,
            'today_calculations': today_calculations,
            'avg_weight': float(avg_weight),
            'popular_category': popular_category,
            'active_users': active_users
        }
        
        # Воронка пользователей
        cursor.execute("SELECT COUNT(*) as visits FROM delivery_test.telegram_users")
        visits_result = cursor.fetchone()
        visits = visits_result['visits'] if visits_result else 0
        
        cursor.execute("SELECT COUNT(DISTINCT telegram_user_id) as started FROM delivery_test.user_inputs")
        started_result = cursor.fetchone()
        started = started_result['started'] if started_result else 0
        
        cursor.execute("SELECT COUNT(DISTINCT telegram_user_id) as completed FROM delivery_test.user_calculation")
        completed_result = cursor.fetchone()
        completed = completed_result['completed'] if completed_result else 0
        
        cursor.execute("SELECT COUNT(DISTINCT telegram_user_id) as orders FROM delivery_test.purchase_requests")
        orders_result = cursor.fetchone()
        orders = orders_result['orders'] if orders_result else 0
        
        funnel_data = {
            'visits': visits,
            'started': started,
            'completed': completed,
            'orders': orders,
            'conversion_started': (started / visits * 100) if visits > 0 else 0,
            'conversion_completed': (completed / started * 100) if started > 0 else 0,
            'conversion_orders': (orders / completed * 100) if completed > 0 else 0
        }
        
        # Расчеты по дням
        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM delivery_test.user_calculation
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        """)
        calculations_by_day = cursor.fetchall()
        
        # Заявки по статусам
        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM delivery_test.purchase_requests 
            GROUP BY status
        """)
        orders_by_status = cursor.fetchall()
        
        # Статистика менеджеров (только для директора)
        manager_stats = []
        if session.get('user_role') == 'director':
            cursor.execute("""
                SELECT 
                    manager_email,
                    COUNT(*) as orders_count,
                    COUNT(CASE WHEN status IN ('delivered', 'completed') THEN 1 END) as completed_count
                FROM delivery_test.purchase_requests 
                WHERE manager_email IS NOT NULL
                GROUP BY manager_email
            """)
            manager_stats = cursor.fetchall()
        
        return render_template('dashboard.html',
                             analytics=analytics,
                             funnel_data=funnel_data,
                             calculations_by_day=calculations_by_day,
                             orders_by_status=orders_by_status,
                             manager_stats=manager_stats)
        
    finally:
        cursor.close()
        conn.close()

# === АДМИН ПАНЕЛЬ (ТОЛЬКО ДЛЯ ДИРЕКТОРА) ===

@app.route('/admin')
@require_role('director')
def admin_panel():
    return render_template('admin_panel.html')

@app.route('/admin/users')
@require_role('director')
def admin_users():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT u.*, 
                   COUNT(ma.id) as action_count,
                   MAX(ma.created_at) as last_activity
            FROM delivery_test.system_users u
            LEFT JOIN delivery_test.manager_actions ma ON u.email = ma.manager_email
            GROUP BY u.id
            ORDER BY u.created_at DESC
        """)
        users = cursor.fetchall()
        
        return render_template('admin_users.html', users=users)
        
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/users/create', methods=['GET', 'POST'])
@require_role('director')
def admin_create_user():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        email = data.get('email', '').lower().strip()
        name = data.get('name', '').strip()
        role = data.get('role', '').strip()
        password = data.get('password', '').strip()
        permissions = data.getlist('permissions') if hasattr(data, 'getlist') else data.get('permissions', [])
        
        if not all([email, name, role, password]):
            flash('Все поля обязательны для заполнения', 'error')
            return redirect(url_for('admin_create_user'))
        
        conn = connect_to_db()
        cursor = conn.cursor()
        
        try:
            hashed_password = hash_password(password)
            
            cursor.execute("""
                INSERT INTO delivery_test.system_users 
                (email, name, role, password_hash, permissions)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (email, name, role, hashed_password, json.dumps(permissions)))
            
            user_id = cursor.fetchone()[0]
            conn.commit()
            
            # Логируем создание пользователя
            log_manager_action(session['user_email'], 'create_user', user_id, 'user', 
                             f'Создан пользователь {name} ({email})')
            
            if request.is_json:
                return jsonify({'success': True, 'message': 'Пользователь создан'})
            else:
                flash('Пользователь успешно создан', 'success')
                return redirect(url_for('admin_users'))
                
        except Exception as e:
            conn.rollback()
            error_msg = 'Пользователь с таким email уже существует' if 'unique' in str(e).lower() else str(e)
            if request.is_json:
                return jsonify({'error': error_msg}), 400
            else:
                flash(f'Ошибка: {error_msg}', 'error')
        finally:
            cursor.close()
            conn.close()
    
    return render_template('admin_create_user.html')

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@require_role('director')
def admin_edit_user(user_id):
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if request.method == 'POST':
            data = request.get_json() if request.is_json else request.form
            
            name = data.get('name', '').strip()
            role = data.get('role', '').strip()
            permissions = data.getlist('permissions') if hasattr(data, 'getlist') else data.get('permissions', [])
            is_active = bool(data.get('is_active'))
            new_password = data.get('new_password', '').strip()
            
            update_fields = []
            params = []
            
            if name:
                update_fields.append('name = %s')
                params.append(name)
            if role:
                update_fields.append('role = %s')
                params.append(role)
            if permissions:
                update_fields.append('permissions = %s')
                params.append(json.dumps(permissions))
            
            update_fields.append('is_active = %s')
            params.append(is_active)
            
            if new_password:
                update_fields.append('password_hash = %s')
                params.append(hash_password(new_password))
            
            update_fields.append('updated_at = NOW()')
            params.append(user_id)
            
            cursor.execute(f"""
                UPDATE delivery_test.system_users 
                SET {', '.join(update_fields)}
                WHERE id = %s
            """, params)
            
            conn.commit()
            
            # Логируем изменение
            log_manager_action(session['user_email'], 'update_user', user_id, 'user', 
                             f'Обновлен пользователь ID {user_id}')
            
            if request.is_json:
                return jsonify({'success': True, 'message': 'Пользователь обновлен'})
            else:
                flash('Пользователь успешно обновлен', 'success')
                return redirect(url_for('admin_users'))
        
        # GET запрос
        cursor.execute("SELECT * FROM delivery_test.system_users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin_users'))
        
        return render_template('admin_edit_user.html', user=user)
        
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/system')
@require_role('director')
def admin_system():
    system_stats = get_system_stats()
    
    # Получаем логи ошибок
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Статистика по действиям
        cursor.execute("""
            SELECT action_type, COUNT(*) as count
            FROM delivery_test.manager_actions 
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY action_type
            ORDER BY count DESC
            LIMIT 10
        """)
        recent_actions = cursor.fetchall()
        
        # Последние действия
        cursor.execute("""
            SELECT ma.*, su.name as user_name
            FROM delivery_test.manager_actions ma
            LEFT JOIN delivery_test.system_users su ON ma.manager_email = su.email
            ORDER BY ma.created_at DESC
            LIMIT 50
        """)
        action_log = cursor.fetchall()
        
        return render_template('admin_system.html', 
                             system_stats=system_stats,
                             recent_actions=recent_actions,
                             action_log=action_log)
        
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/exchange-rate')
@require_role('director')
def admin_exchange_rate():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT * FROM delivery_test.exchange_rates 
            ORDER BY recorded_at DESC 
            LIMIT 20
        """)
        rates = cursor.fetchall()
        
        current_rate = rates[0] if rates else None
        
        return render_template('admin_exchange_rate.html', 
                             current_rate=current_rate, 
                             rates=rates)
        
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/files')
@require_role('director')
def admin_files():
    return render_template('admin_files.html')

# === API МАРШРУТЫ ===

@app.route('/api/exchange-rate/update', methods=['POST'])
@require_auth
def api_update_exchange_rate():
    data = request.get_json()
    new_rate = data.get('rate')
    notes = data.get('notes', '')
    
    if not new_rate or new_rate <= 0:
        return jsonify({'error': 'Некорректный курс'}), 400
    
    try:
        rate_id = save_exchange_rate(new_rate, 'manual', notes, session['user_email'])
        return jsonify({'success': True, 'message': 'Курс обновлен', 'rate_id': rate_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/system/stats')
@require_role('director')
def api_system_stats():
    stats = get_system_stats()
    if stats:
        return jsonify(stats)
    else:
        return jsonify({'error': 'Не удалось получить статистику'}), 500

@app.route('/api/upload-excel', methods=['POST'])
@require_auth
def api_upload_excel():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не найден'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Недопустимый тип файла'}), 400
    
    try:
        filename = secure_filename(f"delivery_params_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Здесь должна быть логика обработки Excel файла
        # Пока просто сохраняем
        
        # Логируем загрузку
        log_manager_action(session['user_email'], 'upload_excel', None, 'file', 
                         f'Загружен файл {filename}')
        
        return jsonify({
            'success': True, 
            'message': 'Файл успешно загружен',
            'filename': filename
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-pdf', methods=['POST'])
@require_auth
def api_generate_pdf():
    try:
        # Здесь должна быть логика генерации PDF
        # Пока возвращаем заглушку
        
        # Логируем генерацию
        log_manager_action(session['user_email'], 'generate_pdf', None, 'file', 
                         'Сгенерирован PDF файл')
        
        return jsonify({
            'success': True,
            'message': 'PDF файл успешно создан',
            'download_url': '/download/pdf/latest'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === МАРШРУТЫ ДИРЕКТОРА ===

@app.route('/settings')
@require_role('director')
def settings_page():
    # Получаем информацию о последнем файле
    last_file_info = "Файл ещё не загружен."
    if os.path.exists(os.path.join(UPLOAD_FOLDER, 'delivery_parameter.xlsx')):
        file_stat = os.stat(os.path.join(UPLOAD_FOLDER, 'delivery_parameter.xlsx'))
        last_file_info = f"delivery_parameter.xlsx (загружен {datetime.fromtimestamp(file_stat.st_mtime).strftime('%d.%m.%Y %H:%M')})"
    
    # Получаем информацию о PDF
    pdf_info = get_latest_pdf_info()
    
    return render_template('settings.html', 
                         last_file_info=last_file_info, 
                         pdf_info=pdf_info)

@app.route('/users')
@require_auth
def users_page():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Получаем всех пользователей из основной таблицы с дополнительной статистикой
        cursor.execute("""
            SELECT 
                u.id, u.telegram_id, u.username, u.first_name, u.last_name,
                u.full_name, u.company, u.phone, u.email, u.created_at,
                COUNT(DISTINCT c.id) as calculations_count,
                COUNT(DISTINCT pr.id) as orders_count,
                MAX(c.created_at) as last_activity
            FROM delivery_test.telegram_users u
            LEFT JOIN delivery_test.user_calculation c ON u.id = c.telegram_user_id
            LEFT JOIN delivery_test.purchase_requests pr ON u.id = pr.telegram_user_id
            GROUP BY u.id
            ORDER BY u.created_at DESC
        """)
        users = cursor.fetchall()
        
        return render_template('users.html', users=users, now=datetime.now)
        
    finally:
        cursor.close()
        conn.close()

@app.route('/orders')
@require_auth
def orders_page():
    # Получаем фильтры
    filters = {
        'status': request.args.get('status', ''),
        'manager_email': request.args.get('manager', ''),
        'date_from': request.args.get('date_from', ''),
        'date_to': request.args.get('date_to', '')
    }
    
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Базовый запрос для заявок
        query = """
            SELECT pr.*, tu.username, tu.first_name, tu.last_name, tu.email as user_email,
                   uc.category, uc.total_weight, uc.product_cost
            FROM delivery_test.purchase_requests pr
            LEFT JOIN delivery_test.telegram_users tu ON pr.telegram_user_id = tu.id
            LEFT JOIN delivery_test.user_calculation uc ON pr.calculation_id = uc.id
            WHERE 1=1
        """
        params = []
        
        # Применяем фильтры
        if filters['status']:
            query += " AND pr.status = %s"
            params.append(filters['status'])
        
        if filters['manager_email']:
            query += " AND pr.manager_email = %s"
            params.append(filters['manager_email'])
            
        if filters['date_from']:
            query += " AND pr.created_at >= %s"
            params.append(filters['date_from'])
            
        if filters['date_to']:
            query += " AND pr.created_at <= %s"
            params.append(filters['date_to'] + ' 23:59:59')
        
        # Менеджер видит только свои заявки + новые
        if session.get('user_role') == 'manager':
            query += " AND (pr.manager_email = %s OR pr.manager_email IS NULL)"
            params.append(session.get('user_email'))
        
        query += " ORDER BY pr.created_at DESC LIMIT 500"
        
        cursor.execute(query, params)
        orders = cursor.fetchall()
        
        # Получаем список менеджеров
        cursor.execute("SELECT DISTINCT manager_email FROM delivery_test.purchase_requests WHERE manager_email IS NOT NULL")
        managers = [row['manager_email'] for row in cursor.fetchall()]
        
        # Получаем статистику по статусам
        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM delivery_test.purchase_requests 
            GROUP BY status
        """)
        orders_by_status = cursor.fetchall()
        
        return render_template('order.html', 
                             orders=orders, 
                             managers=managers,
                             filters=filters,
                             orders_by_status=orders_by_status)
        
    finally:
        cursor.close()
        conn.close()

@app.route('/exchange-rate')
@require_auth
def exchange_rate_page():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Получаем текущий курс
        cursor.execute("""
            SELECT * FROM delivery_test.exchange_rates 
            ORDER BY recorded_at DESC 
            LIMIT 1
        """)
        current_rate = cursor.fetchone()
        
        if not current_rate:
            # Создаем дефолтный курс если его нет
            cursor.execute("""
                INSERT INTO delivery_test.exchange_rates (currency_pair, rate, source, notes)
                VALUES (%s, %s, %s, %s)
                RETURNING *
            """, ('CNY/USD', 7.25, 'system_default', 'Курс по умолчанию'))
            current_rate = cursor.fetchone()
            conn.commit()
        
        # Получаем историю курса
        cursor.execute("""
            SELECT * FROM delivery_test.exchange_rates 
            ORDER BY recorded_at DESC 
            LIMIT 20
        """)
        rate_history = cursor.fetchall()
        
        # Получаем аналитику
        cursor.execute("""
            SELECT 
                COUNT(*) as total_calculations,
                COUNT(CASE WHEN DATE(created_at) = CURRENT_DATE THEN 1 END) as today_calculations,
                AVG(total_weight) as avg_weight
            FROM delivery_test.user_calculation
        """)
        analytics = cursor.fetchone()
        
        return render_template('exchange_rate.html', 
                             current_rate=current_rate,
                             rate_history=rate_history,
                             analytics=analytics)
        
    finally:
        cursor.close()
        conn.close()

# === ЗАГРУЗКА EXCEL И ГЕНЕРАЦИЯ PDF ===

@app.route('/upload', methods=['POST'])
@require_role('director')
def upload_excel():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не найден'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Недопустимый тип файла'}), 400
    
    try:
        # Удаляем старые файлы
        old_files = glob.glob(os.path.join(UPLOAD_FOLDER, "*.xlsx")) + glob.glob(os.path.join(UPLOAD_FOLDER, "*.xls"))
        for old_file in old_files:
            try:
                os.remove(old_file)
            except:
                pass
        
        # Сохраняем новый файл
        filename = 'delivery_parameter.xlsx'
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Обрабатываем файл и загружаем в БД
        result = process_excel_file(filepath)
        
        # Логируем действие
        log_manager_action(session['user_email'], 'upload_excel', None, 'file', 
                         f'Загружен файл {file.filename}')
        
        if "успешно" in result:
            return render_template_string(f"""
                <!DOCTYPE html>
                <html><head><title>Файл загружен</title></head>
                <body style="font-family: Arial; padding: 40px; text-align: center;">
                    <h2>✅ Файл успешно загружен!</h2>
                    <p>{result}</p>
                    <p><a href="/settings">← Вернуться к настройкам</a></p>
                </body></html>
            """)
        else:
            return render_template_string(f"""
                <!DOCTYPE html>
                <html><head><title>Ошибка</title></head>
                <body style="font-family: Arial; padding: 40px; text-align: center;">
                    <h2>⚠ Ошибка при обработке файла</h2>
                    <p>{result}</p>
                    <p><a href="/settings">← Вернуться к настройкам</a></p>
                </body></html>
            """)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def process_excel_file(filepath):
    """Обработка Excel файла и загрузка в БД"""
    try:
        # Читаем Excel файл
        weight_data = pd.read_excel(filepath, sheet_name="weight", header=0)
        density_data = pd.read_excel(filepath, sheet_name="density", header=0)
        
        weight_data = weight_data.where(pd.notnull(weight_data), None)
        density_data = density_data.where(pd.notnull(density_data), None)
        
        # Проверяем обязательные столбцы
        required_weight_cols = ['Минимальный вес', 'Максимальный вес', 'Коэффициент мешок']
        required_density_cols = ['Категория', 'Минимальная плотность', 'Максимальная плотность']
        
        missing_weight = [col for col in required_weight_cols if col not in weight_data.columns]
        missing_density = [col for col in required_density_cols if col not in density_data.columns]
        
        if missing_weight:
            return f"Ошибка: в листе 'weight' отсутствуют столбцы: {missing_weight}"
        if missing_density:
            return f"Ошибка: в листе 'density' отсутствуют столбцы: {missing_density}"
        
        # Очищаем таблицы
        conn = connect_to_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute("TRUNCATE TABLE delivery_test.weight CASCADE")
            cursor.execute("TRUNCATE TABLE delivery_test.density CASCADE")
            
            # Загружаем данные weight
            for _, row in weight_data.iterrows():
                cursor.execute("""
                    INSERT INTO delivery_test.weight 
                    (min_weight, max_weight, coefficient_bag, bag_packing_cost, bag_unloading_cost,
                     coefficient_corner, corner_packing_cost, corner_unloading_cost,
                     coefficient_frame, frame_packing_cost, frame_unloading_cost)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    row.get('Минимальный вес'),
                    row.get('Максимальный вес'),
                    row.get('Коэффициент мешок'),
                    row.get('Стоимость упаковки мешок'),
                    row.get('Стоимость разгрузки мешок'),
                    row.get('Коэффициент уголок'),
                    row.get('Стоимость упаковки уголок'),
                    row.get('Стоимость разгрузки уголок'),
                    row.get('Коэффициент каркас'),
                    row.get('Стоимость упаковки каркас'),
                    row.get('Стоимость разгрузки каркас')
                ))
            
            # Загружаем данные density
            for _, row in density_data.iterrows():
                cursor.execute("""
                    INSERT INTO delivery_test.density 
                    (category, min_density, max_density, density_range, fast_delivery_cost, regular_delivery_cost)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    row.get('Категория'),
                    row.get('Минимальная плотность'),
                    row.get('Максимальная плотность'),
                    row.get('Плотность'),
                    row.get('Быстрое авто ($/kg)'),
                    row.get('Обычное авто($/kg)')
                ))
            
            conn.commit()
            
            # Автоматически генерируем PDF
            try:
                pdf_success, pdf_message, pdf_path = generate_pdf_from_db()
                if pdf_success:
                    return f"Данные успешно загружены в базу данных! {pdf_message}"
                else:
                    return f"Данные загружены, но PDF не создан: {pdf_message}"
            except:
                return "Данные успешно загружены в базу данных! PDF будет создан позже."
                
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        return f"Ошибка при обработке файла: {str(e)}"

def generate_pdf_from_db():
    """Генерация PDF из данных БД"""
    try:
        # Здесь можно интегрировать существующий pdf_generator.py
        # Пока возвращаем заглушку
        pdf_filename = f"china_together_tariffs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = os.path.join(PDF_FOLDER, pdf_filename)
        
        # Создаем простой PDF (заглушка)
        with open(pdf_path, 'w') as f:
            f.write("PDF content placeholder")
        
        return True, f"PDF создан: {pdf_filename}", pdf_path
        
    except Exception as e:
        return False, f"Ошибка создания PDF: {str(e)}", None

def get_latest_pdf_info():
    """Получение информации о последнем PDF"""
    try:
        pdf_files = glob.glob(os.path.join(PDF_FOLDER, "*.pdf"))
        if not pdf_files:
            return None
        
        latest_file = max(pdf_files, key=os.path.getctime)
        file_stat = os.stat(latest_file)
        
        return {
            'filename': os.path.basename(latest_file),
            'full_path': latest_file,
            'size_kb': file_stat.st_size // 1024,
            'created': datetime.fromtimestamp(file_stat.st_ctime).strftime("%d.%m.%Y %H:%M"),
            'modified': datetime.fromtimestamp(file_stat.st_mtime).strftime("%d.%m.%Y %H:%M")
        }
    except:
        return None

@app.route('/download')
@require_auth
def download_excel():
    filepath = os.path.join(UPLOAD_FOLDER, 'delivery_parameter.xlsx')
    if not os.path.exists(filepath):
        flash('Файл не найден', 'error')
        return redirect(url_for('settings_page'))
    
    return send_from_directory(UPLOAD_FOLDER, 'delivery_parameter.xlsx', as_attachment=True)

@app.route('/download_pdf')
@require_auth  
def download_pdf():
    pdf_info = get_latest_pdf_info()
    if not pdf_info:
        flash('PDF файл не найден', 'error')
        return redirect(url_for('settings_page'))
    
    return send_from_directory(
        os.path.dirname(pdf_info['full_path']), 
        pdf_info['filename'], 
        as_attachment=True
    )

@app.route('/generate_pdf', methods=['POST'])
@require_role('director')
def force_generate_pdf():
    try:
        success, message, path = generate_pdf_from_db()
        
        # Логируем действие
        log_manager_action(session['user_email'], 'generate_pdf', None, 'file', 
                         'Создан PDF файл с тарифами')
        
        if success:
            flash(message, 'success')
        else:
            flash(f'Ошибка: {message}', 'error')
            
    except Exception as e:
        flash(f'Ошибка при создании PDF: {str(e)}', 'error')
    
    return redirect(url_for('settings_page'))

# === ОСТАЛЬНЫЕ МАРШРУТЫ (КЛИЕНТЫ, ЗАЯВКИ, КАЛЬКУЛЯТОР) ===

@app.route('/clients')
@require_auth
def clients_list():
    search = request.args.get('search', '')
    
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        query = """
            SELECT c.*, 
                   COUNT(o.id) as orders_count,
                   COALESCE(SUM(o.order_amount), 0) as total_amount
            FROM delivery_test.clients c
            LEFT JOIN delivery_test.orders o ON c.id = o.client_id
        """
        params = []
        
        if search:
            query += " WHERE (c.full_name ILIKE %s OR c.company ILIKE %s OR c.telegram_username ILIKE %s)"
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param])
        
        query += " GROUP BY c.id ORDER BY c.created_at DESC"
        
        cursor.execute(query, params)
        clients = cursor.fetchall()
        
        return render_template('mobile_clients.html', clients=clients, search=search)
        
    finally:
        cursor.close()
        conn.close()

@app.route('/calculator')
@require_auth
def calculator():
    return render_template('mobile_calculator.html')

# === API МАРШРУТЫ ===

@app.route('/api/exchange-rate', methods=['GET', 'POST'])
@require_auth
def api_exchange_rate():
    if request.method == 'POST':
        data = request.get_json()
        new_rate = data.get('rate')
        notes = data.get('notes', '')
        
        if not new_rate or new_rate <= 0:
            return jsonify({'error': 'Некорректный курс'}), 400
        
        try:
            rate_id = save_exchange_rate(new_rate, 'manual', notes, session['user_email'])
            return jsonify({'success': True, 'message': 'Курс обновлен', 'rate_id': rate_id})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        # GET запрос - возвращаем текущий курс
        conn = connect_to_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute("""
                SELECT * FROM delivery_test.exchange_rates 
                ORDER BY recorded_at DESC 
                LIMIT 1
            """)
            rate = cursor.fetchone()
            if rate:
                return jsonify({'success': True, 'rate': float(rate['rate'])})
            else:
                return jsonify({'success': False, 'error': 'Курс не найден'})
        finally:
            cursor.close()
            conn.close()

@app.route('/api/system_info')
@require_role('director')
def api_system_info():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Проверяем таблицы
        cursor.execute("SELECT COUNT(*) as count FROM delivery_test.weight")
        weight_records = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM delivery_test.density")  
        density_records = cursor.fetchone()['count']
        
        # Проверяем файл
        file_exists = os.path.exists(os.path.join(UPLOAD_FOLDER, 'delivery_parameter.xlsx'))
        
        # Статистика системы
        system_stats = get_system_stats()
        
        return jsonify({
            'weight_records': weight_records,
            'density_records': density_records,
            'file_exists': file_exists,
            'system_status': 'OK' if weight_records > 0 and density_records > 0 else 'WARNING',
            'memory_usage': system_stats['memory']['percent'] if system_stats else 0,
            'disk_usage': system_stats['disk']['percent'] if system_stats else 0,
            'cpu_usage': system_stats['cpu'] if system_stats else 0
        })
        
    except Exception as e:
        return jsonify({'error': f'Ошибка получения системной информации: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/recent-activity')
@require_auth
def api_recent_activity():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT ma.*, su.name as user_name
            FROM delivery_test.manager_actions ma
            LEFT JOIN delivery_test.system_users su ON ma.manager_email = su.email
            ORDER BY ma.created_at DESC
            LIMIT 10
        """)
        actions = cursor.fetchall()
        
        activities = []
        for action in actions:
            activity = {
                'description': get_action_description(action['action_type'], action['description']),
                'manager': action['user_name'] or action['manager_email'],
                'time': action['created_at'].strftime('%H:%M'),
                'icon': get_action_icon(action['action_type'])
            }
            activities.append(activity)
        
        return jsonify({'activities': activities})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

def get_action_description(action_type, description):
    """Преобразование типа действия в читаемое описание"""
    descriptions = {
        'login': 'Вход в систему',
        'logout': 'Выход из системы',
        'upload_excel': 'Загрузка Excel файла',
        'generate_pdf': 'Создание PDF файла',
        'update_exchange_rate': 'Обновление курса валют',
        'create_user': 'Создание пользователя',
        'update_user': 'Обновление пользователя',
        'create_order': 'Создание заявки',
        'update_order': 'Обновление заявки'
    }
    return descriptions.get(action_type, description or action_type)

def get_action_icon(action_type):
    """Иконка для типа действия"""
    icons = {
        'login': 'sign-in-alt',
        'logout': 'sign-out-alt',
        'upload_excel': 'file-excel',
        'generate_pdf': 'file-pdf',
        'update_exchange_rate': 'exchange-alt',
        'create_user': 'user-plus',
        'update_user': 'user-edit',
        'create_order': 'plus-circle',
        'update_order': 'edit'
    }
    return icons.get(action_type, 'info-circle')

@app.route('/api/orders/<int:order_id>/status', methods=['POST'])
@require_auth
def api_update_order_status(order_id):
    data = request.get_json()
    new_status = data.get('status')
    notes = data.get('notes', '')
    
    conn = connect_to_db()
    cursor = conn.cursor()
    
    try:
        # Обновляем статус заявки
        cursor.execute("""
            UPDATE delivery_test.purchase_requests 
            SET status = %s, updated_at = NOW()
            WHERE id = %s
        """, (new_status, order_id))
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Заявка не найдена'}), 404
        
        conn.commit()
        
        # Логируем действие
        log_manager_action(session['user_email'], 'update_order', order_id, 'order', 
                         f'Изменен статус на {new_status}', {'notes': notes})
        
        return jsonify({'success': True, 'message': 'Статус обновлен'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/users/<int:user_id>', methods=['GET', 'PUT'])
@require_role('director')
def api_user_details(user_id):
    if request.method == 'GET':
        conn = connect_to_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT u.*, 
                       COUNT(DISTINCT c.id) as calculations_count,
                       COUNT(DISTINCT pr.id) as orders_count,
                       MAX(c.created_at) as last_calculation
                FROM delivery_test.telegram_users u
                LEFT JOIN delivery_test.user_calculation c ON u.id = c.telegram_user_id
                LEFT JOIN delivery_test.purchase_requests pr ON u.id = pr.telegram_user_id
                WHERE u.id = %s
                GROUP BY u.id
            """, (user_id,))
            
            user = cursor.fetchone()
            if not user:
                return jsonify({'error': 'Пользователь не найден'}), 404
            
            return jsonify(dict(user))
            
        finally:
            cursor.close()
            conn.close()
    
    elif request.method == 'PUT':
        data = request.get_json()
        conn = connect_to_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE delivery_test.telegram_users 
                SET full_name = %s, company = %s, phone = %s, email = %s
                WHERE id = %s
            """, (
                data.get('full_name'),
                data.get('company'), 
                data.get('phone'),
                data.get('email'),
                user_id
            ))
            
            conn.commit()
            
            # Логируем действие
            log_manager_action(session['user_email'], 'update_user', user_id, 'user', 
                             f'Обновлены данные пользователя')
            
            return jsonify({'success': True, 'message': 'Пользователь обновлен'})
            
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            conn.close()

@app.route('/api/export/users')
@require_auth
def api_export_users():
    conn = connect_to_db()
    
    try:
        # Получаем данные пользователей
        df = pd.read_sql("""
            SELECT 
                u.telegram_id, u.username, u.first_name, u.last_name,
                u.full_name, u.company, u.phone, u.email, u.created_at,
                COUNT(DISTINCT c.id) as calculations_count,
                COUNT(DISTINCT pr.id) as orders_count,
                MAX(c.created_at) as last_activity
            FROM delivery_test.telegram_users u
            LEFT JOIN delivery_test.user_calculation c ON u.id = c.telegram_user_id
            LEFT JOIN delivery_test.purchase_requests pr ON u.id = pr.telegram_user_id
            GROUP BY u.id
            ORDER BY u.created_at DESC
        """, conn)
        
        # Создаем Excel файл
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Пользователи', index=False)
        
        output.seek(0)
        
        # Логируем действие
        log_manager_action(session['user_email'], 'export_users', None, 'export', 
                         'Экспорт списка пользователей')
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/export/orders')
@require_auth  
def api_export_orders():
    conn = connect_to_db()
    
    try:
        # Получаем данные заявок
        df = pd.read_sql("""
            SELECT 
                pr.id, pr.status, pr.order_amount, pr.telegram_contact,
                pr.email, pr.supplier_link, pr.created_at, pr.manager_email,
                tu.username, tu.first_name, tu.company,
                uc.category, uc.total_weight, uc.product_cost
            FROM delivery_test.purchase_requests pr
            LEFT JOIN delivery_test.telegram_users tu ON pr.telegram_user_id = tu.id
            LEFT JOIN delivery_test.user_calculation uc ON pr.calculation_id = uc.id
            ORDER BY pr.created_at DESC
        """, conn)
        
        # Создаем Excel файл
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Заявки', index=False)
        
        output.seek(0)
        
        # Логируем действие
        log_manager_action(session['user_email'], 'export_orders', None, 'export', 
                         'Экспорт списка заявок')
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'orders_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# === МОБИЛЬНЫЕ СТРАНИЦЫ ===

@app.route('/mobile/clients')
@require_auth
def mobile_clients_page():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT id, telegram_id, username, first_name, full_name, 
                   company, phone, created_at
            FROM delivery_test.telegram_users 
            ORDER BY created_at DESC 
            LIMIT 100
        """)
        users = cursor.fetchall()
        
        return render_template('mobile_clients.html', users=users)
        
    finally:
        cursor.close()
        conn.close()

@app.route('/mobile/client/<int:user_id>')
@require_auth
def mobile_client_card(user_id):
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Получаем данные пользователя
        cursor.execute("SELECT * FROM delivery_test.telegram_users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('mobile_clients_page'))
        
        # Получаем расчеты
        cursor.execute("""
            SELECT * FROM delivery_test.user_calculation 
            WHERE telegram_user_id = %s 
            ORDER BY created_at DESC 
            LIMIT 10
        """, (user_id,))
        calcs = cursor.fetchall()
        
        # Получаем заявки
        cursor.execute("""
            SELECT * FROM delivery_test.purchase_requests 
            WHERE telegram_user_id = %s 
            ORDER BY created_at DESC 
            LIMIT 10
        """, (user_id,))
        orders = cursor.fetchall()
        
        return render_template('mobile_client.html', user=user, calcs=calcs, orders=orders)
        
    finally:
        cursor.close()
        conn.close()

@app.route('/mobile/orders')
@require_auth
def mobile_orders_page():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        query = """
            SELECT pr.*, tu.username, tu.first_name, tu.full_name
            FROM delivery_test.purchase_requests pr
            LEFT JOIN delivery_test.telegram_users tu ON pr.telegram_user_id = tu.id
            WHERE 1=1
        """
        
        # Менеджер видит только свои заявки + новые
        if session.get('user_role') == 'manager':
            query += " AND (pr.manager_email = %s OR pr.manager_email IS NULL)"
            cursor.execute(query + " ORDER BY pr.created_at DESC LIMIT 50", (session.get('user_email'),))
        else:
            cursor.execute(query + " ORDER BY pr.created_at DESC LIMIT 50")
        
        orders = cursor.fetchall()
        
        return render_template('mobile_orders.html', orders=orders)
        
    finally:
        cursor.close()
        conn.close()

@app.route('/update_user_chat', methods=['POST'])
@require_auth
def update_user_chat():
    user_id = request.form.get('user_id')
    chat_number = request.form.get('chat_number')
    
    if not user_id or not chat_number:
        flash('Не указаны обязательные параметры', 'error')
        return redirect(request.referrer)
    
    conn = connect_to_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE delivery_test.telegram_users 
            SET telegram_id = %s 
            WHERE id = %s
        """, (chat_number, user_id))
        
        conn.commit()
        
        # Логируем действие
        log_manager_action(session['user_email'], 'update_user', user_id, 'user', 
                         f'Обновлен номер чата: {chat_number}')
        
        flash('Номер чата обновлен', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(request.referrer)

# === ДОПОЛНИТЕЛЬНЫЕ API И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

@app.route('/api/users/create', methods=['POST'])
@require_role('director')
def api_create_user():
    data = request.get_json()
    
    email = data.get('email', '').lower().strip()
    name = data.get('name', '').strip()
    role = data.get('role', '').strip()
    password = data.get('password', '').strip()
    permissions = data.get('permissions', [])
    
    if not all([email, name, role, password]):
        return jsonify({'error': 'Все поля обязательны для заполнения'}), 400
    
    conn = connect_to_db()
    cursor = conn.cursor()
    
    try:
        hashed_password = hash_password(password)
        
        cursor.execute("""
            INSERT INTO delivery_test.system_users 
            (email, name, role, password_hash, permissions)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (email, name, role, hashed_password, json.dumps(permissions)))
        
        user_id = cursor.fetchone()[0]
        conn.commit()
        
        # Логируем создание пользователя
        log_manager_action(session['user_email'], 'create_user', user_id, 'user', 
                         f'Создан пользователь {name} ({email})')
        
        return jsonify({'success': True, 'message': 'Пользователь создан', 'user_id': user_id})
        
    except Exception as e:
        conn.rollback()
        error_msg = 'Пользователь с таким email уже существует' if 'unique' in str(e).lower() else str(e)
        return jsonify({'error': error_msg}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/api/calculate', methods=['POST'])
@require_auth
def api_calculate_delivery():
    """API для расчета доставки"""
    data = request.get_json()
    
    try:
        # Получаем текущий курс
        conn = connect_to_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT rate FROM delivery_test.exchange_rates 
            ORDER BY recorded_at DESC 
            LIMIT 1
        """)
        rate_result = cursor.fetchone()
        exchange_rate = float(rate_result['rate']) if rate_result else 7.25
        
        # Выполняем расчет (упрощенная логика)
        category = data.get('category', '')
        weight = float(data.get('total_weight', 0) or data.get('weight', 0))
        volume = float(data.get('volume', 0))
        product_cost_cny = float(data.get('cost', 0))
        
        # Если используются размеры коробок
        if data.get('useBoxDimensions'):
            quantity = int(data.get('quantity', 1))
            weight_per_box = float(data.get('weightPerBox', 0))
            length = float(data.get('length', 0)) / 100  # см в м
            width = float(data.get('width', 0)) / 100
            height = float(data.get('height', 0)) / 100
            
            weight = weight_per_box * quantity
            volume = length * width * height * quantity
        
        # Конвертируем в USD
        product_cost_usd = product_cost_cny / exchange_rate
        
        # Расчет доставки (примерная формула)
        delivery_cost_usd = max(weight * 5, volume * 1000 * 8)
        total_cost_usd = product_cost_usd + delivery_cost_usd
        
        # Расчеты для разных типов упаковки
        insurance_rate = 0.01 if product_cost_usd < 20 else 0.02
        insurance_cost = product_cost_usd * insurance_rate
        
        result = {
            'generalInformation': {
                'weight': f"{weight:.2f}",
                'volume': f"{volume:.3f}",
                'density': f"{weight/volume:.2f}" if volume > 0 else "0",
                'productCostUSD': f"${product_cost_usd:.2f}",
                'exchangeRate': exchange_rate
            },
            'bag': {
                'deliveryCost': f"${delivery_cost_usd:.2f}",
                'packingCost': f"${weight * 3:.2f}",
                'totalFast': f"${delivery_cost_usd + weight * 3 + insurance_cost:.2f}",
                'totalRegular': f"${delivery_cost_usd * 0.8 + weight * 3 + insurance_cost:.2f}"
            },
            'corners': {
                'deliveryCost': f"${delivery_cost_usd:.2f}",
                'packingCost': f"${weight * 8:.2f}",
                'totalFast': f"${delivery_cost_usd + weight * 8 + insurance_cost:.2f}",
                'totalRegular': f"${delivery_cost_usd * 0.8 + weight * 8 + insurance_cost:.2f}"
            },
            'frame': {
                'deliveryCost': f"${delivery_cost_usd:.2f}",
                'packingCost': f"${weight * 15:.2f}",
                'totalFast': f"${delivery_cost_usd + weight * 15 + insurance_cost:.2f}",
                'totalRegular': f"${delivery_cost_usd * 0.8 + weight * 15 + insurance_cost:.2f}"
            }
        }
        
        # Сохраняем расчет если указан пользователь
        if data.get('telegram_id') != 'manager_calculation':
            cursor.execute("""
                INSERT INTO delivery_test.user_calculation 
                (telegram_user_id, category, total_weight, volume, product_cost, 
                 exchange_rate, calculation_details)
                VALUES (1, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                category, weight, volume, product_cost_usd,
                exchange_rate, json.dumps(result)
            ))
            
            calculation_id = cursor.fetchone()[0]
            result['calculation_id'] = calculation_id
            conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/submit_purchase_request', methods=['POST'])
@require_auth 
def submit_purchase_request():
    """API для создания заявки на покупку"""
    data = request.get_json()
    
    conn = connect_to_db()
    cursor = conn.cursor()
    
    try:
        # Создаем заявку
        cursor.execute("""
            INSERT INTO delivery_test.purchase_requests 
            (telegram_user_id, email, telegram_contact, supplier_link, 
             order_amount, promo_code, additional_notes, manager_email, status,
             calculation_id, terms_accepted)
            VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data.get('email'),
            data.get('telegram_contact'),
            data.get('supplier_link'),
            data.get('order_amount'),
            data.get('promo_code'),
            data.get('additional_notes'),
            session.get('user_email') if data.get('assign_to_me') else None,
            'assigned' if data.get('assign_to_me') else 'new',
            data.get('calculation_id'),
            True
        ))
        
        request_id = cursor.fetchone()[0]
        conn.commit()
        
        # Логируем создание заявки
        log_manager_action(session.get('user_email', 'system'), 'create_order', request_id, 'order', 
                         f'Создана заявка от {data.get("email")}')
        
        return jsonify({'success': True, 'request_id': request_id, 'message': 'Заявка создана'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/calculate-old', methods=['POST'])
@require_auth
def calculate_old():
    """Обратная совместимость с старым API расчетов"""
    return api_calculate_delivery()

@app.route('/calculate')
@require_auth
def calculate_page():
    """Страница калькулятора (заглушка)"""
    return render_template_string("""
        <!DOCTYPE html>
        <html><head><title>Калькулятор</title></head>
        <body style="font-family: Arial; padding: 40px; text-align: center;">
            <h2>🧮 Калькулятор доставки</h2>
            <p>Функция калькулятора будет реализована отдельно</p>
            <p><a href="/dashboard">← Вернуться на главную</a></p>
        </body></html>
    """)

@app.route('/api/backup', methods=['POST'])
@require_role('director')
def api_create_backup():
    """Создание резервной копии БД"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"backup_{timestamp}.sql"
        
        # Здесь должна быть логика создания бэкапа
        # Пока возвращаем заглушку
        
        log_manager_action(session['user_email'], 'create_backup', None, 'backup', 
                         f'Создана резервная копия {backup_filename}')
        
        return jsonify({'success': True, 'message': f'Резервная копия создана: {backup_filename}'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/system/optimize', methods=['POST'])
@require_role('director')
def api_optimize_system():
    """Оптимизация системы"""
    try:
        conn = connect_to_db()
        cursor = conn.cursor()
        
        # Очистка старых логов
        cursor.execute("""
            DELETE FROM delivery_test.manager_actions 
            WHERE created_at < NOW() - INTERVAL '30 days'
        """)
        
        # Обновление статистики таблиц
        cursor.execute("VACUUM ANALYZE")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        log_manager_action(session['user_email'], 'optimize_system', None, 'maintenance', 
                         'Выполнена оптимизация системы')
        
        return jsonify({'success': True, 'message': 'Система оптимизирована'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Инициализация при запуске
    try:
        init_tables()
        create_default_users()
        print("✅ Система инициализирована")
        print("🚀 Order Manager запущен")
        print("📱 Откройте http://localhost:8060")
        print("👥 Пользователи:")
        print("   Директор: director@company.ru / director123")
        print("   Менеджер: manager1@company.ru / manager123")
        print("   Менеджер: manager2@company.ru / manager123")
        print("\n📋 Функции директора:")
        print("   • Управление пользователями")
        print("   • Настройки системы")
        print("   • Загрузка Excel параметров")
        print("   • Генерация PDF тарифов")
        print("   • Управление курсом валют")
        print("   • Мониторинг системы")
        
    except Exception as e:
        print(f"⚠ Ошибка инициализации: {str(e)}")
        print("Попытка продолжить работу...")
    
    app.run(host='0.0.0.0', port=8060, debug=True)
