#!/bin/bash

echo "🚀 Развертывание Order Manager..."

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден"
    exit 1
fi

# Создание виртуального окружения
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

# Активация виртуального окружения
source venv/bin/activate

# Установка зависимостей
echo "📚 Установка зависимостей..."
pip install -r requirements.txt

# Проверка .env файла
if [ ! -f ".env" ]; then
    echo "⚠️ Файл .env не найден! Скопируйте .env.example в .env"
    exit 1
fi

# Инициализация БД
echo "🗄️ Инициализация базы данных..."
python scripts/init_db.py

# Создание директорий
mkdir -p logs uploads backups

echo "✅ Развертывание завершено!"
echo "🌐 Запустите приложение: python app.py"
