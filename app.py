from flask import Flask, request, redirect, render_template, jsonify, session, flash, url_for, send_file
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
import pandas as pd
from io import BytesIO
import xlsxwriter
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import logging
from logging.handlers import RotatingFileHandler
import traceback

app = Flask(__name__, template_folder='templates')
app.secret_key = secrets.token_hex(16)

load_dotenv()

# Настройка логирования
if not os.path.exists('logs'):
    os.makedirs('logs')

file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240000, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Order Manager startup')

# Конфигурация базы данных
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'delivery_db'),
    'user': os.getenv('DB_USER'), 
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'connect_timeout': int(os.getenv('DB_TIMEOUT', '10'))
}

def connect_to_db():
    return psycopg2.connect(**DB_CONFIG)

def hash_password(password):
    """Хэширование пароля с солью"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    """Проверка пароля"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

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

def require_permission(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_permissions = session.get('user_permissions', [])
            if permission not in user_permissions and session.get('user_role') != 'director':
                flash('Недостаточно прав доступа', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_user_action(action_type, target_id=None, target_type=None, description=None, details=None):
    """Логирование действий пользователя"""
    if 'user_email' not in session:
        return
        
    conn = connect_to_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO delivery_test.manager_actions
            (manager_email, action_type, target_id, target_type, description, details)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            session['user_email'], 
            action_type, 
            target_id, 
            target_type, 
            description,
            json.dumps(details) if details else None
        ))
        conn.commit()
    except Exception as e:
        app.logger.error(f"Ошибка логирования действия: {str(e)}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# Инициализация таблиц
def init_tables():
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        print("🔧 Создаем схему и таблицы...")
        
        # Создаем схему
        cursor.execute("CREATE SCHEMA IF NOT EXISTS delivery_test")
        
        # Проверяем существующие таблицы
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'delivery_test'
        """)
        existing_tables = [row[0] for row in cursor.fetchall()]
        print(f"🗃️ Существующие таблицы: {existing_tables}")
        
        # Создаем недостающие таблицы только если их нет
        if 'system_users' not in existing_tables:
            cursor.execute("""
                CREATE TABLE delivery_test.system_users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    name VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    password_hash TEXT NOT NULL,
                    permissions JSONB DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT (now() AT TIME ZONE 'Europe/Moscow'),
                    updated_at TIMESTAMPTZ DEFAULT (now() AT TIME ZONE 'Europe/Moscow'),
                    is_active BOOLEAN DEFAULT true
                )
            """)
            print("✅ Таблица system_users создана")
            
            # Добавляем директора по умолчанию
            director_password = hash_password('director123')
            cursor.execute("""
                INSERT INTO delivery_test.system_users 
                (email, name, role, password_hash, permissions)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                'director@company.ru', 
                'Директор', 
                'director', 
                director_password,
                json.dumps(['all'])
            ))
            print("✅ Директор по умолчанию создан")
        
        if 'exchange_rates' not in existing_tables:
            cursor.execute("""
                CREATE TABLE delivery_test.exchange_rates (
                    id SERIAL PRIMARY KEY,
                    currency_pair VARCHAR(10) NOT NULL,
                    rate NUMERIC(10, 6) NOT NULL,
                    recorded_at TIMESTAMPTZ DEFAULT (now() AT TIME ZONE 'Europe/Moscow'),
                    source VARCHAR(255),
                    notes TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX idx_exchange_rates_pair_date 
                ON delivery_test.exchange_rates (currency_pair, recorded_at DESC)
            """)
            print("✅ Таблица exchange_rates создана")
            
            # Добавляем начальный курс
            cursor.execute("""
                INSERT INTO delivery_test.exchange_rates (currency_pair, rate, source)
                VALUES ('CNY/USD', 7.2500, 'system')
            """)
            print("✅ Начальный курс добавлен")
        
        if 'manager_actions' not in existing_tables:
            cursor.execute("""
                CREATE TABLE delivery_test.manager_actions (
                    id SERIAL PRIMARY KEY,
                    manager_email VARCHAR(255) NOT NULL,
                    action_type VARCHAR(100) NOT NULL,
                    target_id INTEGER,
                    target_type VARCHAR(50),
                    description TEXT,
                    details JSONB,
                    created_at TIMESTAMPTZ DEFAULT (now() AT TIME ZONE 'Europe/Moscow')
                )
            """)
            print("✅ Таблица manager_actions создана")
        
        # Остальные таблицы...
        if 'clients' not in existing_tables:
            cursor.execute("""
                CREATE TABLE delivery_test.clients (
                    id SERIAL PRIMARY KEY,
                    full_name VARCHAR(255),
                    telegram_username VARCHAR(100),
                    telegram_chat_id VARCHAR(50),
                    company VARCHAR(255),
                    phone VARCHAR(50),
                    email VARCHAR(255),
                    comment TEXT,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now(),
                    created_by VARCHAR(255)
                )
            """)
            print("✅ Таблица clients создана")
        
        if 'orders' not in existing_tables:
            cursor.execute("""
                CREATE TABLE delivery_test.orders (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER REFERENCES delivery_test.clients(id),
                    manager_email VARCHAR(255),
                    status VARCHAR(50) DEFAULT 'new',
                    order_amount DECIMAL(12,2),
                    commission_amount DECIMAL(12,2),
                    reject_reason TEXT,
                    supplier_link TEXT,
                    product_description TEXT,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now(),
                    status_history JSONB DEFAULT '[]',
                    closed_at TIMESTAMPTZ,
                    is_closed BOOLEAN DEFAULT FALSE
                )
            """)
            print("✅ Таблица orders создана")
        
        if 'delivery_calculations' not in existing_tables:
            cursor.execute("""
                CREATE TABLE delivery_test.delivery_calculations (
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
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """)
            print("✅ Таблица delivery_calculations создана")
        
        # Создаем индексы
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_manager_email ON delivery_test.orders(manager_email);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON delivery_test.orders(status);
            CREATE INDEX IF NOT EXISTS idx_orders_created_at ON delivery_test.orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_manager_actions_email ON delivery_test.manager_actions(manager_email);
            CREATE INDEX IF NOT EXISTS idx_manager_actions_created_at ON delivery_test.manager_actions(created_at);
        """)
        print("✅ Индексы созданы")
        
        conn.commit()
        print("✅ Таблицы успешно созданы/проверены")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка создания таблиц: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

# === АУТЕНТИФИКАЦИЯ ===

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '').strip()
        
        conn = connect_to_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT id, email, name, role, password_hash, permissions, is_active
                FROM delivery_test.system_users 
                WHERE email = %s AND is_active = true
            """, (email,))
            
            user = cursor.fetchone()
            
            if user and check_password(password, user['password_hash']):
                session['user_id'] = user['id']
                session['user_email'] = user['email']
                session['user_name'] = user['name']
                session['user_role'] = user['role']
                session['user_permissions'] = user['permissions']
                
                log_user_action('login', description=f'Успешный вход в систему')
                flash(f'Добро пожаловать, {user["name"]}!', 'success')
                return redirect(url_for('dashboard'))
            else:
                log_user_action('login_failed', description=f'Неудачная попытка входа для {email}')
                flash('Неверный email или пароль', 'error')
                
        except Exception as e:
            app.logger.error(f"Ошибка авторизации: {str(e)}")
            flash('Ошибка системы', 'error')
        finally:
            cursor.close()
            conn.close()
    
    return render_template('mobile_login.html')

