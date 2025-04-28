# handlers.py
import logging
from datetime import datetime
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler
)
from database import Session, Department, Employee
from keyboards import *
from utils import is_admin, generate_confirm_code, validate_date
from states import *
from config import PAGE_SIZE

# Настройка логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ================== ОСНОВНЫЕ ОБРАБОТЧИКИ ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user

    if is_admin(user.id):
        keyboard = admin_main_menu()
        text = "👑 Вы вошли как администратор"
    else:
        keyboard = user_main_menu(user.id)
        text = "🔍 Вы можете просматривать сотрудников вашего отдела"

    await update.message.reply_text(text, reply_markup=keyboard)
    return MAIN_MENU


async def view_departments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ списка отделов с пагинацией"""
    query = update.callback_query
    page = int(query.data.split('_')[-1])

    with Session() as session:
        departments = Department.get_all(session, page, PAGE_SIZE)
        total = Department.get_count(session)

    buttons = []
    for dept in departments:
        buttons.append([InlineKeyboardButton(
            dept.name,
            callback_data=f"dept_{dept.id}"
        )])

    # Добавляем пагинацию
    buttons.append(department_pagination(page, total))
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])

    await query.edit_message_text(
        "📂 Список отделов:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return VIEW_DEPARTMENTS


async def edit_department_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт редактирования отдела"""
    query = update.callback_query
    dept_id = int(query.data.split('_')[2])
    context.user_data['edit_dept'] = dept_id

    buttons = [
        [InlineKeyboardButton("✏️ Переименовать", callback_data=f"edit_dept_name_{dept_id}")],
        [InlineKeyboardButton("❌ Удалить отдел", callback_data=f"delete_dept_{dept_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"dept_{dept_id}")]
    ]

    await query.message.edit_text(
        "Выберите действие для отдела:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return EDIT_DEPARTMENT
# ================== ОБРАБОТЧИКИ ДОБАВЛЕНИЯ ==================

async def add_department_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления отдела"""
    if not is_admin(update.effective_user.id):
        await update.callback_query.answer("🚫 Доступ запрещён!", show_alert=True)
        return

    await update.callback_query.message.edit_text(
        "📝 Введите название нового отдела:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="main_menu")]
        ])
    )
    return ADD_DEPARTMENT


async def add_department_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение нового отдела"""
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("🚫 Доступ запрещён!")
            return ConversationHandler.END

        dept_name = update.message.text.strip()

        with Session() as session:
            if session.query(Department).filter_by(name=dept_name).first():
                await update.message.reply_text("❌ Отдел с таким названием уже существует!")
                return ADD_DEPARTMENT  # Повторно запрашиваем название

            new_dept = Department(name=dept_name)
            session.add(new_dept)
            session.commit()

        await update.message.reply_text(f"✅ Отдел '{dept_name}' успешно создан!")
        return await show_main_menu(update, context)  # Возвращаемся в главное меню

    except Exception as e:
        logger.error(f"Ошибка при создании отдела: {str(e)}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла внутренняя ошибка. Попробуйте позже.")
        return ConversationHandler.END


# ================== ОБРАБОТЧИКИ УДАЛЕНИЯ ==================

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления"""
    query = update.callback_query
    target_type, target_id = query.data.split('_')[1:]

    context.user_data['delete_target'] = (target_type, int(target_id))
    confirm_code = generate_confirm_code()
    context.user_data['confirm_code'] = confirm_code

    await query.message.edit_text(
        f"⚠️ Введите код подтверждения: {confirm_code}\n"
        "❗️Это действие нельзя отменить!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="cancel_delete")]
        ])
    )
    return CONFIRM_DELETE


async def confirm_delete_department(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления отдела"""
    query = update.callback_query
    dept_id = int(query.data.split('_')[2])
    context.user_data['delete_target'] = {'type': 'department', 'id': dept_id}

    confirm_code = generate_confirm_code()
    context.user_data['confirm_code'] = confirm_code

    with Session() as session:
        dept = session.get(Department, dept_id)
        emp_count = Employee.get_count_by_department(session, dept_id)

    await query.message.edit_text(
        f"❌ Вы действительно хотите удалить отдел {dept.name}?\n"
        f"Это приведёт к удалению {emp_count} сотрудников!\n"
        f"Для подтверждения введите код: {confirm_code}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Отмена", callback_data=f"dept_{dept_id}")]])
    )
    return CONFIRM_DELETE


