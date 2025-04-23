import logging
from telegram import Update
from telegram.ext import Application, ContextTypes
from handlers import get_handlers
from config import TOKEN, LOG_LEVEL

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=LOG_LEVEL
)
logger = logging.getLogger(__name__)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    if update and update.message:
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")


def main() -> None:
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики
    for handler in get_handlers():
        application.add_handler(handler)

    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    logger.info("Бот запущен!")
    application.run_polling()


if __name__ == "__main__":
    main()