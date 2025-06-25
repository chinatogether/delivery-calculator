import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    WebAppInfo, 
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    FSInputFile,
    BotCommand
)
from aiogram.types.web_app_data import WebAppData
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import os
import json
import logging
import psycopg2
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
API_TOKEN = os.getenv('API_TOKEN')
WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://china-together.ru')

# Путь к PDF файлу с тарифами
TARIFFS_PDF_PATH = "/home/chinatogether/xlsx-web/pdf-files/china_together_tariffs.pdf"

# Инициализация бота и хранилища состояний
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# FAQ данные
FAQ_DATA = {
    "💰 Минимальная сумма заказа": (
        "💰 <b>Минимальная сумма заказа</b>\n\n"
        "Минимальная сумма заказа составляет <b>3000 юаней</b> на одного поставщика."
    ),
    "⚖️ Минимальный вес": (
        "⚖️ <b>Минимальный вес к отправке</b>\n\n"
        "Минимальный вес для отправки составляет <b>10 кг/место</b>."
    ),
    "📦 Что такое место": (
        "📦 <b>Что такое «Место»?</b>\n\n"
        "Грузовое место — это одна единица для перевозки, состоящая из одной или нескольких коробок товара.\n\n"
        "💡 <b>Пример:</b> товар 200 единиц приезжает от поставщика в 2-х коробках, мы на складе делаем "
        "деревянный каркас, объединяя обе коробки. После чего получается одно грузовое место."
    ),
    "📦 Виды упаковки": (
        "📦 <b>Виды упаковки и стоимость</b>\n\n"
        "• <b>Мешок + скотч:</b> 3$/место\n"
        "• <b>Картонные уголки + мешок + скотч:</b> 8$/место\n"
        "• <b>Деревянный каркас + мешок + скотч:</b> 15$/место\n"
        "• <b>Палета</b> (деревянный поддон + водозащитная пленка + деревянный каркас + скотч): 30$/куб"
    ),
    "🕐 Сроки доставки": (
        "🕐 <b>Сроки доставки по категориям товаров</b>\n\n"
        "📌 <b>Обычные товары:</b>\n"
        "— Быстрое авто: снижена цена📉\n"
        "— Обычное авто: снижена цена📉\n"
        "<b>Сроки доставки:</b>\n"
        "— быстрое авто: 13–16 дней\n"
        "— обычное авто: 17–25 дней\n\n"
        "📌 <b>Одежда:</b>\n"
        "— Быстрое авто: снижена цена📉\n"
        "— Обычное авто: снижена цена📉\n"
        "<b>Сроки доставки:</b>\n"
        "— быстрое авто: 15–18 дней\n"
        "— обычное авто: 20–25 дней\n\n"
        "📌 <b>Обувь:</b>\n"
        "— Быстрое авто: снижена цена📉\n"
        "<b>Сроки доставки:</b>\n"
        "— быстрое авто: 12–15 дней"
    ),
    "📋 Страховка": (
        "📋 <b>Страхование товара</b>\n\n"
        "Страховка действует при потере, краже или частичной пропаже товара. Карго не возмещает стоимость за помятую упаковку.\n\n"
        "<b>Тарифы страхования:</b>\n"
        "• до 20$/кг — <b>1%</b> от стоимости\n"
        "• 20-30$/кг — <b>2%</b> от стоимости\n"
        "• 30-40$/кг — <b>3%</b> от стоимости\n"
        "• свыше 40$/кг — <b>обсуждается индивидуально</b>\n\n"
        "⚠️ <b>Запрещенные к перевозке товары:</b> порошковые вещества, легковоспламеняющиеся материалы, жидкости, табачные изделия, лекарственные препараты, режущие предметы, продукты питания."
    ),
    "💳 Как происходит оплата": (
        "💳 <b>Процесс оплаты</b>\n\n"
        "1️⃣ <b>Сначала оплачивается:</b>\n"
        "• Стоимость товара\n"
        "• Доставка по Китаю\n"
        "• Комиссия за выкуп\n\n"
        "2️⃣ <b>Доставка до России</b> оплачивается по приезду в Москву, по актуальному курсу."
    ),
    "💸 Способы оплаты": (
        "💸 <b>Доступные способы оплаты</b>\n\n"
        "• 🏦 Карты <b>Т-банк (Тинькофф)/ Альфабанк</b>\n"
        "• 📱 <b>СБП</b> (Система быстрых платежей)\n"
        "• 💰 <b>USDT</b>\n"
        "• 💸 <b>Наличными в Москве</b>"
    ),
    "🏢 Куда приезжает товар": (
        "🏢 <b>Место получения в Москве</b>\n\n"
        "Товар приезжает на <b>Южные ворота</b> в Москве."
    ),
    "🚛 Доставка в регионы": (
        "🚛 <b>Доставка в регионы</b>\n\n"
        "✅ Отправляем по <b>всем городам России</b>\n\n"
        "На Южных воротах в Москве представлены все популярные транспортные компании:\n"
        "• ЖелДорЭкспедиция\n"
        "• СДЭК\n"
        "• ПЭК\n"
        "• Деловые линии\n"
        "• Байкал\n"
        "• Мейджик и другие."
    ),
    "ℹ️ Дополнительная информация": (
        "ℹ️ <b>Дополнительная информация для заказчиков</b>\n\n"
        "<b>🔸 Что входит в нашу комиссию:</b>\n"
        "• Предварительный просчёт доставки до Москвы\n"
        "• Согласование цены и сроков отгрузки\n"
        "• Общение с поставщиком по вопросам товара\n"
        "• Размещение и оплата заказа\n"
        "• Контроль доставки по Китаю\n"
        "• Консолидация груза на нашем складе\n"
        "• Фотоотчёт и упаковка товара\n"
        "• Организация доставки до Москвы\n\n"
        "<b>🔸 Сроки:</b>\n"
        "• Отгрузка поставщиком: 2-7 дней\n"
        "• Доставка по Китаю: 1-5 дней\n"
        "• Согласованная отправка: до 8 вечера по китайскому времени\n\n"
        "<b>📺 Наш канал с полезной информацией:</b>\n"
        "🔗 <a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>"
    ),
    "📋 Правила получения груза": (
        "📋 <b>ПРИНИМАЙТЕ ГРУЗ ПРАВИЛЬНО!</b>\n\n"
        "❗ <b>Важно:</b> После получения груза недостаточно просто привезти товар домой и написать, что что-то не хватает.\n\n"
        "<b>🎥 Обязательно:</b>\n"
        "• Снимите <b>видео вскрытия груза</b>\n"
        "• Покажите внешнее состояние упаковки\n"
        "• Зафиксируйте весь процесс от вскрытия до пересчета товара\n\n"
        "<b>⚠️ При повреждении упаковки:</b>\n"
        "Обязательно зафиксируйте на видео при получении у транспортной компании и при наличии повреждения упаковки и следов вскрытия!\n\n"
        "<b>📅 График работы:</b> ПН-ПТ с 10:00 до 18:00 (МСК)\n\n"
        "Без видео - вопросы о возмещении или компенсации рассматриваться не будут."
    )
}
# Конфигурация базы данных
DB_CONFIG = {
            'dbname': os.getenv('DB_NAME', 'delivery_db'),
            'user': os.getenv('DB_USER'), 
            'password': os.getenv('DB_PASSWORD'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'connect_timeout': int(os.getenv('DB_TIMEOUT', '10'))
}

# Подключение к базе данных
def connect_to_db():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return None

# Функция для сохранения действий пользователя
def save_user_action(telegram_id, action, details=None):
    conn = connect_to_db()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO delivery_test.user_actions (telegram_user_id, action, details, created_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """, (telegram_id, action, json.dumps(details) if details else None))
        conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"Ошибка сохранения действия: {e}")
    finally:
        conn.close()

# Функция настройки команд бота
async def set_bot_commands():
    commands = [
        BotCommand(command="calculate", description="📊 Рассчитать доставку"),
        BotCommand(command="order", description="🚚 Заказать доставку"),
        BotCommand(command="tariffs", description="📋 Актуальные тарифы"),
        BotCommand(command="help", description="❓ Помощь"),
        BotCommand(command="faq", description="❓ Популярные вопросы"),
        BotCommand(command="restart", description="🔄 Перезапустить бота"),
        BotCommand(command="feedback", description="📝 Отзывы"),
        BotCommand(command="channel", description="📺 Наш канал")
    ]
    await bot.set_my_commands(commands)

# Создание reply-клавиатуры (дублирует команды бота)
def get_main_reply_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📊 Рассчитать доставку"),
                KeyboardButton(text="🚚 Заказать доставку")
            ],
            [
                KeyboardButton(text="📋 Актуальные тарифы"),
                KeyboardButton(text="❓ Помощь")
            ],
            [
                KeyboardButton(text="❓ Популярные вопросы"),
                KeyboardButton(text="🔄 Перезапустить бота")
            ],
            [
                KeyboardButton(text="📝 Отзывы"),
                KeyboardButton(text="📺 Наш канал")
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие или используйте меню бота..."
    )
    return keyboard

# Создание inline-клавиатуры для FAQ
def get_faq_inline_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Минимальная сумма заказа", callback_data="faq_min_order")],
        [InlineKeyboardButton(text="⚖️ Минимальный вес", callback_data="faq_min_weight")],
        [InlineKeyboardButton(text="📦 Что такое место", callback_data="faq_place")],
        [InlineKeyboardButton(text="📦 Виды упаковки", callback_data="faq_packaging")],
        [InlineKeyboardButton(text="🕐 Сроки доставки", callback_data="faq_delivery_times")],
        [InlineKeyboardButton(text="📋 Страховка", callback_data="faq_insurance")],
        [InlineKeyboardButton(text="💳 Как происходит оплата", callback_data="faq_payment")],
        [InlineKeyboardButton(text="💸 Способы оплаты", callback_data="faq_payment_methods")],
        [InlineKeyboardButton(text="🏢 Куда приезжает товар", callback_data="faq_delivery_location")],
        [InlineKeyboardButton(text="🚛 Доставка в регионы", callback_data="faq_regions")],
        [InlineKeyboardButton(text="ℹ️ Дополнительная информация", callback_data="faq_additional_info")],
        [InlineKeyboardButton(text="📋 Правила получения груза", callback_data="faq_cargo_rules")]
    ])
    return keyboard

# Создание inline-клавиатуры для веб-приложений
def get_webapp_inline_keyboard(user_id, username, action="calculate"):
    if action == "calculate":
        web_app_url = f"{WEB_APP_URL}/calculate?telegram_id={user_id}&username={username}"
        button_text = "📊 Открыть калькулятор"
    else:  # order
        web_app_url = f"{WEB_APP_URL}/order?telegram_id={user_id}&username={username}"
        button_text = "🚚 Открыть форму заказа"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=button_text, 
            web_app=WebAppInfo(url=web_app_url)
        )]
    ])
    return keyboard

# Функция для отправки PDF с тарифами
async def send_tariffs_pdf(message: types.Message, user_id: int):
    """Отправляет PDF файл с актуальными тарифами"""
    try:
        # Проверяем существование файла
        if not os.path.exists(TARIFFS_PDF_PATH):
            await message.reply(
                "❌ <b>Файл с тарифами не найден</b>\n\n"
                "Обратитесь к менеджеру для получения актуальных тарифов:",
                parse_mode="HTML"
            )
            save_user_action(user_id, "tariffs_file_not_found")
            return
        
        # Отправляем сообщение о загрузке
        loading_message = await message.reply(
            "📋 <b>Загружаю актуальные тарифы...</b>\n\n"
            "⏳ Подождите немного, файл готовится к отправке.",
            parse_mode="HTML"
        )
        
        # Создаем объект файла
        document = FSInputFile(TARIFFS_PDF_PATH)
        
        # Отправляем файл
        await message.reply_document(
            document=document,
            caption=(
                "📋 <b>Актуальные тарифы China Together</b>\n\n"
                "💡 В файле указаны:\n"
                "• Стоимость доставки по весовым категориям\n"
                "• Цены на упаковку (мешок, картон, дерево)\n"
                "• Тарифы быстрой и обычной доставки\n"
                "• Стоимость дополнительных услуг\n\n"
                f"📅 Дата: {datetime.now().strftime('%d.%m.%Y')}\n\n"
                "📺 Подписывайтесь на наш канал: <a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>"
            ),
            parse_mode="HTML"
        )
        
        # Удаляем сообщение о загрузке
        await loading_message.delete()
        
        # Сохраняем действие в БД
        save_user_action(user_id, "tariffs_downloaded", {
            "file_path": TARIFFS_PDF_PATH,
            "file_size": os.path.getsize(TARIFFS_PDF_PATH)
        })
        
        logger.info(f"Пользователь {user_id} скачал тарифы")
        
    except Exception as e:
        logger.error(f"Ошибка отправки PDF тарифов: {e}")
        await message.reply(
            "❌ <b>Произошла ошибка при отправке тарифов</b>\n\n"
            "Попробуйте позже или обратитесь к менеджеру:",
            parse_mode="HTML"
        )
        save_user_action(user_id, "tariffs_send_error", {"error": str(e)})

# Функция для умных ответов ИИ
def get_smart_response(message_text):
    text = message_text.lower()
    
    # Приветствия
    if any(word in text for word in ['привет', 'здравствуй', 'добро пожаловать', 'hi', 'hello']):
        return ("👋 Привет! Я умный помощник China Together - ваш надежный партнер для доставки из Китая! "
                "Помогу рассчитать стоимость, оформить заказ и ответить на любые вопросы.\n\n"
                "📺 Подписывайтесь на наш канал: <a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>\n\n"
                "Используйте кнопки ниже для быстрого доступа к функциям!")
    
    # Вопросы о доставке и расчетах
    elif any(word in text for word in ['доставка', 'расчет', 'стоимость', 'цена',  'калькулятор']):
        return ("📊 <b>Расчет стоимости доставки:</b>\n\n"
                "Для точного расчета нажмите кнопку '📊 Рассчитать доставку'. Вам нужно указать:\n"
                "• 📦 Категорию товара (обычные, текстиль, одежда, обувь)\n"
                "• ⚖️ Вес и размеры каждой коробки\n"
                "• 💰 Стоимость товара\n"
                "• 📦 Количество коробок\n\n"
                "У нас 3 варианта упаковки: мешок, картонные уголки, деревянный каркас.\n"
                "2 варианта доставки: быстрая (12-15 дней) и обычная (15-20 дней).\n\n"
                "📋 Для просмотра всех тарифов нажмите кнопку '📋 Актуальные тарифы'\n"
                "📺 Наш канал: <a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>")
    
    # Вопросы о тарифах
    elif any(word in text for word in ['тариф', 'тарифы', 'прайс', 'цены', 'стоимость']):
        return ("📋 <b>Актуальные тарифы:</b>\n\n"
                "Для получения полного прайс-листа нажмите кнопку '📋 Актуальные тарифы' - вам будет отправлен PDF файл со всеми актуальными ценами.\n\n"
                "💡 В файле вы найдете:\n"
                "• Тарифы доставки по весу\n"
                "• Стоимость упаковки\n"
                "• Цены дополнительных услуг\n\n"
                "📺 Также подписывайтесь на наш канал: <a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>")
    
    # Благодарности
    elif any(word in text for word in ['спасибо', 'благодар', 'thanks', 'отлично', 'хорошо']):
        return ("😊 Пожалуйста! Рады помочь! China Together всегда к вашим услугам. "
                "Если есть еще вопросы - обращайтесь. Удачных покупок в Китае! 🇨🇳\n\n"
                "📺 Не забудьте подписаться на наш канал: <a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>")
    
    # Общие вопросы
    else:
        return ("🤔 <b>Я готов помочь!</b>\n\n"
                "🎯 <b>Мои возможности:</b>\n"
                "📊 Расчет стоимости доставки\n"
                "🚚 Оформление заказов и выкуп товаров\n"
                "📋 Предоставление актуальных тарифов\n"
                "❓ Ответы на популярные вопросы\n"
                "❓ Справка и помощь\n\n"
                "📺 Наш канал с полезной информацией: <a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>\n\n"
                "Используйте кнопки ниже или меню бота для быстрого доступа к функциям!")

# Функция очистки истории чата
async def clear_chat_history(message: types.Message, user_id: int):
    """Попытка удалить последние сообщения в чате"""
    try:
        # Удаляем последние 20 сообщений (если возможно)
        for i in range(1000):
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id - i)
            except:
                break  # Если не можем удалить сообщение, прекращаем
    except Exception as e:
        logger.warning(f"Не удалось очистить историю чата для пользователя {user_id}: {e}")

# Команда /start
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    first_name = message.from_user.first_name or ""
    
    save_user_action(user_id, "start_command", {
        "username": username,
        "first_name": first_name
    })
    
    keyboard = get_main_reply_keyboard()
    
    await message.reply(
        f"🚀 <b>Добро пожаловать, {first_name}!</b>\n\n"
        "Я умный помощник China Together - помогу рассчитать доставку из Китая и оформить заказ!\n\n"
        "🎯 <b>Что я умею:</b>\n"
        "• 📊 Точный расчет стоимости доставки\n"
        "• 🚚 Оформление заявок на выкуп товаров\n"
        "• 📋 Предоставление актуальных тарифов\n"
        "• 💬 Ответы на популярные вопросы\n\n"
        "📺 <b>Подписывайтесь на наш канал:</b> <a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>\n\n"
        "💡 <b>Используйте кнопки ниже или меню бота для быстрого доступа к функциям!</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# Команда /calculate - Рассчитать доставку
@dp.message(Command("calculate"))
async def calculate_delivery(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    save_user_action(user_id, "calculate_command")
    
    keyboard = get_webapp_inline_keyboard(user_id, username, "calculate")
    await message.reply(
        "📊 <b>Калькулятор доставки</b>\n\n"
        "Нажмите кнопку ниже, чтобы открыть калькулятор и самостоятельно рассчитать стоимость доставки вашего груза из Китая.\n",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# Команда /order - Заказать доставку
@dp.message(Command("order"))
async def order_delivery(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    save_user_action(user_id, "order_command")
    
    keyboard = get_webapp_inline_keyboard(user_id, username, "order")
    await message.reply(
        "🚚 <b>Заказ доставки</b>\n\n"
        "Нажмите кнопку ниже, чтобы оформить заявку на выкуп и доставку товаров из Китая.\n\n",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# Команда /tariffs - Актуальные тарифы
@dp.message(Command("tariffs"))
async def get_tariffs(message: types.Message):
    user_id = message.from_user.id
    save_user_action(user_id, "tariffs_command")
    await send_tariffs_pdf(message, user_id)

# Команда /help - Помощь
@dp.message(Command("help"))
async def help_command(message: types.Message):
    user_id = message.from_user.id
    save_user_action(user_id, "help_command")
    
    help_text = (
        "<b>❓ Как пользоваться сервисом:</b>\n\n"
        "<b>📊 Расчет доставки (/calculate):</b>\n"
        "1️⃣ Выберите команду в меню\n"
        "2️⃣ Заполните все поля формы\n"
        "3️⃣ Получите детальный расчет\n\n"
        "<b>🚚 Заказ доставки (/order):</b>\n"
        "1️⃣ Выберите команду в меню\n"
        "2️⃣ Заполните заявку\n"
        "3️⃣ Менеджер свяжется с вами\n\n"
        "<b>📋 Актуальные тарифы (/tariffs):</b>\n"
        "Получите PDF с полным прайс-листом\n\n"
        "<b>❓ Популярные вопросы (/faq):</b>\n"
        "Быстрые ответы на частые вопросы\n\n"
        "<b>🔄 Перезапуск (/restart):</b>\n"
        "Очистить чат и начать сначала\n\n"
        "<b>📺 Наш канал (/channel):</b>\n"
        "Полезная информация и новости\n\n"
        "📺 <b>Подписывайтесь:</b> <a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>\n\n"
        "💡 <b>Все команды доступны через меню бота!</b>"
    )
    await message.reply(help_text, parse_mode="HTML")

# Команда /faq - Популярные вопросы
@dp.message(Command("faq"))
async def faq_command(message: types.Message):
    user_id = message.from_user.id
    save_user_action(user_id, "faq_command")
    
    keyboard = get_faq_inline_keyboard()
    await message.reply(
        "❓ <b>Популярные вопросы</b>\n\n"
        "Выберите интересующий вас вопрос:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# Команда /feedback - Отзывы    
@dp.message(Command("feedback"))
async def feedback_command(message: types.Message):
    user_id = message.from_user.id
    save_user_action(user_id, "feedback_command")
    await message.reply(
        "📝 <b>Отзывы наших клиентов</b>\n\n"
        "🔗 Перейдите по ссылке, чтобы увидеть отзывы:\n"
        "<a href='https://t.me/feedbacktogetherchina'>https://t.me/feedbacktogetherchina</a>\n\n"
        "📺 <b>Также подписывайтесь на наш канал:</b>\n"
        "<a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>", 
        parse_mode="HTML"
    )

# Команда /channel - Наш канал
@dp.message(Command("channel"))
async def channel_command(message: types.Message):
    user_id = message.from_user.id
    save_user_action(user_id, "channel_command")
    await message.reply(
        "📺 <b>Наш официальный канал</b>\n\n"
        "В нашем канале вы найдете:\n"
        "• 📰 Новости компании\n"
        "• 💡 Полезные советы по покупкам в Китае\n"
        "• 📊 Актуальные тарифы и акции\n"
        "• 🎯 Лайфхаки для экономии на доставке\n\n"
        "🔗 <b>Подписывайтесь:</b> <a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>", 
        parse_mode="HTML"
    )

# Команда /restart - Перезапустить бота
@dp.message(Command("restart"))
async def restart_bot(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    first_name = message.from_user.first_name or ""
    
    save_user_action(user_id, "restart_command")
    
    # Пытаемся очистить историю чата
    await clear_chat_history(message, user_id)
    
    keyboard = get_main_reply_keyboard()
    
    await message.reply(
        f"🔄 <b>Бот перезапущен!</b>\n\n"
        f"Привет снова, {first_name}! История чата очищена.\n\n"
        "🚀 <b>China Together</b> - ваш надежный партнер для доставки из Китая!\n\n"
        "💡 <b>Используйте кнопки ниже или меню бота для быстрого доступа к функциям:</b>\n"
        "📊 Рассчитать доставку\n"
        "🚚 Заказать доставку\n"
        "📋 Актуальные тарифы\n"
        "❓ Популярные вопросы\n\n"
        "📺 <b>Наш канал:</b> <a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>\n\n"
        "Чем могу помочь?",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# Обработка reply-кнопок - работают как команды
@dp.message(F.text.in_([
    "📊 Рассчитать доставку", 
    "🚚 Заказать доставку", 
    "📋 Актуальные тарифы",
    "❓ Помощь",
    "❓ Популярные вопросы",
    "🔄 Перезапустить бота",
    "📝 Отзывы",
    "📺 Наш канал"
]))
async def handle_reply_buttons(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    text = message.text
    
    save_user_action(user_id, "reply_button", {"button": text})
    
    if text == "📊 Рассчитать доставку":
        await calculate_delivery(message)
    
    elif text == "🚚 Заказать доставку":
        await order_delivery(message)
    
    elif text == "📋 Актуальные тарифы":
        await get_tariffs(message)
    
    elif text == "❓ Помощь":
        await help_command(message)
    
    elif text == "❓ Популярные вопросы":
        await faq_command(message)
    
    elif text == "🔄 Перезапустить бота":
        await restart_bot(message)
    
    elif text == "📝 Отзывы":
        await feedback_command(message)
    
    elif text == "📺 Наш канал":
        await channel_command(message)

# Обработка текстовых сообщений (кроме reply-кнопок)
@dp.message(F.text)
async def handle_text_message(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    text = message.text
    
    # Пропускаем обработку, если это текст reply-кнопки
    button_texts = [
        "📊 Рассчитать доставку", "🚚 Заказать доставку", "📋 Актуальные тарифы",
        "❓ Помощь", "❓ Популярные вопросы", "🔄 Перезапустить бота", 
        "📝 Отзывы", "📺 Наш канал"
    ]
    
    if text in button_texts:
        return
    
    save_user_action(user_id, "text_message", {"text": text})
    
    smart_response = get_smart_response(text)
    keyboard = get_main_reply_keyboard()
    
    await message.reply(
        smart_response,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# Обработка данных от веб-приложения
@dp.message(F.web_app_data)
async def handle_web_app_data(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
        user_id = message.from_user.id
        username = message.from_user.username or f"user_{user_id}"
        action = data.get('action', '')
        
        save_user_action(user_id, f"webapp_{action}", data)
        
        if action == 'calculation_completed':
            await handle_calculation_completed(message, data, user_id, username)
        elif action == 'purchase_request_submitted':
            await handle_purchase_request_submitted(message, data, user_id, username)
        else:
            await message.reply("✅ Данные получены и обработаны!")
            
    except Exception as e:
        logger.error(f"Ошибка обработки данных веб-приложения: {e}")
        await message.reply("❌ Произошла ошибка при обработке данных.")

# Обработка завершенного расчета
async def handle_calculation_completed(message, data, user_id, username):
    keyboard = get_webapp_inline_keyboard(user_id, username, "order")
    await message.reply(
        "✅ <b>Расчет успешно выполнен!</b>\n\n"
        f"📊 Категория: {data.get('category', 'Не указано')}\n"
        f"⚖️ Общий вес: {data.get('totalWeight', 0)} кг\n"
        f"💰 Стоимость товара: ${data.get('productCost', 0)}\n\n"
        "Что хотите сделать дальше?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🚚 Заказать доставку", 
                web_app=WebAppInfo(url=f"{WEB_APP_URL}/order?telegram_id={user_id}&username={username}")
            )],
            [InlineKeyboardButton(text="🔄 Новый расчет", callback_data="new_calculation")]
        ]),
        parse_mode="HTML"
    )

# Обработка отправленной заявки
async def handle_purchase_request_submitted(message, data, user_id, username):
    await message.reply(
        "✅ <b>Заявка успешно отправлена!</b>\n\n"
        f"💰 Сумма заказа: {data.get('order_amount', '')}\n"
        f"📱 Telegram: {data.get('telegram_contact', '')}\n\n"
        "🕐 <b>Менеджер свяжется с вами в рабочее время:</b>\n"
        "ПН–ПТ с 10:00 до 18:00 по московскому времени\n\n"
        "📺 <b>Следите за новостями в нашем канале:</b>\n"
        "<a href='https://t.me/Togetherchina'>t.me/Togetherchina</a>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 Мои заявки", callback_data="my_requests")]
        ]),
        parse_mode="HTML"
    )

# Обработка callback-запросов
@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or f"user_{user_id}"
    
    if callback.data == "new_calculation":
        keyboard = get_webapp_inline_keyboard(user_id, username, "calculate")
        await callback.message.answer(
            "🔄 Начните новый расчет доставки:",
            reply_markup=keyboard
        )
        save_user_action(user_id, "new_calculation")
    
    elif callback.data == "my_requests":
        await handle_my_requests(callback.message, user_id)
    
    elif callback.data.startswith("faq_"):
        faq_key_map = {
            "faq_min_order": "💰 Минимальная сумма заказа",
            "faq_min_weight": "⚖️ Минимальный вес",
            "faq_place": "📦 Что такое место",
            "faq_packaging": "📦 Виды упаковки",
            "faq_delivery_times": "🕐 Сроки доставки",
            "faq_insurance": "📋 Страховка",
            "faq_payment": "💳 Как происходит оплата",
            "faq_payment_methods": "💸 Способы оплаты",
            "faq_delivery_location": "🏢 Куда приезжает товар",
            "faq_regions": "🚛 Доставка в регионы",
            "faq_additional_info": "ℹ️ Дополнительная информация",
            "faq_cargo_rules": "📋 Правила получения груза"
        }
        
        faq_key = faq_key_map.get(callback.data)
        if faq_key and faq_key in FAQ_DATA:
            back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К вопросам", callback_data="back_to_faq")]
            ])
            await callback.message.edit_text(
                FAQ_DATA[faq_key],
                reply_markup=back_keyboard,
                parse_mode="HTML"
            )
            save_user_action(user_id, "faq_viewed", {"question": faq_key})
    
    elif callback.data == "back_to_faq":
        keyboard = get_faq_inline_keyboard()
        await callback.message.edit_text(
            "❓ <b>Популярные вопросы</b>\n\n"
            "Выберите интересующий вас вопрос:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    await callback.answer()

# Вспомогательные функции
async def handle_my_requests(message, user_id):
    requests = get_user_purchase_requests(user_id)
    if requests:
        requests_text = "<b>📂 Ваши заявки на выкуп:</b>\n\n"
        for i, req in enumerate(requests[:5], 1):
            status_emoji = {
                'new': '🆕', 'in_review': '👀', 'approved': '✅',
                'rejected': '❌', 'completed': '🎉'
            }.get(req['status'], '❓')
            
            requests_text += (
                f"{i}. {status_emoji} {req['created_at'][:16]}\n"
                f"   💰 Сумма: {req['order_amount']}\n"
                f"   📧 Email: {req['email']}\n\n"
            )
        await message.reply(requests_text, parse_mode="HTML")
    else:
        username = message.from_user.username or f"user_{user_id}"
        keyboard = get_webapp_inline_keyboard(user_id, username, "order")
        await message.reply(
            "📭 У вас пока нет заявок на выкуп.\n\n"
            "Хотите оформить заявку?",
            reply_markup=keyboard
        )
    save_user_action(user_id, "view_requests")

# Функция получения заявок пользователя на выкуп
def get_user_purchase_requests(telegram_id):
    conn = connect_to_db()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pr.*, u.telegram_id
            FROM delivery_test.purchase_requests pr
            JOIN delivery_test.telegram_users u ON pr.telegram_user_id = u.id
            WHERE u.telegram_id = %s
            ORDER BY pr.created_at DESC
            LIMIT 10
        """, (str(telegram_id),))
        
        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            record['created_at'] = record['created_at'].strftime('%Y-%m-%d %H:%M')
            results.append(record)
        
        cursor.close()
        return results
    except Exception as e:
        logger.error(f"Ошибка получения заявок: {e}")
        return []
    finally:
        conn.close()

# Удаление webhook
async def delete_webhook():
    await bot.delete_webhook()

# Запуск бота
async def main():
    await delete_webhook()
    await set_bot_commands()  # Устанавливаем команды бота
    logger.info("🤖 China Together Bot запущен!")
    logger.info(f"🌐 Web App URL: {WEB_APP_URL}")
    logger.info(f"📋 Tariffs PDF Path: {TARIFFS_PDF_PATH}")
    logger.info("📋 Команды бота установлены!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
