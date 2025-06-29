# 🚀 China Together Order Manager

Современная система управления заказами и доставками из Китая с веб-интерфейсом для менеджеров и директора.

## 📋 Описание

Order Manager - это комплексная система для управления заявками на доставку, пользователями и расчетами стоимости доставки из Китая. Система предоставляет удобный веб-интерфейс для менеджеров и расширенную аналитику для директора.

## ✨ Основные возможности

### 🔐 Авторизация и роли
- **Авторизация по email** (поддержка Яндекс и других доменов)
- **Роли пользователей**: Директор и Менеджер
- **Разграничение доступа** к функциям

### 📊 Управление заявками
- **Статусы заявок**: Новый → В работе → Рассчитана доставка → В пути → Доставлено
- **Фильтрация и поиск** по всем параметрам
- **История изменений** статусов с комментариями
- **Назначение менеджеров** на заявки
- **Экспорт данных** в Excel

### 👥 Управление пользователями
- **База клиентов** с полными контактными данными
- **Расчеты доставки** прямо из панели менеджера
- **Редактирование данных** пользователей
- **Генерация счет-фактур**

### 💱 Управление курсом валют
- **Ручное обновление** курса юань/доллар
- **График изменений** с историей
- **Анализ влияния** на расчеты доставки

### ⚙️ Настройки системы
- **Загрузка Excel файлов** с параметрами доставки
- **Автоматическая генерация PDF** с тарифами
- **Мониторинг состояния** системы
- **Резервное копирование**

### 📈 Аналитика (для директора)
- **Воронка конверсии** пользователей
- **Производительность менеджеров**
- **Статистика по доставкам**
- **Графики активности**

## 🛠️ Технические требования

- **Python 3.8+**
- **PostgreSQL 12+**
- **Flask 2.3+**
- **4GB RAM минимум**
- **Linux/Unix сервер**

## 📦 Установка

### 1. Клонирование репозитория
```bash
git clone https://github.com/yourusername/order-manager.git
cd order-manager
```

### 2. Создание виртуального окружения
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

### 3. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения
```bash
cp .env.example .env
# Отредактируйте .env файл с вашими настройками
```

### 5. Создание папок
```bash
mkdir -p logs uploads exports
chmod 755 logs uploads exports
```

### 6. Инициализация базы данных
```bash
python -c "from app import init_management_tables; init_management_tables()"
```

### 7. Запуск приложения
```bash
# Для разработки
python app.py

# Для продакшена
chmod +x run.sh
./run.sh
```

## 🎯 Быстрый старт

### Авторизованные пользователи по умолчанию:
- **director@chinatogether.ru** - Директор (полный доступ)
- **manager1@chinatogether.ru** - Менеджер
- **manager2@chinatogether.ru** - Менеджер

### Первые шаги:
1. Откройте http://localhost:8060
2. Войдите с email директора
3. Загрузите Excel файл с параметрами в "Настройки"
4. Установите курс валют
5. Начните работу с заявками

## 📚 API Endpoints

### Аутентификация
- `POST /login` - Вход в систему
- `GET /logout` - Выход из системы

### Заявки
- `GET /orders` - Список заявок
- `POST /api/orders/{id}/status` - Изменение статуса
- `GET /api/export/orders` - Экспорт в Excel

### Пользователи
- `GET /users` - Список пользователей
- `GET /api/export/users` - Экспорт в Excel

### Курс валют
- `GET /exchange-rate` - Управление курсом
- `POST /api/exchange-rate` - Обновление курса

### Настройки
- `GET /settings` - Настройки системы
- `POST /upload` - Загрузка Excel файлов

## 🎨 Дизайн

Система использует современный дизайн с фирменными цветами China Together:
- **Основной**: #1a365d (темно-синий)
- **Вторичный**: #2c5aa0 (синий)
- **Акцент**: #3182ce (светло-синий)
- **Адаптивная верстка** для всех устройств

## 🔧 Конфигурация

### Основные настройки в .env:
```bash
# Порт приложения
APP_PORT=8060

# База данных
DB_NAME=delivery_db
DB_USER=your_user
DB_PASSWORD=your_password

# Пути к файлам
UPLOAD_FOLDER=/path/to/uploads
PDF_FOLDER=/path/to/exports
```

## 🚀 Деплой на сервер

### С использованием systemd:
```bash
# Создать файл /etc/systemd/system/order-manager.service
sudo nano /etc/systemd/system/order-manager.service

# Добавить содержимое сервиса
[Unit]
Description=China Together Order Manager
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/order-manager
Environment=PATH=/path/to/order-manager/venv/bin
ExecStart=/path/to/order-manager/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target

# Запустить сервис
sudo systemctl enable order-manager
sudo systemctl start order-manager
```

### С использованием nginx (обратный прокси):
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8060;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 📝 Логирование

Приложение ведет подробные логи в папке `logs/`:
- `application.log` - Общие логи приложения
- `auth.log` - Логи авторизации
- `actions.log` - Логи действий пользователей

## 🔒 Безопасность

- **HTTPS обязателен** для продакшена
- **Ограничение доступа** по email доменам
- **Логирование всех действий**
- **Защита от CSRF атак**
- **Валидация загружаемых файлов**

## 🤝 Участие в разработке

1. Форкните репозиторий
2. Создайте ветку для новой функции
3. Внесите изменения
4. Добавьте тесты
5. Создайте Pull Request

## 📞 Поддержка

По вопросам использования и разработки:
- **Email**: support@chinatogether.ru
- **Telegram**: @ChinaTogetherSupport
- **Issues**: GitHub Issues

## 📄 Лицензия

Этот проект разработан специально для China Together и является частной разработкой.

---

**China Together Order Manager** - Современное решение для управления заказами доставки из Китая 🇨🇳 → 🇷🇺
