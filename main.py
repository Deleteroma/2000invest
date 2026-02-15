import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, \
    ContextTypes, filters

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для разговора
(MAIN_MENU, SELECT_CAR, ADD_CAR, EDIT_CAR, DELETE_CAR,
 ADD_EXPENSE, SET_TOTAL_INVESTMENT, DELETE_EXPENSE,
 SELECT_SERVICE_TYPE, SET_LAST_OIL_CHANGE, ADD_SERVICE) = range(11)

# Конфигурация
BOT_TOKEN = '8477674042:AAEOFIOLskgqEfOzFzD2zSDyIvA8vBLyV-Q'  # Замените на ваш токен


class CarFinanceBot:
    def __init__(self):
        self.init_database()

    def init_database(self):
        """Инициализация базы данных с проверкой структуры"""
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

        # Проверяем существование таблицы cars и её структуру
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cars'")
        table_exists = cursor.fetchone()

        if table_exists:
            # Проверяем, есть ли колонка user_id в существующей таблице
            cursor.execute("PRAGMA table_info(cars)")
            columns = cursor.fetchall()
            column_names = [column[1] for column in columns]

            if 'user_id' not in column_names:
                print("Обновление структуры базы данных...")

                # Проверяем, существует ли уже таблица cars_new
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cars_new'")
                cars_new_exists = cursor.fetchone()

                if not cars_new_exists:
                    # Создаем новую таблицу с правильной структурой
                    cursor.execute('''
                        CREATE TABLE cars_new (
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

                    # Копируем данные из старой таблицы
                    # Для старых записей user_id будет NULL
                    cursor.execute('''
                        INSERT INTO cars_new (id, name, brand, model, year, license_plate, created_date)
                        SELECT id, name, brand, model, year, license_plate, created_date FROM cars
                    ''')

                    # Удаляем старую таблицу
                    cursor.execute("DROP TABLE cars")

                    # Переименовываем новую таблицу
                    cursor.execute("ALTER TABLE cars_new RENAME TO cars")

                    print("Структура базы данных успешно обновлена!")
                else:
                    # Если cars_new уже существует, просто переименовываем
                    print("Восстановление структуры базы данных...")
                    cursor.execute("DROP TABLE IF EXISTS cars")
                    cursor.execute("ALTER TABLE cars_new RENAME TO cars")
        else:
            # Создаем таблицу автомобилей с привязкой к пользователю
            cursor.execute('''
                CREATE TABLE cars (
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

        # Проверяем и обновляем структуру связанных таблиц
        self.update_related_tables(cursor)

        conn.commit()
        conn.close()

    def update_related_tables(self, cursor):
        """Обновление структуры связанных таблиц"""
        # Таблица для общих инвестиций
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS total_investments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_id INTEGER,
                amount REAL NOT NULL,
                description TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (car_id) REFERENCES cars (id) ON DELETE CASCADE
            )
        ''')

        # Таблица для ежедневных расходов
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

        # Таблица для технического обслуживания
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS service_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_id INTEGER,
                service_type TEXT NOT NULL,
                mileage INTEGER NOT NULL,
                description TEXT,
                cost REAL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (car_id) REFERENCES cars (id) ON DELETE CASCADE
            )
        ''')

        # Таблица для отслеживания замены масла
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

    def register_user(self, user_id, username, first_name, last_name):
        """Регистрация или обновление пользователя"""
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()

        # Проверяем, существует ли пользователь
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()

        if not user:
            # Добавляем нового пользователя
            cursor.execute(
                "INSERT INTO users (id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, last_name)
            )
            conn.commit()

        conn.close()

    # Методы для работы с автомобилями (теперь с user_id)
    def add_car(self, user_id, name, brand="", model="", year=None, license_plate=""):
        """Добавление нового автомобиля для конкретного пользователя"""
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
        """Получение списка автомобилей пользователя"""
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, brand, model, year, license_plate FROM cars WHERE user_id = ? ORDER BY created_date",
            (user_id,)
        )
        cars = cursor.fetchall()
        conn.close()
        return cars

    def get_car_by_id(self, car_id, user_id):
        """Получение информации об автомобиле по ID (с проверкой владельца)"""
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, brand, model, year, license_plate FROM cars WHERE id = ? AND user_id = ?",
            (car_id, user_id)
        )
        car = cursor.fetchone()
        conn.close()
        return car

    def delete_car(self, car_id, user_id):
        """Удаление автомобиля и всех связанных записей (с проверкой владельца)"""
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()

        # Сначала проверяем, принадлежит ли автомобиль пользователю
        cursor.execute("SELECT id FROM cars WHERE id = ? AND user_id = ?", (car_id, user_id))
        if not cursor.fetchone():
            conn.close()
            return False

        # Удаляем автомобиль (связанные записи удалятся автоматически благодаря ON DELETE CASCADE)
        cursor.execute("DELETE FROM cars WHERE id = ? AND user_id = ?", (car_id, user_id))

        conn.commit()
        conn.close()
        return True

    def update_car(self, car_id, user_id, name, brand, model, year, license_plate):
        """Обновление информации об автомобиле (с проверкой владельца)"""
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()

        # Проверяем владельца
        cursor.execute("SELECT id FROM cars WHERE id = ? AND user_id = ?", (car_id, user_id))
        if not cursor.fetchone():
            conn.close()
            return False

        cursor.execute(
            "UPDATE cars SET name = ?, brand = ?, model = ?, year = ?, license_plate = ? WHERE id = ? AND user_id = ?",
            (name, brand, model, year, license_plate, car_id, user_id)
        )
        conn.commit()
        conn.close()
        return True

    # Методы для работы с расходами (с проверкой владельца через car_id)
    def check_car_ownership(self, car_id, user_id):
        """Проверка, принадлежит ли автомобиль пользователю"""
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cars WHERE id = ? AND user_id = ?", (car_id, user_id))
        result = cursor.fetchone() is not None
        conn.close()
        return result

    def add_total_investment(self, car_id, user_id, amount, description=""):
        """Добавление общей инвестиции в машину (с проверкой владельца)"""
        if not self.check_car_ownership(car_id, user_id):
            return False

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO total_investments (car_id, amount, description) VALUES (?, ?, ?)",
            (car_id, amount, description)
        )
        conn.commit()
        conn.close()
        return True

    def add_daily_expense(self, car_id, user_id, amount, description, mileage=None):
        """Добавление ежедневного расхода (с проверкой владельца)"""
        if not self.check_car_ownership(car_id, user_id):
            return False

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO daily_expenses (car_id, amount, description, mileage) VALUES (?, ?, ?, ?)",
            (car_id, amount, description, mileage)
        )
        conn.commit()
        conn.close()
        return True

    def add_oil_change(self, car_id, user_id, mileage, oil_type="", next_change_mileage=None):
        """Добавление записи о замене масла (с проверкой владельца)"""
        if not self.check_car_ownership(car_id, user_id):
            return False

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()

        if not next_change_mileage:
            next_change_mileage = mileage + 10000  # По умолчанию через 10000 км

        cursor.execute(
            "INSERT INTO oil_changes (car_id, mileage, oil_type, next_change_mileage) VALUES (?, ?, ?, ?)",
            (car_id, mileage, oil_type, next_change_mileage)
        )
        conn.commit()
        conn.close()
        return True

    def add_service_record(self, car_id, user_id, service_type, mileage, description="", cost=0):
        """Добавление записи о техническом обслуживании (с проверкой владельца)"""
        if not self.check_car_ownership(car_id, user_id):
            return False

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO service_records (car_id, service_type, mileage, description, cost) VALUES (?, ?, ?, ?, ?)",
            (car_id, service_type, mileage, description, cost)
        )
        conn.commit()
        conn.close()
        return True

    def get_last_oil_change(self, car_id, user_id):
        """Получение последней информации о замене масла (с проверкой владельца)"""
        if not self.check_car_ownership(car_id, user_id):
            return None

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT mileage, oil_type, next_change_mileage, date FROM oil_changes WHERE car_id = ? ORDER BY date DESC LIMIT 1",
            (car_id,)
        )
        oil_change = cursor.fetchone()
        conn.close()
        return oil_change

    def get_service_history(self, car_id, user_id, limit=10):
        """Получение истории обслуживания (с проверкой владельца)"""
        if not self.check_car_ownership(car_id, user_id):
            return []

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT service_type, mileage, description, cost, date FROM service_records WHERE car_id = ? ORDER BY date DESC LIMIT ?",
            (car_id, limit)
        )
        services = cursor.fetchall()
        conn.close()
        return services

    def get_car_statistics(self, car_id, user_id):
        """Получение полной статистики по автомобилю (с проверкой владельца)"""
        if not self.check_car_ownership(car_id, user_id):
            return None

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()

        # Общие инвестиции
        cursor.execute("SELECT SUM(amount) FROM total_investments WHERE car_id = ?", (car_id,))
        total_invest = cursor.fetchone()[0] or 0

        # Ежедневные расходы
        cursor.execute("SELECT SUM(amount) FROM daily_expenses WHERE car_id = ?", (car_id,))
        daily_total = cursor.fetchone()[0] or 0

        # Последний пробег
        cursor.execute(
            "SELECT mileage FROM daily_expenses WHERE car_id = ? AND mileage IS NOT NULL ORDER BY date DESC LIMIT 1",
            (car_id,))
        last_mileage = cursor.fetchone()
        last_mileage = last_mileage[0] if last_mileage else 0

        # Последняя замена масла
        last_oil = self.get_last_oil_change(car_id, user_id)

        conn.close()

        return {
            'total_investment': total_invest,
            'daily_expenses': daily_total,
            'total': total_invest + daily_total,
            'last_mileage': last_mileage,
            'last_oil_change': last_oil
        }

    def get_recent_expenses(self, car_id, user_id, limit=15):
        """Получение последних расходов (с проверкой владельца)"""
        if not self.check_car_ownership(car_id, user_id):
            return []

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT amount, description, mileage, date FROM daily_expenses WHERE car_id = ? ORDER BY date DESC LIMIT ?",
            (car_id, limit)
        )
        expenses = cursor.fetchall()
        conn.close()
        return expenses

    def get_last_expense(self, car_id, user_id):
        """Получение последнего расхода (с проверкой владельца)"""
        if not self.check_car_ownership(car_id, user_id):
            return None

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, amount, description, date FROM daily_expenses WHERE car_id = ? ORDER BY date DESC LIMIT 1",
            (car_id,)
        )
        expense = cursor.fetchone()
        conn.close()
        return expense

    def delete_expense_by_id(self, expense_id, car_id, user_id):
        """Удаление расхода по ID (с проверкой владельца)"""
        if not self.check_car_ownership(car_id, user_id):
            return False

        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM daily_expenses WHERE id = ? AND car_id = ?", (expense_id, car_id))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted


