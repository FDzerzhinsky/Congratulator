# keyboards.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import PAGE_SIZE
from database import Department, Employee

def admin_main_menu() -> InlineKeyboardMarkup:
    """Главное меню администратора"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить отдел", callback_data="add_department"),
         InlineKeyboardButton("👥 Добавить сотрудника", callback_data="add_employee")],  # Проверьте callback_data
        [InlineKeyboardButton("📂 Просмотреть отделы", callback_data="view_departments_1")]
    ])

def department_pagination(page: int, total: int) -> list:
    """Кнопки пагинации для списка отделов"""
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"view_departments_{page-1}"))
    if page * PAGE_SIZE < total:
        buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"view_departments_{page+1}"))
    return buttons

def employee_details_keyboard(emp_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    """Клавиатура для деталей сотрудника"""
    buttons = []
    if is_admin:
        buttons.extend([
            [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_emp_{emp_id}")],
            [InlineKeyboardButton("🗑️ Удалить", callback_data=f"del_emp_{emp_id}")]
        ])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_department")])
    return InlineKeyboardMarkup(buttons)

def user_main_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Мои сотрудники", callback_data="view_my_department")]
    ])