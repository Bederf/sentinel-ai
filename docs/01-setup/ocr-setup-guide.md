# OCR Infrastructure Setup Guide

**Last Updated:** 2026-02-09
**Status:** Core Infrastructure (Required)

## Overview

OCR (Optical Character Recognition) is a **core infrastructure component** used across multiple SENTINEL BMS Intelligence modules:

| Module | Use Case | Phase |
|--------|----------|-------|
| **Floor Plan Sanitization** | Extract text labels before API transmission (security) | Phase A (Digital Twin) |
| **Work Order Pipeline** | Parse technician service sheets and meter readings | Phase 41 (Technician Mobile) |
| **Equipment Vision** | Read model/serial plates from photos | Vision Service |
| **Equipment Lookup** | Extract building/equipment identifiers from documents | Equipment Manager |

## System Requirements

### 1. Python Package
Already included in `backend/requirements.txt`:
```
pytesseract>=0.3.10
```

### 2. System Binary (tesseract-ocr)
**Required:** Install the Tesseract-OCR system binary

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr libtesseract-dev
```

**Verify installation:**
```bash
tesseract --version
# Expected: tesseract 4.x.x or 5.x.x
```

#### macOS
```bash
brew install tesseract
```

**Verify:**
```bash
tesseract --version
```

#### Windows (WSL or Native)
**Windows WSL:**
```bash
wsl
sudo apt-get update
sudo apt-get install -y tesseract-ocr libtesseract-dev
```

**Windows Native:**
- Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
- Install to default location: `C:\Program Files\Tesseract-OCR`
- Or use: `choco install tesseract` (if using Chocolatey)

**Configure PATH in Python:**
```python
import pytesseract
pytesseract.pytesseract.pytesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

#### Docker
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*
```

#### Cloud Platforms

**AWS EC2:**
```bash
sudo yum update -y
sudo yum install -y tesseract
```

**Google Cloud Platform:**
```bash
sudo apt-get install -y tesseract-ocr libtesseract-dev
```

**Azure Container Instances:**
Use Docker base image with tesseract pre-installed.

## Language Support

### Additional OCR Languages
For multi-language support (e.g., Afrikaans for South African documents):

```bash
# Install language data for all languages
sudo apt-get install -y tesseract-ocr-all

# Or specific languages:
# English (default, already included)
# Afrikaans
sudo apt-get install -y tesseract-ocr-afr
# Multiple language installation
sudo apt-get install -y tesseract-ocr-{eng,afr,equ}
```

### Using Alternative Languages in Code
```python
import pytesseract
from PIL import Image

image = Image.open("document_afrikaans.png")
text = pytesseract.image_to_string(image, lang='afr')
```

## Configuration

### Environment Variables
```bash
# Optional: Specify tesseract binary location (if non-standard)
export TESSERACT_CMD=/usr/bin/tesseract

# Optional: Set language preference
export TESSERACT_LANG=eng+afr
```

### Python Configuration
In application startup (`backend/app/config/settings.py`):
```python
import os
import pytesseract

# Auto-detect tesseract installation
try:
    pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
except pytesseract.TesseractNotFoundError:
    TESSERACT_AVAILABLE = False
    logger.warning("Tesseract-OCR not installed. Some features degraded.")
```

## Graceful Degradation

OCR failures are graceful within SENTINEL systems:

### Floor Plan Sanitization (Phase A)
- **Without OCR:** Removes text by masking regions (basic geometry preserved)
- **Result:** Geometric skeleton still works for Claude vision extraction
- **Status:** ✅ Acceptable (security maintained)

### Work Order Technician Pipeline (Phase 41)
- **Without OCR:** Service sheet data must be entered manually
- **Status:** ⚠️ Degraded functionality
- **Workaround:** Technician uses text input fields in Clawd bot

### Equipment Vision
- **Without OCR:** Serial plates must be identified manually
- **Status:** ⚠️ Degraded functionality
- **Workaround:** Technician provides serial manually

## Testing OCR Installation

### Quick Test
```bash
# In backend directory
python3 << 'EOF'
import pytesseract
from PIL import Image

# Test text extraction
test_text = pytesseract.image_to_string(Image.new('RGB', (100, 30), color='white'))
print("OCR Status: ✅ WORKING")
EOF
```

### Comprehensive Test
```bash
cd backend
source venv/bin/activate
pytest tests/services/test_floor_plan_sanitizer.py::TestFloorPlanSanitizer::test_extract_text_regions -v
# Should PASS if tesseract installed, SKIP if not
```

### Real Document Test
```bash
python3 << 'EOF'
from app.services.floor_plan_sanitizer import get_floor_plan_sanitizer

sanitizer = get_floor_plan_sanitizer()
print(f"OCR Installed: {sanitizer.ocr_installed}")

if sanitizer.ocr_installed:
    print("✅ OCR Ready for production")
else:
    print("⚠️  OCR Not installed - graceful degradation active")