# Создаем экземпляр бота
bot = CarFinanceBot()

# Глобальная переменная для хранения выбранного автомобиля (по пользователю)
user_car_selection = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start"""
    user = update.effective_user

    # Регистрируем пользователя
    bot.register_user(
        user.id,
        user.username,
        user.first_name,
        user.last_name
    )

    # Получаем автомобили пользователя
    cars = bot.get_user_cars(user.id)

    if not cars:
        # Если нет автомобилей, предлагаем добавить первый
        keyboard = [
            [InlineKeyboardButton("➕ Добавить автомобиль", callback_data='add_car')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"👋 Здравствуйте, {user.first_name}!\n\n"
            "🚗 Добро пожаловать в Финансовый ассистент автомобиля!\n\n"
            "У вас пока нет добавленных автомобилей. Давайте добавим первый!",
            reply_markup=reply_markup
        )
        return ADD_CAR

    # Показываем меню выбора автомобиля
    keyboard = []
    for car_id, name, brand, model, year, plate in cars:
        car_info = f"{brand} {model}" if brand and model else name
        if year:
            car_info += f" ({year})"
        keyboard.append([InlineKeyboardButton(f"🚗 {car_info}", callback_data=f'select_car_{car_id}')])

    keyboard.append([InlineKeyboardButton("➕ Добавить новый автомобиль", callback_data='add_car')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 С возвращением, {user.first_name}!\n\n"
        "🚗 Выберите автомобиль:",
        reply_markup=reply_markup
    )

    return SELECT_CAR


async def car_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, car_id: int) -> int:
    """Меню для выбранного автомобиля"""
    user_id = update.effective_user.id

    # Проверяем, принадлежит ли автомобиль пользователю
    car = bot.get_car_by_id(car_id, user_id)
    if not car:
        # Если автомобиль не найден или не принадлежит пользователю, возвращаемся к списку
        if update.callback_query:
            await update.callback_query.message.edit_text(
                "❌ Автомобиль не найден или доступ запрещен."
            )
        else:
            await update.message.reply_text("❌ Автомобиль не найден или доступ запрещен.")
        return await show_car_list(update, context)

    # Получаем объект сообщения в зависимости от типа update
    if update.callback_query:
        message = update.callback_query.message
    else:
        message = update.message

    user_car_selection[user_id] = car_id

    car_name = f"{car[2]} {car[3]}" if car[2] and car[3] else car[1]
    stats = bot.get_car_statistics(car_id, user_id)

    # Проверка необходимости замены масла
    oil_warning = ""
    if stats and stats['last_oil_change']:
        last_oil_mileage, oil_type, next_oil_mileage, date = stats['last_oil_change']
        current_mileage = stats['last_mileage']

        if current_mileage >= next_oil_mileage:
            oil_warning = "\n⚠️ ТРЕБУЕТСЯ ЗАМЕНА МАСЛА!"
        elif next_oil_mileage - current_mileage < 1000:
            oil_warning = f"\n⏰ Скоро замена масла (осталось {next_oil_mileage - current_mileage} км)"

    keyboard = [
        [InlineKeyboardButton("💰 Добавить расход", callback_data='add_expense')],
        [InlineKeyboardButton("🔧 Техническое обслуживание", callback_data='service_menu')],
        [InlineKeyboardButton("📊 Статистика", callback_data='view_stats')],
        [InlineKeyboardButton("💵 Общие инвестиции", callback_data='total_investment')],
        [InlineKeyboardButton("📝 Последние расходы", callback_data='recent_expenses')],
        [InlineKeyboardButton("🛢 Замена масла", callback_data='oil_change')],
        [InlineKeyboardButton("✏️ Редактировать авто", callback_data='edit_car')],
        [InlineKeyboardButton("❌ Удалить авто", callback_data='delete_car')],
        [InlineKeyboardButton("🔙 К списку авто", callback_data='back_to_cars')]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    header = f"🚗 {car_name}\n"
    if car[5]:  # license_plate
        header += f"📋 Госномер: {car[5]}\n"

    if stats:
        header += f"💰 Всего вложено: {stats['total']:,.2f} руб.\n"
        header += f"📊 Текущий пробег: {stats['last_mileage']} км"
    else:
        header += f"💰 Всего вложено: 0 руб.\n"
        header += f"📊 Текущий пробег: 0 км"

    header += oil_warning

    if update.callback_query:
        await message.edit_text(header, reply_markup=reply_markup)
    else:
        await message.reply_text(header, reply_markup=reply_markup)

    return MAIN_MENU


async def show_car_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать список автомобилей пользователя"""
    user_id = update.effective_user.id
    cars = bot.get_user_cars(user_id)

    keyboard = []
    for car_id, name, brand, model, year, plate in cars:
        car_info = f"{brand} {model}" if brand and model else name
        if year:
            car_info += f" ({year})"
        keyboard.append([InlineKeyboardButton(f"🚗 {car_info}", callback_data=f'select_car_{car_id}')])

    keyboard.append([InlineKeyboardButton("➕ Добавить новый автомобиль", callback_data='add_car')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.edit_text(
            "🚗 Выберите автомобиль:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "🚗 Выберите автомобиль:",
            reply_markup=reply_markup
        )

    return SELECT_CAR


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    current_car_id = user_car_selection.get(user_id)

    # Обработка выбора автомобиля
    if query.data.startswith('select_car_'):
        car_id = int(query.data.replace('select_car_', ''))
        return await car_menu(update, context, car_id)

    elif query.data == 'back_to_cars':
        return await show_car_list(update, context)

    elif query.data == 'add_car':
        await query.message.edit_text(
            "➕ Добавление нового автомобиля\n\n"
            "Введите информацию об автомобиле в формате:\n"
            "Название, Марка, Модель, Год, Номер\n\n"
            "Можно указать только название, остальное по желанию.\n"
            "Пример: Моя Лада, Lada, Vesta, 2020, А123БВ777\n"
            "Или просто: Моя машина"
        )
        return ADD_CAR

    elif query.data == 'edit_car':
        if not current_car_id:
            return await show_car_list(update, context)

        car = bot.get_car_by_id(current_car_id, user_id)
        if not car:
            await query.message.edit_text("❌ Автомобиль не найден или доступ запрещен.")
            return await show_car_list(update, context)

        await query.message.edit_text(
            f"✏️ Редактирование автомобиля\n\n"
            f"Текущие данные:\n"
            f"Название: {car[1]}\n"
            f"Марка: {car[2] or 'не указана'}\n"
            f"Модель: {car[3] or 'не указана'}\n"
            f"Год: {car[4] or 'не указан'}\n"
            f"Номер: {car[5] or 'не указан'}\n\n"
            f"Введите новые данные в том же формате:"
        )
        return EDIT_CAR

    elif query.data == 'delete_car':
        if not current_car_id:
            return await show_car_list(update, context)

        car = bot.get_car_by_id(current_car_id, user_id)
        if not car:
            await query.message.edit_text("❌ Автомобиль не найден или доступ запрещен.")
            return await show_car_list(update, context)

        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data='confirm_delete_car')],
            [InlineKeyboardButton("❌ Нет, отмена", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(
            f"⚠️ Вы действительно хотите удалить автомобиль {car[1]}?\n"
            f"Все связанные расходы и история обслуживания будут удалены!\n"
            f"Это действие нельзя отменить.",
            reply_markup=reply_markup
        )
        return DELETE_CAR

    elif query.data == 'confirm_delete_car':
        if current_car_id:
            if bot.delete_car(current_car_id, user_id):
                user_car_selection.pop(user_id, None)
                await query.message.edit_text("✅ Автомобиль успешно удален!")
            else:
                await query.message.edit_text("❌ Ошибка при удалении автомобиля.")

            # Возвращаемся к списку автомобилей
            return await show_car_list(update, context)

    elif query.data == 'service_menu':
        keyboard = [
            [InlineKeyboardButton("🛢 Замена масла", callback_data='oil_change')],
            [InlineKeyboardButton("🔧 Плановое ТО", callback_data='planned_service')],
            [InlineKeyboardButton("🔨 Ремонт", callback_data='repair_service')],
            [InlineKeyboardButton("📋 История обслуживания", callback_data='service_history')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(
            "🔧 Меню технического обслуживания\n\n"
            "Выберите тип обслуживания:",
            reply_markup=reply_markup
        )
        return SELECT_SERVICE_TYPE

    elif query.data == 'oil_change':
        if not current_car_id:
            return await show_car_list(update, context)

        last_oil = bot.get_last_oil_change(current_car_id, user_id)

        if last_oil:
            mileage, oil_type, next_mileage, date = last_oil
            date_obj = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
            formatted_date = date_obj.strftime('%d.%m.%Y')

            text = (
                f"🛢 Последняя замена масла:\n"
                f"📅 Дата: {formatted_date}\n"
                f"📊 Пробег: {mileage} км\n"
                f"🛢 Масло: {oil_type or 'не указано'}\n"
                f"⏰ Следующая замена: {next_mileage} км\n\n"
            )
        else:
            text = "🛢 Замена масла ещё не производилась\n\n"

        text += "Введите данные о замене масла в формате:\n"
        text += "Пробег, Тип масла (необязательно), Интервал замены (необязательно)\n"
        text += "Пример: 15000, Mobil 5W30, 10000\n"
        text += "Или просто: 15000"

        await query.message.edit_text(text)
        return SET_LAST_OIL_CHANGE

    elif query.data == 'service_history':
        if not current_car_id:
            return await show_car_list(update, context)

        services = bot.get_service_history(current_car_id, user_id, 15)

        if not services:
            text = "📋 История обслуживания пуста"
        else:
            text = "📋 ИСТОРИЯ ОБСЛУЖИВАНИЯ:\n\n"
            for service_type, mileage, description, cost, date in services:
                date_obj = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
                formatted_date = date_obj.strftime('%d.%m.%Y')
                text += f"📅 {formatted_date} | {mileage} км\n"
                text += f"🔧 {service_type}\n"
                if description:
                    text += f"📝 {description}\n"
                if cost:
                    text += f"💰 {cost:,.2f} руб.\n"
                text += "\n"

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='service_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(text, reply_markup=reply_markup)
        return SELECT_SERVICE_TYPE

    elif query.data in ['planned_service', 'repair_service']:
        service_type = "Плановое ТО" if query.data == 'planned_service' else "Ремонт"
        context.user_data['service_type'] = service_type

        await query.message.edit_text(
            f"🔧 {service_type}\n\n"
            f"Введите информацию в формате:\n"
            f"Пробег, Описание, Стоимость\n"
            f"Пример: 20000, Замена тормозных колодок, 5000"
        )
        return ADD_SERVICE

    elif query.data == 'add_expense':
        if not current_car_id:
            return await show_car_list(update, context)

        await query.message.edit_text(
            "📝 Опишите, что вы сделали с машиной и сколько потратили.\n"
            "Введите в формате: Сумма Описание, Пробег(необязательно)\n"
            "Примеры:\n"
            "2500 Замена масла, 15000\n"
            "1000 Мойка"
        )
        return ADD_EXPENSE

    elif query.data == 'view_stats':
        if not current_car_id:
            return await show_car_list(update, context)

        return await show_statistics(update, context, current_car_id)

    elif query.data == 'total_investment':
        if not current_car_id:
            return await show_car_list(update, context)

        await query.message.edit_text(
            "💰 Введите общую сумму инвестиций в машину и описание:\n"
            "Формат: Сумма Описание\n"
            "Например: 500000 Покупка автомобиля"
        )
        return SET_TOTAL_INVESTMENT

    elif query.data == 'recent_expenses':
        if not current_car_id:
            return await show_car_list(update, context)

        return await show_recent_expenses(update, context, current_car_id)

    elif query.data == 'delete_expense':
        if not current_car_id:
            return await show_car_list(update, context)

        return await confirm_delete(update, context, current_car_id)

    elif query.data == 'confirm_delete_yes':
        return await handle_delete_confirmation(update, context)

    elif query.data == 'back_to_menu':
        if not current_car_id:
            return await show_car_list(update, context)

        return await car_menu(update, context, current_car_id)

    return MAIN_MENU


async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE, car_id: int) -> int:
    """Показать статистику расходов по автомобилю"""
    query = update.callback_query
    user_id = query.from_user.id

    stats = bot.get_car_statistics(car_id, user_id)
    car = bot.get_car_by_id(car_id, user_id)

    if not car or not stats:
        await query.message.edit_text("❌ Ошибка загрузки статистики.")
        return await show_car_list(update, context)

    stats_text = (
        f"📊 СТАТИСТИКА ПО АВТОМОБИЛЮ {car[1]}\n\n"
        f"💰 Общие инвестиции: {stats['total_investment']:,.2f} руб.\n"
        f"📅 Ежедневные расходы: {stats['daily_expenses']:,.2f} руб.\n"
        f"💵 ВСЕГО ВЛОЖЕНО: {stats['total']:,.2f} руб.\n"
        f"📊 Текущий пробег: {stats['last_mileage']} км\n"
    )

    if stats['last_oil_change']:
        last_oil_mileage, oil_type, next_mileage, date = stats['last_oil_change']
        date_obj = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
        formatted_date = date_obj.strftime('%d.%m.%Y')

        stats_text += f"\n🛢 Последняя замена масла:\n"
        stats_text += f"   Дата: {formatted_date}\n"
        stats_text += f"   Пробег: {last_oil_mileage} км\n"
        stats_text += f"   Следующая: {next_mileage} км\n"

        if stats['last_mileage'] >= next_mileage:
            stats_text += "   ⚠️ ТРЕБУЕТСЯ ЗАМЕНА!\n"
        elif next_mileage - stats['last_mileage'] < 1000:
            stats_text += f"   ⏰ Осталось {next_mileage - stats['last_mileage']} км\n"

    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(stats_text, reply_markup=reply_markup)
    return MAIN_MENU


async def show_recent_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE, car_id: int) -> int:
    """Показать последние расходы"""
    query = update.callback_query
    user_id = query.from_user.id

    expenses = bot.get_recent_expenses(car_id, user_id, 15)

    if not expenses:
        text = "📝 У вас пока нет записей о расходах."
    else:
        text = "📝 ПОСЛЕДНИЕ РАСХОДЫ:\n\n"
        for amount, description, mileage, date in expenses:
            date_obj = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
            formatted_date = date_obj.strftime('%d.%m.%Y %H:%M')
            mileage_text = f" [{mileage} км]" if mileage else ""
            text += f"• {formatted_date}{mileage_text}\n  {description}: {amount:,.2f} руб.\n\n"

    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(text, reply_markup=reply_markup)
    return MAIN_MENU


async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, car_id: int) -> int:
    """Подтверждение удаления последнего расхода"""
    query = update.callback_query
    user_id = query.from_user.id

    expense = bot.get_last_expense(car_id, user_id)

    if not expense:
        text = "❌ Нет записей для удаления."
        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
    else:
        expense_id, amount, description, date = expense
        date_obj = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
        formatted_date = date_obj.strftime('%d.%m.%Y %H:%M')

        text = (
            f"⚠️ Подтвердите удаление последнего расхода:\n\n"
            f"📅 {formatted_date}\n"
            f"📝 {description}\n"
            f"💰 {amount:,.2f} руб.\n\n"
            f"Действие нельзя отменить!"
        )

        context.user_data['delete_expense_id'] = expense_id
        context.user_data['delete_car_id'] = car_id

        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data='confirm_delete_yes')],
            [InlineKeyboardButton("❌ Нет, отмена", callback_data='back_to_menu')]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(text, reply_markup=reply_markup)
    return DELETE_EXPENSE


