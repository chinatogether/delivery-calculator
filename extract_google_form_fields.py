#!/usr/bin/env python3
"""
Скрипт для извлечения ID полей из Google Forms
Использует веб-скрапинг для получения правильных entry ID
"""

import requests
import re
import json
from bs4 import BeautifulSoup
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_google_form_fields(form_url):
    """
    Извлекает ID полей из Google Forms
    
    Args:
        form_url (str): URL формы Google Forms (viewform)
    
    Returns:
        dict: Словарь с найденными entry ID
    """
    try:
        logger.info(f"🔍 Извлечение полей из формы: {form_url}")
        
        # Настраиваем сессию с правильными заголовками
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        
        # Получаем HTML страницы
        response = session.get(form_url, timeout=30)
        response.raise_for_status()
        
        logger.info(f"✅ HTML получен, размер: {len(response.text)} символов")
        
        # Парсим HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем JavaScript код с данными формы
        script_tags = soup.find_all('script')
        form_data = None
        
        for script in script_tags:
            if script.string and 'FB_PUBLIC_LOAD_DATA_' in script.string:
                # Извлекаем JSON данные из JavaScript
                script_content = script.string
                
                # Ищем JSON данные формы
                json_match = re.search(r'FB_PUBLIC_LOAD_DATA_.*?(\[.*?\]);', script_content, re.DOTALL)
                if json_match:
                    try:
                        json_str = json_match.group(1)
                        form_data = json.loads(json_str)
                        logger.info("✅ JSON данные формы найдены")
                        break
                    except json.JSONDecodeError:
                        continue
        
        if not form_data:
            logger.warning("⚠️ Не удалось найти JSON данные, используем альтернативный метод")
            return extract_fields_from_html(response.text)
        
        # Извлекаем поля из JSON данных
        fields = extract_fields_from_json(form_data)
        
        if fields:
            logger.info(f"✅ Найдено {len(fields)} полей")
            return fields
        else:
            logger.warning("⚠️ Поля не найдены в JSON, используем HTML парсинг")
            return extract_fields_from_html(response.text)
            
    except Exception as e:
        logger.error(f"❌ Ошибка при извлечении полей: {e}")
        return {}

def extract_fields_from_json(form_data):
    """Извлекает поля из JSON данных формы"""
    fields = {}
    
    try:
        # Google Forms хранит данные в сложной структуре
        # Обычно поля находятся в form_data[1][1]
        if len(form_data) > 1 and len(form_data[1]) > 1:
            questions = form_data[1][1]
            
            for question in questions:
                if isinstance(question, list) and len(question) > 4:
                    # question[4] обычно содержит entry ID
                    # question[1] содержит текст вопроса
                    
                    entry_id = None
                    question_text = ""
                    
                    # Ищем entry ID в разных позициях
                    for item in question:
                        if isinstance(item, list) and len(item) > 0:
                            for subitem in item:
                                if isinstance(subitem, list) and len(subitem) > 0:
                                    for entry in subitem:
                                        if isinstance(entry, int) and entry > 100000000:
                                            entry_id = f"entry.{entry}"
                                            break
                    
                    # Извлекаем текст вопроса
                    if len(question) > 1 and isinstance(question[1], str):
                        question_text = question[1].lower()
                    
                    if entry_id and question_text:
                        # Определяем тип поля по тексту вопроса
                        field_name = classify_field(question_text)
                        if field_name:
                            fields[field_name] = entry_id
                            logger.info(f"📝 {field_name}: {entry_id} ('{question_text[:50]}...')")
        
        return fields
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга JSON: {e}")
        return {}

