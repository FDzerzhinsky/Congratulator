from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler
)
from datetime import datetime
import random
from database import Session, Department, Employee
from keyboards import (
    admin_main_menu,
    department_pagination,
    employee_details_keyboard
)
from utils import is_admin, generate_confirm_code, validate_date
from config import PAGE_SIZE, LOG_LEVEL, CONFIRM_CODE_LENGTH
from states import *

# Настройка логирования
logging.basicConfig(level=LOG_LEVEL)
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
    dept_name = update.message.text.strip()

    with Session() as session:
        if session.query(Department).filter_by(name=dept_name).first():
            await update.message.reply_text("❌ Отдел с таким названием уже существует!")
            return ADD_DEPARTMENT

        new_dept = Department(name=dept_name)
        session.add(new_dept)
        session.commit()

    await update.message.reply_text(f"✅ Отдел '{dept_name}' успешно создан!")
    return await show_main_menu(update, context)


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
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    if is_admin(user_id):
        keyboard = admin_main_menu()
    else:
        keyboard = user_main_menu(user_id)

    if query:
        await query.message.edit_text("🏠 Главное меню:", reply_markup=keyboard)
    else:
        await update.message.reply_text("🏠 Главное меню:", reply_markup=keyboard)

    return MAIN_MENU


# ================== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ==================

def get_handlers() -> list:
    """Возвращает список обработчиков для регистрации"""
    return [
        ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                MAIN_MENU: [
                    CallbackQueryHandler(view_departments, pattern=r"^view_departments"),
                    CallbackQueryHandler(add_department_start, pattern=r"^add_department")
                ],
                ADD_DEPARTMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_department_finish)
                ],
                CONFIRM_DELETE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, execute_delete)
                ]
            },
            fallbacks=[CallbackQueryHandler(show_main_menu, pattern=r"^main_menu")]
        )
    ]