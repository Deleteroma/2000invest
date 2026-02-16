import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, \
    ContextTypes, filters

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для разговора - 38 состояний (ИСПРАВЛЕНО)
(MAIN_MENU, SELECT_CAR, ADD_CAR, EDIT_CAR, DELETE_CAR,
 ADD_EXPENSE, SET_TOTAL_INVESTMENT, DELETE_EXPENSE,
 SELECT_SERVICE_TYPE, SERVICE_HISTORY,
 # Состояния для пошагового добавления авто
 CAR_NAME, CAR_BRAND, CAR_MODEL, CAR_YEAR, CAR_VIN, CAR_PLATE,
 # Состояния для пошагового редактирования авто
 EDIT_CAR_NAME, EDIT_CAR_BRAND, EDIT_CAR_MODEL, EDIT_CAR_YEAR, EDIT_CAR_VIN, EDIT_CAR_PLATE,
 # Состояния для пошаговой замены масла
 OIL_MILEAGE, OIL_TYPE, OIL_INTERVAL, OIL_DATE,
 # Состояния для расходов
 EXPENSE_AMOUNT, EXPENSE_DESC, EXPENSE_MILEAGE, EXPENSE_DATE,
 # Состояния для ТО и расходников
 SERVICE_MILEAGE, SERVICE_DESC, SERVICE_COST,
 # Состояния для расходников
 CONSUMABLE_NAME, CONSUMABLE_PART_NUMBER, CONSUMABLE_CAR,
 # Состояние для удаления расходника и подтверждения удаления авто
 DELETE_CONSUMABLE, DELETE_CAR_CONFIRM) = range(38)  # 0-37 = 38 состояний

# Конфигурация
BOT_TOKEN = '8477674042:AAEOFIOLskgqEfOzFzD2zSDyIvA8vBLyV-Q'  # Замените на ваш токен

# Каталоги - только нужные ссылки
CAR_CATALOGS = {
    'japanese': {
        'name': '🇯🇵 Японские автомобили',
        'url': 'https://www.japancats.ru/',
        'description': 'Каталог запчастей для японских автомобилей по VIN'
    },
    'bmw': {
        'name': '🇩🇪 BMW',
        'url': 'https://etk.club/',
        'description': 'Оригинальные каталоги BMW по VIN'
    }
}


