#!/usr/bin/env python3
"""
Скрипт инициализации базы данных для Order Manager
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'delivery_db'),
    'user': os.getenv('DB_USER'), 
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432')
}

def init_database():
    """Инициализация базы данных"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("🔧 Создание схемы delivery_test...")
        cursor.execute("CREATE SCHEMA IF NOT EXISTS delivery_test")
        
        # Здесь добавьте все SQL команды для создания таблиц
        # из вашего init_management_tables()
        
        conn.commit()
        print("✅ База данных успешно инициализирована!")
        
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    init_database()
