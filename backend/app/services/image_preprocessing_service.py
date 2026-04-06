"""Image preprocessing for OCR pipeline.

Prepares uploaded photos (job cards, service sheets) for Claude Vision extraction:
- Deskew via Hough line transform
- Denoise via fastNlMeansDenoising
- Contrast enhancement via CLAHE
- Auto-crop to document boundary
- Resize for API limits (max 2048px)
- Quality assessment (blur score, brightness)
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Quality thresholds — skip preprocessing steps when input is already good
BLUR_THRESHOLD = 100.0  # Laplacian variance; higher = sharper
SKEW_THRESHOLD = 0.5  # degrees; skip deskew if below
BRIGHTNESS_LOW = 60
BRIGHTNESS_HIGH = 200
MAX_DIMENSION = 2048  # Max px for Claude Vision


class ImagePreprocessor:
    """Adaptive image preprocessor for document photos."""

    def preprocess(self, image_data: bytes, media_type: str) -> tuple[bytes, dict]:
        """Run adaptive preprocessing pipeline.

        Args:
            image_data: Raw image bytes (JPEG/PNG)
            media_type: MIME type (image/jpeg, image/png)

        Returns:
            Tuple of (processed_bytes, metadata_dict)
        """
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image")

        quality = self._assess_quality(img)
        steps_applied = []

        # Deskew if needed
        if abs(quality.get("skew_angle", 0)) > SKEW_THRESHOLD:
            img = self._deskew(img, quality["skew_angle"])
            steps_applied.append("deskew")

        # Denoise if blurry
        if quality["blur_score"] < BLUR_THRESHOLD:
            img = self._denoise(img)
            steps_applied.append("denoise")

        # Enhance contrast if brightness is off
        brightness = quality["brightness"]
        if brightness < BRIGHTNESS_LOW or brightness > BRIGHTNESS_HIGH:
            img = self._enhance_contrast(img)
            steps_applied.append("contrast")

        # Auto-crop to document boundary
        cropped = self._auto_crop(img)
        if cropped is not None:
            img = cropped
            steps_applied.append("crop")

        # Resize for API
        img = self._resize_for_api(img)
        steps_applied.append("resize")

        # Re-assess quality after processing
        final_quality = self._assess_quality(img)

        # Encode back to bytes
        ext = ".png" if "png" in media_type else ".jpg"
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 92] if ext == ".jpg" else []
        _, encoded = cv2.imencode(ext, img, encode_params)
        processed_bytes = encoded.tobytes()

        metadata = {
            "original_blur_score": round(quality["blur_score"], 2),
            "final_blur_score": round(final_quality["blur_score"], 2),
            "skew_angle": round(quality.get("skew_angle", 0), 2),
            "brightness": round(brightness, 1),
            "steps_applied": steps_applied,
            "original_size": len(image_data),
            "processed_size": len(processed_bytes),
        }

        logger.info(
            "Preprocessed image: steps=%s, blur %.1f→%.1f",
            steps_applied,
            quality["blur_score"],
            final_quality["blur_score"],
        )

        return processed_bytes, metadata

    def _assess_quality(self, img: np.ndarray) -> dict:
        """Assess image quality metrics."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Blur score via Laplacian variance (higher = sharper)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Brightness (mean pixel value)
        brightness = float(np.mean(gray))

        # Skew angle via Hough lines
        skew_angle = self._detect_skew(gray)

        return {
            "blur_score": float(blur_score),
            "brightness": brightness,
            "skew_angle": skew_angle,
        }

    def _detect_skew(self, gray: np.ndarray) -> float:
        """Detect document skew angle using Hough line transform."""
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10)
        if lines is None:
            return 0.0

        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            # Only consider near-horizontal lines
            if abs(angle) < 15:
                angles.append(angle)

        if not angles:
            return 0.0

        return float(np.median(angles))

    def _deskew(self, img: np.ndarray, angle: float) -> np.ndarray:
        """Rotate image to correct skew."""
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    def _denoise(self, img: np.ndarray) -> np.ndarray:
        """Adaptive denoising."""
        return cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)

    def _enhance_contrast(self, img: np.ndarray) -> np.ndarray:
        """CLAHE histogram equalization on L channel."""
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(l_channel)
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    def _auto_crop(self, img: np.ndarray) -> np.ndarray | None:
        """Crop to largest rectangular contour (document boundary)."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        area_ratio = cv2.contourArea(largest) / (img.shape[0] * img.shape[1])

        # Only crop if the contour covers 30-95% of the image
        if area_ratio < 0.3 or area_ratio > 0.95:
            return None

        x, y, w, h = cv2.boundingRect(largest)
        # Add small margin
        margin = 5
        x = max(0, x - margin)
        y = max(0, y - margin)
        w = min(img.shape[1] - x, w + 2 * margin)
        h = min(img.shape[0] - y, h + 2 * margin)

        return img[y : y + h, x : x + w]

    def _resize_for_api(self, img: np.ndarray) -> np.ndarray:
        """Resize so longest edge <= MAX_DIMENSION."""
        h, w = img.shape[:2]
        if max(h, w) <= MAX_DIMENSION:
            return img

        scale = MAX_DIMENSION / max(h, w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


# Singleton
_preprocessor: ImagePreprocessor | None = None


def get_image_preprocessor() -> ImagePreprocessor:
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = ImagePreprocessor()
    return _preprocessor
