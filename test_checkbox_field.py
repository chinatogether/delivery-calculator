#!/usr/bin/env python3
"""
Специальный тест для checkbox поля в Google Forms
"""

import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_checkbox_variations():
    """Тестирует различные варианты значений для checkbox поля"""
    
    form_url = "https://docs.google.com/forms/d/e/1FAIpQLSfONB0hP9sCKurPmcyuHyAj_ffmF2tmLrum9kKlyMSWqDGm_w/formResponse"
    
    # Различные варианты значений для checkbox
    checkbox_variations = [
        # Полный текст из формы
        'Я подтверждаю, что ознакомлен(а) с условиями и правилами работы и выражаю свое согласие с ними.',
        # Короткие варианты
        'on',
        'true',
        '1',
        'checked',
        # Возможные значения для Google Forms checkbox
        'Я подтверждаю, что ознакомлен(а) с условиями и правилами работы и выражаю свое согласие с ними.',
    ]
    
    print("🔲 ТЕСТИРОВАНИЕ CHECKBOX ПОЛЯ")
    print("=" * 50)
    print("📋 Entry ID: entry.363561279")
    print("📝 Тестируем различные значения...")
    print()
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded'
    })
    
    successful_values = []
    
    for i, checkbox_value in enumerate(checkbox_variations, 1):
        print(f"🧪 Тест {i}: {checkbox_value[:50]}{'...' if len(checkbox_value) > 50 else ''}")
        
        # Минимальный набор данных для теста
        test_data = {
            'emailAddress': f'test{i}@example.com',
            'entry.1244169801': f'@test_user_{i}',
            'entry.363561279': checkbox_value  # Тестируемое checkbox значение
        }
        
        try:
            response = session.post(
                form_url,
                data=test_data,
                timeout=15,
                allow_redirects=True
            )
            
            # Анализируем результат
            success_indicators = ['formresponse', 'thanks', 'submitted', 'viewanalytics']
            response_url_lower = response.url.lower()
            is_success = any(indicator in response_url_lower for indicator in success_indicators)
            
            if response.status_code == 200 and is_success:
                print(f"   ✅ УСПЕХ! Значение работает")
                successful_values.append(checkbox_value)
            else:
                print(f"   ❌ Не работает (статус: {response.status_code}, URL: {response.url})")
                
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        
        print()
    
    print("🎯 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    print("=" * 40)
    
    if successful_values:
        print(f"✅ Найдено {len(successful_values)} рабочих значений:")
        for value in successful_values:
            print(f"   - {value[:70]}{'...' if len(value) > 70 else ''}")
        
        print(f"\n📝 РЕКОМЕНДАЦИЯ:")
        print(f"Используйте это значение в коде:")
        print(f"'{successful_values[0]}'")
        
    else:
        print("❌ Ни одно значение не сработало")
        print("💡 Возможные причины:")
        print("   1. Неправильный entry ID")
        print("   2. Форма требует заполнения обязательных полей")
        print("   3. Изменились настройки формы")

def create_checkbox_test_links():
    """Создает тестовые ссылки для ручной проверки checkbox"""
    
    base_url = "https://docs.google.com/forms/d/e/1FAIpQLSfONB0hP9sCKurPmcyuHyAj_ffmF2tmLrum9kKlyMSWqDGm_w/viewform"
    
    # Различные варианты для предзаполнения checkbox
    test_values = [
        'Я подтверждаю, что ознакомлен(а) с условиями и правилами работы и выражаю свое согласие с ними.',
        'on',
        'true',
        '1'
    ]
    
    print(f"\n🔗 ТЕСТОВЫЕ ССЫЛКИ ДЛЯ РУЧНОЙ ПРОВЕРКИ CHECKBOX:")
    print("=" * 60)
    
    for i, value in enumerate(test_values, 1):
        # Базовые параметры
        params = {
            'emailAddress': 'test@example.com',
            'entry.1244169801': '@test_user',
            'entry.363561279': value  # Checkbox значение
        }
        
        params_str = '&'.join([f"{k}={requests.utils.quote(str(v))}" for k, v in params.items()])
        test_url = f"{base_url}?{params_str}"
        
        print(f"\n{i}. Тест значения: {value[:50]}{'...' if len(value) > 50 else ''}")
        print(f"   {test_url}")
    
    print(f"\n📋 Инструкция:")
    print("1. Откройте каждую ссылку")
    print("2. Проверьте, установлена ли галочка в checkbox")
    print("3. Если да - это правильное значение!")

def main():
    """Основная функция"""
    print("🔲 СПЕЦИАЛЬНОЕ ТЕСТИРОВАНИЕ CHECKBOX ПОЛЯ")
    print("=" * 55)
    
    # Создаем тестовые ссылки
    create_checkbox_test_links()
    
    # Запрашиваем разрешение на автоматическое тестирование
    print(f"\n⚠️  ВНИМАНИЕ:")
    print("Автоматическое тестирование отправит несколько заявок в форму.")
    print("Продолжить? (y/n): ", end="")
    
    try:
        choice = input().lower().strip()
        if choice in ['y', 'yes', 'да', 'д']:
            print()
            test_checkbox_variations()
        else:
            print("Автоматическое тестирование пропущено.")
            print("Используйте тестовые ссылки выше для ручной проверки.")
    except KeyboardInterrupt:
        print("\nТестирование прервано пользователем.")

if __name__ == "__main__":
    main()
