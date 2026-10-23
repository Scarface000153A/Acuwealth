"""OCR subprocess worker.

Runs RapidOCR in a short-lived process so all ONNX Runtime memory is returned
to the OS when it exits. The main web worker (gunicorn, 512MB on Render) would
otherwise accumulate ORT arena memory across imports and get OOM-killed.

Usage:  python _ocr_worker.py <pdf|image>  < raw_bytes >  stdout: JSON [page_text,...]
"""
import io
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import import_service


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else 'pdf'
    data = sys.stdin.buffer.read()
    texts = []

    if mode == 'pdf':
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                page_image = page.to_image(resolution=200).original.convert('RGB')
                texts.append(import_service._rapidocr_image_to_text(page_image))
    else:
        from PIL import Image
        image = Image.open(io.BytesIO(data)).convert('RGB')
        texts.append(import_service._rapidocr_image_to_text(image))

    sys.stdout.write(json.dumps(texts))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