async def execute_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение удаления"""
    user_input = update.message.text
    confirm_code = context.user_data.get('confirm_code')
    delete_target = context.user_data.get('delete_target')

    if not delete_target or user_input != confirm_code:
        await update.message.reply_text("❌ Неверный код подтверждения!")
        return await show_main_menu(update, context)

    with Session() as session:
        if delete_target['type'] == "department":
            department = session.get(Department, delete_target['id'])
            session.delete(department)
        session.commit()

    await update.message.reply_text("✅ Отдел успешно удалён!")
    return await show_main_menu(update, context)

async def edit_department_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование названия отдела"""
    query = update.callback_query
    await query.answer()  # Добавить подтверждение нажатия
    dept_id = int(query.data.split('_')[3])  # Индекс 3 для паттерна edit_dept_name_123
    context.user_data['edit_dept'] = dept_id

    await query.message.edit_text(
        "📝 Введите новое название отдела:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_dept_{dept_id}")]
        ])
    )
    return EDIT_DEPARTMENT_NAME  # Использовать отдельное состояние для ввода названия

async def save_department_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    dept_id = context.user_data.get('edit_dept')

    with Session() as session:
        department = session.get(Department, dept_id)
        department.name = new_name
        session.commit()

    await update.message.reply_text(f"✅ Отдел переименован в '{new_name}'!")
    return await view_employees(update, context, dept_id=dept_id)  # Вернуться к списку сотрудников

async def edit_employee_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт редактирования сотрудника"""
    query = update.callback_query
    await query.answer()  # Добавить подтверждение нажатия
    emp_id = int(query.data.split('_')[2])
    context.user_data['edit_emp'] = emp_id

    buttons = [
        [InlineKeyboardButton("✏️ ФИО", callback_data=f"edit_emp_name_{emp_id}")],
        [InlineKeyboardButton("📅 Дата рождения", callback_data=f"edit_emp_birth_{emp_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"emp_{emp_id}")]  # Исправлен паттерн
    ]

    await query.message.edit_text(
        "Выберите поле для редактирования:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return EDIT_EMPLOYEE_FIELD


async def delete_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление сотрудника"""
    query = update.callback_query
    emp_id = int(query.data.split('_')[2])

    with Session() as session:
        employee = session.get(Employee, emp_id)
        session.delete(employee)
        session.commit()

    await query.answer("✅ Сотрудник удалён!")
    return await view_employees(update, context, dept_id=employee.department_id)


# ================== ОБРАБОТЧИКИ РЕДАКТИРОВАНИЯ СОТРУДНИКА ==================
async def edit_employee_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование ФИО сотрудника"""
    query = update.callback_query
    await query.answer()
    emp_id = int(query.data.split('_')[3])
    context.user_data['edit_emp'] = emp_id

    await query.message.edit_text(
        "✏️ Введите новое ФИО сотрудника:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data=f"emp_{emp_id}")]
        ])
    )
    return EDIT_EMPLOYEE_NAME  # Добавьте это состояние в states.py

async def edit_employee_birth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование даты рождения сотрудника"""
    query = update.callback_query
    await query.answer()
    emp_id = int(query.data.split('_')[3])
    context.user_data['edit_emp'] = emp_id

    await query.message.edit_text(
        "📅 Введите новую дату рождения (ДД.ММ.ГГГГ):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data=f"emp_{emp_id}")]
        ])
    )
    return EDIT_EMPLOYEE_BIRTH  # Добавьте это состояние в states.py


async def save_employee_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    emp_id = context.user_data.get('edit_emp')

    with Session() as session:
        employee = session.get(Employee, emp_id)
        employee.full_name = new_name
        session.commit()

    await update.message.reply_text("✅ ФИО обновлено!")
    return await view_employee_details(update, context)


async def save_employee_birth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_str = update.message.text
    if not validate_date(date_str):
        await update.message.reply_text("❌ Неверный формат даты!")
        return EDIT_EMPLOYEE_BIRTH

    emp_id = context.user_data.get('edit_emp')
    with Session() as session:
        employee = session.get(Employee, emp_id)
        employee.birth_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        session.commit()

    await update.message.reply_text("✅ Дата рождения обновлена!")
    return await view_employee_details(update, context)

# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    try:
        user_id = update.effective_user.id
        keyboard = admin_main_menu() if is_admin(user_id) else user_main_menu(user_id)

        # Отправляем новое сообщение с клавиатурой
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🏠 Главное меню:",
            reply_markup=keyboard
        )

        # Очищаем историю сообщений из контекста
        if "message_ids" in context.user_data:
            del context.user_data["message_ids"]

        return MAIN_MENU

    except Exception as e:
        logger.error(f"Ошибка в show_main_menu: {str(e)}", exc_info=True)
        return ConversationHandler.END