def extract_fields_from_html(html_content):
    """Альтернативный метод извлечения полей из HTML"""
    fields = {}
    
    try:
        # Ищем все input и textarea элементы с name="entry.*"
        entry_pattern = r'name=["\']entry\.(\d+)["\']'
        entry_matches = re.findall(entry_pattern, html_content)
        
        # Ищем связанные с ними labels или data-* атрибуты
        for entry_num in entry_matches:
            entry_id = f"entry.{entry_num}"
            
            # Ищем контекст вокруг этого entry
            context_pattern = rf'entry\.{entry_num}.*?(?:label|aria-label|data-label)[^>]*>([^<]*)'
            context_match = re.search(context_pattern, html_content, re.IGNORECASE | re.DOTALL)
            
            if context_match:
                label_text = context_match.group(1).strip().lower()
                field_name = classify_field(label_text)
                
                if field_name:
                    fields[field_name] = entry_id
                    logger.info(f"📝 {field_name}: {entry_id} (из HTML)")
        
        # Дополнительные паттерны поиска
        additional_patterns = [
            (r'почт.*?entry\.(\d+)', 'email'),
            (r'telegram.*?entry\.(\d+)', 'telegram_contact'),
            (r'поставщик.*?entry\.(\d+)', 'supplier_link'),
            (r'сумм.*?entry\.(\d+)', 'order_amount'),
            (r'промо.*?entry\.(\d+)', 'promo_code'),
            (r'услови.*?entry\.(\d+)', 'terms_accepted'),
        ]
        
        for pattern, field_name in additional_patterns:
            if field_name not in fields:
                match = re.search(pattern, html_content, re.IGNORECASE)
                if match:
                    entry_id = f"entry.{match.group(1)}"
                    fields[field_name] = entry_id
                    logger.info(f"📝 {field_name}: {entry_id} (дополнительный поиск)")
        
        return fields
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга HTML: {e}")
        return {}

def classify_field(text):
    """Классифицирует поле по тексту"""
    text = text.lower().strip()
    
    # Маппинг ключевых слов на поля
    field_mapping = {
        'email': ['email', 'почт', 'mail', '"Электронн'],
        'telegram_contact': ['telegram', 'телеграм', 'контакт', 'ссылка на ваш', 'личный телеграм'],
        'supplier_link': ['поставщик', 'ссылка на поставщика', '1688', 'supplier'],
        'order_amount': ['сумм', 'заказ', 'планируете', 'amount', 'юан'],
        'promo_code': ['промо', 'promo', 'код'],
        'terms_accepted': ['услови', 'правил', 'согласие', 'подтвержда', 'terms', 'agreement']
    }
    
    for field_name, keywords in field_mapping.items():
        for keyword in keywords:
            if keyword in text:
                return field_name
    
    return None

def generate_mapping_code(fields):
    """Генерирует код для обновления field_mapping"""
    if not fields:
        return "# Поля не найдены"
    
    code = "# Обновите field_mapping в google_forms_sender.py:\n"
    code += "self.field_mapping = {\n"
    
    for field_name, entry_id in fields.items():
        code += f"    '{field_name}': '{entry_id}',\n"
    
    code += "}\n"
    
    return code

def main():
    """Основная функция"""
    form_url = "https://docs.google.com/forms/d/e/1FAIpQLSfONB0hP9sCKurPmcyuHyAj_ffmF2tmLrum9kKlyMSWqDGm_w/viewform"
    
    print("🔍 Извлечение ID полей из Google Forms...")
    print(f"📋 URL формы: {form_url}")
    print()
    
    fields = extract_google_form_fields(form_url)
    
    if fields:
        print("✅ Найденные поля:")
        print("=" * 50)
        
        for field_name, entry_id in fields.items():
            print(f"{field_name:20} → {entry_id}")
        
        print()
        print("📝 Код для обновления:")
        print("=" * 50)
        print(generate_mapping_code(fields))
        
        # Сохраняем в файл
        with open('google_forms_mapping.txt', 'w', encoding='utf-8') as f:
            f.write("Google Forms Field Mapping\n")
            f.write("=" * 30 + "\n\n")
            f.write(f"Form URL: {form_url}\n\n")
            f.write("Found fields:\n")
            for field_name, entry_id in fields.items():
                f.write(f"{field_name}: {entry_id}\n")
            f.write("\n" + generate_mapping_code(fields))
        
        print("💾 Результаты сохранены в google_forms_mapping.txt")
        
    else:
        print("❌ Поля не найдены")
        print("💡 Попробуйте:")
        print("   1. Проверить URL формы")
        print("   2. Убедиться, что форма публична")
        print("   3. Извлечь поля вручную из HTML")

if __name__ == "__main__":
    main()
