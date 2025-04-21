# utils.py
import random
from config import ADMIN_IDS, CONFIRM_CODE_LENGTH
from datetime import datetime

def is_admin(user_id: int) -> bool:
    """Проверка прав администратора"""
    return user_id in ADMIN_IDS

def generate_confirm_code() -> str:
    """Генерация кода подтверждения"""
    return ''.join(random.choices('0123456789', k=CONFIRM_CODE_LENGTH))

def validate_date(date_str: str) -> bool:
    """Валидация даты в формате ДД.ММ.ГГГГ"""
    try:
        datetime.strptime(date_str, "%d.%m.%Y")
        return True
    except ValueError:
        return False