async def handle_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка подтверждения удаления"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    expense_id = context.user_data.get('delete_expense_id')
    car_id = context.user_data.get('delete_car_id')

    if expense_id and car_id and bot.delete_expense_by_id(expense_id, car_id, user_id):
        text = "✅ Расход успешно удален!"
    else:
        text = "❌ Ошибка при удалении"

    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(text, reply_markup=reply_markup)
    return MAIN_MENU


async def handle_car_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода нового автомобиля"""
    user_id = update.effective_user.id
    text = update.message.text

    # Парсим введенные данные
    parts = [p.strip() for p in text.split(',')]

    name = parts[0]
    brand = parts[1] if len(parts) > 1 else ""
    model = parts[2] if len(parts) > 2 else ""

    year = None
    if len(parts) > 3 and parts[3].strip():
        try:
            year = int(parts[3])
        except ValueError:
            year = None

    license_plate = parts[4] if len(parts) > 4 else ""

    car_id = bot.add_car(user_id, name, brand, model, year, license_plate)

    keyboard = [[InlineKeyboardButton(f"🚗 Перейти к автомобилю", callback_data=f'select_car_{car_id}')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✅ Автомобиль успешно добавлен!\n\n"
        f"Название: {name}\n"
        f"Марка: {brand or 'не указана'}\n"
        f"Модель: {model or 'не указана'}\n"
        f"Год: {year or 'не указан'}\n"
        f"Номер: {license_plate or 'не указан'}",
        reply_markup=reply_markup
    )

    return SELECT_CAR


async def handle_edit_car_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка редактирования автомобиля"""
    user_id = update.effective_user.id
    car_id = user_car_selection.get(user_id)

    if not car_id:
        return await start(update, context)

    text = update.message.text
    parts = [p.strip() for p in text.split(',')]

    name = parts[0]
    brand = parts[1] if len(parts) > 1 else ""
    model = parts[2] if len(parts) > 2 else ""

    year = None
    if len(parts) > 3 and parts[3].strip():
        try:
            year = int(parts[3])
        except ValueError:
            year = None

    license_plate = parts[4] if len(parts) > 4 else ""

    if bot.update_car(car_id, user_id, name, brand, model, year, license_plate):
        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ Автомобиль успешно обновлен!",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ Ошибка при обновлении автомобиля.")

    return MAIN_MENU