class CarFinanceBot:
    def __init__(self):
        self.init_database()

    def init_database(self):
        """Инициализация и миграция базы данных"""
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

        # Проверяем существование таблицы cars
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cars'")
        table_exists = cursor.fetchone()

        if table_exists:
            # Проверяем, какие колонки есть в таблице cars
            cursor.execute("PRAGMA table_info(cars)")
            columns = cursor.fetchall()
            column_names = [column[1] for column in columns]

            # Добавляем колонку vin, если её нет
            if 'vin' not in column_names:
                print("🔄 Добавление колонки vin в таблицу cars...")
                cursor.execute("ALTER TABLE cars ADD COLUMN vin TEXT")
                print("✅ Колонка vin добавлена")

            # Добавляем колонку current_mileage, если её нет
            if 'current_mileage' not in column_names:
                print("🔄 Добавление колонки current_mileage в таблицу cars...")
                cursor.execute("ALTER TABLE cars ADD COLUMN current_mileage INTEGER DEFAULT 0")
                print("✅ Колонка current_mileage добавлена")

            # Добавляем колонку expense_date в daily_expenses, если её нет
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_expenses'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(daily_expenses)")
                exp_columns = cursor.fetchall()
                exp_column_names = [col[1] for col in exp_columns]

                if 'expense_date' not in exp_column_names:
                    print("🔄 Добавление колонки expense_date в таблицу daily_expenses...")
                    cursor.execute("ALTER TABLE daily_expenses ADD COLUMN expense_date DATE")
                    print("✅ Колонка expense_date добавлена")

            # Добавляем колонку change_date в oil_changes, если её нет
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='oil_changes'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(oil_changes)")
                oil_columns = cursor.fetchall()
                oil_column_names = [col[1] for col in oil_columns]

                if 'change_date' not in oil_column_names:
                    print("🔄 Добавление колонки change_date в таблицу oil_changes...")
                    cursor.execute("ALTER TABLE oil_changes ADD COLUMN change_date DATE")
                    print("✅ Колонка change_date добавлена")
        else:
            # Создаем таблицу автомобилей с VIN и текущим пробегом
            cursor.execute('''
                CREATE TABLE cars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    name TEXT NOT NULL,
                    brand TEXT,
                    model TEXT,
                    year INTEGER,
                    vin TEXT,
                    license_plate TEXT,
                    current_mileage INTEGER DEFAULT 0,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')

        # Таблица для расходов (ремонт и обслуживание)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_id INTEGER,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                mileage INTEGER,
                expense_date DATE,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (car_id) REFERENCES cars (id) ON DELETE CASCADE
            )
        ''')

        # Таблица для общих инвестиций (покупка авто, крупные вложения)
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

        # Таблица для замены масла
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS oil_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_id INTEGER,
                mileage INTEGER NOT NULL,
                oil_type TEXT,
                next_change_mileage INTEGER,
                change_date DATE,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (car_id) REFERENCES cars (id) ON DELETE CASCADE
            )
        ''')

        # Таблица для технического обслуживания (ТО и ремонт)
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

        # Таблица для расходников (артикулы запчастей)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS consumables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                car_id INTEGER,
                name TEXT NOT NULL,
                part_number TEXT,
                notes TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (car_id) REFERENCES cars (id) ON DELETE CASCADE
            )
        ''')

        conn.commit()
        conn.close()
        print("✅ База данных готова")

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

    def add_car(self, user_id, name, brand="", model="", year=None, vin="", license_plate=""):
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO cars (user_id, name, brand, model, year, vin, license_plate) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, brand, model, year, vin, license_plate)
        )
        car_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return car_id

    def update_car(self, car_id, user_id, name, brand="", model="", year=None, vin="", license_plate=""):
        """Обновление информации об автомобиле"""
        if not self.check_car_ownership(car_id, user_id):
            return False
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cars SET name = ?, brand = ?, model = ?, year = ?, vin = ?, license_plate = ? WHERE id = ? AND user_id = ?",
            (name, brand, model, year, vin, license_plate, car_id, user_id)
        )
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def get_user_cars(self, user_id):
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, name, brand, model, year, vin, license_plate, current_mileage FROM cars WHERE user_id = ? ORDER BY created_date",
                (user_id,)
            )
            cars = cursor.fetchall()
        except sqlite3.OperationalError:
            # Если ошибка, пробуем без новых колонок
            cursor.execute(
                "SELECT id, name, brand, model, year, license_plate FROM cars WHERE user_id = ? ORDER BY created_date",
                (user_id,)
            )
            cars = cursor.fetchall()
            # Преобразуем в формат с 8 полями
            cars = [(car[0], car[1], car[2], car[3], car[4], "", car[5], 0) for car in cars]
        conn.close()
        return cars

    def get_car_by_id(self, car_id, user_id):
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, name, brand, model, year, vin, license_plate, current_mileage FROM cars WHERE id = ? AND user_id = ?",
                (car_id, user_id)
            )
            car = cursor.fetchone()
        except sqlite3.OperationalError:
            cursor.execute(
                "SELECT id, name, brand, model, year, license_plate FROM cars WHERE id = ? AND user_id = ?",
                (car_id, user_id)
            )
            car_data = cursor.fetchone()
            if car_data:
                car = (car_data[0], car_data[1], car_data[2], car_data[3], car_data[4], "", car_data[5], 0)
            else:
                car = None
        conn.close()
        return car

    def delete_car(self, car_id, user_id):
        """Удаление автомобиля и всех связанных данных"""
        if not self.check_car_ownership(car_id, user_id):
            return False
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        # Благодаря ON DELETE CASCADE все связанные записи удалятся автоматически
        cursor.execute("DELETE FROM cars WHERE id = ? AND user_id = ?", (car_id, user_id))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def update_car_mileage(self, car_id, user_id, new_mileage):
        """Обновление текущего пробега автомобиля"""
        if not self.check_car_ownership(car_id, user_id):
            return False
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cars SET current_mileage = ? WHERE id = ? AND user_id = ?",
            (new_mileage, car_id, user_id)
        )
        conn.commit()
        conn.close()
        return True

    def add_daily_expense(self, car_id, user_id, amount, description, mileage=None, expense_date=None):
        if not self.check_car_ownership(car_id, user_id):
            return False
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        if not expense_date:
            expense_date = datetime.now().strftime('%Y-%m-%d')

        # Добавляем расход
        cursor.execute(
            "INSERT INTO daily_expenses (car_id, amount, description, mileage, expense_date) VALUES (?, ?, ?, ?, ?)",
            (car_id, amount, description, mileage, expense_date)
        )

        # Обновляем текущий пробег, если указан
        if mileage:
            cursor.execute(
                "UPDATE cars SET current_mileage = ? WHERE id = ? AND user_id = ?",
                (mileage, car_id, user_id)
            )

        conn.commit()
        conn.close()
        return True

    def add_oil_change(self, car_id, user_id, mileage, oil_type="", next_change_mileage=None, change_date=None):
        if not self.check_car_ownership(car_id, user_id):
            return False
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()

        if not change_date:
            change_date = datetime.now().strftime('%Y-%m-%d')

        if not next_change_mileage:
            next_change_mileage = mileage + 10000

        cursor.execute(
            "INSERT INTO oil_changes (car_id, mileage, oil_type, next_change_mileage, change_date) VALUES (?, ?, ?, ?, ?)",
            (car_id, mileage, oil_type, next_change_mileage, change_date)
        )

        # Обновляем текущий пробег
        cursor.execute(
            "UPDATE cars SET current_mileage = ? WHERE id = ? AND user_id = ?",
            (mileage, car_id, user_id)
        )

        # Также добавляем в расходы (замена масла)
        cursor.execute(
            "INSERT INTO daily_expenses (car_id, amount, description, mileage, expense_date) VALUES (?, ?, ?, ?, ?)",
            (car_id, 0, f"Замена масла ({oil_type})", mileage, change_date)
        )

        conn.commit()
        conn.close()
        return True

    def add_service_record(self, car_id, user_id, service_type, mileage, description="", cost=0):
        if not self.check_car_ownership(car_id, user_id):
            return False
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO service_records (car_id, service_type, mileage, description, cost) VALUES (?, ?, ?, ?, ?)",
            (car_id, service_type, mileage, description, cost)
        )

        # Обновляем текущий пробег
        cursor.execute(
            "UPDATE cars SET current_mileage = ? WHERE id = ? AND user_id = ?",
            (mileage, car_id, user_id)
        )

        # Также добавляем в расходы, если есть стоимость
        if cost > 0:
            cursor.execute(
                "INSERT INTO daily_expenses (car_id, amount, description, mileage, expense_date) VALUES (?, ?, ?, ?, ?)",
                (car_id, cost, f"{service_type}: {description}", mileage, datetime.now().strftime('%Y-%m-%d'))
            )
        conn.commit()
        conn.close()
        return True

    def add_consumable(self, user_id, car_id, name, part_number="", notes=""):
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO consumables (user_id, car_id, name, part_number, notes) VALUES (?, ?, ?, ?, ?)",
            (user_id, car_id, name, part_number, notes)
        )
        consumable_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return consumable_id

    def get_consumables(self, user_id, car_id=None):
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        if car_id:
            cursor.execute(
                "SELECT id, name, part_number, notes, date FROM consumables WHERE user_id = ? AND car_id = ? ORDER BY date DESC",
                (user_id, car_id)
            )
        else:
            cursor.execute(
                "SELECT id, name, part_number, notes, date FROM consumables WHERE user_id = ? ORDER BY date DESC",
                (user_id,)
            )
        consumables = cursor.fetchall()
        conn.close()
        return consumables

    def delete_consumable(self, consumable_id, user_id):
        """Удаление расходника"""
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM consumables WHERE id = ? AND user_id = ?",
            (consumable_id, user_id)
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def check_car_ownership(self, car_id, user_id):
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cars WHERE id = ? AND user_id = ?", (car_id, user_id))
        result = cursor.fetchone() is not None
        conn.close()
        return result

    def get_last_oil_change(self, car_id, user_id):
        if not self.check_car_ownership(car_id, user_id):
            return None
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT mileage, oil_type, next_change_mileage, change_date, date FROM oil_changes WHERE car_id = ? ORDER BY date DESC LIMIT 1",
                (car_id,)
            )
            oil_change = cursor.fetchone()
        except sqlite3.OperationalError:
            cursor.execute(
                "SELECT mileage, oil_type, next_change_mileage, date FROM oil_changes WHERE car_id = ? ORDER BY date DESC LIMIT 1",
                (car_id,)
            )
            oc = cursor.fetchone()
            if oc:
                oil_change = (oc[0], oc[1], oc[2], oc[3][:10], oc[3])
            else:
                oil_change = None
        conn.close()
        return oil_change

    def get_service_history(self, car_id, user_id, limit=10):
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

    def get_recent_expenses(self, car_id, user_id, days=30):
        """Получение расходов за последние N дней"""
        if not self.check_car_ownership(car_id, user_id):
            return []
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # Проверяем, есть ли колонка expense_date
        try:
            cursor.execute(
                "SELECT amount, description, mileage, expense_date FROM daily_expenses WHERE car_id = ? AND expense_date >= ? ORDER BY expense_date DESC, date DESC",
                (car_id, cutoff_date)
            )
        except sqlite3.OperationalError:
            # Если нет, используем date
            cursor.execute(
                "SELECT amount, description, mileage, date FROM daily_expenses WHERE car_id = ? AND date >= ? ORDER BY date DESC",
                (car_id, cutoff_date)
            )
            expenses = cursor.fetchall()
            # Преобразуем date в строку даты
            expenses = [(e[0], e[1], e[2], e[3][:10] if e[3] else datetime.now().strftime('%Y-%m-%d')) for e in
                        expenses]
            conn.close()
            return expenses

        expenses = cursor.fetchall()
        conn.close()
        return expenses

    def get_car_statistics(self, car_id, user_id):
        if not self.check_car_ownership(car_id, user_id):
            return None
        conn = sqlite3.connect('car_finance.db')
        cursor = conn.cursor()

        cursor.execute("SELECT SUM(amount) FROM daily_expenses WHERE car_id = ?", (car_id,))
        daily_total = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(amount) FROM total_investments WHERE car_id = ?", (car_id,))
        total_invest = cursor.fetchone()[0] or 0

        # Получаем текущий пробег из таблицы cars
        cursor.execute("SELECT current_mileage FROM cars WHERE id = ?", (car_id,))
        current_mileage = cursor.fetchone()
        current_mileage = current_mileage[0] if current_mileage else 0

        last_oil = self.get_last_oil_change(car_id, user_id)

        # Получаем расходы за последние 30 дней
        recent = self.get_recent_expenses(car_id, user_id, 30)

        conn.close()
        return {
            'daily_expenses': daily_total,
            'total_investment': total_invest,
            'total': daily_total + total_invest,
            'last_mileage': current_mileage,
            'last_oil_change': last_oil,
            'recent_expenses': recent
        }


