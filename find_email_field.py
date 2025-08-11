#!/usr/bin/env python3
"""
Специальный скрипт для поиска entry ID для email поля в Google Forms
"""

import requests
import re
import json
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def find_email_entry_id():
    """
    Ищет entry ID для email поля различными способами
    """
    form_url = "https://docs.google.com/forms/d/e/1FAIpQLSfONB0hP9sCKurPmcyuHyAj_ffmF2tmLrum9kKlyMSWqDGm_w/viewform"
    
    try:
        logger.info("🔍 Поиск entry ID для email поля...")
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        response = session.get(form_url, timeout=30)
        response.raise_for_status()
        
        html_content = response.text
        
        print("📋 АНАЛИЗ EMAIL ПОЛЯ В GOOGLE FORMS")
        print("=" * 50)
        
        # 1. Ищем все упоминания email в HTML
        email_patterns = [
            r'email.*?entry\.(\d+)',
            r'entry\.(\d+).*?email',
            r'emailAddress.*?entry\.(\d+)',
            r'entry\.(\d+).*?emailAddress',
            r'почт.*?entry\.(\d+)',
            r'entry\.(\d+).*?почт',
            r'электронн.*?entry\.(\d+)',
            r'entry\.(\d+).*?электронн'
        ]
        
        found_entries = set()
        
        for pattern in email_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                found_entries.add(f"entry.{match}")
        
        print(f"🔍 Найдено потенциальных email entry: {len(found_entries)}")
        for entry in sorted(found_entries):
            print(f"   - {entry}")
        
        # 2. Ищем стандартные поля Google Forms для email
        standard_email_fields = [
            'emailAddress',
            'email',
            'entry.email',
            'emailReceipt'
        ]
        
        print(f"\n📧 СТАНДАРТНЫЕ EMAIL ПОЛЯ:")
        for field in standard_email_fields:
            if field in html_content:
                print(f"   ✅ Найдено: {field}")
            else:
                print(f"   ❌ Не найдено: {field}")
        
        # 3. Ищем все entry ID и их контекст
        all_entries = {
            'entry.1244169801': 'Telegram contact',
            'entry.1332237779': 'Supplier link', 
            'entry.1319459294': 'Order amount',
            'entry.211960837': 'Promo code',
            'entry.363561279': 'Terms accepted'
        }
        
        print(f"\n📝 АНАЛИЗ ИЗВЕСТНЫХ ENTRY ID:")
        for entry_id, description in all_entries.items():
            context = find_entry_context_around(html_content, entry_id)
            print(f"   {entry_id}: {description}")
            print(f"      Контекст: {context[:100]}...")
        
        # 4. Ищем специальное поведение email в Google Forms
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Ищем input поля с типом email
        email_inputs = soup.find_all('input', {'type': 'email'})
        print(f"\n📧 INPUT[TYPE=EMAIL] ПОЛЯ: {len(email_inputs)}")
        for inp in email_inputs:
            attrs = inp.attrs
            print(f"   Атрибуты: {attrs}")
        
        # Ищем поля с валидацией email
        email_validation = soup.find_all(attrs={'data-validation': re.compile('email', re.I)})
        print(f"\n✅ ПОЛЯ С EMAIL ВАЛИДАЦИЕЙ: {len(email_validation)}")
        for field in email_validation:
            print(f"   {field.attrs}")
        
        # 5. Предлагаем решения
        print(f"\n💡 РЕКОМЕНДАЦИИ:")
        
        if found_entries:
            print(f"🔍 Попробуйте эти entry ID для email:")
            for entry in sorted(found_entries):
                print(f"   'email': '{entry}',")
        
        print(f"\n📧 Или используйте стандартные поля:")
        print(f"   'email': 'emailAddress',")
        print(f"   'email': 'email',")
        
        # 6. Создаем тестовые URLs
        print(f"\n🧪 ТЕСТОВЫЕ ССЫЛКИ:")
        
        test_email = "test@example.com"
        base_url = form_url.replace('/viewform', '/viewform?usp=pp_url')
        
        # Тестируем стандартные поля
        for field in ['emailAddress', 'email']:
            test_url = f"{base_url}&{field}={test_email}"
            print(f"   {field}: {test_url}")
        
        # Тестируем найденные entry
        for entry in sorted(found_entries):
            test_url = f"{base_url}&{entry}={test_email}"
            print(f"   {entry}: {test_url}")
        
        return found_entries
        
    except Exception as e:
        logger.error(f"❌ Ошибка поиска email поля: {e}")
        return set()

def find_entry_context_around(html_content, entry_id):
    """Находит контекст вокруг entry ID"""
    try:
        entry_num = entry_id.replace('entry.', '')
        pattern = rf'.{{0,100}}{entry_num}.{{0,100}}'
        match = re.search(pattern, html_content, re.IGNORECASE)
        if match:
            context = match.group(0)
            # Убираем HTML теги
            context = re.sub(r'<[^>]+>', ' ', context)
            context = ' '.join(context.split())
            return context
        return "Контекст не найден"
    except:
        return "Ошибка поиска"

def test_email_fields():
    """
    Создает тестовые ссылки для проверки email полей
    """
    print(f"\n🧪 ИНСТРУКЦИЯ ПО ТЕСТИРОВАНИЮ EMAIL ПОЛЯ:")
    print("=" * 50)
    
    base_form_url = "https://docs.google.com/forms/d/e/1FAIpQLSfONB0hP9sCKurPmcyuHyAj_ffmF2tmLrum9kKlyMSWqDGm_w/viewform"
    test_email = "test@example.com"
    
    test_fields = [
        'emailAddress',
        'email',
        'entry.email',
        'emailReceipt'
    ]
    
    print("1. Попробуйте открыть каждую из этих ссылок:")
    print("2. Проверьте, заполнилось ли поле email автоматически")
    print("3. Если да - используйте это поле в маппинге")
    print()
    
    for field in test_fields:
        test_url = f"{base_form_url}?{field}={test_email}"
        print(f"   🔗 Тест {field}:")
        print(f"      {test_url}")
        print()
    
    print("📝 Если ни одна ссылка не работает:")
    print("   1. Откройте форму в браузере")
    print("   2. Найдите поле Email")
    print("   3. Нажмите F12 → Elements")
    print("   4. Найдите <input> для email поля")
    print("   5. Посмотрите атрибут name='...'")

def main():
    """Основная функция"""
    print("🔍 ПОИСК EMAIL ENTRY ID В GOOGLE FORMS")
    print("=" * 50)
    
    # Ищем email entry ID
    found_entries = find_email_entry_id()
    
    # Показываем инструкцию по тестированию
    test_email_fields()
    
    print(f"\n🎯 СЛЕДУЮЩИЕ ШАГИ:")
    print("1. Откройте тестовые ссылки выше")
    print("2. Найдите рабочее поле для email")
    print("3. Обновите field_mapping в google_forms_sender.py")
    print("4. Запустите: python google_forms_sender.py")

if __name__ == "__main__":
    main()