async def add_employee_general_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт добавления сотрудника (выбор отдела из главного меню)"""
    if not is_admin(update.effective_user.id):
        await update.callback_query.answer("🚫 Доступ запрещён!", show_alert=True)
        return ConversationHandler.END

    try:
        with Session() as session:
            departments = Department.get_all(session)

        buttons = [
            [InlineKeyboardButton(dept.name, callback_data=f"add_emp_{dept.id}")]
            for dept in departments
        ]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])

        # Используем answer_callback_query для подтверждения нажатия
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(
            "Выберите отдел для сотрудника:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return ADD_EMPLOYEE_START

    except Exception as e:
        logger.error(f"Ошибка в add_employee_general_start: {str(e)}")
        await update.callback_query.message.reply_text("⚠️ Ошибка при загрузке отделов.")
        return ConversationHandler.END

async def add_employee_from_department(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки 'Добавить сотрудника' внутри отдела"""
    query = update.callback_query
    await query.answer()
    dept_id = int(query.data.split('_')[2])
    context.user_data['current_dept'] = dept_id

    await query.message.reply_text(
        "Введите ФИО сотрудника:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data=f"dept_{dept_id}")]])
    )
    return ADD_EMPLOYEE_NAME

async def add_employee_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало ввода данных сотрудника"""
    query = update.callback_query
    dept_id = int(query.data.split("_")[2])
    context.user_data["current_dept"] = dept_id

    await query.message.edit_text(
        "Введите ФИО сотрудника:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="main_menu")]
        ])
    )
    return ADD_EMPLOYEE_NAME


# ================== ОБРАБОТЧИКИ ДОБАВЛЕНИЯ СОТРУДНИКА ==================

async def add_employee_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода ФИО сотрудника"""
    context.user_data['new_employee'] = {'full_name': update.message.text}
    if 'current_dept' not in context.user_data:
        await update.message.reply_text("❌ Ошибка контекста. Начните заново.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📅 Введите дату рождения сотрудника (ДД.ММ.ГГГГ):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="main_menu")]
        ])
    )
    return ADD_EMPLOYEE_BIRTH


async def add_employee_birth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода даты рождения"""
    date_str = update.message.text

    if not validate_date(date_str):
        await update.message.reply_text("❌ Неверный формат даты! Введите ДД.ММ.ГГГГ:")
        return ADD_EMPLOYEE_BIRTH

    context.user_data['new_employee']['birth_date'] = datetime.strptime(date_str, "%d.%m.%Y").date()

    await update.message.reply_text(
        "🆔 Введите Telegram ID сотрудника (или 'пропустить'):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADD_EMPLOYEE_TG_ID


async def add_employee_tg_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода Telegram ID"""
    tg_id = update.message.text
    context_data = context.user_data['new_employee']

    try:
        if tg_id.lower() != 'пропустить':
            context_data['telegram_id'] = int(tg_id)
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID! Введите число:")
        return ADD_EMPLOYEE_TG_ID

    # Сохранение сотрудника
    with Session() as session:
        new_employee = Employee(
            full_name=context_data['full_name'],
            birth_date=context_data['birth_date'],
            telegram_id=context_data.get('telegram_id'),
            department_id=context.user_data['current_dept']
        )
        session.add(new_employee)
        session.commit()

    # Очищаем контекст
    context.user_data.clear()

    # Отправляем сообщение и клавиатуру через новый метод
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="✅ Сотрудник успешно добавлен!"
    )
    return await show_main_menu(update, context)