# Создаем экземпляр бота
bot = CarFinanceBot()
user_car_selection = {}


# Функция для создания клавиатуры с кнопкой назад
def back_keyboard(back_to):
    """Создает клавиатуру с одной кнопкой назад"""
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_{back_to}")]]
    return InlineKeyboardMarkup(keyboard)


def keyboard_with_back(buttons, back_to):
    """Добавляет кнопку назад к существующей клавиатуре"""
    keyboard = buttons.copy()
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_{back_to}")])
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start"""
    user = update.effective_user
    bot.register_user(user.id, user.username, user.first_name, user.last_name)

    cars = bot.get_user_cars(user.id)

    if not cars:
        keyboard = [[InlineKeyboardButton("➕ Добавить автомобиль", callback_data='add_car')]]
        await update.message.reply_text(
            f"👋 Здравствуйте, {user.first_name}!\n\n🚗 У вас нет автомобилей. Добавьте первый:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_CAR

    keyboard = []
    for car_id, name, brand, model, year, vin, plate, mileage in cars:
        car_name = f"{brand} {model}" if brand and model else name
        keyboard.append([InlineKeyboardButton(f"🚗 {car_name} ({mileage} км)", callback_data=f'select_car_{car_id}')])

    keyboard.append([InlineKeyboardButton("➕ Добавить авто", callback_data='add_car')])

    await update.message.reply_text(
        "🚗 Выберите автомобиль:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_CAR


async def car_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, car_id: int) -> int:
    """Меню выбранного автомобиля"""
    user_id = update.effective_user.id
    car = bot.get_car_by_id(car_id, user_id)

    if not car:
        if update.callback_query:
            await update.callback_query.message.edit_text("❌ Автомобиль не найден")
        return await show_car_list(update, context)

    user_car_selection[user_id] = car_id

    car_name = f"{car[2]} {car[3]}" if car[2] and car[3] else car[1]
    stats = bot.get_car_statistics(car_id, user_id)

    # Проверка масла
    oil_warning = ""
    if stats and stats['last_oil_change']:
        last_mileage, oil_type, next_mileage, change_date, full_date = stats['last_oil_change']
        current = stats['last_mileage']
        if current >= next_mileage:
            oil_warning = "\n⚠️ ТРЕБУЕТСЯ ЗАМЕНА МАСЛА!"
        elif next_mileage - current < 1000:
            oil_warning = f"\n⏰ Осталось {next_mileage - current} км до замены масла"

    header = f"🚗 {car_name}\n"
    if car[6]:  # license_plate
        header += f"📋 Госномер: {car[6]}\n"
    if car[5]:  # VIN
        header += f"🔢 VIN: `{car[5]}`\n"
    header += f"💰 Всего: {stats['total']:,.0f} руб.\n"
    header += f"📊 Пробег: {stats['last_mileage']} км"
    header += oil_warning

    keyboard = [
        [InlineKeyboardButton("💰 Добавить расход", callback_data='add_expense')],
        [InlineKeyboardButton("🛢 Замена масла", callback_data='oil_change')],
        [InlineKeyboardButton("🔧 Техобслуживание", callback_data='service_menu')],
        [InlineKeyboardButton("📦 Расходники", callback_data='consumables_menu')],
        [InlineKeyboardButton("📚 Каталоги", callback_data='catalogs_menu')],
        [InlineKeyboardButton("📊 Статистика", callback_data='view_stats')],
        [InlineKeyboardButton("✏️ Редактировать авто", callback_data='edit_car')],
        [InlineKeyboardButton("🗑 Удалить авто", callback_data='delete_car')],
        [InlineKeyboardButton("🔙 К списку авто", callback_data='back_to_cars')]
    ]

    if update.callback_query:
        await update.callback_query.message.edit_text(
            header,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            header,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    return MAIN_MENU


async def show_car_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать список автомобилей"""
    user_id = update.effective_user.id
    cars = bot.get_user_cars(user_id)

    keyboard = []
    for car_id, name, brand, model, year, vin, plate, mileage in cars:
        car_name = f"{brand} {model}" if brand and model else name
        keyboard.append([InlineKeyboardButton(f"🚗 {car_name} ({mileage} км)", callback_data=f'select_car_{car_id}')])

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