async def handle_expense_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода расхода"""
    user_id = update.effective_user.id
    car_id = user_car_selection.get(user_id)

    if not car_id:
        return await start(update, context)

    text = update.message.text

    try:
        # Парсим введенные данные
        if ',' in text:
            expense_part, mileage_part = text.split(',', 1)
            amount_desc = expense_part.strip()
            try:
                mileage = int(mileage_part.strip())
            except ValueError:
                mileage = None
        else:
            amount_desc = text
            mileage = None

        parts = amount_desc.split(' ', 1)
        amount = float(parts[0].replace(',', '.'))
        description = parts[1] if len(parts) > 1 else "Без описания"

        # Сохраняем в базу данных
        if bot.add_daily_expense(car_id, user_id, amount, description, mileage):
            keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response = f"✅ Расход успешно добавлен!\n\n💰 Сумма: {amount:,.2f} руб.\n📝 Описание: {description}"
            if mileage:
                response += f"\n📊 Пробег: {mileage} км"

            await update.message.reply_text(response, reply_markup=reply_markup)
        else:
            await update.message.reply_text("❌ Ошибка при добавлении расхода.")

    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Неверный формат. Пожалуйста, введите сумму и описание через пробел.\n"
            "Пример: 2500 Замена масла, 15000"
        )
        return ADD_EXPENSE

    return MAIN_MENU


async def handle_total_investment_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода общей инвестиции"""
    user_id = update.effective_user.id
    car_id = user_car_selection.get(user_id)

    if not car_id:
        return await start(update, context)

    text = update.message.text

    try:
        parts = text.split(' ', 1)
        amount = float(parts[0].replace(',', '.'))
        description = parts[1] if len(parts) > 1 else "Инвестиция в авто"

        if bot.add_total_investment(car_id, user_id, amount, description):
            keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"✅ Инвестиция успешно добавлена!\n\n"
                f"💰 Сумма: {amount:,.2f} руб.\n"
                f"📝 Описание: {description}",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ Ошибка при добавлении инвестиции.")

    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Неверный формат. Пожалуйста, введите сумму и описание через пробел.\n"
            "Например: 500000 Покупка автомобиля"
        )
        return SET_TOTAL_INVESTMENT

    return MAIN_MENU