@app.route('/logout')
def logout():
    log_user_action('logout', description='Выход из системы')
    session.clear()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('login'))

# === ГЛАВНАЯ СТРАНИЦА ===

@app.route('/')
@require_auth
def dashboard():
    try:
        stats = get_dashboard_stats()
        
        if stats is None:
            stats = {
                'total_clients': 0,
                'orders_this_month': 0,
                'my_orders': 0,
                'my_revenue': 0,
                'new_orders': 0,
                'manager_stats': []
            }
        
        return render_template('mobile_dashboard.html', stats=stats)
        
    except Exception as e:
        app.logger.error(f"Ошибка в dashboard: {str(e)}")
        stats = {
            'total_clients': 0,
            'orders_this_month': 0,
            'my_orders': 0,
            'my_revenue': 0,
            'new_orders': 0,
            'manager_stats': []
        }
        return render_template('mobile_dashboard.html', stats=stats)

def get_dashboard_stats():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        user_role = session.get('user_role')
        user_email = session.get('user_email')
        
        stats = {}
        
        # Общая статистика
        try:
            cursor.execute("SELECT COUNT(*) as total FROM delivery_test.clients")
            result = cursor.fetchone()
            stats['total_clients'] = result['total'] if result else 0
        except Exception:
            stats['total_clients'] = 0
        
        try:
            cursor.execute("SELECT COUNT(*) as total FROM delivery_test.orders WHERE created_at >= date_trunc('month', CURRENT_DATE)")
            result = cursor.fetchone()
            stats['orders_this_month'] = result['total'] if result else 0
        except Exception:
            stats['orders_this_month'] = 0
        
        if user_role == 'manager':
            try:
                cursor.execute("""
                    SELECT COUNT(*) as my_orders 
                    FROM delivery_test.orders 
                    WHERE manager_email = %s AND created_at >= date_trunc('month', CURRENT_DATE)
                """, (user_email,))
                result = cursor.fetchone()
                stats['my_orders'] = result['my_orders'] if result else 0
            except Exception:
                stats['my_orders'] = 0
            
            try:
                cursor.execute("""
                    SELECT COALESCE(SUM(order_amount), 0) as total_amount
                    FROM delivery_test.orders 
                    WHERE manager_email = %s AND status = 'paid' 
                    AND created_at >= date_trunc('month', CURRENT_DATE)
                """, (user_email,))
                result = cursor.fetchone()
                stats['my_revenue'] = result['total_amount'] if result else 0
            except Exception:
                stats['my_revenue'] = 0
                
        elif user_role == 'director':
            try:
                cursor.execute("""
                    SELECT 
                        manager_email,
                        COUNT(*) as orders_count,
                        COALESCE(SUM(order_amount), 0) as total_amount,
                        COALESCE(SUM(commission_amount), 0) as total_commission
                    FROM delivery_test.orders 
                    WHERE created_at >= date_trunc('month', CURRENT_DATE)
                      AND manager_email IS NOT NULL
                    GROUP BY manager_email
                """)
                stats['manager_stats'] = cursor.fetchall() or []
            except Exception:
                stats['manager_stats'] = []
        
        try:
            cursor.execute("SELECT COUNT(*) as count FROM delivery_test.orders WHERE status = 'new'")
            result = cursor.fetchone()
            stats['new_orders'] = result['count'] if result else 0
        except Exception:
            stats['new_orders'] = 0
        
        return stats
        
    except Exception as e:
        app.logger.error(f"Ошибка в get_dashboard_stats: {str(e)}")
        return {
            'total_clients': 0,
            'orders_this_month': 0,
            'my_orders': 0,
            'my_revenue': 0,
            'new_orders': 0,
            'manager_stats': []
        }
    finally:
        cursor.close()
        conn.close()

# === УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ (ТОЛЬКО ДИРЕКТОР) ===

@app.route('/settings')
@require_role('director')
def settings():
    """Настройки системы для директора"""
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Получаем всех пользователей
        cursor.execute("""
            SELECT id, email, name, role, permissions, is_active, created_at, updated_at
            FROM delivery_test.system_users 
            ORDER BY created_at DESC
        """)
        users = cursor.fetchall()
        
        # Системная информация
        system_info = get_system_info()
        
        # Последние ошибки
        recent_errors = get_recent_errors()
        
        # Активность пользователей
        cursor.execute("""
            SELECT manager_email, COUNT(*) as actions_count, 
                   MAX(created_at) as last_activity
            FROM delivery_test.manager_actions 
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY manager_email
            ORDER BY actions_count DESC
        """)
        user_activity = cursor.fetchall()
        
        return render_template('mobile_settings.html', 
                             users=users, 
                             system_info=system_info,
                             recent_errors=recent_errors,
                             user_activity=user_activity)
        
    except Exception as e:
        app.logger.error(f"Ошибка в settings: {str(e)}")
        flash('Ошибка загрузки настроек', 'error')
        return redirect(url_for('dashboard'))
    finally:
        cursor.close()
        conn.close()

def get_system_info():
    """Получение информации о системе"""
    try:
        # Использование памяти
        memory = psutil.virtual_memory()
        
        # Использование диска
        disk = psutil.disk_usage('/')
        
        # Загрузка CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Информация о процессе
        process = psutil.Process()
        process_memory = process.memory_info()
        
        return {
            'memory': {
                'total': round(memory.total / (1024**3), 2),  # GB
                'available': round(memory.available / (1024**3), 2),  # GB
                'percent': memory.percent
            },
            'disk': {
                'total': round(disk.total / (1024**3), 2),  # GB
                'free': round(disk.free / (1024**3), 2),  # GB
                'percent': round((disk.used / disk.total) * 100, 1)
            },
            'cpu': {
                'percent': cpu_percent
            },
            'process': {
                'memory_mb': round(process_memory.rss / (1024**2), 2),  # MB
                'pid': process.pid
            },
            'uptime': str(datetime.now() - datetime.fromtimestamp(psutil.boot_time()))
        }
    except Exception as e:
        app.logger.error(f"Ошибка получения системной информации: {str(e)}")
        return {
            'memory': {'total': 0, 'available': 0, 'percent': 0},
            'disk': {'total': 0, 'free': 0, 'percent': 0},
            'cpu': {'percent': 0},
            'process': {'memory_mb': 0, 'pid': 0},
            'uptime': 'Неизвестно'
        }

def get_recent_errors(limit=20):
    """Получение последних ошибок из лог-файла"""
    try:
        errors = []
        log_file = 'logs/app.log'
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # Ищем строки с ERROR
            for line in reversed(lines[-1000:]):  # Последние 1000 строк
                if 'ERROR' in line:
                    errors.append({
                        'timestamp': line.split(' ')[0] + ' ' + line.split(' ')[1],
                        'message': line.strip()
                    })
                    if len(errors) >= limit:
                        break
        
        return errors
    except Exception as e:
        app.logger.error(f"Ошибка чтения лог-файла: {str(e)}")
        return []

