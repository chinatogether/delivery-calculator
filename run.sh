#!/bin/bash

# Скрипт запуска China Together Order Manager
# Использование: ./run.sh [start|stop|restart|status]

APP_NAME="order-manager"
APP_DIR="/home/chinatogether/order-manager"
VENV_DIR="$APP_DIR/venv"
PID_FILE="$APP_DIR/app.pid"
LOG_FILE="$APP_DIR/logs/application.log"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция логирования
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Проверка существования виртуального окружения
check_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        error "Виртуальное окружение не найдено в $VENV_DIR"
        log "Создание виртуального окружения..."
        python3 -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"
        pip install -r requirements.txt
        success "Виртуальное окружение создано"
    fi
}

# Создание необходимых директорий
create_dirs() {
    log "Создание необходимых директорий..."
    mkdir -p "$APP_DIR/logs"
    mkdir -p "$APP_DIR/uploads"
    mkdir -p "$APP_DIR/exports"
    chmod 755 "$APP_DIR/logs" "$APP_DIR/uploads" "$APP_DIR/exports"
}

# Функция запуска приложения
start() {
    log "Запуск $APP_NAME..."
    
    # Проверяем, не запущено ли уже приложение
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            warning "Приложение уже запущено (PID: $PID)"
            return 1
        else
            log "Удаление устаревшего PID файла"
            rm -f "$PID_FILE"
        fi
    fi
    
    # Проверяем виртуальное окружение
    check_venv
    
    # Создаем директории
    create_dirs
    
    # Переходим в директорию приложения
    cd "$APP_DIR"
    
    # Активируем виртуальное окружение
    source "$VENV_DIR/bin/activate"
    
    # Проверяем переменные окружения
    if [ ! -f ".env" ]; then
        warning "Файл .env не найден, используем значения по умолчанию"
        if [ -f ".env.example" ]; then
            log "Создание .env из .env.example"
            cp .env.example .env
        fi
    fi
    
    # Запускаем приложение в фоне
    log "Запуск Flask приложения..."
    nohup python app.py > "$LOG_FILE" 2>&1 &
    
    # Сохраняем PID
    echo $! > "$PID_FILE"
    
    # Ждем немного для проверки запуска
    sleep 3
    
    # Проверяем, что процесс запустился
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        success "$APP_NAME запущен (PID: $PID)"
        log "Логи доступны в: $LOG_FILE"
        log "Приложение доступно по адресу: http://localhost:8060"
    else
        error "Не удалось запустить приложение"
        log "Проверьте логи: $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

# Функция остановки приложения
stop() {
    log "Остановка $APP_NAME..."
    
    if [ ! -f "$PID_FILE" ]; then
        warning "PID файл не найден, приложение не запущено"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    
    if ps -p $PID > /dev/null 2>&1; then
        log "Отправка сигнала TERM процессу $PID"
        kill $PID
        
        # Ждем завершения процесса
        for i in {1..10}; do
            if ! ps -p $PID > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        
        # Если процесс все еще работает, принудительно завершаем
        if ps -p $PID > /dev/null 2>&1; then
            warning "Принудительное завершение процесса"
            kill -9 $PID
        fi
        
        rm -f "$PID_FILE"
        success "$APP_NAME остановлен"
    else
        warning "Процесс с PID $PID не найден"
        rm -f "$PID_FILE"
    fi
}

# Функция перезапуска
restart() {
    log "Перезапуск $APP_NAME..."
    stop
    sleep 2
    start
}

# Функция проверки статуса
status() {
    log "Проверка статуса $APP_NAME..."
    
    if [ ! -f "$PID_FILE" ]; then
        echo -e "Статус: ${RED}ОСТАНОВЛЕН${NC}"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "Статус: ${GREEN}ЗАПУЩЕН${NC}"
        echo "PID: $PID"
        echo "Время запуска: $(ps -o lstart= -p $PID)"
        echo "Использование памяти: $(ps -o %mem= -p $PID | tr -d ' ')%"
        echo "Использование CPU: $(ps -o %cpu= -p $PID | tr -d ' ')%"
        
        # Проверяем доступность порта
        if netstat -tuln | grep -q ":8060 "; then
            echo -e "Порт 8060: ${GREEN}ОТКРЫТ${NC}"
        else
            echo -e "Порт 8060: ${RED}ЗАКРЫТ${NC}"
        fi
        
        # Показываем последние логи
        if [ -f "$LOG_FILE" ]; then
            echo ""
            echo "Последние записи в логах:"
            tail -5 "$LOG_FILE"
        fi
    else
        echo -e "Статус: ${RED}ОСТАНОВЛЕН${NC} (PID файл существует, но процесс не найден)"
        rm -f "$PID_FILE"
        return 1
    fi
}

# Функция показа логов
logs() {
    if [ -f "$LOG_FILE" ]; then
        log "Показ логов $APP_NAME..."
        tail -f "$LOG_FILE"
    else
        error "Файл логов не найден: $LOG_FILE"
    fi
}

# Функция установки зависимостей
install() {
    log "Установка зависимостей..."
    check_venv
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    pip install -r requirements.txt --upgrade
    success "Зависимости установлены"
}

# Функция обновления приложения
update() {
    log "Обновление $APP_NAME..."
    cd "$APP_DIR"
    
    # Останавливаем если запущено
    if [ -f "$PID_FILE" ]; then
        stop
        NEED_RESTART=true
    fi
    
    # Обновляем код из git
    if [ -d ".git" ]; then
        log "Обновление из git репозитория..."
        git pull origin main
    fi
    
    # Обновляем зависимости
    install
    
    # Запускаем если было запущено
    if [ "$NEED_RESTART" = true ]; then
        start
    fi
    
    success "Обновление завершено"
}

# Функция резервного копирования
backup() {
    log "Создание резервной копии..."
    
    BACKUP_DIR="$APP_DIR/backups"
    BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/backup_$BACKUP_DATE.tar.gz"
    
    mkdir -p "$BACKUP_DIR"
    
    # Создаем архив
    tar -czf "$BACKUP_FILE" \
        --exclude="venv" \
        --exclude="logs" \
        --exclude="backups" \
        --exclude="__pycache__" \
        -C "$APP_DIR/.." \
        "$(basename "$APP_DIR")"
    
    success "Резервная копия создана: $BACKUP_FILE"
}

# Обработка аргументов командной строки
case "${1:-}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    install)
        install
        ;;
    update)
        update
        ;;
    backup)
        backup
        ;;
    *)
        echo "Использование: $0 {start|stop|restart|status|logs|install|update|backup}"
        echo ""
        echo "Команды:"
        echo "  start    - Запустить приложение"
        echo "  stop     - Остановить приложение"
        echo "  restart  - Перезапустить приложение"
        echo "  status   - Показать статус приложения"
        echo "  logs     - Показать логи в реальном времени"
        echo "  install  - Установить/обновить зависимости"
        echo "  update   - Обновить приложение из git"
        echo "  backup   - Создать резервную копию"
        exit 1
        ;;
esac
