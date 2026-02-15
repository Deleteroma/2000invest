import os
import sys
import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, \
    ContextTypes, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для разговора
(MAIN_MENU, SELECT_CAR, ADD_CAR, EDIT_CAR, DELETE_CAR,
 ADD_EXPENSE, SET_TOTAL_INVESTMENT, DELETE_EXPENSE,
 SELECT_SERVICE_TYPE, SET_LAST_OIL_CHANGE, ADD_SERVICE) = range(11)

# Конфигурация - читаем токен из переменных окружения
BOT_TOKEN = "8477674042:AAEOFIOLskgqEfOzFzD2zSDyIvA8vBLyV-Q"
if not BOT_TOKEN:
    logger.error("❌ Токен бота не найден!")
    sys.exit(1)

logger.info("✅ Токен бота успешно загружен")


class CarFinanceBot:
    def __init__(self):
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()

        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                registered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица автомобилей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                brand TEXT,
                model TEXT,
                year INTEGER,
                license_plate TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Таблица для расходов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_id INTEGER,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                mileage INTEGER,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (car_id) REFERENCES cars (id) ON DELETE CASCADE
            )
        ''')

        # Таблица для замены масла
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS oil_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_id INTEGER,
                mileage INTEGER NOT NULL,
                oil_type TEXT,
                next_change_mileage INTEGER,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (car_id) REFERENCES cars (id) ON DELETE CASCADE
            )
        ''')

        conn.commit()
        conn.close()

    def register_user(self, user_id, username, first_name, last_name):
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, last_name)
            )
            conn.commit()
        conn.close()

    def add_car(self, user_id, name, brand="", model="", year=None, license_plate=""):
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO cars (user_id, name, brand, model, year, license_plate) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, brand, model, year, license_plate)
        )
        car_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return car_id

    def get_user_cars(self, user_id):
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, brand, model, year, license_plate FROM cars WHERE user_id = ? ORDER BY created_date",
            (user_id,)
        )
        cars = cursor.fetchall()
        conn.close()
        return cars


# Создаем экземпляр бота
bot = CarFinanceBot()
user_car_selection = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start"""
    user = update.effective_user
    bot.register_user(user.id, user.username, user.first_name, user.last_name)

    cars = bot.get_user_cars(user.id)

    if not cars:
        keyboard = [[InlineKeyboardButton("➕ Добавить автомобиль", callback_data='add_car')]]
        await update.message.reply_text(
            f"👋 Здравствуйте, {user.first_name}!\n\n🚗 Добавьте первый автомобиль:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADD_CAR

    keyboard = []
    for car_id, name, brand, model, year, plate in cars:
        car_name = f"{brand} {model}" if brand and model else name
        keyboard.append([InlineKeyboardButton(f"🚗 {car_name}", callback_data=f'select_car_{car_id}')])

    keyboard.append([InlineKeyboardButton("➕ Добавить авто", callback_data='add_car')])

    await update.message.reply_text(
        "🚗 Выберите автомобиль:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_CAR


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()

    if query.data == 'add_car':
        await query.message.edit_text(
            "➕ Введите название автомобиля:\nПример: Toyota Camry"
        )
        return ADD_CAR

    elif query.data.startswith('select_car_'):
        car_id = int(query.data.replace('select_car_', ''))
        user_car_selection[update.effective_user.id] = car_id

        keyboard = [
            [InlineKeyboardButton("💰 Добавить расход", callback_data='add_expense')],
            [InlineKeyboardButton("🛢 Замена масла", callback_data='oil_change')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_cars')]
        ]

        await query.message.edit_text(
            "🚗 Меню автомобиля:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MAIN_MENU

    elif query.data == 'back_to_cars':
        return await show_car_list(update, context)

    elif query.data == 'add_expense':
        await query.message.edit_text(
            "💰 Введите расход в формате:\nСумма Описание, Пробег\nПример: 2500 Замена масла, 15000"
        )
        return ADD_EXPENSE

    elif query.data == 'oil_change':
        await query.message.edit_text(
            "🛢 Введите замену масла:\nПробег, Тип масла\nПример: 15000, Mobil 5W30"
        )
        return SET_LAST_OIL_CHANGE

    return MAIN_MENU


async def show_car_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать список автомобилей"""
    user_id = update.effective_user.id
    cars = bot.get_user_cars(user_id)

    keyboard = []
    for car_id, name, brand, model, year, plate in cars:
        car_name = f"{brand} {model}" if brand and model else name
        keyboard.append([InlineKeyboardButton(f"🚗 {car_name}", callback_data=f'select_car_{car_id}')])

    keyboard.append([InlineKeyboardButton("➕ Добавить авто", callback_data='add_car')])

    if update.callback_query:
        await update.callback_query.message.edit_text(
            "🚗 Выберите автомобиль:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            "🚗 Выберите автомобиль:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    return SELECT_CAR


async def handle_car_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода автомобиля"""
    user_id = update.effective_user.id
    car_name = update.message.text.strip()

    bot.add_car(user_id, car_name)

    keyboard = [[InlineKeyboardButton("🚗 К автомобилям", callback_data='back_to_cars')]]
    await update.message.reply_text(
        f"✅ Автомобиль '{car_name}' добавлен!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_CAR


async def handle_expense_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода расхода"""
    user_id = update.effective_user.id
    car_id = user_car_selection.get(user_id)

    if not car_id:
        return await start(update, context)

    text = update.message.text

    try:
        if ',' in text:
            expense_part, mileage_part = text.split(',', 1)
            amount_desc = expense_part.strip()
            try:
                mileage = int(mileage_part.strip())
            except:
                mileage = None
        else:
            amount_desc = text
            mileage = None

        parts = amount_desc.split(' ', 1)
        amount = float(parts[0].replace(',', '.'))
        description = parts[1] if len(parts) > 1 else "Без описания"

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO daily_expenses (car_id, amount, description, mileage) VALUES (?, ?, ?, ?)",
            (car_id, amount, description, mileage)
        )
        conn.commit()
        conn.close()

        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_cars')]]
        await update.message.reply_text(
            f"✅ Расход добавлен!\n💰 {amount} руб.\n📝 {description}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        return ADD_EXPENSE

    return SELECT_CAR


async def handle_oil_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода замены масла"""
    user_id = update.effective_user.id
    car_id = user_car_selection.get(user_id)

    if not car_id:
        return await start(update, context)

    text = update.message.text
    parts = [p.strip() for p in text.split(',')]

    try:
        mileage = int(parts[0])
        oil_type = parts[1] if len(parts) > 1 else ""
        next_mileage = mileage + 10000

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO oil_changes (car_id, mileage, oil_type, next_change_mileage) VALUES (?, ?, ?, ?)",
            (car_id, mileage, oil_type, next_mileage)
        )
        conn.commit()
        conn.close()

        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_cars')]]
        await update.message.reply_text(
            f"✅ Замена масла зарегистрирована!\n📊 Пробег: {mileage} км",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        return SET_LAST_OIL_CHANGE

    return SELECT_CAR


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена действия"""
    await update.message.reply_text("Действие отменено. Используйте /start")
    return ConversationHandler.END


def main():
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECT_CAR: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_car_input)
            ],
            MAIN_MENU: [CallbackQueryHandler(button_handler)],
            ADD_CAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_car_input)],
            ADD_EXPENSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expense_input)],
            SET_LAST_OIL_CHANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_oil_input)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)

    print("🚗 Бот запущен...")
    application.run_polling()


if __name__ == '__main__':
    main()