@app.route('/api/users/create', methods=['POST'])
@require_role('director')
def create_user():
    """Создание нового пользователя"""
    data = request.get_json()
    
    try:
        email = data.get('email', '').lower().strip()
        name = data.get('name', '').strip()
        role = data.get('role', 'manager')
        password = data.get('password', '')
        permissions = data.get('permissions', [])
        
        if not email or not name or not password:
            return jsonify({'error': 'Заполните все обязательные поля'}), 400
        
        # Хэшируем пароль
        password_hash = hash_password(password)
        
        conn = connect_to_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO delivery_test.system_users 
                (email, name, role, password_hash, permissions)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (email, name, role, password_hash, json.dumps(permissions)))
            
            user_id = cursor.fetchone()[0]
            conn.commit()
            
            log_user_action('user_create', user_id, 'user', f'Создан пользователь {email}')
            
            return jsonify({
                'success': True, 
                'message': f'Пользователь {email} создан',
                'user_id': user_id
            })
            
        except psycopg2.IntegrityError:
            conn.rollback()
            return jsonify({'error': 'Пользователь с таким email уже существует'}), 400
            
    except Exception as e:
        app.logger.error(f"Ошибка создания пользователя: {str(e)}")
        return jsonify({'error': 'Ошибка создания пользователя'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/users/<int:user_id>/password', methods=['POST'])
@require_role('director')
def change_user_password(user_id):
    """Смена пароля пользователя"""
    data = request.get_json()
    new_password = data.get('password', '')
    
    if not new_password:
        return jsonify({'error': 'Пароль не может быть пустым'}), 400
    
    try:
        password_hash = hash_password(new_password)
        
        conn = connect_to_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE delivery_test.system_users 
            SET password_hash = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING email
        """, (password_hash, user_id))
        
        result = cursor.fetchone()
        if not result:
            return jsonify({'error': 'Пользователь не найден'}), 404
        
        user_email = result[0]
        conn.commit()
        
        log_user_action('password_change', user_id, 'user', f'Изменен пароль для {user_email}')
        
        return jsonify({'success': True, 'message': 'Пароль изменен'})
        
    except Exception as e:
        app.logger.error(f"Ошибка смены пароля: {str(e)}")
        return jsonify({'error': 'Ошибка смены пароля'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/users/<int:user_id>/toggle', methods=['POST'])
@require_role('director')
def toggle_user_status(user_id):
    """Активация/деактивация пользователя"""
    try:
        conn = connect_to_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE delivery_test.system_users 
            SET is_active = NOT is_active, updated_at = NOW()
            WHERE id = %s
            RETURNING email, is_active
        """, (user_id,))
        
        result = cursor.fetchone()
        if not result:
            return jsonify({'error': 'Пользователь не найден'}), 404
        
        user_email, is_active = result
        conn.commit()
        
        status = 'активирован' if is_active else 'деактивирован'
        log_user_action('user_toggle', user_id, 'user', f'Пользователь {user_email} {status}')
        
        return jsonify({
            'success': True, 
            'message': f'Пользователь {status}',
            'is_active': is_active
        })
        
    except Exception as e:
        app.logger.error(f"Ошибка изменения статуса пользователя: {str(e)}")
        return jsonify({'error': 'Ошибка изменения статуса'}), 500
    finally:
        cursor.close()
        conn.close()

# === УПРАВЛЕНИЕ КУРСОМ ВАЛЮТ ===

@app.route('/exchange-rate')
@require_auth
def exchange_rate():
    """Страница управления курсом валют"""
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT currency_pair, rate, source, recorded_at, notes
            FROM delivery_test.exchange_rates 
            WHERE currency_pair = 'CNY/USD'
            ORDER BY recorded_at DESC 
            LIMIT 10
        """)
        rates = cursor.fetchall()
        
        current_rate = rates[0] if rates else {
            'currency_pair': 'CNY/USD',
            'rate': 7.25, 
            'recorded_at': datetime.now(), 
            'source': 'default',
            'notes': None
        }
        
        return render_template('mobile_exchange_rate.html', 
                             current_rate=current_rate, history=rates)
        
    except Exception as e:
        app.logger.error(f"Ошибка в exchange_rate: {str(e)}")
        current_rate = {
            'currency_pair': 'CNY/USD',
            'rate': 7.25, 
            'recorded_at': datetime.now(), 
            'source': 'default',
            'notes': None
        }
        return render_template('mobile_exchange_rate.html', 
                             current_rate=current_rate, history=[])
    finally:
        cursor.close()
        conn.close()

def save_exchange_rate(currency_pair, rate, source=None, notes=None):
    """Сохранение курса валют"""
    conn = connect_to_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO delivery_test.exchange_rates 
            (currency_pair, rate, source, notes)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (currency_pair, rate, source, notes))
        
        rate_id = cursor.fetchone()[0]
        conn.commit()
        
        log_user_action('exchange_rate_update', rate_id, 'exchange_rate', 
                       f'Обновлен курс {currency_pair}: {rate}', 
                       {'rate': float(rate), 'source': source})
        
        return rate_id
        
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Ошибка сохранения курса: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

@app.route('/api/exchange-rate', methods=['POST'])
@require_auth
def update_exchange_rate():
    """API для обновления курса валют"""
    data = request.get_json()
    
    try:
        rate = float(data.get('rate', 0))
        currency_pair = data.get('currency_pair', 'CNY/USD')
        notes = data.get('notes', '')
        
        if rate <= 0:
            return jsonify({'error': 'Некорректный курс'}), 400
        
        save_exchange_rate(
            currency_pair=currency_pair,
            rate=rate,
            source=session['user_email'],
            notes=notes
        )
        
        return jsonify({'success': True, 'message': 'Курс обновлен'})
        
    except ValueError:
        return jsonify({'error': 'Некорректное значение курса'}), 400
    except Exception as e:
        app.logger.error(f"Ошибка API обновления курса: {str(e)}")
        return jsonify({'error': 'Ошибка обновления курса'}), 500

@app.route('/api/exchange-rate/current')
@require_auth
def api_current_exchange_rate():
    """API получения текущего курса"""
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT currency_pair, rate, recorded_at, source 
            FROM delivery_test.exchange_rates 
            WHERE currency_pair = 'CNY/USD'
            ORDER BY recorded_at DESC 
            LIMIT 1
        """)
        rate = cursor.fetchone()
        
        if rate:
            return jsonify({
                'currency_pair': rate['currency_pair'],
                'rate': float(rate['rate']),
                'recorded_at': rate['recorded_at'].isoformat(),
                'source': rate['source']
            })
        else:
            return jsonify({
                'currency_pair': 'CNY/USD',
                'rate': 7.25, 
                'recorded_at': datetime.now().isoformat(), 
                'source': 'system'
            })
            
    except Exception as e:
        app.logger.error(f"Ошибка API курса: {str(e)}")
        return jsonify({
            'currency_pair': 'CNY/USD',
            'rate': 7.25, 
            'recorded_at': datetime.now().isoformat(), 
            'source': 'system'
        })
    finally:
        cursor.close()
        conn.close()