async def catalogs_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Меню каталогов запчастей"""
    query = update.callback_query
    user_id = query.from_user.id
    current_car_id = user_car_selection.get(user_id)

    # Получаем информацию о текущем автомобиле
    car = None
    if current_car_id:
        car = bot.get_car_by_id(current_car_id, user_id)

    text = "📚 КАТАЛОГИ ЗАПЧАСТЕЙ\n\n"

    # Показываем VIN текущего автомобиля, если есть
    if car and car[5]:  # VIN
        text += f"🔢 VIN вашего автомобиля: `{car[5]}`\n"
        text += "Скопируйте VIN для поиска в каталогах\n\n"

    # Каталоги
    for key, cat in CAR_CATALOGS.items():
        text += f"🔗 {cat['name']}: {cat['url']}\n"
        text += f"📝 {cat['description']}\n\n"

    text += "💡 Вставьте VIN в поле поиска на сайте"

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return MAIN_MENU


async def show_oil_change_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню замены масла"""
    query = update.callback_query
    user_id = query.from_user.id
    current_car_id = user_car_selection.get(user_id)

    last_oil = bot.get_last_oil_change(current_car_id, user_id) if current_car_id else None

    text = ""
    if last_oil:
        mileage, oil_type, next_mileage, change_date, full_date = last_oil
        text = f"🛢 Последняя замена: {mileage} км, {oil_type}\n"
        text += f"📅 Дата: {change_date}\n"
        text += f"⏰ Следующая: {next_mileage} км\n\n"

    text += "Введите текущий пробег (км):"
    await query.message.edit_text(text, reply_markup=back_keyboard('menu'))
    return OIL_MILEAGE


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    current_car_id = user_car_selection.get(user_id)

    # Обработка кнопок "Назад"
    if query.data.startswith('back_to_'):
        target = query.data.replace('back_to_', '')
        if target == 'cars':
            return await show_car_list(update, context)
        elif target == 'menu' and current_car_id:
            return await car_menu(update, context, current_car_id)
        elif target == 'service_menu':
            return await service_menu(update, context)
        elif target == 'consumables':
            return await consumables_menu(update, context)
        elif target == 'oil_change':
            return await show_oil_change_menu(update, context)

    # Выбор автомобиля
    if query.data.startswith('select_car_'):
        car_id = int(query.data.replace('select_car_', ''))
        return await car_menu(update, context, car_id)

    # Добавление авто - пошагово
    elif query.data == 'add_car':
        await query.message.edit_text(
            "🚗 Введите название автомобиля:",
            reply_markup=back_keyboard('cars')
        )
        return CAR_NAME

    # Редактирование авто
    elif query.data == 'edit_car':
        if not current_car_id:
            return await show_car_list(update, context)

        car = bot.get_car_by_id(current_car_id, user_id)
        if not car:
            await query.message.edit_text("❌ Автомобиль не найден")
            return await show_car_list(update, context)

        # Показываем текущие данные и предлагаем ввести новые
        text = f"✏️ РЕДАКТИРОВАНИЕ АВТОМОБИЛЯ\n\n"
        text += f"Текущие данные:\n"
        text += f"📝 Название: {car[1]}\n"
        text += f"🏭 Марка: {car[2] or 'не указана'}\n"
        text += f"🚘 Модель: {car[3] or 'не указана'}\n"
        text += f"📅 Год: {car[4] or 'не указан'}\n"
        text += f"🔢 VIN: {car[5] or 'не указан'}\n"
        text += f"📋 Госномер: {car[6] or 'не указан'}\n\n"
        text += "Введите новое название автомобиля:"

        await query.message.edit_text(text, reply_markup=back_keyboard('menu'))
        return EDIT_CAR_NAME

    # Добавление расхода
    elif query.data == 'add_expense':
        await query.message.edit_text(
            "💰 Введите сумму расхода:",
            reply_markup=back_keyboard('menu')
        )
        return EXPENSE_AMOUNT

    # Замена масла
    elif query.data == 'oil_change':
        return await show_oil_change_menu(update, context)

    # Меню техобслуживания
    elif query.data == 'service_menu':
        return await service_menu(update, context)

    # Меню расходников
    elif query.data == 'consumables_menu':
        return await consumables_menu(update, context)

    # Меню каталогов
    elif query.data == 'catalogs_menu':
        return await catalogs_menu(update, context)

    # Добавление расходника
    elif query.data == 'add_consumable':
        await query.message.edit_text(
            "📦 Введите название расходника (например: Масляный фильтр):",
            reply_markup=back_keyboard('consumables')
        )
        return CONSUMABLE_NAME

    # Просмотр расходников
    elif query.data == 'view_consumables':
        return await view_consumables(update, context)

    # Удаление расходника
    elif query.data == 'delete_consumable_mode':
        return await delete_consumable_mode(update, context)

    elif query.data.startswith('delete_consumable_'):
        consumable_id = int(query.data.replace('delete_consumable_', ''))
        context.user_data['delete_consumable_id'] = consumable_id
        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data='confirm_delete_consumable')],
            [InlineKeyboardButton("❌ Нет, отмена", callback_data='view_consumables')]
        ]
        await query.message.edit_text(
            "⚠️ Вы уверены, что хотите удалить этот расходник?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return DELETE_CONSUMABLE

    elif query.data == 'confirm_delete_consumable':
        consumable_id = context.user_data.get('delete_consumable_id')
        if consumable_id and bot.delete_consumable(consumable_id, user_id):
            await query.message.edit_text("✅ Расходник удален!")
        else:
            await query.message.edit_text("❌ Ошибка при удалении")
        return await view_consumables(update, context)

    # Удаление автомобиля
    elif query.data == 'delete_car':
        if not current_car_id:
            return await show_car_list(update, context)

        car = bot.get_car_by_id(current_car_id, user_id)
        if not car:
            await query.message.edit_text("❌ Автомобиль не найден")
            return await show_car_list(update, context)

        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data='confirm_delete_car')],
            [InlineKeyboardButton("❌ Нет, отмена", callback_data='back_to_menu')]
        ]
        await query.message.edit_text(
            f"⚠️ ВНИМАНИЕ! Вы действительно хотите удалить автомобиль {car[1]}?\n\n"
            f"Все связанные данные будут безвозвратно удалены:\n"
            f"• История расходов\n"
            f"• Замены масла\n"
            f"• Техобслуживание\n"
            f"• Расходники\n\n"
            f"Это действие нельзя отменить!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return DELETE_CAR_CONFIRM

    elif query.data == 'confirm_delete_car':
        if current_car_id and bot.delete_car(current_car_id, user_id):
            user_car_selection.pop(user_id, None)
            await query.message.edit_text("✅ Автомобиль успешно удален!")
        else:
            await query.message.edit_text("❌ Ошибка при удалении автомобиля")
        return await show_car_list(update, context)

    # Плановое ТО или ремонт
    elif query.data in ['planned_service', 'repair_service']:
        service_type = "Плановое ТО" if query.data == 'planned_service' else "Ремонт"
        context.user_data['service_type'] = service_type
        await query.message.edit_text(
            f"{service_type}\n\nВведите пробег (км):",
            reply_markup=back_keyboard('service_menu')
        )
        return SERVICE_MILEAGE

    # История обслуживания
    elif query.data == 'service_history':
        if not current_car_id:
            return await show_car_list(update, context)

        services = bot.get_service_history(current_car_id, user_id, 10)

        if not services:
            text = "📋 История обслуживания пуста"
        else:
            text = "📋 ИСТОРИЯ ОБСЛУЖИВАНИЯ:\n\n"
            for stype, mileage, desc, cost, date in services:
                d = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
                text += f"📅 {d} | {mileage} км\n🔧 {stype}\n"
                if desc: text += f"📝 {desc}\n"
                if cost: text += f"💰 {cost:,.0f} руб.\n\n"

        await query.message.edit_text(text, reply_markup=back_keyboard('service_menu'))
        return SELECT_SERVICE_TYPE

    # Статистика
    elif query.data == 'view_stats' and current_car_id:
        stats = bot.get_car_statistics(current_car_id, user_id)
        car = bot.get_car_by_id(current_car_id, user_id)

        if not stats:
            await query.message.edit_text("❌ Ошибка загрузки")
            return await car_menu(update, context, current_car_id)

        text = f"📊 СТАТИСТИКА {car[1]}\n"
        text += f"{'=' * 30}\n\n"
        text += f"💰 Всего расходов: {stats['total']:,.0f} руб.\n"
        text += f"📊 Текущий пробег: {stats['last_mileage']} км\n"

        if stats['last_oil_change']:
            m, t, n, cd, d = stats['last_oil_change']
            text += f"\n🛢 Последняя замена масла:\n"
            text += f"   📅 {cd} | {m} км\n"
            text += f"   ⏰ Следующая: {n} км\n"

        text += f"\n📝 ПОСЛЕДНИЕ РАСХОДЫ:\n"
        text += f"{'-' * 30}\n"

        if stats['recent_expenses']:
            for amount, description, mileage, expense_date in stats['recent_expenses'][:10]:
                mileage_text = f" [{mileage} км]" if mileage else ""
                text += f"• {expense_date}{mileage_text}\n"
                text += f"  {description}: {amount:,.0f} руб.\n"
        else:
            text += "Нет расходов за последние 30 дней\n"

        await query.message.edit_text(text, reply_markup=back_keyboard('menu'))
        return MAIN_MENU

    return MAIN_MENU


async def service_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Меню техобслуживания"""
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("🔧 Плановое ТО", callback_data='planned_service')],
        [InlineKeyboardButton("🔨 Ремонт", callback_data='repair_service')],
        [InlineKeyboardButton("📋 История", callback_data='service_history')]
    ]
    await query.message.edit_text(
        "🔧 Техническое обслуживание:",
        reply_markup=keyboard_with_back(keyboard, 'menu')
    )
    return SELECT_SERVICE_TYPE


async def consumables_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Меню расходников"""
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("➕ Добавить расходник", callback_data='add_consumable')],
        [InlineKeyboardButton("📋 Список расходников", callback_data='view_consumables')],
        [InlineKeyboardButton("🗑 Удалить расходник", callback_data='delete_consumable_mode')]
    ]
    await query.message.edit_text(
        "📦 Управление расходниками:",
        reply_markup=keyboard_with_back(keyboard, 'menu')
    )
    return MAIN_MENU


