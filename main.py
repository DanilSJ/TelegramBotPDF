import os
import asyncio
import logging
import zipfile
import io
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
import tempfile
from pathlib import Path
import aiohttp
from pdf_processor import PDFProcessor
from config import Config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем директории если их нет
os.makedirs("temp_files", exist_ok=True)
os.makedirs("processed_files", exist_ok=True)

# Настройки сессии с увеличенными таймаутами
session = AiohttpSession(
    api=TelegramAPIServer.from_base("http://localhost:8081", is_local=True)
)

# Инициализация бота с увеличенными таймаутами
bot = Bot(
    token=Config.BOT_TOKEN,
    session=session,
    timeout=1800,  # Увеличили до 30 минут
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Инициализация процессора PDF
pdf_processor = PDFProcessor()


# Состояния для FSM
class UserStates(StatesGroup):
    waiting_for_pdf = State()
    waiting_for_action = State()
    waiting_for_contrast_settings = State()
    waiting_for_quality_settings = State()
    waiting_for_brightness_settings = State()


# Клавиатуры
def get_main_keyboard():
    """Клавиатура для выбора действия с PDF"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📸 Преобразовать в изображения", callback_data="action_images")
    builder.button(text="📦 Сжать размер PDF", callback_data="action_compress")
    builder.button(text="🎨 Настроить контраст/яркость", callback_data="action_contrast")
    builder.button(text="⚙️ Настройки обработки", callback_data="action_settings")
    builder.adjust(1)
    return builder.as_markup()


def get_settings_keyboard():
    """Клавиатура настроек"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Настроить качество", callback_data="settings_quality")
    builder.button(text="🌓 Настроить контраст", callback_data="settings_contrast")
    builder.button(text="☀️ Настроить яркость", callback_data="settings_brightness")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()


def get_back_to_settings_keyboard():
    """Клавиатура для возврата в настройки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад к настройкам", callback_data="back_to_settings")
    return builder.as_markup()


def get_back_to_contrast_keyboard():
    """Клавиатура для возврата к выбору контраста"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад к контрасту", callback_data="back_to_contrast")
    return builder.as_markup()


def get_back_to_brightness_keyboard():
    """Клавиатура для возврата к выбору яркости"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад к яркости", callback_data="back_to_brightness")
    return builder.as_markup()


def get_back_to_main_keyboard():
    """Клавиатура для возврата в главное меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад в главное меню", callback_data="back_to_main")
    return builder.as_markup()


def get_quality_keyboard():
    """Клавиатура выбора качества"""
    builder = InlineKeyboardBuilder()
    builder.button(text="Высокое (300 DPI)", callback_data="quality_high")
    builder.button(text="Среднее (150 DPI)", callback_data="quality_medium")
    builder.button(text="Низкое (72 DPI)", callback_data="quality_low")
    builder.button(text="⬅️ Назад", callback_data="back_to_settings")
    builder.adjust(1)
    return builder.as_markup()


def get_contrast_keyboard():
    """Клавиатура выбора контраста"""
    builder = InlineKeyboardBuilder()
    builder.button(text="Высокий (+30%)", callback_data="contrast_high")
    builder.button(text="Средний (+15%)", callback_data="contrast_medium")
    builder.button(text="Низкий (+5%)", callback_data="contrast_low")
    builder.button(text="Пользовательский", callback_data="contrast_custom")
    builder.button(text="⬅️ Назад", callback_data="back_to_settings")
    builder.adjust(1)
    return builder.as_markup()


def get_brightness_keyboard():
    """Клавиатура выбора яркости"""
    builder = InlineKeyboardBuilder()
    builder.button(text="Увеличить (+20)", callback_data="brightness_plus")
    builder.button(text="Уменьшить (-20)", callback_data="brightness_minus")
    builder.button(text="Пользовательская", callback_data="brightness_custom")
    builder.button(text="⬅️ Назад", callback_data="back_to_settings")
    builder.adjust(1)
    return builder.as_markup()