EOF
```

## Troubleshooting

### Error: "tesseract is not installed"
```
TesseractNotFoundError: tesseract is not installed or it's not in your PATH
```

**Solution:**
1. Verify installation: `tesseract --version`
2. If not found, install (see system requirements above)
3. Add to PATH if in non-standard location:
   ```bash
   export PATH="/custom/path/to/tesseract:$PATH"
   ```
4. Or set in Python:
   ```python
   import pytesseract
   pytesseract.pytesseract.pytesseract_cmd = '/custom/path/tesseract'
   ```

### Error: "libtesseract.so.4 not found"
```
OSError: libtesseract.so.4 not found
```

**Solution:**
```bash
# Install development headers
sudo apt-get install -y libtesseract-dev
```

### Poor OCR Accuracy on Floor Plans
**Symptoms:** Equipment labels misread, text cut off

**Solutions:**
1. **Image Quality:** Ensure floor plan is > 150 DPI
2. **Contrast:** Increase image contrast before OCR:
   ```python
   from PIL import ImageEnhance
   enhancer = ImageEnhance.Contrast(image)
   image = enhancer.enhance(2.0)
   ```
3. **Language:** Specify correct language:
   ```python
   pytesseract.image_to_string(image, lang='eng+afr')
   ```
4. **Preprocessing:** Apply threshold:
   ```python
   import cv2
   _, image = cv2.threshold(image, 150, 255, cv2.THRESH_BINARY)
   ```

### Docker Container OCR Issues
**Symptom:** Works locally, fails in Docker

**Solution:** Ensure Dockerfile includes tesseract installation (see Docker section above)

### Performance: OCR Too Slow
**Symptom:** Floor plan extraction takes > 30 seconds

**Solutions:**
1. **Reduce image size:** Downscale before OCR
   ```python
   image.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
   ```
2. **Extract ROI:** OCR only regions with text (not entire image)
3. **Parallel processing:** Process multiple floors concurrently
4. **Cloud OCR alternative:** For non-sensitive data, use Azure OCR or AWS Textract

## Production Deployment

### Kubernetes Deployment
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: bms-backend
spec:
  containers:
  - name: bms-backend
    image: bms-backend:latest
    # Tesseract included in container image
    # See Dockerfile in project root
```

### Docker Compose
```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    # Tesseract installed via Dockerfile
```

### Health Check
Include OCR status in health endpoint:
```python
@router.get("/health")
async def health_check():
    from app.services.floor_plan_sanitizer import get_floor_plan_sanitizer
    sanitizer = get_floor_plan_sanitizer()
    return {
        "status": "healthy",
        "ocr_available": sanitizer.ocr_installed,
        "components": {
            "ocr": "available" if sanitizer.ocr_installed else "missing"
        }
    }
```

## Performance Metrics

### Typical OCR Performance
| Operation | Time | VRAM | CPU |
|-----------|------|------|-----|
| Load image | 10ms | 5MB | <1% |
| Text detection | 100-500ms | 20MB | 40-80% |
| Equipment extraction | 50-200ms | 15MB | 30-60% |
| **Total per floor** | **200-800ms** | **50MB** | **40-80%** |

### Optimization Tips
1. **Batch processing:** OCR multiple floors in parallel (separate processes)
2. **Image optimization:** Compress before OCR (trades accuracy for speed)
3. **ROI extraction:** Only OCR regions likely to have text
4. **Caching:** Cache OCR results for identical images

## Security Considerations

### Floor Plan Sanitization (Phase A)
OCR is used to **identify and remove** sensitive text before API transmission:
- ✅ Original floor plan stays local
- ✅ OCR extracts text positions locally
- ✅ Only geometric skeleton sent to Claude API
- ✅ Text never leaves building

### Data Privacy
OCR output is treated as potentially sensitive:
- Do NOT log OCR results in analytics
- Do NOT cache OCR results in shared storage
- OCR data is ephemeral (used only for immediate processing)

## Related Documentation

- **Floor Plan Sanitization:** `docs/04-features/digital-twin-builder.md` (Phase A)
- **Technician Mobile:** `docs/04-features/technician-mobile.md` (Phase 41)
- **Vision Service:** `backend/app/services/vision_service.py`
- **OCR Correction Handler:** `backend/app/services/clawd_integration/ocr_correction_handler.py`

## Checklist: OCR Setup

- [ ] Tesseract-OCR system binary installed (`tesseract --version` works)
- [ ] pytesseract Python package installed (in venv)
- [ ] `backend/tests/services/test_floor_plan_sanitizer.py` tests pass
- [ ] Health endpoint shows `"ocr_available": true`
- [ ] Floor plan sanitization works end-to-end
- [ ] Technician mobile OCR features functional
- [ ] Docker/cloud deployment includes tesseract
- [ ] Documentation updated with OCR requirements
- [ ] Team aware of OCR as core infrastructure

## Support

For OCR-related issues:
1. Check troubleshooting section above
2. Review test output: `pytest tests/services/test_floor_plan_sanitizer.py -v`
3. Check tesseract version: `tesseract --version`
4. Review logs: `grep -i ocr backend/app.log`
5. Escalate: Report with system tesseract version and error details

---

**Status:** ✅ Production Ready
**Last Verified:** 2026-02-09
**Maintained By:** SENTINEL Development Team