async def handle_oil_change_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

        if len(parts) > 2:
            next_interval = int(parts[2])
            next_mileage = mileage + next_interval
        else:
            next_mileage = mileage + 10000  # По умолчанию через 10000 км

        if bot.add_oil_change(car_id, user_id, mileage, oil_type, next_mileage):
            keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"✅ Замена масла зарегистрирована!\n\n"
                f"📊 Пробег: {mileage} км\n"
                f"🛢 Масло: {oil_type or 'не указано'}\n"
                f"⏰ Следующая замена: {next_mileage} км",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ Ошибка при регистрации замены масла.")

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат. Пожалуйста, введите пробег и опционально тип масла и интервал.\n"
            "Пример: 15000, Mobil 5W30, 10000"
        )
        return SET_LAST_OIL_CHANGE

    return MAIN_MENU


async def handle_service_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода техобслуживания"""
    user_id = update.effective_user.id
    car_id = user_car_selection.get(user_id)

    if not car_id:
        return await start(update, context)

    text = update.message.text
    parts = [p.strip() for p in text.split(',')]

    try:
        mileage = int(parts[0])
        description = parts[1] if len(parts) > 1 else ""
        cost = float(parts[2].replace(',', '.')) if len(parts) > 2 else 0

        service_type = context.user_data.get('service_type', 'Техобслуживание')

        if bot.add_service_record(car_id, user_id, service_type, mileage, description, cost):
            keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response = f"✅ Запись о ТО добавлена!\n\n🔧 {service_type}\n📊 Пробег: {mileage} км"
            if description:
                response += f"\n📝 {description}"
            if cost:
                response += f"\n💰 {cost:,.2f} руб."

            await update.message.reply_text(response, reply_markup=reply_markup)
        else:
            await update.message.reply_text("❌ Ошибка при добавлении записи о ТО.")

    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Неверный формат. Пожалуйста, введите пробег, описание и стоимость через запятую.\n"
            "Пример: 20000, Замена тормозных колодок, 5000"
        )
        return ADD_SERVICE

    return MAIN_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена действия"""
    await update.message.reply_text(
        "Действие отменено. Используйте /start для возврата в меню."
    )
    return ConversationHandler.END


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")


def main():
    """Основная функция запуска бота"""
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Создаем обработчик разговора
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECT_CAR: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_car_input)
            ],
            MAIN_MENU: [
                CallbackQueryHandler(button_handler)
            ],
            ADD_CAR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_car_input),
                CallbackQueryHandler(button_handler)
            ],
            EDIT_CAR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_car_input),
                CallbackQueryHandler(button_handler)
            ],
            DELETE_CAR: [
                CallbackQueryHandler(button_handler)
            ],
            ADD_EXPENSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expense_input),
                CallbackQueryHandler(button_handler)
            ],
            SET_TOTAL_INVESTMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_total_investment_input),
                CallbackQueryHandler(button_handler)
            ],
            DELETE_EXPENSE: [
                CallbackQueryHandler(button_handler)
            ],
            SELECT_SERVICE_TYPE: [
                CallbackQueryHandler(button_handler)
            ],
            SET_LAST_OIL_CHANGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_oil_change_input),
                CallbackQueryHandler(button_handler)
            ],
            ADD_SERVICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_service_input),
                CallbackQueryHandler(button_handler)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)

    # Запускаем бота
    print("🚗 Финансовый ассистент автомобиля запущен...")
    print("Бот готов к работе с несколькими пользователями!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()