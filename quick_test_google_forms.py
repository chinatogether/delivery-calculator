#!/usr/bin/env python3
"""
Быстрый тест Google Forms с правильными entry ID
"""

import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def quick_test():
    """Быстрый тест отправки в Google Forms"""
    
    # URL для отправки данных
    form_url = "https://docs.google.com/forms/d/e/1FAIpQLSfONB0hP9sCKurPmcyuHyAj_ffmF2tmLrum9kKlyMSWqDGm_w/formResponse"
    
    # Точные entry ID из FB_PUBLIC_LOAD_DATA_
    test_data = {
        'emailAddress': 'test@example.com',           # Email поле
        'entry.1244169801': '@test_user_telegram',    # Telegram
        'entry.1332237779': 'https://test-supplier.com/product',  # Поставщик  
        'entry.1319459294': '5000-10000 юаней',       # Сумма заказа
        'entry.211960837': 'TEST123',                 # Промокод
        # Checkbox поле - используем точное значение опции из формы
        'entry.363561279': 'Я подтверждаю, что ознакомлен(а) с условиями и правилами работы и выражаю свое согласие с ними.'
    }
    
    print("🧪 БЫСТРЫЙ ТЕСТ GOOGLE FORMS")
    print("=" * 40)
    print("📋 Отправляемые данные:")
    for field, value in test_data.items():
        print(f"   {field}: {value}")
    print()
    
    try:
        # Настраиваем сессию
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded'
        })
        
        logger.info("📤 Отправка данных в Google Form...")
        
        # Отправляем данные
        response = session.post(
            form_url,
            data=test_data,
            timeout=30,
            allow_redirects=True
        )
        
        print(f"📊 РЕЗУЛЬТАТ:")
        print(f"   Статус: {response.status_code}")
        print(f"   URL ответа: {response.url}")
        print(f"   Размер ответа: {len(response.text)} символов")
        
        # Анализируем результат
        success_indicators = [
            'formresponse',
            'thanks', 
            'submitted',
            'success',
            'viewanalytics'
        ]
        
        response_url_lower = response.url.lower()
        is_success = any(indicator in response_url_lower for indicator in success_indicators)
        
        if response.status_code == 200 and is_success:
            print("   ✅ УСПЕХ! Данные отправлены в Google Form")
            return True
        elif 'viewform' in response_url_lower:
            print("   ⚠️  Форма вернулась к viewform - возможна ошибка валидации")
            print("   💡 Проверьте правильность данных")
            return False
        else:
            print(f"   ❌ Неопределенный результат")
            print(f"   💡 Проверьте URL и entry ID")
            return False
            
    except Exception as e:
        print(f"   ❌ ОШИБКА: {e}")
        return False

def create_prefilled_test_link():
    """Создает предзаполненную ссылку для ручной проверки"""
    
    base_url = "https://docs.google.com/forms/d/e/1FAIpQLSfONB0hP9sCKurPmcyuHyAj_ffmF2tmLrum9kKlyMSWqDGm_w/viewform"
    
    # Тестовые данные для предзаполнения
    test_params = {
        'emailAddress': 'test@example.com',
        'entry.1244169801': '@test_user',
        'entry.1332237779': 'https://test-supplier.com',
        'entry.1319459294': '10000-15000 юаней',
        'entry.211960837': 'TESTCODE',
        'entry.363561279': 'Я подтверждаю, что ознакомлен(а) с условиями и правилами работы и выражаю свое согласие с ними.'
    }
    
    # Формируем URL с параметрами
    params_str = '&'.join([f"{k}={requests.utils.quote(str(v))}" for k, v in test_params.items() if v])
    prefilled_url = f"{base_url}?{params_str}"
    
    print(f"\n🔗 ПРЕДЗАПОЛНЕННАЯ ССЫЛКА ДЛЯ РУЧНОЙ ПРОВЕРКИ:")
    print("=" * 60)
    print(prefilled_url)
    print()
    print("📋 Инструкция:")
    print("1. Откройте ссылку выше в браузере")
    print("2. Проверьте, что все поля заполнились правильно")
    print("3. Если да - маппинг корректный!")
    print("4. Если нет - нужно искать правильные entry ID")

def main():
    """Основная функция"""
    print("🚀 ТЕСТИРОВАНИЕ GOOGLE FORMS ИНТЕГРАЦИИ")
    print("=" * 50)
    
    # 1. Показываем маппинг
    print("📋 ИСПОЛЬЗУЕМЫЙ МАППИНГ (из FB_PUBLIC_LOAD_DATA_):")
    mapping = {
        'email': 'emailAddress',
        'telegram_contact': 'entry.1244169801',
        'supplier_link': 'entry.1332237779', 
        'order_amount': 'entry.1319459294',
        'promo_code': 'entry.211960837',
        'terms_accepted': 'entry.363561279'
    }
    
    for field, entry in mapping.items():
        print(f"   {field:15} → {entry}")
    print()
    
    # 2. Создаем предзаполненную ссылку
    create_prefilled_test_link()
    
    # 3. Тестируем отправку
    print(f"\n🧪 АВТОМАТИЧЕСКИЙ ТЕСТ ОТПРАВКИ:")
    print("=" * 40)
    
    success = quick_test()
    
    print(f"\n🎯 РЕЗУЛЬТАТ ТЕСТИРОВАНИЯ:")
    if success:
        print("✅ Тест пройден! Google Forms интеграция работает")
        print("🚀 Можно запускать основное приложение: python app.py")
    else:
        print("❌ Тест не пройден")
        print("💡 Рекомендации:")
        print("   1. Проверьте предзаполненную ссылку выше")
        print("   2. Убедитесь, что все поля заполняются")
        print("   3. Если нет - проверьте entry ID в коде")

if __name__ == "__main__":
    main()
