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
from keyboards import admin_main_menu, user_main_menu, department_pagination
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


async def execute_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение удаления"""
    user_input = update.message.text
    confirm_code = context.user_data.get('confirm_code')
    target_type, target_id = context.user_data.get('delete_target')

    if user_input != confirm_code:
        await update.message.reply_text("❌ Неверный код подтверждения!")
        return await show_main_menu(update, context)

    with Session() as session:
        if target_type == "department":
            department = session.get(Department, target_id)
            session.delete(department)
        elif target_type == "employee":
            employee = session.get(Employee, target_id)
            session.delete(employee)

        session.commit()

    await update.message.reply_text("✅ Удаление выполнено успешно!")
    return await show_main_menu(update, context)


# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    try:
        query = update.callback_query
        if query:
            await query.answer()
            message = query.message
        else:
            message = update.message

        user_id = update.effective_user.id
        keyboard = admin_main_menu() if is_admin(user_id) else user_main_menu(user_id)

        await message.edit_text("🏠 Главное меню:", reply_markup=keyboard)
        return MAIN_MENU

    except Exception as e:
        logger.error(f"Ошибка в show_main_menu: {str(e)}", exc_info=True)
        return ConversationHandler.END

async def add_employee_general_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        await update.callback_query.message.edit_text(
            "Выберите отдел для сотрудника:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return ADD_EMPLOYEE_START

    except Exception as e:
        logger.error(f"Ошибка в add_employee_general_start: {str(e)}")
        await update.callback_query.message.reply_text("⚠️ Ошибка при загрузке отделов.")
        return ConversationHandler.END


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

    await update.message.reply_text("✅ Сотрудник успешно добавлен!")
    return await show_main_menu(update, context)

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
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],
                ADD_DEPARTMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_department_finish),
                    CallbackQueryHandler(show_main_menu, pattern=r"^main_menu$")
                ],
                ADD_EMPLOYEE_START: [
                    CallbackQueryHandler(add_employee_start, pattern=r"^add_emp_"),
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
                ]
            },
            fallbacks=[CommandHandler("start", start)]
        )
    ]