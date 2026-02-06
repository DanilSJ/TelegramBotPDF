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
import cv2

class PDFProcessor:
    def __init__(self):
        self.user_settings_file = "user_settings.json"
        self.user_settings = self.load_user_settings()
        self.default_settings = {
            'contrast': 2.0,  # Увеличил до экстремального
            'brightness': 50,  # Увеличил до экстремального
            'sharpness': 1.5,
            'auto_enhance': True,
            'dpi': 300
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

    async def _compress_pdf_with_method(self, pdf_path: str, method: str) -> Optional[str]:
        """Внутренний метод сжатия с конкретным алгоритмом"""
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, f"compressed_{method}.pdf")

        try:
            return await self._compress_with_ghostscript(
                pdf_path, output_path
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

    def _final_optimize(self, path):
        doc = fitz.open(path)
        doc.save(
            path,
            garbage=4,
            deflate=True,
            clean=True
        )
        doc.close()

    async def _compress_with_ghostscript(self, pdf_path: str, output_path: str, settings: dict) -> str:
        gs = "gswin64c" if os.name == "nt" else "gs"
        command = [
            gs,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",

            # Экстремальное сжатие
            "-dPDFSETTINGS=/screen",
            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            "-dSubsetFonts=true",
            "-dDownsampleColorImages=true",
            "-dDownsampleGrayImages=true",
            "-dDownsampleMonoImages=true",
            "-dColorImageResolution=72",
            "-dGrayImageResolution=72",
            "-dMonoImageResolution=72",
            "-dColorImageDownsampleType=/Bicubic",
            "-dGrayImageDownsampleType=/Bicubic",
            "-dAutoFilterColorImages=false",
            "-dAutoFilterGrayImages=false",
            "-dColorImageFilter=/DCTEncode",
            "-dGrayImageFilter=/DCTEncode",
            "-dJPEGQ=30",
            "-dStripICCProfiles=true",
            "-dFastWebView=false",

            f"-sOutputFile={output_path}",
            pdf_path
        ]

        proc = await asyncio.create_subprocess_exec(*command)
        await proc.communicate()

        if not os.path.exists(output_path):
            raise Exception("Ghostscript failed")

        return output_path

    async def _compress_with_fitz(self, pdf_path, output_path, settings):

        dpi = settings["image_dpi"]
        quality = settings["image_quality"]

        doc = fitz.open(pdf_path)
        new = fitz.open()

        zoom = dpi / 72

        for p in doc:
            pix = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)

            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=quality, optimize=True)

            page = new.new_page(width=pix.width, height=pix.height)
            page.insert_image(page.rect, stream=buf.getvalue())

        new.save(output_path, garbage=4, deflate=True)
        doc.close()
        new.close()

        return output_path

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

    async def enhance_image_with_settings(
            self,
            image_path: str,
            contrast: float = 1.15,
            brightness: float = 0,
            quality: int = 200,
            dpi: int = 300
    ) -> str:

        try:
            img = cv2.imread(image_path)
            if img is None:
                return image_path

            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # === DPI scaling (НЕ трогаем пользовательские значения) ===

            user_contrast = contrast
            user_brightness = brightness

            base_dpi = 300.0
            dpi_factor = dpi / base_dpi

            effective_contrast = float(user_contrast * dpi_factor)
            effective_brightness = int(user_brightness * dpi_factor)

            effective_contrast = max(0.3, min(effective_contrast, 8.0))
            effective_brightness = max(-150, min(effective_brightness, 150))

            img = img.astype(np.float32)

            img = img * effective_contrast + effective_brightness

            img = np.clip(img, 0, 255)

            img = img.astype(np.uint8)

            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            output_path = image_path.replace(".jpg", "_enhanced.jpg")

            cv2.imwrite(
                output_path,
                img,
                [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            )

            return output_path

        except Exception as e:
            print("OpenCV enhance error:", e)
            return image_path

    def _apply_extreme_brightness(self, img: Image.Image, brightness: float) -> Image.Image:
        """Применение экстремальной яркости"""
        import numpy as np

        img_array = np.array(img, dtype=np.float32)

        # Сильное осветление всех каналов
        boost_factor = 1 + (brightness / 50)  # Очень агрессивный коэффициент
        img_array = img_array * boost_factor

        # Добавляем смещение для очень светлых тонов
        offset = brightness * 2
        img_array = img_array + offset

        # Обрезаем значения
        img_array = np.clip(img_array, 0, 255)

        return Image.fromarray(img_array.astype(np.uint8))

    def _apply_extreme_darkness(self, img: Image.Image, darkness: float) -> Image.Image:
        """Применение экстремальной темноты"""
        import numpy as np

        img_array = np.array(img, dtype=np.float32)

        # Сильное затемнение
        dark_factor = 1 - (darkness / 100)
        img_array = img_array * max(dark_factor, 0.1)  # Не ниже 10%

        # Дополнительное смещение для очень темных тонов
        offset = -darkness * 1.5
        img_array = img_array + offset

        # Обрезаем значения
        img_array = np.clip(img_array, 0, 255)

        return Image.fromarray(img_array.astype(np.uint8))

    def _boost_saturation(self, img: Image.Image, contrast: float) -> Image.Image:
        """Усиление насыщенности цвета"""
        from PIL import ImageEnhance

        # Конвертируем в HSV для работы с насыщенностью
        hsv_img = img.convert('HSV')
        h, s, v = hsv_img.split()

        # Усиливаем насыщенность
        saturation_factor = min(1.0 + (contrast - 1.0) * 0.5, 3.0)
        enhancer = ImageEnhance.Brightness(s)
        s_enhanced = enhancer.enhance(saturation_factor)

        # Собираем обратно
        enhanced_hsv = Image.merge('HSV', (h, s_enhanced, v))
        return enhanced_hsv.convert('RGB')

    def _apply_color_extremes(self, img: Image.Image, brightness: float, contrast: float) -> Image.Image:
        """Применение экстремальной коррекции цвета"""
        import numpy as np

        img_array = np.array(img, dtype=np.float32)

        # Разделяем каналы
        r, g, b = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2]

        # Создаем экстремальные цветовые эффекты
        if brightness > 0:
            # Для осветления - усиливаем теплые тоны
            r = r * (1.0 + (brightness / 100) * 0.3)
            g = g * (1.0 + (brightness / 100) * 0.1)
        elif brightness < 0:
            # Для затемнения - усиливаем холодные тоны
            b = b * (1.0 + (abs(brightness) / 100) * 0.2)

        if contrast > 1.5:
            # Экстремальный контраст - разделение тонов
            mask = (r + g + b) / 3 > 128
            r[mask] = r[mask] * 1.2
            g[mask] = g[mask] * 1.2
            b[mask] = b[mask] * 1.2
            r[~mask] = r[~mask] * 0.8
            g[~mask] = g[~mask] * 0.8
            b[~mask] = b[~mask] * 0.8

        # Собираем обратно и обрезаем
        img_array = np.stack([r, g, b], axis=2)
        img_array = np.clip(img_array, 0, 255)

        return Image.fromarray(img_array.astype(np.uint8))

    def _add_vignette(self, img: Image.Image, brightness: float) -> Image.Image:
        """Добавление виньетирования для драматического эффекта"""
        import numpy as np
        from PIL import ImageFilter

        width, height = img.size

        # Создаем маску виньетирования
        x = np.linspace(-1, 1, width)
        y = np.linspace(-1, 1, height)
        X, Y = np.meshgrid(x, y)

        # Радиальная маска
        radius = np.sqrt(X ** 2 + Y ** 2)

        if brightness > 0:
            # Для осветления - края темнее
            vignette = 1 - 0.5 * radius ** 2
        else:
            # Для затемнения - края светлее
            vignette = 0.5 + 0.5 * radius ** 2

        vignette = np.clip(vignette, 0, 1)

        # Применяем маску к изображению
        img_array = np.array(img, dtype=np.float32)
        img_array = img_array * vignette[..., np.newaxis]
        img_array = np.clip(img_array, 0, 255)

        return Image.fromarray(img_array.astype(np.uint8))

    # В классе PDFProcessor добавьте:

    async def pdf_to_images_simple(self, pdf_path: str, dpi: int = 300) -> List[str]:
        """Конвертация PDF в изображения ТОЛЬКО с настройкой DPI (без улучшений)"""
        images = []
        temp_dir = tempfile.mkdtemp()

        try:
            doc = fitz.open(pdf_path)

            # Получаем имя файла для названия изображений
            pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                zoom = dpi / 72

                # Ограничиваем максимальный размер для Telegram
                max_size = 10000
                rect = page.rect
                width = rect.width * zoom
                height = rect.height * zoom

                if width > max_size or height > max_size:
                    scale_factor = max_size / max(width, height)
                    zoom *= scale_factor

                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # Используем имя PDF файла в названии изображения
                img_path = os.path.join(temp_dir, f"{pdf_name}_page_{page_num + 1}.jpg")
                pix.save(img_path, output="jpg")

                # Оптимизируем размер для Telegram
                self.optimize_image_size(img_path, max_file_size=1024 * 1024)

                images.append(img_path)

            doc.close()

        except Exception as e:
            raise

        return images

    # В класс PDFProcessor добавьте:

    def validate_settings(self, user_id: int, dpi: int = None, contrast: float = None, brightness: int = None):
        """Валидация настроек пользователя"""
        errors = []

        if dpi is not None:
            if dpi < 72:
                errors.append("DPI не может быть меньше 72")
            elif dpi > 1200:
                errors.append("DPI не может быть больше 1200")

        if contrast is not None:
            if contrast < 0.1:
                errors.append("Контрастность не может быть меньше 0.1")
            elif contrast > 10.0:
                errors.append("Контрастность не может быть больше 10.0")

        if brightness is not None:
            if brightness < -100:
                errors.append("Яркость не может быть меньше -100")
            elif brightness > 100:
                errors.append("Яркость не может быть больше 100")

        return errors

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
            user_id: int = None
    ) -> List[str]:
        """Конвертация PDF в улучшенные изображения с применением настроек пользователя"""
        images = []
        temp_dir = tempfile.mkdtemp()

        try:
            # Получаем настройки пользователя
            if user_id:
                settings = self.get_user_settings(user_id)
                contrast = settings.get('contrast', 1.15)
                brightness = settings.get('brightness', 0)
                dpi = settings.get('dpi', 300)
            else:
                contrast = 1.15
                brightness = 0
                dpi = 300

            doc = fitz.open(pdf_path)

            # Получаем имя файла без расширения
            pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                zoom = dpi / 72

                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # Сохраняем временное изображение с именем исходного файла
                temp_img_path = os.path.join(temp_dir, f"{pdf_name}_page_{page_num + 1}.jpg")
                pix.save(temp_img_path, output="jpg")

                # Применяем улучшения (яркость и контраст)
                enhanced_img_path = await self.enhance_image_with_settings(
                    temp_img_path,
                    contrast=contrast,
                    brightness=brightness,
                    dpi=dpi
                )

                # Оптимизируем размер для Telegram
                self.optimize_image_size(enhanced_img_path, max_file_size=1024 * 1024)

                images.append(enhanced_img_path)

                # Удаляем временный файл если он отличается от улучшенного
                if enhanced_img_path != temp_img_path and os.path.exists(temp_img_path):
                    os.remove(temp_img_path)

            doc.close()

        except Exception as e:
            # Пробуем базовый метод как запасной вариант
            images = await self.pdf_to_images(pdf_path, dpi=dpi)

        return images

    async def pdf_to_images(self, pdf_path: str, dpi: int = None, max_size: int = 10000) -> List[str]:
        """Конвертация PDF в изображения"""
        images = []
        temp_dir = tempfile.mkdtemp()

        try:
            # Если DPI не указан, используем настройки по умолчанию
            if dpi is None:
                dpi = 300

            doc = fitz.open(pdf_path)

            # Получаем имя файла для названия изображений
            pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]

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

                # Используем имя PDF файла в названии изображения
                img_path = os.path.join(temp_dir, f"{pdf_name}_page_{page_num + 1}.jpg")
                pix.save(img_path, output="jpg")
                images.append(img_path)

            doc.close()

        except Exception as e:
            raise

        return images

    async def compress_pdf(self, pdf_path: str) -> str:
        temp_dir = tempfile.mkdtemp()
        output = os.path.join(temp_dir, "brutal.pdf")

        await self._brutal_rebuild(pdf_path, output)

        return output

    async def _nuke_with_ghostscript(self, input_pdf, output_pdf):

        cmd = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",

            "-dPDFSETTINGS=/screen",

            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            "-dSubsetFonts=true",
            "-dEmbedAllFonts=true",

            "-dDownsampleColorImages=true",
            "-dDownsampleGrayImages=true",
            "-dDownsampleMonoImages=true",

            "-dColorImageResolution=120",
            "-dGrayImageResolution=120",
            "-dMonoImageResolution=120",

            "-dColorImageDownsampleType=/Bicubic",
            "-dGrayImageDownsampleType=/Bicubic",

            "-dAutoFilterColorImages=false",
            "-dAutoFilterGrayImages=false",

            "-dColorImageFilter=/DCTEncode",
            "-dGrayImageFilter=/DCTEncode",

            "-dJPEGQ=40",

            "-dStripICCProfiles=true",
            "-dFastWebView=true",
            "-dDiscardCachedFonts=true",

            "-sOutputFile=" + output_pdf,
            input_pdf
        ]

        p = await asyncio.create_subprocess_exec(*cmd)
        await p.communicate()

        if not os.path.exists(output_pdf):
            raise Exception("GS failed")

    async def _brutal_rebuild(self, pdf_path, output_path):

        doc = fitz.open(pdf_path)
        new = fitz.open()

        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(1.3, 1.3), alpha=False)

            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=35, optimize=True)

            p = new.new_page(width=pix.width, height=pix.height)
            p.insert_image(p.rect, stream=buf.getvalue())

        new.save(output_path, garbage=4, deflate=True)
        doc.close()
        new.close()

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

        # Выполняем сжатие
        return await self.compress_pdf(pdf_path)


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
            preview_path = os.path.join(temp_dir, f"preview.jpg")
            pix.save(preview_path, output="jpg")
            doc.close()

            # Применяем текущие настройки
            enhanced_preview = await self.enhance_image_with_settings(
                preview_path,
                contrast=contrast,
                brightness=brightness,
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

        # Получаем оригинальное имя файла
        original_basename = os.path.basename(pdf_path)
        name_without_ext = os.path.splitext(original_basename)[0]

        # Конвертируем с нужным DPI
        images = await self.pdf_to_images(pdf_path, dpi=dpi)

        # Переименовываем файлы изображений
        renamed_images = []
        for i, image_path in enumerate(images, 1):
            dir_path = os.path.dirname(image_path)
            ext = os.path.splitext(image_path)[1]
            new_name = f"{name_without_ext}_страница_{i}{ext}"
            new_path = os.path.join(dir_path, new_name)

            # Переименовываем файл
            os.rename(image_path, new_path)
            renamed_images.append(new_path)

        return renamed_images


    async def compress_pdf_with_settings(self, pdf_path: str, user_id: int) -> str:
        """Сжатие PDF с учетом настроек пользователя"""
        # Сохраняем оригинальное имя
        original_dir = os.path.dirname(pdf_path)
        original_name = os.path.basename(pdf_path)

        # Получаем имя без расширения и расширение
        name_without_ext = os.path.splitext(original_name)[0]

        # Выполняем сжатие
        compressed_path = await self.smart_compress_pdf(pdf_path)

        # Переименовываем сжатый файл в оригинальное имя
        final_path = os.path.join(original_dir, original_name)

        # Если сжатый файл отличается по пути, перемещаем/переименовываем его
        if compressed_path != final_path:
            # Удаляем старый файл если существует
            if os.path.exists(final_path):
                os.remove(final_path)
            os.rename(compressed_path, final_path)

        return final_path

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
            updates['contrast'] = max(0.5, min(10.0, float(updates['contrast'])))  # Изменил с 3.0 на 10.0
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

    async def adjust_contrast_brightness(
            self,
            input_pdf_path: str,
            dpi: int = 150,
            contrast: float = 1.0,
            brightness: float = 1.0,
            original_name: str = "output.pdf"
    ):

        # Force brutal always
        zoom = dpi / 72

        doc = fitz.open(input_pdf_path)
        new_doc = fitz.open()

        for page in doc:

            pix = page.get_pixmap(
                matrix=fitz.Matrix(zoom, zoom),
                alpha=False
            )

            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Apply enhancements
            if contrast != 1.0:
                img = ImageEnhance.Contrast(img).enhance(contrast)

            if brightness != 1.0:
                img = ImageEnhance.Brightness(img).enhance(brightness)

            buf = io.BytesIO()

            img.save(
                buf,
                "JPEG",
                quality=60,
                subsampling=2,
                optimize=True
            )

            p = new_doc.new_page(width=pix.width, height=pix.height)
            p.insert_image(p.rect, stream=buf.getvalue())

        temp_dir = tempfile.mkdtemp()
        out_path = os.path.join(temp_dir, original_name)

        new_doc.save(out_path, garbage=4, deflate=True)

        doc.close()
        new_doc.close()

        return out_path

    def _optimize_pdf_size(self, pdf_path: str):
        """Оптимизация размера PDF файла"""
        try:
            # Переоткрываем и пересохраняем с оптимизацией
            doc = fitz.open(pdf_path)
            doc.save(pdf_path,
                     garbage=4,  # Удаление неиспользуемых объектов
                     deflate=True,  # Сжатие потоков
                     clean=True)  # Очистка
            doc.close()
        except:
            pass

    def _create_pdf_from_images_alternative(self, images: list, output_path: str) -> str:
        """Альтернативный метод создания PDF из изображений"""
        try:
            from PIL import Image
            import img2pdf

            # Открываем все изображения
            img_objects = []
            for img_path in images:
                with Image.open(img_path) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    # Сохраняем с оптимизацией
                    optimized_path = img_path + "_opt.jpg"
                    img.save(optimized_path, "JPEG", quality=75, optimize=True)
                    img_objects.append(optimized_path)

            # Создаем PDF
            with open(output_path, "wb") as f:
                f.write(img2pdf.convert(img_objects))

            # Удаляем временные файлы
            for path in img_objects:
                if os.path.exists(path):
                    os.remove(path)

            return output_path
        except Exception as e:

            raise

    async def compress_pdf_safe(self, pdf_path: str, user_id: int) -> str:
        """Безопасное сжатие без увеличения размера"""
        original_size = os.path.getsize(pdf_path)

        # Пробуем обычное сжатие
        compressed_path = await self.compress_pdf_with_settings(pdf_path, user_id)
        compressed_size = os.path.getsize(compressed_path)

        try:
            test_path = await self._compress_pdf_with_method(pdf_path)
            test_size = os.path.getsize(test_path)

            os.remove(test_path)

        except:
            pass



        if os.path.exists(compressed_path) and compressed_path != pdf_path:
            os.remove(compressed_path)

        return pdf_path

    def get_enhancement_presets(self) -> Dict[str, Dict]:
        """Получение ПРЕДУСТАНОВЛЕННЫХ НАСТРОЕК с экстремальными эффектами"""
        return {
            'light': {'contrast': 1.5, 'brightness': 30, 'sharpness': 1.2, 'auto_enhance': True},
            'medium': {'contrast': 2.0, 'brightness': 50, 'sharpness': 1.5, 'auto_enhance': True},
            'strong': {'contrast': 2.5, 'brightness': 70, 'sharpness': 2.0, 'auto_enhance': True},
            'extreme_light': {'contrast': 3.0, 'brightness': 80, 'sharpness': 2.5, 'auto_enhance': False},
            'extreme_dark': {'contrast': 2.8, 'brightness': -60, 'sharpness': 2.0, 'auto_enhance': False},
            'vivid_colors': {'contrast': 2.2, 'brightness': 40, 'sharpness': 1.8, 'auto_enhance': True},
            'dramatic_bw': {'contrast': 3.0, 'brightness': 20, 'sharpness': 2.5, 'auto_enhance': False},
            'custom': {}  # Пользовательские настройки
        }

    def apply_preset(self, user_id: int, preset_name: str):
        """Применение предустановленных настроек"""
        presets = self.get_enhancement_presets()
        if preset_name in presets:
            self.update_user_settings(user_id, presets[preset_name])
            return True
        return False

    async def compress_pdf_with_enhancement(self, pdf_path: str, user_id: int) -> str:
        return await self.compress_pdf_safe(pdf_path, user_id)

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