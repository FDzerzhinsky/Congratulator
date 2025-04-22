import logging
from telegram.ext import Application
from handlers import get_handlers
from config import TOKEN, LOG_LEVEL

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=LOG_LEVEL
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Запуск бота"""
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики
    for handler in get_handlers():
        application.add_handler(handler)

    # Запускаем бота
    logger.info("Бот запущен!")
    application.run_polling()


if __name__ == "__main__":
    main()