def get_contrast_apply_keyboard():
    """Клавиатура для применения контраста"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Применить с текущими настройками", callback_data="apply_contrast")
    builder.button(text="⚙️ Изменить настройки", callback_data="action_settings")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()


# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.clear()
    await message.answer(
        "👋 Привет! Я бот для работы с PDF файлами.\n\n"
        "Отправьте мне PDF файл, и я предложу варианты обработки:\n\n"
        "📸 <b>Преобразовать в изображения</b> - конвертирую PDF в высококачественные картинки\n"
        "📦 <b>Сжать размер PDF</b> - уменьшаю размер файла без потери качества\n"
        "🎨 <b>Настроить контраст/яркость</b> - улучшаю читаемость сканов (как на i2pdf.com)\n\n"
        "⚙️ Также вы можете настроить параметры обработки в меню настроек.",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(
        "📚 <b>Справка по использованию бота:</b>\n\n"
        "1. Отправьте мне PDF файл\n"
        "2. Выберите действие из предложенных\n"
        "3. Настройте параметры при необходимости\n"
        "4. Получите обработанный файл\n\n"
        "🔧 <b>Настройки:</b>\n"
        "• Качество изображений (DPI)\n"
        "• Уровень контраста\n"
        "• Уровень яркости\n\n"
        "💡 <b>Совет:</b> Для сканированных документов используйте функцию настройки контраста и яркости для улучшения читаемости.",
        parse_mode="HTML"
    )


@dp.message(F.document)
async def handle_pdf(message: Message, state: FSMContext):
    """Обработка полученного PDF файла"""
    if message.document.mime_type != "application/pdf":
        await message.answer("❌ Пожалуйста, отправьте именно PDF файл.")
        return

    try:
        await state.set_state(UserStates.waiting_for_action)

        # Скачиваем файл
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path

        # Сохраняем временный файл
        temp_dir = tempfile.mkdtemp()
        input_pdf_path = os.path.join(temp_dir, f"input_{file_id}.pdf")
        await bot.download_file(file_path, input_pdf_path)

        # Сохраняем информацию о файле в состоянии
        await state.update_data(
            input_pdf_path=input_pdf_path,
            temp_dir=temp_dir,
            file_id=file_id,
            original_file_name=message.document.file_name
        )

        await message.answer(
            f"✅ PDF файл получен: <b>{message.document.file_name}</b>\n"
            f"📄 Размер: {message.document.file_size / 1024:.1f} КБ\n\n"
            "Выберите действие:",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )

    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        await message.answer("❌ Произошла ошибка при обработке файла. Попробуйте еще раз.")


@dp.callback_query(F.data == "action_images")
async def process_images(callback: CallbackQuery, state: FSMContext):
    """Обработка преобразования в изображения"""
    await callback.answer()

    data = await state.get_data()
    input_pdf_path = data.get('input_pdf_path')
    original_name = data.get('original_file_name', 'document')
    temp_dir = data.get('temp_dir')

    try:
        # Создаем прогресс-сообщение
        progress_msg = await callback.message.edit_text("🔄 Преобразую PDF в изображения...")

        # Получаем настройки качества
        user_settings = pdf_processor.get_user_settings(callback.from_user.id)
        dpi = user_settings.get('dpi', 300)

        # Конвертируем в изображения
        images = await pdf_processor.pdf_to_images(input_pdf_path, dpi=dpi)

        if not images:
            await progress_msg.edit_text("❌ Не удалось преобразовать PDF в изображения.")
            return

        await progress_msg.edit_text(f"✅ Создано {len(images)} изображений\n📦 Подготавливаю архив...")

        # Создаем список всех изображений для архива
        images_list = [(i, img_path) for i, img_path in enumerate(images, 1)]

        # Создаем один архив со всеми изображениями
        archive_bytes = pdf_processor.create_archive_from_images(images_list)

        # Отправляем один архив
        archive_name = f"{Path(original_name).stem}_images.zip"

        # Разбиваем на части если файл больше 45MB (ограничение Telegram)
        CHUNK_SIZE = 400 * 1024 * 1024  # 45MB (оставляем запас)


        # Если архив меньше 45MB, отправляем как есть
        await progress_msg.edit_text(f"📤 Отправляю архив ({len(archive_bytes) / 1024 / 1024:.1f} MB)...")

        # Используем отдельную задачу для отправки
        asyncio.create_task(send_document_with_retry(
            callback.message,
            archive_bytes,
            archive_name,
            f"📁 Все изображения ({len(images)} страниц)"
        ))

        # Удаляем сообщение о прогрессе через 2 секунды
        await asyncio.sleep(2)
        await progress_msg.delete()

        await cleanup_images_and_temp(images, temp_dir)

    except Exception as e:
        logger.error(f"Error in process_images: {e}")
        try:
            await callback.message.edit_text("❌ Произошла ошибка при обработке файла. Попробуйте еще раз.")
        except:
            await callback.message.answer("❌ Произошла ошибка при обработке файла. Попробуйте еще раз.")


async def send_document_with_retry(message, file_bytes, filename, caption, max_retries=3):
    """Отправка документа с повторными попытками"""
    for attempt in range(max_retries):
        try:
            await bot.send_document(
                chat_id=message.from_user.id,
                document=FSInputFile(filename),
            )
            return True
        except Exception as e:
            logger.error(f"Error sending document (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
    return False


async def cleanup_images_and_temp(images, temp_dir):
    """Очистка временных файлов"""
    try:
        # Удаляем изображения
        for image_path in images:
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except:
                    pass

        # Удаляем временную директорию
        if os.path.exists(temp_dir):
            for root, dirs, files in os.walk(temp_dir, topdown=False):
                for name in files:
                    try:
                        os.remove(os.path.join(root, name))
                    except:
                        pass
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except:
                        pass
            try:
                os.rmdir(temp_dir)
            except:
                pass
    except Exception as e:
        logger.error(f"Error cleaning up files: {e}")


@dp.callback_query(F.data == "action_compress")
async def process_compress(callback: CallbackQuery, state: FSMContext):
    """Обработка сжатия PDF"""
    await callback.answer()

    data = await state.get_data()
    input_pdf_path = data.get('input_pdf_path')
    original_name = data.get('original_file_name', 'document')

    try:
        progress_msg = await callback.message.edit_text("🔍 Анализирую структуру PDF...")

        # Получаем информацию о файле
        original_size = os.path.getsize(input_pdf_path)

        await progress_msg.edit_text(
            f"📊 Исходный размер: {original_size / 1024 / 1024:.2f} MB\n🔄 Начинаю сжатие...")

        # Используем умное сжатие
        compressed_path = await pdf_processor.smart_compress_pdf(input_pdf_path)

        # Получаем размер после сжатия
        compressed_size = os.path.getsize(compressed_path)
        compression_ratio = compressed_size / original_size

        # Формируем сообщение о результате
        result_message = (
            f"✅ PDF файл сжат!\n\n"
            f"📊 Результат:\n"
            f"• Исходный размер: {original_size / 1024:.0f} KB\n"
            f"• После сжатия: {compressed_size / 1024:.0f} KB\n"
            f"• Экономия: {((original_size - compressed_size) / original_size * 100):.1f}%\n"
            f"• Коэффициент: {compression_ratio:.2f}"
        )

        if compression_ratio > 0.95:
            result_message += "\n\n⚠️ Сжатие незначительное. Файл уже оптимизирован."
        elif compression_ratio > 0.8:
            result_message += "\n\n✅ Умеренное сжатие."
        else:
            result_message += "\n\n🎉 Отличное сжатие!"

        # Отправляем сжатый файл
        compressed_file = FSInputFile(
            compressed_path,
            filename=f"compressed_{original_name}"
        )

        await progress_msg.delete()
        await callback.message.answer_document(
            compressed_file,
            caption=result_message
        )

        # Очищаем временные файлы
        if compressed_path != input_pdf_path:  # Не удаляем оригинал если он не сжался
            os.remove(compressed_path)
        pdf_processor.cleanup_temp_files(data.get('temp_dir'))

    except Exception as e:
        logger.error(f"Error in process_compress: {e}")
        try:
            await callback.message.edit_text("❌ Произошла ошибка при сжатии файла. Попробуйте еще раз.")
        except:
            await callback.message.answer("❌ Произошла ошибка при сжатии файла. Попробуйте еще раз.")


@dp.callback_query(F.data == "action_contrast")
async def process_contrast(callback: CallbackQuery, state: FSMContext):
    """Обработка настройки контраста/яркости"""
    await callback.answer()

    data = await state.get_data()
    await state.update_data(action="contrast")

    user_settings = pdf_processor.get_user_settings(callback.from_user.id)
    contrast = user_settings.get('contrast', 1.15)
    brightness = user_settings.get('brightness', 0)

    await callback.message.edit_text(
        f"🎨 <b>Настройки контраста и яркости</b>\n\n"
        f"Текущие настройки:\n"
        f"• Контраст: {contrast:.2f}\n"
        f"• Яркость: {brightness}\n\n"
        f"Выберите действие:",
        parse_mode="HTML",
        reply_markup=get_contrast_apply_keyboard()
    )


@dp.callback_query(F.data == "apply_contrast")
async def apply_contrast(callback: CallbackQuery, state: FSMContext):
    """Применение настроек контраста/яркости к PDF"""
    await callback.answer()

    data = await state.get_data()
    input_pdf_path = data.get('input_pdf_path')
    original_name = data.get('original_file_name', 'document')

    try:
        progress_msg = await callback.message.edit_text("🎨 Применяю настройки контраста и яркости...")

        # Применяем настройки контраста и яркости
        enhanced_pdf_path = await pdf_processor.adjust_contrast_brightness(
            input_pdf_path,
            callback.from_user.id
        )

        # Отправляем обработанный файл
        enhanced_file = FSInputFile(
            enhanced_pdf_path,
            filename=f"enhanced_{original_name}"
        )

        await progress_msg.delete()
        await callback.message.answer_document(
            enhanced_file,
            caption="✅ PDF файл обработан с настройками контраста и яркости"
        )

        # Очищаем временные файлы
        if os.path.exists(enhanced_pdf_path):
            os.remove(enhanced_pdf_path)
        pdf_processor.cleanup_temp_files(data.get('temp_dir'))

    except Exception as e:
        logger.error(f"Error in apply_contrast: {e}")
        try:
            await callback.message.edit_text("❌ Произошла ошибка при обработке файла. Попробуйте еще раз.")
        except:
            await callback.message.answer("❌ Произошла ошибка при обработке файла. Попробуйте еще раз.")


@dp.callback_query(F.data == "action_settings")
async def process_settings(callback: CallbackQuery):
    """Показ меню настроек"""
    await callback.answer()

    user_settings = pdf_processor.get_user_settings(callback.from_user.id)
    dpi = user_settings.get('dpi', 300)
    contrast = user_settings.get('contrast', 1.15)
    brightness = user_settings.get('brightness', 0)

    await callback.message.edit_text(
        f"⚙️ <b>Настройки обработки PDF</b>\n\n"
        f"Текущие настройки:\n"
        f"• Качество (DPI): {dpi}\n"
        f"• Контраст: {contrast:.2f}\n"
        f"• Яркость: {brightness}\n\n"
        f"Выберите параметр для настройки:",
        parse_mode="HTML",
        reply_markup=get_settings_keyboard()
    )


@dp.callback_query(F.data.startswith("settings_"))
async def process_setting_select(callback: CallbackQuery):
    """Обработка выбора настройки"""
    await callback.answer()

    setting_type = callback.data.split("_")[1]

    if setting_type == "quality":
        await callback.message.edit_text(
            "🎯 Выберите качество для преобразования PDF в изображения:",
            reply_markup=get_quality_keyboard()
        )
    elif setting_type == "contrast":
        await callback.message.edit_text(
            "🌓 Выберите уровень контраста:",
            reply_markup=get_contrast_keyboard()
        )
    elif setting_type == "brightness":
        await callback.message.edit_text(
            "☀️ Выберите уровень яркости:",
            reply_markup=get_brightness_keyboard()
        )


@dp.callback_query(F.data.startswith("quality_"))
async def process_quality_setting(callback: CallbackQuery):
    """Обработка выбора качества"""
    await callback.answer()

    quality = callback.data.split("_")[1]

    if quality == "high":
        dpi = 300
    elif quality == "medium":
        dpi = 150
    elif quality == "low":
        dpi = 72
    else:
        await callback.answer("❌ Неизвестный параметр качества")
        return

    pdf_processor.update_user_settings(callback.from_user.id, {'dpi': dpi})
    await callback.message.edit_text(
        f"✅ Качество установлено: {dpi} DPI",
        reply_markup=get_back_to_settings_keyboard()
    )


@dp.callback_query(F.data.startswith("contrast_"))
async def process_contrast_setting(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора контраста"""
    await callback.answer()

    contrast_level = callback.data.split("_")[1]

    if contrast_level == "high":
        contrast = 1.3
    elif contrast_level == "medium":
        contrast = 1.15
    elif contrast_level == "low":
        contrast = 1.05
    elif contrast_level == "custom":
        await callback.message.edit_text(
            "✏️ Введите значение контраста (от 0.5 до 2.0):\n"
            "Например: 1.25",
            reply_markup=get_back_to_contrast_keyboard()
        )
        await state.set_state(UserStates.waiting_for_contrast_settings)
        return
    else:
        await callback.answer("❌ Неизвестный параметр контраста")
        return

    pdf_processor.update_user_settings(callback.from_user.id, {'contrast': contrast})
    await callback.message.edit_text(
        f"✅ Контраст установлен: {contrast:.2f}",
        reply_markup=get_back_to_settings_keyboard()
    )


