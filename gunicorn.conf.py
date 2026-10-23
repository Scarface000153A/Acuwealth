# Gunicorn auto-configuration (picked up automatically, no dashboard changes needed).
#
# OCR of scanned PDFs (RapidOCR ONNX inference) can exceed gunicorn's default
# 30s worker timeout on Render's small instances, which kills the worker and
# returns an empty response. Allow ample time for multi-page OCR.
timeout = 300
graceful_timeout = 300
# Keep memory bounded on free-tier instances (512MB): ONNX models are loaded
# into each worker's memory, so a single worker avoids doubling footprint.
workers = 1
threads = 2