# === РАБОТА С EXCEL И PDF ===

@app.route('/upload-excel', methods=['GET', 'POST'])
@require_auth
def upload_excel():
    """Загрузка Excel файла с параметрами"""
    if request.method == 'POST':
        try:
            if 'file' not in request.files:
                flash('Файл не выбран', 'error')
                return redirect(request.url)
            
            file = request.files['file']
            if file.filename == '':
                flash('Файл не выбран', 'error')
                return redirect(request.url)
            
            if file and file.filename.lower().endswith(('.xlsx', '.xls')):
                # Сохраняем файл
                filename = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
                filepath = os.path.join('uploads', filename)
                
                # Создаем папку если её нет
                os.makedirs('uploads', exist_ok=True)
                
                file.save(filepath)
                
                # Обрабатываем Excel файл
                result = process_excel_file(filepath)
                
                log_user_action('excel_upload', description=f'Загружен файл {filename}', 
                               details={'filename': filename, 'result': result})
                
                flash(f'Файл успешно загружен и обработан. Обработано {result["rows"]} строк.', 'success')
                
                # Можем предложить создать PDF
                session['last_excel_data'] = result['data']
                session['last_excel_filename'] = filename
                
                return redirect(url_for('generate_pdf'))
            else:
                flash('Поддерживаются только файлы Excel (.xlsx, .xls)', 'error')
        
        except Exception as e:
            app.logger.error(f"Ошибка загрузки Excel: {str(e)}")
            flash('Ошибка обработки файла', 'error')
    
    return render_template('mobile_upload_excel.html')

def process_excel_file(filepath):
    """Обработка Excel файла"""
    try:
        # Читаем Excel файл
        df = pd.read_excel(filepath)
        
        # Базовая обработка - можно расширить под ваши нужды
        processed_data = []
        
        for index, row in df.iterrows():
            processed_row = {}
            for col in df.columns:
                processed_row[str(col)] = str(row[col]) if pd.notna(row[col]) else ''
            processed_data.append(processed_row)
        
        return {
            'rows': len(processed_data),
            'columns': list(df.columns),
            'data': processed_data
        }
        
    except Exception as e:
        app.logger.error(f"Ошибка обработки Excel файла: {str(e)}")
        raise