@dp.callback_query(F.data.startswith("brightness_"))
async def process_brightness_setting(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора яркости"""
    await callback.answer()

    brightness_level = callback.data.split("_")[1]

    if brightness_level == "plus":
        brightness = 20
    elif brightness_level == "minus":
        brightness = -20
    elif brightness_level == "custom":
        await callback.message.edit_text(
            "✏️ Введите значение яркости (от -100 до 100):\n"
            "Например: 15",
            reply_markup=get_back_to_brightness_keyboard()
        )
        await state.set_state(UserStates.waiting_for_brightness_settings)
        return
    else:
        await callback.answer("❌ Неизвестный параметр яркости")
        return

    pdf_processor.update_user_settings(callback.from_user.id, {'brightness': brightness})
    await callback.message.edit_text(
        f"✅ Яркость установлена: {brightness}",
        reply_markup=get_back_to_settings_keyboard()
    )


@dp.callback_query(F.data.startswith("back_to_"))
async def process_back(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки назад"""
    await callback.answer()

    back_to = callback.data.split("_")[2]

    if back_to == "main":
        await callback.message.edit_text(
            "Выберите действие:",
            reply_markup=get_main_keyboard()
        )
    elif back_to == "settings":
        user_settings = pdf_processor.get_user_settings(callback.from_user.id)
        dpi = user_settings.get('dpi', 300)
        contrast = user_settings.get('contrast', 1.15)
        brightness = user_settings.get('brightness', 0)

        await callback.message.edit_text(
            f"⚙️ <b>Настройки обработки PDF</b>\n\n"
            f"Текущие настройки:\n"
            f"• Качество (DPI): {dpi}\n"
            f"• Контраст: {contrast:.2f}\n"
            f"• Яркость: {brightness}\n\n"
            f"Выберите параметр для настройки:",
            parse_mode="HTML",
            reply_markup=get_settings_keyboard()
        )
    elif back_to == "contrast":
        await callback.message.edit_text(
            "🌓 Выберите уровень контраста:",
            reply_markup=get_contrast_keyboard()
        )
    elif back_to == "brightness":
        await callback.message.edit_text(
            "☀️ Выберите уровень яркости:",
            reply_markup=get_brightness_keyboard()
        )


# Обработчики текстовых сообщений для кастомных настроек
@dp.message(UserStates.waiting_for_contrast_settings)
async def process_custom_contrast(message: Message, state: FSMContext):
    """Обработка пользовательского значения контраста"""
    try:
        contrast = float(message.text)
        if 0.5 <= contrast <= 2.0:
            pdf_processor.update_user_settings(message.from_user.id, {'contrast': contrast})
            await message.answer(
                f"✅ Контраст установлен: {contrast:.2f}",
                reply_markup=get_back_to_contrast_keyboard()
            )
            await state.clear()
        else:
            await message.answer("❌ Значение должно быть от 0.5 до 2.0. Попробуйте еще раз:")
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число. Например: 1.25")


@dp.message(UserStates.waiting_for_brightness_settings)
async def process_custom_brightness(message: Message, state: FSMContext):
    """Обработка пользовательского значения яркости"""
    try:
        brightness = int(message.text)
        if -100 <= brightness <= 100:
            pdf_processor.update_user_settings(message.from_user.id, {'brightness': brightness})
            await message.answer(
                f"✅ Яркость установлена: {brightness}",
                reply_markup=get_back_to_brightness_keyboard()
            )
            await state.clear()
        else:
            await message.answer("❌ Значение должно быть от -100 до 100. Попробуйте еще раз:")
    except ValueError:
        await message.answer("❌ Пожалуйста, введите целое число. Например: 15")


# Запуск бота
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot, polling_timeout=30)


if __name__ == "__main__":
    asyncio.run(main())