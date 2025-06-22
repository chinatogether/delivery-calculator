#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF Generator для China Together
Модуль для генерации PDF файлов с тарифами доставки
"""

import os
import glob
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from jinja2 import Template
import pdfkit

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем директорию, где находится этот файл
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Конфигурация путей относительно текущего файла
PDF_FOLDER = os.path.join(BASE_DIR, "pdf-files")
TEMPLATES_FOLDER = os.path.join(BASE_DIR, "templates")

# Путь к wkhtmltopdf (попробуем найти автоматически)
def find_wkhtmltopdf():
    """Автоматически находит путь к wkhtmltopdf"""
    possible_paths = [
        '/usr/bin/wkhtmltopdf',
        '/usr/local/bin/wkhtmltopdf',
        '/opt/wkhtmltopdf/bin/wkhtmltopdf',
        'wkhtmltopdf'  # Если в PATH
    ]
    
    for path in possible_paths:
        if os.path.exists(path) or path == 'wkhtmltopdf':
            try:
                # Проверяем, работает ли команда
                os.system(f"{path} --version > /dev/null 2>&1")
                return path
            except:
                continue
    
    logger.warning("wkhtmltopdf не найден, используем значение по умолчанию")
    return '/usr/bin/wkhtmltopdf'

WKHTMLTOPDF_PATH = find_wkhtmltopdf()
WKHTMLTOPDF_CONFIG = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)

# Настройки для wkhtmltopdf
PDF_OPTIONS = {
    'page-size': 'A4',
    'margin-top': '15mm',
    'margin-right': '15mm',
    'margin-bottom': '15mm',
    'margin-left': '15mm',
    'encoding': "UTF-8",
    'no-outline': None,
    'enable-local-file-access': None,
    'print-media-type': None,
    'disable-smart-shrinking': None,
    'zoom': '1.2',  # Увеличивает масштаб для лучшей читаемости
    'dpi': '300',
    'quiet': '',  # Подавляем вывод wkhtmltopdf
}

class PDFGenerator:
    """Класс для генерации PDF файлов с тарифами"""
    
    def __init__(self, db_config):
        """
        Инициализация генератора PDF
        
        Args:
            db_config (dict): Конфигурация подключения к БД
        """
        self.db_config = db_config
        self.ensure_directories()
        logger.info(f"PDF Generator инициализирован. PDF папка: {PDF_FOLDER}")
    
    def ensure_directories(self):
        """Создает необходимые директории"""
        try:
            os.makedirs(PDF_FOLDER, exist_ok=True)
            os.makedirs(TEMPLATES_FOLDER, exist_ok=True)
            logger.info(f"Директории созданы: {PDF_FOLDER}, {TEMPLATES_FOLDER}")
        except Exception as e:
            logger.error(f"Ошибка создания директорий: {str(e)}")
    
    def connect_to_db(self):
        """Подключение к базе данных"""
        try:
            return psycopg2.connect(**self.db_config)
        except Exception as e:
            logger.error(f"Ошибка подключения к БД: {str(e)}")
            raise
    
    def remove_old_pdf_files(self):
        """Удаляет старые PDF файлы"""
        try:
            pdf_files = glob.glob(os.path.join(PDF_FOLDER, "*.pdf"))
            
            for file_path in pdf_files:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Удален старый PDF файл: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении старых PDF файлов: {str(e)}")
            return False
    
    def get_density_data_for_pdf(self):
        """Получает данные из таблицы density для формирования PDF"""
        conn = self.connect_to_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT category, min_density, max_density, density_range,
                       fast_delivery_cost, regular_delivery_cost
                FROM delivery_test.density
                ORDER BY category, min_density DESC
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                logger.warning("Нет данных в таблице density")
                return {}
            
            # Группируем данные по категориям
            categories_data = {}
            for row in rows:
                category = row['category']
                if category not in categories_data:
                    categories_data[category] = []
                categories_data[category].append(row)
            
            logger.info(f"Получено данных для {len(categories_data)} категорий")
            return categories_data
            
        except Exception as e:
            logger.error(f"Ошибка получения данных для PDF: {str(e)}")
            return {}
        finally:
            cursor.close()
            conn.close()
    
    def load_html_template(self):
        """Загружает HTML шаблон для PDF"""
        template_path = os.path.join(TEMPLATES_FOLDER, 'pdf_template.html')
        
        try:
            if not os.path.exists(template_path):
                logger.error(f"HTML шаблон не найден: {template_path}")
                # Создаем базовый шаблон, если его нет
                self.create_default_template()
            
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            return Template(template_content)
        except Exception as e:
            logger.error(f"Ошибка загрузки HTML шаблона: {str(e)}")
            raise
    
    def create_default_template(self):
        """Создает базовый HTML шаблон, если его нет"""
        template_path = os.path.join(TEMPLATES_FOLDER, 'pdf_template.html')
        
        default_template = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Тарифы доставки - China Together</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #E74C3C; text-align: center; }
        h2 { color: #E74C3C; margin-top: 30px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
        th { background-color: #f2f2f2; }
        .info { margin-top: 15px; font-size: 12px; background: #f8f9fa; padding: 10px; }
    </style>
</head>
<body>
    <h1>China Together - Тарифы доставки</h1>
    <p style="text-align: center; color: #666;">Сгенерировано: {{ generation_date }}</p>
    
    {% for category, rows in categories_data.items() %}
        <h2>{{ category }}</h2>
        <table>
            <thead>
                <tr>
                    <th>Плотность</th>
                    <th>Быстрое авто ($/kg)</th>
                    <th>Обычное авто ($/kg)</th>
                </tr>
            </thead>
            <tbody>
                {% for row in rows %}
                <tr>
                    <td>{{ row.density_range }}</td>
                    <td>${{ "%.2f"|format(row.fast_delivery_cost) }}</td>
                    <td>${{ "%.2f"|format(row.regular_delivery_cost) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <div class="info">
            <strong>Информация по доставке:</strong><br>
            • Сроки: Быстрое авто (12-15 дней), Обычное авто (18-25 дней)<br>
            • Страховка: до 20$/kg - 1%, 20-30$/kg - 2%, 30-40$/kg - 3%, свыше 40$/kg - индивидуально<br>
            • Упаковка: мешок+скотч 3$/место, уголки 8$/место, каркас 15$/место, паллета 30$/куб<br>
            • Копии брендов: +0.2$ к тарифу<br>
        </div>
        <div style="page-break-after: always;"></div>
    {% endfor %}
</body>
</html>'''
        
        try:
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(default_template)
            logger.info(f"Создан базовый HTML шаблон: {template_path}")
        except Exception as e:
            logger.error(f"Ошибка создания базового шаблона: {str(e)}")
    
    def generate_pdf_from_db(self, filename="china_together_tariffs.pdf"):
        """
        Основная функция генерации PDF из данных БД
        
        Args:
            filename (str): Имя файла PDF
            
        Returns:
            tuple: (success: bool, message: str, file_path: str)
        """
        try:
            logger.info("Начинаем генерацию PDF...")
            
            # Проверяем wkhtmltopdf
            if not os.path.exists(WKHTMLTOPDF_PATH) and WKHTMLTOPDF_PATH != 'wkhtmltopdf':
                return False, f"wkhtmltopdf не найден по пути: {WKHTMLTOPDF_PATH}", None
            
            # Удаляем старые PDF файлы
            self.remove_old_pdf_files()
            
            # Получаем данные из БД
            categories_data = self.get_density_data_for_pdf()
            
            if not categories_data:
                return False, "Нет данных в базе для генерации PDF", None
            
            # Загружаем HTML шаблон
            template = self.load_html_template()
            
            # Подготавливаем данные для шаблона
            template_data = {
                'categories_data': categories_data,
                'generation_date': datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                'total_categories': len(categories_data)
            }
            
            # Рендерим HTML
            html_content = template.render(**template_data)
            
            # Генерируем PDF
            output_path = os.path.join(PDF_FOLDER, filename)
            
            logger.info(f"Создаем PDF файл: {output_path}")
            
            pdfkit.from_string(
                html_content, 
                output_path, 
                options=PDF_OPTIONS,
                configuration=WKHTMLTOPDF_CONFIG
            )
            
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                logger.info(f"PDF успешно создан: {output_path} (размер: {file_size} байт)")
                return True, f"PDF успешно создан (размер: {file_size//1024} КБ)", output_path
            else:
                return False, "PDF файл не был создан", None
                
        except Exception as e:
            error_msg = f"Ошибка при генерации PDF: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None
    
    def get_pdf_info(self):
        """Получает информацию о существующих PDF файлах"""
        try:
            pdf_files = glob.glob(os.path.join(PDF_FOLDER, "*.pdf"))
            
            if not pdf_files:
                return None
            
            # Берем самый новый файл
            latest_file = max(pdf_files, key=os.path.getctime)
            
            file_stat = os.stat(latest_file)
            file_info = {
                'filename': os.path.basename(latest_file),
                'full_path': latest_file,
                'size': file_stat.st_size,
                'size_kb': file_stat.st_size // 1024,
                'created': datetime.fromtimestamp(file_stat.st_ctime).strftime("%d.%m.%Y %H:%M:%S"),
                'modified': datetime.fromtimestamp(file_stat.st_mtime).strftime("%d.%m.%Y %H:%M:%S")
            }
            
            return file_info
            
        except Exception as e:
            logger.error(f"Ошибка получения информации о PDF: {str(e)}")
            return None

def create_pdf_generator():
    """Фабричная функция для создания генератора PDF"""
    db_config = {
        'dbname': "delivery_db",
        'user': "chinatogether", 
        'password': "O99ri1@",
        'host': "localhost",
        'port': "5432",
        'connect_timeout': 10
    }
    
    return PDFGenerator(db_config)

def generate_tariffs_pdf():
    """
    Основная функция для вызова из app.py
    
    Returns:
        tuple: (success: bool, message: str, file_path: str)
    """
    try:
        generator = create_pdf_generator()
        return generator.generate_pdf_from_db()
    except Exception as e:
        error_msg = f"Критическая ошибка генерации PDF: {str(e)}"
        logger.error(error_msg)
        return False, error_msg, None

def get_latest_pdf_info():
    """
    Получает информацию о последнем созданном PDF
    
    Returns:
        dict or None: Информация о файле
    """
    try:
        generator = create_pdf_generator()
        return generator.get_pdf_info()
    except Exception as e:
        logger.error(f"Ошибка получения информации о PDF: {str(e)}")
        return None

if __name__ == "__main__":
    # Тестирование генерации PDF
    print("Тестируем генерацию PDF...")
    print(f"Рабочая директория: {BASE_DIR}")
    print(f"PDF папка: {PDF_FOLDER}")
    print(f"Templates папка: {TEMPLATES_FOLDER}")
    print(f"wkhtmltopdf путь: {WKHTMLTOPDF_PATH}")
    
    success, message, file_path = generate_tariffs_pdf()
    
    if success:
        print(f"✅ {message}")
        print(f"📁 Файл: {file_path}")
        
        # Показываем информацию о файле
        pdf_info = get_latest_pdf_info()
        if pdf_info:
            print(f"📊 Размер: {pdf_info['size_kb']} КБ")
            print(f"📅 Создан: {pdf_info['created']}")
    else:
        print(f"❌ {message}")