@app.route('/generate-pdf')
@require_auth
def generate_pdf():
    """Генерация PDF отчета"""
    try:
        excel_data = session.get('last_excel_data')
        filename = session.get('last_excel_filename', 'data.xlsx')
        
        if not excel_data:
            flash('Нет данных для генерации PDF. Сначала загрузите Excel файл.', 'error')
            return redirect(url_for('upload_excel'))
        
        # Генерируем PDF
        pdf_path = create_pdf_report(excel_data, filename)
        
        log_user_action('pdf_generate', description=f'Создан PDF отчет из {filename}')
        
        return send_file(pdf_path, as_attachment=True, 
                        download_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        
    except Exception as e:
        app.logger.error(f"Ошибка генерации PDF: {str(e)}")
        flash('Ошибка генерации PDF', 'error')
        return redirect(url_for('upload_excel'))

def create_pdf_report(data, source_filename):
    """Создание PDF отчета"""
    try:
        # Создаем папку для PDF если её нет
        os.makedirs('reports', exist_ok=True)
        
        pdf_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = os.path.join('reports', pdf_filename)
        
        # Создаем PDF
        c = canvas.Canvas(pdf_path, pagesize=A4)
        width, height = A4
        
        # Заголовок
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, f"Отчет по данным из {source_filename}")
        
        # Дата создания
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 80, f"Дата создания: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        c.drawString(50, height - 100, f"Создал: {session.get('user_name', 'Неизвестно')}")
        
        # Данные
        y_position = height - 140
        c.setFont("Helvetica", 10)
        
        for i, row in enumerate(data[:50]):  # Ограничиваем 50 строками
            if y_position < 50:
                c.showPage()
                y_position = height - 50
            
            row_text = f"Строка {i+1}: " + ", ".join([f"{k}: {v}" for k, v in row.items()][:3])
            if len(row_text) > 80:
                row_text = row_text[:77] + "..."
            
            c.drawString(50, y_position, row_text)
            y_position -= 20
        
        if len(data) > 50:
            c.drawString(50, y_position - 20, f"... и еще {len(data) - 50} строк")
        
        c.save()
        return pdf_path
        
    except Exception as e:
        app.logger.error(f"Ошибка создания PDF: {str(e)}")
        raise

# === ОСТАЛЬНЫЕ МАРШРУТЫ (сокращенные версии) ===

@app.route('/clients')
@require_auth
def clients_list():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        search = request.args.get('search', '')
        
        # Запрос для получения клиентов
        query = """
            SELECT 
                c.id,
                c.full_name,
                c.telegram_username,
                c.telegram_chat_id,
                c.company,
                c.phone,
                c.email,
                c.comment,
                c.created_at,
                c.created_by,
                COUNT(o.id) as orders_count,
                COALESCE(SUM(o.order_amount), 0) as total_amount
            FROM delivery_test.clients c
            LEFT JOIN delivery_test.orders o ON c.id = o.client_id
        """
        params = []
        
        if search:
            query += """ 
                WHERE c.full_name ILIKE %s 
                   OR c.company ILIKE %s 
                   OR c.telegram_username ILIKE %s
                   OR c.email ILIKE %s
            """
            search_param = f"%{search}%"
            params = [search_param] * 4
        
        query += " GROUP BY c.id ORDER BY c.created_at DESC"
        
        cursor.execute(query, params)
        clients = cursor.fetchall()
        
        return render_template('mobile_clients.html', 
                             clients=clients, 
                             search=search)
        
    except Exception as e:
        app.logger.error(f"Ошибка в clients_list: {str(e)}")
        flash('Ошибка загрузки клиентов', 'error')
        return render_template('mobile_clients.html', clients=[], search='')
    finally:
        cursor.close()
        conn.close()

@app.route('/clients/add', methods=['GET', 'POST'])
@require_auth
def add_client():
    if request.method == 'POST':
        conn = connect_to_db()
        cursor = conn.cursor()
        
        try:
            # Получаем данные из JSON запроса
            data = request.get_json()
            
            cursor.execute("""
                INSERT INTO delivery_test.clients 
                (full_name, telegram_username, telegram_chat_id, 
                 company, phone, email, comment, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data.get('full_name', ''),
                data.get('telegram_username', ''),
                data.get('telegram_chat_id', ''),
                data.get('company', ''),
                data.get('phone', ''),
                data.get('email', ''),
                data.get('comment', ''),
                session['user_email']
            ))
            
            client_id = cursor.fetchone()[0]
            conn.commit()
            
            log_user_action('client_create', client_id, 'client', 
                          f"Создан клиент {data.get('full_name')}")
            
            return jsonify({
                'success': True,
                'message': 'Клиент успешно создан',
                'client_id': client_id
            })
            
        except Exception as e:
            conn.rollback()
            app.logger.error(f"Ошибка создания клиента: {str(e)}")
            return jsonify({
                'success': False, 
                'error': str(e)
            }), 400
        finally:
            cursor.close()
            conn.close()
    
    # GET запрос - показываем форму
    # Используем правильное имя шаблона
    return render_template('mobile_client_add.html')       

@app.route('/orders/<int:order_id>')
@require_auth
def order_detail(order_id):
    """Детальная страница заявки"""
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT 
                pr.*,
                tu.username,
                tu.first_name,
                tu.last_name,
                tu.full_name,
                tu.company,
                tu.phone as user_phone
            FROM delivery_test.purchase_requests pr
            LEFT JOIN delivery_test.telegram_users tu ON pr.telegram_user_id = tu.id
            WHERE pr.id = %s
        """, (order_id,))
        
        order = cursor.fetchone()
        
        if not order:
            flash('Заявка не найдена', 'error')
            return redirect(url_for('orders_list'))
        
        # Преобразуем order_amount
        if order.get('order_amount'):
            try:
                amount_str = str(order['order_amount']).replace('$', '').replace(',', '').strip()
                order['order_amount'] = float(amount_str) if amount_str else 0
            except:
                order['order_amount'] = 0
        
        return render_template('mobile_order_detail.html', order=order)
        
    except Exception as e:
        app.logger.error(f"Ошибка в order_detail: {str(e)}")
        flash('Ошибка загрузки заявки', 'error')
        return redirect(url_for('orders_list'))
    finally:
        cursor.close()
        conn.close()

