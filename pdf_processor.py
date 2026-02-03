import io
import os
import asyncio
import tempfile
import zipfile
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import fitz
from PIL import Image, ImageEnhance
import img2pdf
import json
import re

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
        """Конвертация PDF в изображения"""
        images = []
        temp_dir = tempfile.mkdtemp()

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                zoom = dpi / 72

                # Корректировка масштаба для Telegram
                rect = page.rect
                width = rect.width * zoom
                height = rect.height * zoom

                if width > max_size or height > max_size:
                    scale_factor = max_size / max(width, height)
                    zoom *= scale_factor

                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                img_path = os.path.join(temp_dir, f"page_{page_num + 1}.png")
                pix.save(img_path)
                images.append(img_path)

            doc.close()

        except Exception as e:
            print(f"Error converting PDF to images: {e}")
            raise

        return images

    def optimize_image_size(self, image_path: str, max_file_size: int = 2 * 1024 * 1024):
        """Оптимизация размера файла изображения"""
        try:
            file_size = os.path.getsize(image_path)
            if file_size <= max_file_size:
                return

            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # Уменьшаем качество постепенно
                quality = 85
                while quality > 40 and file_size > max_file_size:
                    img.save(image_path, "JPEG", quality=quality, optimize=True)
                    file_size = os.path.getsize(image_path)
                    quality -= 10

        except Exception as e:
            print(f"Error optimizing image size: {e}")

    async def compress_pdf(self, pdf_path: str, method: str = "aggressive") -> str:
        """
        Сжатие PDF файла с различными методами

        Args:
            pdf_path: путь к исходному PDF файлу
            method: метод сжатия ("aggressive", "balanced", "light")

        Returns:
            Путь к сжатому PDF файлу
        """
        # Сначала получаем информацию о файле
        original_size = os.path.getsize(pdf_path)

        # Пробуем несколько методов, пока не получим хорошее сжатие
        methods_to_try = ["aggressive", "balanced", "light", "extreme"]

        for compress_method in methods_to_try:
            try:
                output_path = await self._compress_pdf_with_method(
                    pdf_path,
                    compress_method
                )

                if output_path and os.path.exists(output_path):
                    compressed_size = os.path.getsize(output_path)
                    compression_ratio = compressed_size / original_size

                    # Если сжатие более 10% или это последний метод
                    if compression_ratio < 0.9 or compress_method == methods_to_try[-1]:
                        print(
                            f"Method {compress_method}: {original_size / 1024:.0f}KB -> {compressed_size / 1024:.0f}KB ({compression_ratio:.2%})")
                        return output_path
                    else:
                        # Удаляем плохо сжатый файл и пробуем следующий метод
                        os.remove(output_path)

            except Exception as e:
                print(f"Error with {compress_method} compression: {e}")
                continue

        # Если все методы не сработали, возвращаем исходный файл
        return pdf_path

    async def _compress_pdf_with_method(self, pdf_path: str, method: str) -> Optional[str]:
        """Внутренний метод сжатия с конкретным алгоритмом"""
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, f"compressed_{method}.pdf")

        # Настройки для разных методов сжатия
        settings = {
            "light": {
                "gs_settings": "/prepress",  # Минимальное сжатие
                "image_quality": 90,
                "image_dpi": 150,
                "aggressive": False
            },
            "balanced": {
                "gs_settings": "/ebook",  # Баланс качество/размер
                "image_quality": 75,
                "image_dpi": 150,
                "aggressive": True
            },
            "aggressive": {
                "gs_settings": "/screen",  # Максимальное сжатие
                "image_quality": 60,
                "image_dpi": 96,
                "aggressive": True
            },
            "extreme": {
                "gs_settings": "/screen",  # Экстремальное сжатие
                "image_quality": 40,
                "image_dpi": 72,
                "aggressive": True,
                "extreme": True
            }
        }

        method_settings = settings.get(method, settings["balanced"])

        try:
            # Пробуем через Ghostscript с оптимизированными параметрами
            if await self._has_ghostscript():
                return await self._compress_with_ghostscript(
                    pdf_path, output_path, method_settings
                )
            else:
                # Альтернативный метод без Ghostscript
                return await self._compress_with_fitz(
                    pdf_path, output_path, method_settings
                )

        except Exception as e:
            print(f"Error in compression method {method}: {e}")
            return None

    async def _has_ghostscript(self) -> bool:
        """Проверка наличия Ghostscript"""
        try:
            process = await asyncio.create_subprocess_exec(
                'gs', '--version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return process.returncode == 0
        except:
            return False

    async def _compress_with_ghostscript(self, pdf_path: str, output_path: str, settings: dict) -> str:
        """Сжатие через Ghostscript с расширенными параметрами"""
        gs_settings = settings["gs_settings"]
        image_quality = settings["image_quality"]
        image_dpi = settings["image_dpi"]

        # Команда Ghostscript с оптимизацией изображений
        command = [
            'gs',
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            f'-dPDFSETTINGS={gs_settings}',
            '-dNOPAUSE',
            '-dQUIET',
            '-dBATCH',

            # Оптимизация изображений
            '-dDownsampleColorImages=true',
            f'-dColorImageResolution={image_dpi}',
            f'-dColorImageDownsampleThreshold=1.0',
            f'-dColorImageDownsampleType=/Bicubic',

            '-dDownsampleGrayImages=true',
            f'-dGrayImageResolution={image_dpi}',
            f'-dGrayImageDownsampleThreshold=1.0',
            f'-dGrayImageDownsampleType=/Bicubic',

            '-dDownsampleMonoImages=true',
            f'-dMonoImageResolution={image_dpi}',
            f'-dMonoImageDownsampleThreshold=1.0',
            f'-dMonoImageDownsampleType=/Subsample',

            # Качество JPEG
            f'-dColorImageFilter=/DCTEncode',
            f'-dGrayImageFilter=/DCTEncode',
            f'-dColorConversionStrategy=/sRGB',
            f'-dEncodeColorImages=true',
            f'-dEncodeGrayImages=true',
            f'-dEncodeMonoImages=true',
            f'-dAutoFilterColorImages=false',
            f'-dAutoFilterGrayImages=false',

            # Настройки сжатия
            '-dCompressFonts=true',
            '-dEmbedAllFonts=true',
            '-dSubsetFonts=true',
            '-dCompressPages=true',
            '-dUseFlateCompression=true',
            f'-dFlateEncodeFilter=/FlateEncode',

            # Качество JPEG (для настроек)
            f'-dColorImageQuality={image_quality}',
            f'-dGrayImageQuality={image_quality}',

            f'-sOutputFile={output_path}',
            pdf_path
        ]

        # Для экстремального сжатия добавляем дополнительные параметры
        if settings.get("extreme", False):
            command.insert(5, '-dColorConversionStrategy=/Gray')
            command.insert(6, '-dProcessColorModel=/DeviceGray')
            command.insert(7, '-dColorImageDepth=4')

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0 and os.path.exists(output_path):
            return output_path
        else:
            raise Exception(f"Ghostscript failed: {stderr.decode()}")

    async def _compress_with_fitz(self, pdf_path: str, output_path: str, settings: dict) -> str:
        """Альтернативный метод сжатия через PyMuPDF"""
        temp_dir = tempfile.mkdtemp()

        try:
            doc = fitz.open(pdf_path)
            new_doc = fitz.open()

            # Получаем настройки
            image_quality = settings["image_quality"]
            image_dpi = settings["image_dpi"]
            aggressive = settings.get("aggressive", True)

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                new_page = new_doc.new_page(
                    width=page.rect.width,
                    height=page.rect.height
                )

                # Копируем страницу с оптимизацией
                new_page.show_pdf_page(
                    page.rect,
                    doc,
                    page_num
                )

            # Опции сохранения для максимального сжатия
            save_options = {
                'garbage': 4,  # Удаление неиспользуемых объектов
                'deflate': True,  # Сжатие потоков
                'deflate_images': aggressive,  # Сжатие изображений
                'deflate_fonts': aggressive,  # Сжатие шрифтов
                'clean': True,  # Очистка
                'pretty': False,  # Без форматирования
            }

            # Дополнительная оптимизация изображений
            if aggressive:
                save_options['images'] = image_dpi
                # Можно добавить дополнительную обработку изображений
                await self._optimize_images_in_pdf(new_doc, image_quality, image_dpi)

            new_doc.save(output_path, **save_options)
            new_doc.close()
            doc.close()

            return output_path

        except Exception as e:
            raise Exception(f"PyMuPDF compression failed: {e}")

    async def _optimize_images_in_pdf(self, doc, quality: int, dpi: int):
        """Оптимизация изображений внутри PDF документа"""
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)

            # Получаем список изображений на странице
            image_list = page.get_images()

            for img_index, img_info in enumerate(image_list):
                try:
                    xref = img_info[0]
                    # Можно добавить дополнительную обработку изображений
                    # Например, изменение разрешения или сжатие
                    pass
                except Exception as e:
                    print(f"Error optimizing image {img_index} on page {page_num}: {e}")

    async def analyze_pdf_structure(self, pdf_path: str) -> Dict:
        """Анализ структуры PDF для выбора оптимального метода сжатия"""
        try:
            doc = fitz.open(pdf_path)
            info = {
                "pages": len(doc),
                "has_images": False,
                "has_text": False,
                "has_forms": False,
                "file_size": os.path.getsize(pdf_path),
                "metadata": doc.metadata
            }

            # Анализируем несколько страниц
            for i in range(min(3, len(doc))):
                page = doc.load_page(i)
                text = page.get_text()
                images = page.get_images()

                if text.strip():
                    info["has_text"] = True
                if images:
                    info["has_images"] = True

            doc.close()
            return info

        except Exception as e:
            print(f"Error analyzing PDF: {e}")
            return {}

    async def smart_compress_pdf(self, pdf_path: str) -> str:
        """
        Умное сжатие PDF с анализом содержимого

        Args:
            pdf_path: путь к исходному PDF файлу

        Returns:
            Путь к сжатому PDF файлу
        """
        # Анализируем PDF
        analysis = await self.analyze_pdf_structure(pdf_path)
        original_size = analysis.get("file_size", os.path.getsize(pdf_path))

        # Выбираем метод на основе анализа
        if analysis.get("has_images", False):
            if original_size > 50 * 1024 * 1024:  # Более 50MB
                method = "extreme"
            elif original_size > 10 * 1024 * 1024:  # Более 10MB
                method = "aggressive"
            else:
                method = "balanced"
        elif analysis.get("has_text", False) and not analysis.get("has_images", False):
            method = "light"  # Только текст - легкое сжатие
        else:
            method = "balanced"  # По умолчанию

        print(f"Selected compression method: {method}")

        # Выполняем сжатие
        return await self.compress_pdf(pdf_path, method)

    async def adjust_contrast_brightness(self, pdf_path: str, user_id: int) -> str:
        """Настройка контраста и яркости PDF"""
        settings = self.get_user_settings(user_id)
        contrast = settings.get('contrast', 1.15)
        brightness = settings.get('brightness', 0)

        temp_dir = tempfile.mkdtemp()
        processed_dir = os.path.join(temp_dir, "processed")
        os.makedirs(processed_dir, exist_ok=True)

        output_pdf_path = os.path.join(temp_dir, "enhanced.pdf")

        try:
            # Используем более низкое DPI для экономии памяти
            images = await self.pdf_to_images(pdf_path, dpi=150)
            processed_images = []

            for i, img_path in enumerate(images):
                with Image.open(img_path) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')

                    # Применяем контраст
                    if contrast != 1.0:
                        enhancer = ImageEnhance.Contrast(img)
                        img = enhancer.enhance(contrast)

                    # Применяем яркость
                    if brightness != 0:
                        enhancer = ImageEnhance.Brightness(img)
                        img = enhancer.enhance(1 + brightness / 100)

                    # Сохраняем с оптимизацией
                    processed_path = os.path.join(processed_dir, f"page_{i + 1}.jpg")
                    img.save(processed_path, "JPEG", quality=85, optimize=True)
                    processed_images.append(processed_path)

                # Удаляем временное изображение
                os.remove(img_path)

            # Конвертируем обратно в PDF
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
        """Создает ZIP архив из изображений"""
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
            for page_num, image_path in images_list:
                try:
                    ext = os.path.splitext(image_path)[1].lower()
                    filename = f"страница_{page_num}{ext}"

                    # Оптимизируем изображение перед добавлением в архив
                    self.optimize_image_size(image_path)

                    with open(image_path, 'rb') as img_file:
                        img_data = img_file.read()
                        zip_file.writestr(filename, img_data)
                except Exception as e:
                    print(f"Error adding image {image_path} to archive: {e}")
                    continue

        zip_buffer.seek(0)
        return zip_buffer.getvalue()