import io
import os
import asyncio
import tempfile
import zipfile
from pathlib import Path
from typing import List, Dict
import fitz
from PIL import Image, ImageEnhance
import img2pdf
import json

from aiogram.types import BufferedInputFile


class PDFProcessor:
    def __init__(self):
        self.user_settings_file = "user_settings.json"
        self.user_settings = self.load_user_settings()

    def load_user_settings(self) -> Dict:
        """Загрузка настроек пользователей из файла"""
        if os.path.exists(self.user_settings_file):
            try:
                with open(self.user_settings_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_user_settings(self):
        """Сохранение настроек пользователей в файл"""
        with open(self.user_settings_file, 'w') as f:
            json.dump(self.user_settings, f, indent=2)

    def get_user_settings(self, user_id: int) -> Dict:
        """Получение настроек пользователя"""
        return self.user_settings.get(str(user_id), {})

    def update_user_settings(self, user_id: int, updates: Dict):
        """Обновление настроек пользователя"""
        user_id_str = str(user_id)
        if user_id_str not in self.user_settings:
            self.user_settings[user_id_str] = {}

        self.user_settings[user_id_str].update(updates)
        self.save_user_settings()

    async def pdf_to_images(self, pdf_path: str, dpi: int = 300, max_size: int = 10000) -> List[str]:
        """
        Конвертация PDF в изображения с оптимизацией размера

        Args:
            pdf_path: путь к PDF файлу
            dpi: качество изображений
            max_size: максимальный размер изображения (для Telegram)

        Returns:
            Список путей к созданным изображениям
        """
        images = []
        temp_dir = tempfile.mkdtemp()

        try:
            # Открываем PDF с помощью PyMuPDF
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)

                # Рассчитываем матрицу с учетом ограничений Telegram
                zoom = dpi / 72

                # Получаем размеры страницы
                rect = page.rect
                width = rect.width * zoom
                height = rect.height * zoom

                # Если размеры превышают лимит Telegram, уменьшаем масштаб
                if width > max_size or height > max_size:
                    scale_factor = max_size / max(width, height)
                    zoom *= scale_factor

                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # Сохраняем изображение
                img_path = os.path.join(temp_dir, f"page_{page_num + 1}.png")
                pix.save(img_path)

                # Опционально: дополнительная оптимизация размера файла
                self.optimize_image_size(img_path)

                images.append(img_path)

            doc.close()

        except Exception as e:
            print(f"Error converting PDF to images: {e}")
            raise

        return images

    def optimize_image_size(self, image_path: str, max_file_size: int = 5 * 1024 * 1024):
        """
        Оптимизация размера файла изображения
        """
        try:
            file_size = os.path.getsize(image_path)
            if file_size <= max_file_size:
                return

            with Image.open(image_path) as img:
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # Сохраняем с оптимизацией
                quality = 95
                while quality > 50 and os.path.getsize(image_path) > max_file_size:
                    img.save(image_path, "PNG", optimize=True)
                    quality -= 5

        except Exception as e:
            print(f"Error optimizing image size: {e}")

    async def compress_pdf(self, pdf_path: str) -> str:
        """
        Сжатие PDF файла без потери качества

        Args:
            pdf_path: путь к исходному PDF файлу

        Returns:
            Путь к сжатому PDF файлу
        """
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, "compressed.pdf")

        try:
            # Используем Ghostscript для сжатия PDF
            command = [
                'gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
                '-dPDFSETTINGS=/ebook', '-dNOPAUSE', '-dQUIET', '-dBATCH',
                f'-sOutputFile={output_path}', pdf_path
            ]

            # Запускаем процесс сжатия
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                # Если Ghostscript недоступен, используем альтернативный метод
                print("Ghostscript not available, using alternative method")
                return await self.compress_pdf_alternative(pdf_path)

            return output_path

        except Exception as e:
            print(f"Error compressing PDF: {e}")
            # Используем альтернативный метод при ошибке
            return await self.compress_pdf_alternative(pdf_path)

    async def compress_pdf_alternative(self, pdf_path: str) -> str:
        """Альтернативный метод сжатия PDF"""
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, "compressed.pdf")

        try:
            doc = fitz.open(pdf_path)

            # Создаем новый документ с оптимизированными изображениями
            new_doc = fitz.open()

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
                new_page.show_pdf_page(page.rect, doc, page_num)

            # Сохраняем с оптимизацией
            new_doc.save(output_path, garbage=4, deflate=True)
            new_doc.close()
            doc.close()

            return output_path

        except Exception as e:
            print(f"Error in alternative compression: {e}")
            raise

    async def adjust_contrast_brightness(self, pdf_path: str, user_id: int) -> str:
        """
        Настройка контраста и яркости PDF как на i2pdf.com

        Args:
            pdf_path: путь к исходному PDF файлу
            user_id: ID пользователя для получения настроек

        Returns:
            Путь к обработанному PDF файлу
        """
        # Получаем настройки пользователя
        settings = self.get_user_settings(user_id)
        contrast = settings.get('contrast', 1.15)
        brightness = settings.get('brightness', 0)

        temp_dir = tempfile.mkdtemp()
        images_dir = os.path.join(temp_dir, "images")
        processed_dir = os.path.join(temp_dir, "processed")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(processed_dir, exist_ok=True)

        output_pdf_path = os.path.join(temp_dir, "enhanced.pdf")

        try:
            # 1. Конвертируем PDF в изображения
            images = await self.pdf_to_images(pdf_path, dpi=150)

            processed_images = []

            for i, img_path in enumerate(images):
                # 2. Обрабатываем каждое изображение
                with Image.open(img_path) as img:
                    # Конвертируем в RGB если нужно
                    if img.mode != 'RGB':
                        img = img.convert('RGB')

                    # Применяем контраст
                    enhancer = ImageEnhance.Contrast(img)
                    img = enhancer.enhance(contrast)

                    # Применяем яркость
                    enhancer = ImageEnhance.Brightness(img)
                    img = enhancer.enhance(1 + brightness / 100)

                    # Сохраняем обработанное изображение
                    processed_path = os.path.join(processed_dir, f"page_{i + 1}.jpg")
                    img.save(processed_path, "JPEG", quality=95, optimize=True)
                    processed_images.append(processed_path)

                # Удаляем временное изображение
                os.remove(img_path)

            # 3. Конвертируем обработанные изображения обратно в PDF
            with open(output_pdf_path, "wb") as f:
                f.write(img2pdf.convert(processed_images))

            return output_pdf_path

        except Exception as e:
            print(f"Error adjusting contrast/brightness: {e}")
            raise

    def cleanup_temp_files(self, temp_dir: str):
        """Очистка временных файлов"""
        try:
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Error cleaning up temp files: {e}")

    def create_archive_from_images(self, images_list):
        """
        Создает ZIP архив из всех изображений

        Args:
            images_list: список кортежей (номер_страницы, путь_к_изображению)

        Returns:
            bytes: данные архива
        """
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
            for page_num, image_path in images_list:
                try:
                    # Определяем расширение файла
                    ext = os.path.splitext(image_path)[1].lower()
                    filename = f"страница_{page_num}{ext}"

                    with open(image_path, 'rb') as img_file:
                        img_data = img_file.read()
                        zip_file.writestr(filename, img_data)
                except Exception as e:
                    print(f"Error adding image {image_path} to archive: {e}")
                    continue

        zip_buffer.seek(0)
        return zip_buffer.getvalue()
