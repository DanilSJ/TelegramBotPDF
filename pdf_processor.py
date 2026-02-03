import io
import os
import asyncio
import tempfile
import zipfile
from typing import List, Dict, Optional, Tuple
import fitz
from PIL import Image, ImageEnhance, ImageOps, ImageFilter
import img2pdf
import json
import numpy as np


class PDFProcessor:
    def __init__(self):
        self.user_settings_file = "user_settings.json"
        self.user_settings = self.load_user_settings()
        self.default_settings = {
            'contrast': 1.5,  # Увеличил по умолчанию
            'brightness': 20,  # Увеличил по умолчанию
            'sharpness': 1.2,
            'auto_enhance': True
        }

    def load_user_settings(self) -> Dict:
        """Загрузка настроек пользователей из файла"""
        if os.path.exists(self.user_settings_file):
            try:
                with open(self.user_settings_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    async def enhance_image_with_settings(
            self,
            image_path: str,
            contrast: float = 1.5,
            brightness: float = 20,
            sharpness: float = 1.2,
            auto_enhance: bool = True
    ) -> str:
        """Улучшение изображения с расширенными настройками"""
        try:
            with Image.open(image_path) as img:
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                original_img = img.copy()

                # Автоулучшение если включено
                if auto_enhance:
                    img = self.auto_enhance_image(img)

                # Применяем яркость с усиленным эффектом
                if brightness != 0:
                    # Преобразуем в более агрессивное значение
                    brightness_factor = 1 + (brightness / 50)  # Более сильный эффект
                    enhancer = ImageEnhance.Brightness(img)
                    img = enhancer.enhance(brightness_factor)

                # Применяем контраст с усиленным эффектом
                if contrast != 1.0:
                    # Используем квадрат значения для более сильного эффекта
                    enhanced_contrast = contrast ** 1.5
                    enhancer = ImageEnhance.Contrast(img)
                    img = enhancer.enhance(enhanced_contrast)

                # Применяем резкость
                if sharpness != 1.0:
                    enhancer = ImageEnhance.Sharpness(img)
                    img = enhancer.enhance(sharpness)

                # Добавляем легкую шумоподавление для сканов
                if img.mode == 'RGB':
                    # Легкая медианная фильтрация для уменьшения шума
                    img = img.filter(ImageFilter.MedianFilter(size=1))

                # Сохраняем результат
                output_path = image_path.replace('.png', '_enhanced.jpg')
                img.save(output_path, "JPEG", quality=95, optimize=True, subsampling=0)


                return output_path

        except Exception as e:
            print(f"Error enhancing image: {e}")
            return image_path

    def auto_enhance_image(self, img: Image.Image) -> Image.Image:
        """Автоматическое улучшение изображения"""
        # Конвертируем в массив для анализа
        img_array = np.array(img)

        # Вычисляем гистограмму
        if len(img_array.shape) == 3:  # RGB изображение
            # Разделяем каналы
            r, g, b = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2]

            # Вычисляем статистику по каналам
            r_min, r_max = np.percentile(r, [2, 98])
            g_min, g_max = np.percentile(g, [2, 98])
            b_min, b_max = np.percentile(b, [2, 98])

            # Применяем автоматическую коррекцию уровней
            r_corrected = np.clip((r - r_min) * 255.0 / (r_max - r_min), 0, 255).astype(np.uint8)
            g_corrected = np.clip((g - g_min) * 255.0 / (g_max - g_min), 0, 255).astype(np.uint8)
            b_corrected = np.clip((b - b_min) * 255.0 / (b_max - b_min), 0, 255).astype(np.uint8)

            # Собираем обратно
            enhanced_array = np.stack([r_corrected, g_corrected, b_corrected], axis=2)
            img = Image.fromarray(enhanced_array)

        # Автоматическая коррекция контраста
        img = ImageOps.autocontrast(img, cutoff=2)

        return img

    async def pdf_to_images_with_enhancement(
            self,
            pdf_path: str,
            user_id: int = None,
            dpi: int = 150
    ) -> List[str]:
        """Конвертация PDF в улучшенные изображения"""
        images = []
        temp_dir = tempfile.mkdtemp()

        try:
            # Получаем настройки пользователя или используем дефолтные
            if user_id:
                settings = self.get_user_settings(user_id)
                contrast = settings.get('contrast', self.default_settings['contrast'])
                brightness = settings.get('brightness', self.default_settings['brightness'])
                sharpness = settings.get('sharpness', self.default_settings['sharpness'])
                auto_enhance = settings.get('auto_enhance', self.default_settings['auto_enhance'])
            else:
                contrast = self.default_settings['contrast']
                brightness = self.default_settings['brightness']
                sharpness = self.default_settings['sharpness']
                auto_enhance = self.default_settings['auto_enhance']

            doc = fitz.open(pdf_path)

            # Получаем имя файла без расширения
            pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                zoom = dpi / 72

                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # Сохраняем временное изображение с именем исходного файла
                temp_img_path = os.path.join(temp_dir, f"{pdf_name}_page_{page_num + 1}.png")
                pix.save(temp_img_path)

                # Применяем улучшения
                enhanced_img_path = await self.enhance_image_with_settings(
                    temp_img_path,
                    contrast=contrast,
                    brightness=brightness,
                    sharpness=sharpness,
                    auto_enhance=auto_enhance
                )

                # Оптимизируем размер
                self.optimize_image_size(enhanced_img_path)

                images.append(enhanced_img_path)

                # Удаляем временный файл
                if os.path.exists(temp_img_path):
                    os.remove(temp_img_path)

            doc.close()

        except Exception as e:
            print(f"Error converting PDF with enhancement: {e}")
            raise

        return images

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


    def cleanup_temp_files(self, temp_dir: str):
        """Очистка временных файлов"""
        try:
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Error cleaning up temp files: {e}")

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

    async def create_preview_image(
            self,
            pdf_path: str,
            user_id: int = None,
            page_num: int = 0
    ) -> Tuple[str, Dict]:
        """Создание предпросмотра с текущими настройками"""
        temp_dir = tempfile.mkdtemp()

        try:
            # Получаем настройки
            if user_id:
                settings = self.get_user_settings(user_id)
                contrast = settings.get('contrast', self.default_settings['contrast'])
                brightness = settings.get('brightness', self.default_settings['brightness'])
                sharpness = settings.get('sharpness', self.default_settings['sharpness'])
            else:
                contrast = self.default_settings['contrast']
                brightness = self.default_settings['brightness']
                sharpness = self.default_settings['sharpness']

            # Открываем PDF и получаем первую страницу
            doc = fitz.open(pdf_path)
            page = doc.load_page(min(page_num, len(doc) - 1))

            # Рендерим с низким DPI для быстрого предпросмотра
            zoom = 100 / 72  # Низкое разрешение для скорости
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # Сохраняем временное изображение
            preview_path = os.path.join(temp_dir, f"preview.png")
            pix.save(preview_path)
            doc.close()

            # Применяем текущие настройки
            enhanced_preview = await self.enhance_image_with_settings(
                preview_path,
                contrast=contrast,
                brightness=brightness,
                sharpness=sharpness,
                auto_enhance=True
            )

            # Информация о примененных настройках
            settings_info = {
                'contrast': contrast,
                'brightness': brightness,
                'sharpness': sharpness,
                'page': page_num + 1,
                'total_pages': len(doc)
            }

            return enhanced_preview, settings_info

        except Exception as e:
            print(f"Error creating preview: {e}")
            raise

    async def convert_to_images_with_settings(self, pdf_path: str, user_id: int) -> List[str]:
        """Конвертация PDF в изображения с настройками пользователя"""
        # Получаем настройки пользователя
        user_settings = self.get_user_settings(user_id)
        dpi = user_settings.get('dpi', 300)

        # Конвертируем с нужным DPI
        return await self.pdf_to_images(pdf_path, dpi=dpi)

    async def compress_pdf_with_settings(self, pdf_path: str, user_id: int) -> str:
        """Сжатие PDF с учетом настроек пользователя"""
        # Здесь можно добавить настройки сжатия для разных пользователей
        return await self.smart_compress_pdf(pdf_path)

    def save_user_settings(self):
        """Сохранение настроек пользователей в файл"""
        with open(self.user_settings_file, 'w') as f:
            json.dump(self.user_settings, f, indent=2)

    def get_user_settings(self, user_id: int) -> Dict:
        """Получение настроек пользователя"""
        user_id_str = str(user_id)
        if user_id_str not in self.user_settings:
            self.user_settings[user_id_str] = {
                'dpi': 300,
                'contrast': 1.15,
                'brightness': 0
            }
        return self.user_settings[user_id_str]

    def update_user_settings(self, user_id: int, updates: Dict):
        """Обновление настроек пользователя"""
        user_id_str = str(user_id)
        if user_id_str not in self.user_settings:
            self.user_settings[user_id_str] = {}

        # Ограничиваем значения
        if 'contrast' in updates:
            updates['contrast'] = max(0.5, min(3.0, float(updates['contrast'])))
        if 'brightness' in updates:
            updates['brightness'] = max(-100, min(100, int(updates['brightness'])))
        if 'dpi' in updates:
            updates['dpi'] = max(72, min(600, int(updates['dpi'])))

        self.user_settings[user_id_str].update(updates)

        # Сохраняем в файл
        self.save_user_settings()

    def reset_user_settings(self, user_id: int):
        """Сброс настроек пользователя к значениям по умолчанию"""
        user_id_str = str(user_id)
        self.user_settings[user_id_str] = self.default_settings.copy()
        self.save_user_settings()

    async def adjust_contrast_brightness(self, pdf_path: str, user_id: int) -> str:
        """Настройка контраста и яркости PDF с использованием настроек пользователя"""
        # Получаем настройки пользователя
        user_settings = self.get_user_settings(user_id)
        contrast = user_settings.get('contrast', 1.15)
        brightness = user_settings.get('brightness', 0)

        temp_dir = tempfile.mkdtemp()
        processed_dir = os.path.join(temp_dir, "processed")
        os.makedirs(processed_dir, exist_ok=True)

        output_pdf_path = os.path.join(temp_dir, "enhanced.pdf")

        try:
            doc = fitz.open(pdf_path)
            processed_images = []

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)

                # Рендерим страницу как изображение с высоким DPI
                zoom = 2.0  # 144 DPI (72 * 2)
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # Сохраняем временное изображение
                img_path = os.path.join(temp_dir, f"page_{page_num}.png")
                pix.save(img_path)

                # Применяем контраст и яркость
                enhanced_img_path = await self.enhance_image_with_settings(
                    img_path,
                    contrast=contrast,
                    brightness=brightness,
                    sharpness=1.0,
                    auto_enhance=True
                )

                processed_images.append(enhanced_img_path)

                # Удаляем временное изображение
                if os.path.exists(img_path):
                    os.remove(img_path)

            doc.close()

            # Конвертируем обратно в PDF
            if processed_images:
                with open(output_pdf_path, "wb") as f:
                    f.write(img2pdf.convert(processed_images))

            # Очищаем временные изображения
            for img_path in processed_images:
                if os.path.exists(img_path):
                    os.remove(img_path)

            return output_pdf_path

        except Exception as e:
            print(f"Error adjusting contrast/brightness: {e}")
            # В случае ошибки возвращаем оригинальный файл
            return pdf_path

    def get_enhancement_presets(self) -> Dict[str, Dict]:
        """Получение предустановленных настроек улучшения"""
        return {
            'light': {'contrast': 1.2, 'brightness': 10, 'sharpness': 1.1, 'auto_enhance': True},
            'medium': {'contrast': 1.5, 'brightness': 20, 'sharpness': 1.2, 'auto_enhance': True},
            'strong': {'contrast': 2.0, 'brightness': 30, 'sharpness': 1.5, 'auto_enhance': True},
            'text_only': {'contrast': 2.5, 'brightness': 15, 'sharpness': 2.0, 'auto_enhance': False},
            'photo': {'contrast': 1.3, 'brightness': 25, 'sharpness': 1.1, 'auto_enhance': True},
            'custom': {}  # Пользовательские настройки
        }

    def apply_preset(self, user_id: int, preset_name: str):
        """Применение предустановленных настроек"""
        presets = self.get_enhancement_presets()
        if preset_name in presets:
            self.update_user_settings(user_id, presets[preset_name])
            return True
        return False

    # Остальные методы остаются без изменений (optimize_image_size, compress_pdf и т.д.)
    def optimize_image_size(self, image_path: str, max_file_size: int = 1024 * 1024) -> bool:
        """Оптимизация размера файла изображения для Telegram"""
        try:
            file_size = os.path.getsize(image_path)
            if file_size <= max_file_size:
                return True

            with Image.open(image_path) as img:
                original_width, original_height = img.size

                # Определяем максимальные размеры для Telegram
                max_dimension = 1280
                if original_width > max_dimension or original_height > max_dimension:
                    # Сохраняем пропорции
                    ratio = min(max_dimension / original_width, max_dimension / original_height)
                    new_width = int(original_width * ratio)
                    new_height = int(original_height * ratio)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Постепенно уменьшаем качество
                quality = 90
                while quality > 40 and file_size > max_file_size:
                    # Сохраняем во временный файл
                    temp_path = image_path + ".tmp"

                    if img.mode != 'RGB':
                        img = img.convert('RGB')

                    img.save(temp_path, "JPEG", quality=quality, optimize=True)
                    file_size = os.path.getsize(temp_path)
                    quality -= 10

                # Заменяем оригинальный файл оптимизированным
                if os.path.exists(temp_path):
                    os.replace(temp_path, image_path)

                return True

        except Exception as e:
            print(f"Error optimizing image size: {e}")
            return False