async def view_employees(update: Update, context: ContextTypes.DEFAULT_TYPE, dept_id: int = None):
    query = update.callback_query
    if query:
        await query.answer()
        dept_id = int(query.data.split('_')[1]) if not dept_id else dept_id
    else:
        dept_id = context.user_data.get('current_dept')

    with Session() as session:
        department = session.get(Department, dept_id)
        employees = Employee.get_by_department(session, dept_id, page=1)

    buttons = []
    for emp in employees:
        prefix = "👑 " if emp.is_head else ""
        buttons.append([InlineKeyboardButton(f"{prefix}{emp.full_name}", callback_data=f"emp_{emp.id}")])

    if is_admin(update.effective_user.id):
        buttons.append([
            InlineKeyboardButton("✏️ Редактировать отдел", callback_data=f"edit_dept_{dept_id}"),
            InlineKeyboardButton("➕ Добавить сотрудника", callback_data=f"add_emp_{dept_id}")
        ])

    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="view_departments_1")])

    if query:
        await query.edit_message_text(
            f"Отдел: {department.name}\nСотрудники:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Отдел: {department.name}\nСотрудники:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    return VIEW_EMPLOYEES


async def view_employee_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ детальной информации о сотруднике"""
    query = update.callback_query
    await query.answer()
    emp_id = int(query.data.split('_')[1])

    # Сохраняем ID сотрудника для возврата
    context.user_data['last_emp_id'] = emp_id  # Добавлено

    with Session() as session:
        employee = session.get(Employee, emp_id)
        department = employee.department

    # Сохраняем ID отдела для кнопки "Назад"
    context.user_data['current_dept'] = department.id

    text = (
        f"👤 {employee.full_name}\n"
        f"🎂 Дата рождения: {employee.birth_date.strftime('%d.%m.%Y')}\n"
        f"🏢 Отдел: {department.name}\n"
        f"🆔 Telegram ID: {employee.telegram_id or 'не указан'}"
    )

    keyboard = employee_details_keyboard(emp_id, is_admin(query.from_user.id))
    await query.message.edit_text(text, reply_markup=keyboard)
    return VIEW_EMPLOYEE_DETAILS

# ================== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ==================

def get_handlers() -> list:
    return [
        ConversationHandler(
            entry_points=[
                CommandHandler("start", start),
                CallbackQueryHandler(add_employee_general_start, pattern=r"^add_employee$")
            ],
            states={
                MAIN_MENU: [
                    CallbackQueryHandler(view_departments, pattern=r"^view_departments_"),
                    CallbackQueryHandler(add_department_start, pattern=r"^add_department$"),
                    CallbackQueryHandler(add_employee_general_start, pattern=r"^add_employee$"),
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],
                ADD_DEPARTMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_department_finish),
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],
                VIEW_DEPARTMENTS: [
                    # Добавьте это:
                    CallbackQueryHandler(view_employees, pattern=r"^dept_"),
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],
                EDIT_DEPARTMENT: [
                    CallbackQueryHandler(edit_department_name, pattern=r"^edit_dept_name_"),
                    CallbackQueryHandler(confirm_delete_department, pattern=r"^delete_dept_"),
                    CallbackQueryHandler(view_employees, pattern=r"^dept_"),
                ],
                EDIT_DEPARTMENT_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_department_name),
                    CallbackQueryHandler(lambda update, context: edit_department_start(update, context)),
                ],
                VIEW_EMPLOYEES: [
                    CallbackQueryHandler(view_employee_details, pattern=r"^emp_"),
                    CallbackQueryHandler(add_employee_start, pattern=r"^add_emp_"),  # Обработка добавления сотрудника
                    CallbackQueryHandler(edit_department_start, pattern=r"^edit_dept_"),  # Редактирование отдела
                    CallbackQueryHandler(view_departments, pattern=r"^view_departments_"),  # Кнопка "Назад"
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],
                VIEW_EMPLOYEE_DETAILS: [
                    CallbackQueryHandler(edit_employee_start, pattern=r"^edit_emp_"),
                    CallbackQueryHandler(delete_employee, pattern=r"^del_emp_"),
                    CallbackQueryHandler(
                        view_employee_details,  # Изменено с lambda-функции
                        pattern=r"^emp_"
                    ),
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],

                ADD_EMPLOYEE_START: [
                    CallbackQueryHandler(add_employee_from_department, pattern=r"^add_emp_"),
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],
                ADD_EMPLOYEE_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_employee_name),
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],
                ADD_EMPLOYEE_BIRTH: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_employee_birth),
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],
                ADD_EMPLOYEE_TG_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_employee_tg_id),
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],
                EDIT_EMPLOYEE_FIELD: [
                    CallbackQueryHandler(edit_employee_name, pattern=r"^edit_emp_name_"),
                    CallbackQueryHandler(edit_employee_birth, pattern=r"^edit_emp_birth_"),
                    CallbackQueryHandler(view_employee_details, pattern=r"^emp_"),  # Обработка кнопки "Назад"
                ],
                EDIT_EMPLOYEE_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_employee_name),
                    CallbackQueryHandler(lambda update, ctx: view_employee_details(update, ctx)),
                ],
                EDIT_EMPLOYEE_BIRTH: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_employee_birth),
                    CallbackQueryHandler(lambda update, ctx: view_employee_details(update, ctx)),
                ],
                CONFIRM_DELETE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, execute_delete),
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],
            },
            fallbacks=[CommandHandler("start", start)]
        ),
        CallbackQueryHandler(view_employees, pattern=r"^dept_"),
        CallbackQueryHandler(edit_department_start, pattern=r"^edit_dept_"),
        CallbackQueryHandler(confirm_delete_department, pattern=r"^delete_dept_"),
        CallbackQueryHandler(add_employee_from_department, pattern=r"^add_emp_"),
        CallbackQueryHandler(edit_employee_start, pattern=r"^edit_emp_"),
        CallbackQueryHandler(delete_employee, pattern=r"^del_emp_"),
        CallbackQueryHandler(view_employee_details, pattern=r"^emp_")  # Для возврата из редактирования
    ]