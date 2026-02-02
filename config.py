import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Токен бота из переменных окружения
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_URL = os.getenv("API_URL", "http://localhost:8081")

    # Настройки по умолчанию
    DEFAULT_DPI = 300
    DEFAULT_CONTRAST = 1.15
    DEFAULT_BRIGHTNESS = 0

    # Максимальный размер файла (в байтах)
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