@app.route('/clients/<int:client_id>')
@require_auth
def client_detail(client_id):
    """Детальная страница клиента"""
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT c.*, 
                   COUNT(DISTINCT o.id) as orders_count,
                   COALESCE(SUM(CASE 
                       WHEN o.order_amount ~ '^[0-9.]+$' THEN o.order_amount::numeric 
                       ELSE 0 
                   END), 0) as total_amount
            FROM delivery_test.clients c
            LEFT JOIN delivery_test.orders o ON c.id = o.client_id
            WHERE c.id = %s
            GROUP BY c.id
        """, (client_id,))
        
        client = cursor.fetchone()
        
        if not client:
            flash('Клиент не найден', 'error')
            return redirect(url_for('clients_list'))
        
        # Получаем заказы клиента
        cursor.execute("""
            SELECT * FROM delivery_test.orders 
            WHERE client_id = %s 
            ORDER BY created_at DESC
            LIMIT 10
        """, (client_id,))
        
        orders = cursor.fetchall()
        
        return render_template('mobile_client_detail.html', 
                             client=client, 
                             orders=orders)
        
    except Exception as e:
        app.logger.error(f"Ошибка в client_detail: {str(e)}")
        flash('Ошибка загрузки данных клиента', 'error')
        return redirect(url_for('clients_list'))
    finally:
        cursor.close()
        conn.close()

@app.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
@require_auth
def edit_client(client_id):
    """Редактирование клиента"""
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if request.method == 'POST':
            data = request.get_json() if request.is_json else request.form
            
            cursor.execute("""
                UPDATE delivery_test.clients 
                SET full_name = %s,
                    telegram_username = %s,
                    telegram_chat_id = %s,
                    company = %s,
                    phone = %s,
                    email = %s,
                    comment = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id
            """, (
                data.get('full_name'),
                data.get('telegram_username'),
                data.get('telegram_chat_id'),
                data.get('company'),
                data.get('phone'),
                data.get('email'),
                data.get('comment'),
                client_id
            ))
            
            conn.commit()
            
            if request.is_json:
                return jsonify({'success': True, 'message': 'Клиент обновлен'})
            else:
                flash('Клиент обновлен', 'success')
                return redirect(url_for('client_detail', client_id=client_id))
        
        # GET запрос
        cursor.execute("SELECT * FROM delivery_test.clients WHERE id = %s", (client_id,))
        client = cursor.fetchone()
        
        if not client:
            flash('Клиент не найден', 'error')
            return redirect(url_for('clients_list'))
        
        return render_template('mobile_edit_client.html', client=client)
        
    except Exception as e:
        app.logger.error(f"Ошибка редактирования клиента: {str(e)}")
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)}), 400
        else:
            flash('Ошибка сохранения', 'error')
            return redirect(url_for('client_detail', client_id=client_id))
    finally:
        cursor.close()
        conn.close()

@app.route('/api/debug/check-data')
@require_role('director')
def debug_check_data():
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Проверяем purchase_requests
        cursor.execute("SELECT COUNT(*) as count FROM delivery_test.purchase_requests")
        pr_count = cursor.fetchone()['count']
        
        # Проверяем telegram_users  
        cursor.execute("SELECT COUNT(*) as count FROM delivery_test.telegram_users")
        tu_count = cursor.fetchone()['count']
        
        # Проверяем clients
        cursor.execute("SELECT COUNT(*) as count FROM delivery_test.clients")
        cl_count = cursor.fetchone()['count']
        
        # Проверяем orders
        cursor.execute("SELECT COUNT(*) as count FROM delivery_test.orders")
        ord_count = cursor.fetchone()['count']
        
        return jsonify({
            'purchase_requests': pr_count,
            'telegram_users': tu_count,
            'clients': cl_count,
            'orders': ord_count
        })
        
    finally:
        cursor.close()
        conn.close()

@app.route('/orders')
@require_auth
def orders_list():
        conn = connect_to_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Получаем фильтры из запроса
            status_filter = request.args.get('status', '')
            manager_filter = request.args.get('manager', '')
            
            # Базовый запрос - используем таблицу purchase_requests
            query = """
                SELECT 
                    pr.id,
                    pr.telegram_user_id,
                    pr.calculation_id,
                    pr.manager_email,
                    pr.status,
                    pr.email,
                    pr.telegram_contact,
                    pr.supplier_link,
                    pr.order_amount,
                    pr.promo_code,
                    pr.additional_notes,
                    pr.created_at,
                    pr.updated_at,
                    tu.username,
                    tu.first_name,
                    tu.last_name,
                    tu.full_name,
                    tu.company
                FROM delivery_test.purchase_requests pr
                LEFT JOIN delivery_test.telegram_users tu ON pr.telegram_user_id = tu.id
                WHERE 1=1
            """
            params = []
            
            # Применяем фильтры
            if status_filter:
                query += " AND pr.status = %s"
                params.append(status_filter)
                
            if manager_filter:
                query += " AND pr.manager_email = %s"
                params.append(manager_filter)
            
            # Для менеджера показываем только его заявки и новые
            if session.get('user_role') == 'manager':
                query += " AND (pr.manager_email = %s OR pr.manager_email IS NULL OR pr.status = 'new')"
                params.append(session.get('user_email'))
            
            query += " ORDER BY pr.created_at DESC"
            
            cursor.execute(query, params)
            orders = cursor.fetchall()

            for order in orders:
                if order.get('order_amount'):
                    try:
                        # Убираем возможные символы валюты и пробелы
                        amount_str = str(order['order_amount']).replace('$', '').replace(',', '').strip()
                        order['order_amount'] = float(amount_str) if amount_str else 0
                    except (ValueError, TypeError):
                        order['order_amount'] = 0
                else:
                    order['order_amount'] = 0
            
            # Получаем список менеджеров для фильтра
            cursor.execute("""
                SELECT DISTINCT manager_email 
                FROM delivery_test.purchase_requests 
                WHERE manager_email IS NOT NULL
            """)
            managers = [row['manager_email'] for row in cursor.fetchall()]
            
            return render_template('mobile_orders.html', 
                                orders=orders, 
                                managers=managers,
                                status_filter=status_filter,
                                manager_filter=manager_filter)
            
        except Exception as e:
            app.logger.error(f"Ошибка в orders_list: {str(e)}")
            flash('Ошибка загрузки заявок', 'error')
            return render_template('mobile_orders.html', orders=[], managers=[])
        finally:
            cursor.close()
            conn.close()
        

@app.route('/calculator')
@require_auth
def calculator():
    return render_template('mobile_calculator.html')

@app.route('/analytics')
@require_role('director')
def analytics():
    return render_template('mobile_analytics.html', manager_stats=[], status_stats=[])

# === API ENDPOINTS ===

@app.route('/api/system-status')
@require_role('director')
def system_status():
    """API для получения статуса системы"""
    try:
        return jsonify({
            'status': 'healthy',
            'info': get_system_info(),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/user-activity')
@require_role('director')
def user_activity():
    """API для получения активности пользователей"""
    conn = connect_to_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        days = request.args.get('days', 7, type=int)
        
        cursor.execute("""
            SELECT 
                manager_email,
                action_type,
                COUNT(*) as count,
                DATE_TRUNC('day', created_at) as date
            FROM delivery_test.manager_actions 
            WHERE created_at >= NOW() - INTERVAL '%s days'
            GROUP BY manager_email, action_type, DATE_TRUNC('day', created_at)
            ORDER BY date DESC, count DESC
        """, (days,))
        
        activity = cursor.fetchall()
        
        return jsonify([{
            'manager_email': row['manager_email'],
            'action_type': row['action_type'],
            'count': row['count'],
            'date': row['date'].isoformat()
        } for row in activity])
        
    except Exception as e:
        app.logger.error(f"Ошибка получения активности: {str(e)}")
        return jsonify({'error': 'Ошибка получения данных'}), 500
    finally:
        cursor.close()
        conn.close()

# === ОБРАБОТЧИКИ ОШИБОК ===

@app.errorhandler(404)
def not_found_error(error):
    return render_template('mobile_error.html', error='Страница не найдена'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Внутренняя ошибка сервера: {str(error)}")
    return render_template('mobile_error.html', error='Внутренняя ошибка сервера'), 500

# === MIDDLEWARE ===

@app.before_request
def before_request():
    """Выполняется перед каждым запросом"""
    # Логируем все POST/PUT/DELETE запросы
    if request.method in ['POST', 'PUT', 'DELETE'] and 'user_email' in session:
        app.logger.info(f"Запрос {request.method} {request.path} от {session['user_email']}")

@app.after_request
def after_request(response):
    """Выполняется после каждого запроса"""
    # Логируем ошибки
    if response.status_code >= 400:
        app.logger.warning(f"Ответ {response.status_code} для {request.path}")
    
    return response

if __name__ == '__main__':
    try:
        # Создаем необходимые папки
        for folder in ['logs', 'uploads', 'reports']:
            os.makedirs(folder, exist_ok=True)
        
        init_tables()
        print("✅ Система инициализирована")
        
        print("🚀 Enhanced Order Manager запущен")
        print("📱 Откройте http://localhost:8060")
        print("👥 Пользователи:")
        print("   Директор: director@company.ru / director123")
        print("")
        print("📋 Функции директора:")
        print("   • Управление пользователями и правами")
        print("   • Мониторинг сервера и системы")
        print("   • Загрузка Excel и генерация PDF")
        print("   • Управление курсом валют")
        print("   • Просмотр логов и ошибок")
        print("   • Аналитика и отчеты")
        
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")
    
    app.run(host='0.0.0.0', port=8060, debug=True)