async def view_consumables(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Просмотр расходников"""
    query = update.callback_query
    user_id = query.from_user.id
    current_car_id = user_car_selection.get(user_id)

    consumables = bot.get_consumables(user_id, current_car_id)

    if not consumables:
        text = "📦 Список расходников пуст"
    else:
        text = "📦 ВАШИ РАСХОДНИКИ:\n\n"
        for cid, name, part_num, notes, date in consumables:
            d = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
            text += f"📌 {name}\n"
            if part_num: text += f"   🔢 Артикул: {part_num}\n"
            if notes: text += f"   📝 {notes}\n"
            text += f"   📅 {d}\n\n"

    await query.message.edit_text(text, reply_markup=back_keyboard('consumables'))
    return MAIN_MENU


async def delete_consumable_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Режим выбора расходника для удаления"""
    query = update.callback_query
    user_id = query.from_user.id
    current_car_id = user_car_selection.get(user_id)

    consumables = bot.get_consumables(user_id, current_car_id)

    if not consumables:
        await query.message.edit_text(
            "📦 Нет расходников для удаления",
            reply_markup=back_keyboard('consumables')
        )
        return MAIN_MENU

    keyboard = []
    for cid, name, part_num, notes, date in consumables[:10]:
        display_name = f"{name}"
        if part_num:
            display_name += f" ({part_num})"
        keyboard.append([InlineKeyboardButton(f"❌ {display_name}", callback_data=f'delete_consumable_{cid}')])

    await query.message.edit_text(
        "🗑 Выберите расходник для удаления:",
        reply_markup=keyboard_with_back(keyboard, 'consumables')
    )
    return DELETE_CONSUMABLE


# === ПОШАГОВОЕ ДОБАВЛЕНИЕ АВТОМОБИЛЯ ===
async def car_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['car_name'] = update.message.text
    await update.message.reply_text(
        "Введите марку автомобиля (или отправьте '-' чтобы пропустить):",
        reply_markup=back_keyboard('cars')
    )
    return CAR_BRAND


async def car_brand_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    context.user_data['car_brand'] = text if text != '-' else ""
    await update.message.reply_text(
        "Введите модель (или отправьте '-' чтобы пропустить):",
        reply_markup=back_keyboard('cars')
    )
    return CAR_MODEL


async def car_model_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    context.user_data['car_model'] = text if text != '-' else ""
    await update.message.reply_text(
        "Введите год выпуска (или отправьте '-' чтобы пропустить):",
        reply_markup=back_keyboard('cars')
    )
    return CAR_YEAR


async def car_year_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    try:
        context.user_data['car_year'] = int(text) if text != '-' else None
    except:
        context.user_data['car_year'] = None
    await update.message.reply_text(
        "Введите VIN номер (или отправьте '-' чтобы пропустить):",
        reply_markup=back_keyboard('cars')
    )
    return CAR_VIN


async def car_vin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    context.user_data['car_vin'] = text if text != '-' else ""
    await update.message.reply_text(
        "Введите госномер (или отправьте '-' чтобы пропустить):",
        reply_markup=back_keyboard('cars')
    )
    return CAR_PLATE


async def car_plate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    license_plate = text if text != '-' else ""

    user_id = update.effective_user.id
    car_id = bot.add_car(
        user_id,
        context.user_data['car_name'],
        context.user_data.get('car_brand', ''),
        context.user_data.get('car_model', ''),
        context.user_data.get('car_year'),
        context.user_data.get('car_vin', ''),
        license_plate
    )

    # Очищаем временные данные
    for key in ['car_name', 'car_brand', 'car_model', 'car_year', 'car_vin']:
        context.user_data.pop(key, None)

    keyboard = [[InlineKeyboardButton(f"🚗 Перейти к авто", callback_data=f'select_car_{car_id}')]]
    await update.message.reply_text(
        "✅ Автомобиль успешно добавлен!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_CAR


# === ПОШАГОВОЕ РЕДАКТИРОВАНИЕ АВТОМОБИЛЯ ===
async def edit_car_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['edit_car_name'] = update.message.text
    await update.message.reply_text(
        "Введите новую марку автомобиля (или отправьте '-' чтобы оставить без изменений):",
        reply_markup=back_keyboard('menu')
    )
    return EDIT_CAR_BRAND


async def edit_car_brand_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    context.user_data['edit_car_brand'] = text if text != '-' else ""
    await update.message.reply_text(
        "Введите новую модель (или отправьте '-' чтобы оставить без изменений):",
        reply_markup=back_keyboard('menu')
    )
    return EDIT_CAR_MODEL


async def edit_car_model_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    context.user_data['edit_car_model'] = text if text != '-' else ""
    await update.message.reply_text(
        "Введите новый год выпуска (или отправьте '-' чтобы оставить без изменений):",
        reply_markup=back_keyboard('menu')
    )
    return EDIT_CAR_YEAR


async def edit_car_year_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    try:
        context.user_data['edit_car_year'] = int(text) if text != '-' else None
    except:
        context.user_data['edit_car_year'] = None
    await update.message.reply_text(
        "Введите новый VIN номер (или отправьте '-' чтобы оставить без изменений):",
        reply_markup=back_keyboard('menu')
    )
    return EDIT_CAR_VIN


async def edit_car_vin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    context.user_data['edit_car_vin'] = text if text != '-' else ""
    await update.message.reply_text(
        "Введите новый госномер (или отправьте '-' чтобы оставить без изменений):",
        reply_markup=back_keyboard('menu')
    )
    return EDIT_CAR_PLATE


async def edit_car_plate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    license_plate = text if text != '-' else ""

    user_id = update.effective_user.id
    car_id = user_car_selection.get(user_id)

    if bot.update_car(
            car_id,
            user_id,
            context.user_data['edit_car_name'],
            context.user_data.get('edit_car_brand', ''),
            context.user_data.get('edit_car_model', ''),
            context.user_data.get('edit_car_year'),
            context.user_data.get('edit_car_vin', ''),
            license_plate
    ):
        await update.message.reply_text("✅ Автомобиль успешно обновлен!")
    else:
        await update.message.reply_text("❌ Ошибка при обновлении автомобиля")

    # Очищаем временные данные
    for key in ['edit_car_name', 'edit_car_brand', 'edit_car_model', 'edit_car_year', 'edit_car_vin']:
        context.user_data.pop(key, None)

    return await car_menu(update, context, car_id)


# === ПОШАГОВОЕ ДОБАВЛЕНИЕ РАСХОДА ===
async def expense_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(',', '.'))
        context.user_data['expense_amount'] = amount
        await update.message.reply_text(
            "Введите описание расхода:",
            reply_markup=back_keyboard('menu')
        )
        return EXPENSE_DESC
    except:
        await update.message.reply_text(
            "❌ Неверный формат. Введите число (например: 1500):",
            reply_markup=back_keyboard('menu')
        )
        return EXPENSE_AMOUNT


async def expense_desc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['expense_desc'] = update.message.text
    await update.message.reply_text(
        "Введите пробег (км) или отправьте '-' чтобы пропустить:",
        reply_markup=back_keyboard('menu')
    )
    return EXPENSE_MILEAGE


async def expense_mileage_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    try:
        mileage = None if text == '-' else int(text)
        context.user_data['expense_mileage'] = mileage
    except:
        context.user_data['expense_mileage'] = None

    await update.message.reply_text(
        "Введите дату расхода в формате ДД.ММ.ГГГГ\n"
        "(или отправьте '-' чтобы использовать сегодняшнюю дату):",
        reply_markup=back_keyboard('menu')
    )
    return EXPENSE_DATE


async def expense_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    car_id = user_car_selection.get(user_id)

    text = update.message.text

    if text == '-':
        expense_date = datetime.now().strftime('%Y-%m-%d')
    else:
        try:
            day, month, year = map(int, text.split('.'))
            expense_date = datetime(year, month, day).strftime('%Y-%m-%d')
        except:
            await update.message.reply_text(
                "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ\n"
                "Например: 16.02.2026",
                reply_markup=back_keyboard('menu')
            )
            return EXPENSE_DATE

    if bot.add_daily_expense(
            car_id,
            user_id,
            context.user_data['expense_amount'],
            context.user_data['expense_desc'],
            context.user_data.get('expense_mileage'),
            expense_date
    ):
        date_formatted = datetime.strptime(expense_date, '%Y-%m-%d').strftime('%d.%m.%Y')
        await update.message.reply_text(f"✅ Расход на {date_formatted} добавлен!")
    else:
        await update.message.reply_text("❌ Ошибка при добавлении расхода")

    # Очищаем данные
    for key in ['expense_amount', 'expense_desc', 'expense_mileage']:
        context.user_data.pop(key, None)

    return await car_menu(update, context, car_id)


# === ПОШАГОВАЯ ЗАМЕНА МАСЛА ===
async def oil_mileage_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        mileage = int(update.message.text)
        context.user_data['oil_mileage'] = mileage
        await update.message.reply_text(
            "Введите тип масла (или отправьте '-' чтобы пропустить):",
            reply_markup=back_keyboard('oil_change')
        )
        return OIL_TYPE
    except:
        await update.message.reply_text(
            "❌ Введите число (пробег в км):",
            reply_markup=back_keyboard('menu')
        )
        return OIL_MILEAGE


async def oil_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    context.user_data['oil_type'] = text if text != '-' else ""
    await update.message.reply_text(
        "Введите интервал замены (км) или отправьте '-' для стандартного (10000 км):",
        reply_markup=back_keyboard('oil_change')
    )
    return OIL_INTERVAL


async def oil_interval_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == '-':
        context.user_data['oil_interval'] = None
    else:
        try:
            interval = int(text)
            context.user_data['oil_interval'] = interval
        except:
            context.user_data['oil_interval'] = None

    await update.message.reply_text(
        "Введите дату замены в формате ДД.ММ.ГГГГ\n"
        "(или отправьте '-' чтобы использовать сегодняшнюю дату):",
        reply_markup=back_keyboard('oil_change')
    )
    return OIL_DATE


async def oil_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    car_id = user_car_selection.get(user_id)

    text = update.message.text

    if text == '-':
        change_date = datetime.now().strftime('%Y-%m-%d')
    else:
        try:
            day, month, year = map(int, text.split('.'))
            change_date = datetime(year, month, day).strftime('%Y-%m-%d')
        except:
            await update.message.reply_text(
                "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ",
                reply_markup=back_keyboard('oil_change')
            )
            return OIL_DATE

    mileage = context.user_data['oil_mileage']
    interval = context.user_data.get('oil_interval')
    next_mileage = mileage + interval if interval else mileage + 10000

    if bot.add_oil_change(
            car_id,
            user_id,
            mileage,
            context.user_data.get('oil_type', ''),
            next_mileage,
            change_date
    ):
        date_formatted = datetime.strptime(change_date, '%Y-%m-%d').strftime('%d.%m.%Y')
        await update.message.reply_text(f"✅ Замена масла на {date_formatted} зарегистрирована!")
    else:
        await update.message.reply_text("❌ Ошибка при регистрации замены масла")

    # Очищаем данные
    context.user_data.pop('oil_mileage', None)
    context.user_data.pop('oil_type', None)
    context.user_data.pop('oil_interval', None)

    return await car_menu(update, context, car_id)


# === ПОШАГОВОЕ ТЕХОБСЛУЖИВАНИЕ ===
async def service_mileage_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        mileage = int(update.message.text)
        context.user_data['service_mileage'] = mileage
        await update.message.reply_text(
            "Введите описание работ:",
            reply_markup=back_keyboard('service_menu')
        )
        return SERVICE_DESC
    except:
        await update.message.reply_text(
            "❌ Введите число (пробег в км):",
            reply_markup=back_keyboard('service_menu')
        )
        return SERVICE_MILEAGE


async def service_desc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['service_desc'] = update.message.text
    await update.message.reply_text(
        "Введите стоимость (или отправьте '-' если неизвестно):",
        reply_markup=back_keyboard('service_menu')
    )
    return SERVICE_COST


async def service_cost_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    car_id = user_car_selection.get(user_id)

    text = update.message.text
    try:
        cost = 0 if text == '-' else float(text.replace(',', '.'))
    except:
        cost = 0

    service_type = context.user_data.get('service_type', 'Техобслуживание')

    if bot.add_service_record(
            car_id,
            user_id,
            service_type,
            context.user_data['service_mileage'],
            context.user_data.get('service_desc', ''),
            cost
    ):
        await update.message.reply_text("✅ Запись о ТО добавлена!")
    else:
        await update.message.reply_text("❌ Ошибка при добавлении записи")

    # Очищаем данные
    context.user_data.pop('service_mileage', None)
    context.user_data.pop('service_desc', None)
    context.user_data.pop('service_type', None)

    return await car_menu(update, context, car_id)


# === ПОШАГОВОЕ ДОБАВЛЕНИЕ РАСХОДНИКА ===
async def consumable_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['consumable_name'] = update.message.text
    await update.message.reply_text(
        "Введите артикул (или отправьте '-' чтобы пропустить):",
        reply_markup=back_keyboard('consumables')
    )
    return CONSUMABLE_PART_NUMBER


async def consumable_part_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    context.user_data['consumable_part'] = text if text != '-' else ""

    user_id = update.effective_user.id
    cars = bot.get_user_cars(user_id)

    if len(cars) == 1:
        car_id = cars[0][0]
        bot.add_consumable(
            user_id,
            car_id,
            context.user_data['consumable_name'],
            context.user_data['consumable_part'],
            ""
        )

        context.user_data.pop('consumable_name', None)
        context.user_data.pop('consumable_part', None)

        await update.message.reply_text("✅ Расходник добавлен!")
        return await car_menu(update, context, car_id)
    else:
        keyboard = []
        for car_id, name, brand, model, year, vin, plate, mileage in cars:
            car_name = f"{brand} {model}" if brand and model else name
            keyboard.append([InlineKeyboardButton(f"🚗 {car_name}", callback_data=f'consumable_car_{car_id}')])

        await update.message.reply_text(
            "Выберите автомобиль для расходника:",
            reply_markup=keyboard_with_back(keyboard, 'consumables')
        )
        return CONSUMABLE_CAR


async def consumable_car_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data.startswith('consumable_car_'):
        car_id = int(query.data.replace('consumable_car_', ''))
        user_id = query.from_user.id

        bot.add_consumable(
            user_id,
            car_id,
            context.user_data['consumable_name'],
            context.user_data['consumable_part'],
            ""
        )

        context.user_data.pop('consumable_name', None)
        context.user_data.pop('consumable_part', None)

        await query.message.edit_text("✅ Расходник добавлен!")
        return await car_menu(update, context, car_id)

    return MAIN_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    current_car_id = user_car_selection.get(user_id)

    if current_car_id:
        await update.message.reply_text("❌ Действие отменено")
        return await car_menu(update, context, current_car_id)
    else:
        await update.message.reply_text("❌ Действие отменено")
        return await show_car_list(update, context)


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECT_CAR: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, car_name_handler)
            ],
            MAIN_MENU: [CallbackQueryHandler(button_handler)],

            # Состояния добавления авто
            CAR_NAME: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, car_name_handler)
            ],
            CAR_BRAND: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, car_brand_handler)
            ],
            CAR_MODEL: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, car_model_handler)
            ],
            CAR_YEAR: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, car_year_handler)
            ],
            CAR_VIN: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, car_vin_handler)
            ],
            CAR_PLATE: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, car_plate_handler)
            ],

            # Состояния редактирования авто
            EDIT_CAR_NAME: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_car_name_handler)
            ],
            EDIT_CAR_BRAND: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_car_brand_handler)
            ],
            EDIT_CAR_MODEL: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_car_model_handler)
            ],
            EDIT_CAR_YEAR: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_car_year_handler)
            ],
            EDIT_CAR_VIN: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_car_vin_handler)
            ],
            EDIT_CAR_PLATE: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_car_plate_handler)
            ],

            # Состояния расхода
            EXPENSE_AMOUNT: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, expense_amount_handler)
            ],
            EXPENSE_DESC: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, expense_desc_handler)
            ],
            EXPENSE_MILEAGE: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, expense_mileage_handler)
            ],
            EXPENSE_DATE: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, expense_date_handler)
            ],

            # Состояния замены масла
            OIL_MILEAGE: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, oil_mileage_handler)
            ],
            OIL_TYPE: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, oil_type_handler)
            ],
            OIL_INTERVAL: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, oil_interval_handler)
            ],
            OIL_DATE: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, oil_date_handler)
            ],

            # Состояния ТО
            SERVICE_MILEAGE: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, service_mileage_handler)
            ],
            SERVICE_DESC: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, service_desc_handler)
            ],
            SERVICE_COST: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, service_cost_handler)
            ],

            # Состояния расходников
            CONSUMABLE_NAME: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, consumable_name_handler)
            ],
            CONSUMABLE_PART_NUMBER: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, consumable_part_handler)
            ],
            CONSUMABLE_CAR: [CallbackQueryHandler(consumable_car_handler)],
            DELETE_CONSUMABLE: [CallbackQueryHandler(button_handler)],

            # Состояние подтверждения удаления авто
            DELETE_CAR_CONFIRM: [CallbackQueryHandler(button_handler)],

            SELECT_SERVICE_TYPE: [CallbackQueryHandler(button_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )

    application.add_handler(conv_handler)
    print("🚗 Бот запущен...")
    print("✅ Кнопка 'Назад' есть во всех меню")
    print("✅ Добавлена дата в замену масла")
    print("✅ Пробег автоматически обновляется")
    print("✅ Удаление расходников")
    print("✅ Удаление автомобилей")
    print("✅ Редактирование автомобилей")
    print("✅ Каталоги: Japancats и ETK")
    print("✅ VIN отображается в каталогах")
    application.run_polling()


if __name__ == '__main__':
    main()