"""
Smart Import Service for UPI/Bank Transactions.

Supports:
- Image OCR (screenshots from UPI apps, bank apps)
- PDF parsing (bank statements, UPI app exports)
- CSV/Excel parsing (standard bank exports)
- SMS/Email text parsing (forwarded transaction notifications)

Auto-detects:
- Transaction type (income/expense)
- Amount, date, description/merchant
- UPI-specific patterns (GPay, PhonePe, Paytm, BHIM, etc.)
- Auto-categorization based on merchant keywords
"""

import re
import io
import csv
from datetime import datetime, date, timedelta
from typing import Any, Optional
from decimal import Decimal

from PIL import Image
import pandas as pd
import pdfplumber

# Optional: pytesseract for OCR (requires Tesseract binary installed)
try:
    import pytesseract
    # Set tesseract path for Windows if not in PATH
    import os
    import platform
    
    if platform.system() == 'Windows':
        # Common Tesseract installation paths
        tesseract_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        ]
        for path in tesseract_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break
    
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

# Optional: rapidocr (pure-pip OCR, works without system binaries - used on servers)
try:
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    RAPIDOCR_AVAILABLE = True
except ImportError:
    RAPIDOCR_AVAILABLE = False

_ocr_engine = None


def _get_ocr_engine():
    """Lazily create the RapidOCR engine (loads ONNX models on first use)."""
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = RapidOCR()
    return _ocr_engine


def _rapidocr_image_to_text(image) -> str:
    """OCR an image with RapidOCR and reconstruct reading-order text.
    
    RapidOCR returns positioned text boxes. We group them into lines by
    vertical position, order left-to-right, and re-insert the spaces it
    tends to drop between letters/digits (e.g. "22Oct2026" -> "22 Oct 2026").
    """
    # Cap image size: full-size A4 scans at 200 DPI exhaust the memory of
    # small server instances (Render free tier = 512MB -> worker OOM kill).
    # PP-OCR is accurate on ~1600px images.
    max_side = 1600
    if max(image.size) > max_side:
        scale = max_side / max(image.size)
        image = image.resize(
            (max(1, int(image.size[0] * scale)), max(1, int(image.size[1] * scale))),
            Image.LANCZOS)
    
    engine = _get_ocr_engine()
    result, _ = engine(np.array(image))
    if not result:
        return ''
    
    # Each item: [box(4 points), text, score]
    items = []
    for box, text, score in result:
        if not text or not text.strip():
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append({
            'x': min(xs), 'y': min(ys), 'h': max(ys) - min(ys), 'text': text.strip(),
        })
    
    # Group into lines: items whose vertical centers are close together
    items.sort(key=lambda it: it['y'])
    lines = []
    for item in items:
        placed = False
        for line in lines:
            ref = line[0]
            if abs((item['y'] + item['h'] / 2) - (ref['y'] + ref['h'] / 2)) < max(item['h'], ref['h']) * 0.6:
                line.append(item)
                placed = True
                break
        if not placed:
            lines.append([item])
    
    out_lines = []
    for line in lines:
        line.sort(key=lambda it: it['x'])
        line_text = ' '.join(it['text'] for it in line)
        # Re-insert spaces the model drops between digit/letter boundaries
        line_text = re.sub(r'(\d)([A-Za-z])', r'\1 \2', line_text)
        line_text = re.sub(r'([A-Za-z])(\d)', r'\1 \2', line_text)
        out_lines.append(line_text)
    
    return '\n'.join(out_lines)

# Optional: cv2 for image preprocessing
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


# ============ CATEGORY MAPPING ============
MERCHANT_CATEGORIES = {
    # Dining
    'zomato': 'Dining',
    'swiggy': 'Dining',
    'ubereats': 'Dining',
    'dunzo': 'Dining',
    'starbucks': 'Dining',
    'ccd': 'Dining',
    'dominos': 'Dining',
    'pizza hut': 'Dining',
    'mcdonald': 'Dining',
    'kfc': 'Dining',
    'burger king': 'Dining',
    
    # Transport
    'uber': 'Transport',
    'ola': 'ola',
    'rapido': 'Transport',
    'metro': 'Transport',
    'dmrc': 'Transport',
    'bmrc': 'Transport',
    'bus': 'Transport',
    'redbus': 'Transport',
    'make my trip': 'Travel',
    'goibibo': 'Travel',
    'ixigo': 'Travel',
    
    # Shopping
    'amazon': 'Shopping',
    'flipkart': 'Shopping',
    'myntra': 'Shopping',
    'ajio': 'Shopping',
    'nykaa': 'Shopping',
    'ikea': 'Shopping',
    'reliance': 'Shopping',
    'dmart': 'Shopping',
    'big bazaar': 'Shopping',
    
    # Utilities
    'electricity': 'Utilities',
    'water': 'Utilities',
    'gas': 'Utilities',
    'indane': 'Utilities',
    'bharat gas': 'Utilities',
    'jio': 'Utilities',
    'airtel': 'Utilities',
    'vi': 'Utilities',
    'vodafone': 'Utilities',
    'idea': 'Utilities',
    'act': 'Utilities',
    'spectranet': 'Utilities',
    
    # Entertainment
    'bookmyshow': 'Entertainment',
    'pvr': 'Entertainment',
    'inox': 'Entertainment',
    'netflix': 'Entertainment',
    'prime': 'Entertainment',
    'hotstar': 'Entertainment',
    'spotify': 'Entertainment',
    'youtube': 'Entertainment',
    
    # Healthcare
    'pharmeasy': 'Healthcare',
    '1mg': 'Healthcare',
    'netmeds': 'Healthcare',
    'apollo': 'Healthcare',
    'fortis': 'Healthcare',
    'max': 'Healthcare',
    
    # Education
    'byjus': 'Education',
    'unacademy': 'Education',
    'coursera': 'Education',
    'udemy': 'Education',
    
    # Travel
    'irctc': 'Travel',
    ' SpiceJet': 'Travel',
    'indigo': 'Travel',
    'vistara': 'Travel',
    'air india': 'Travel',
    'oyo': 'Travel',
    'goibibo': 'Travel',
    'booking': 'Travel',
    'agoda': 'Travel',
    
    # Income indicators
    'salary': 'Salary',
    'salary credit': 'Salary',
    'dividend': 'Investments',
    'interest': 'Investments',
    'refund': 'Other income',
    'cashback': 'Other income',
    'reward': 'Other income',
    'gift': 'Gifts',
}

UPI_APPS = ['google pay', 'gpay', 'phonepe', 'paytm', 'bhIM', 'amazon pay', 'whatsapp pay', 'mobiKwik', 'freecharge']


def parse_image_to_text(image_data: bytes) -> str:
    """Extract text from image using OCR (Tesseract, falling back to RapidOCR)."""
    image = Image.open(io.BytesIO(image_data))
    
    if not TESSERACT_AVAILABLE:
        if RAPIDOCR_AVAILABLE:
            # RapidOCR handles dark-mode screenshots well without preprocessing
            return _rapidocr_image_to_text(image.convert('RGB'))
        raise RuntimeError("No OCR engine is installed (need Tesseract or rapidocr-onnxruntime).")
    
    # Preprocess image for better OCR results
    # Convert to grayscale
    if image.mode != 'L':
        image = image.convert('L')
    
    # Increase image size for better OCR (2x)
    width, height = image.size
    image = image.resize((width * 2, height * 2), Image.LANCZOS)
    
    # Apply thresholding to make text clearer
    from PIL import ImageFilter, ImageOps
    # Enhance contrast
    image = ImageOps.autocontrast(image, cutoff=5)
    
    # Apply sharpening filter
    image = image.filter(ImageFilter.SHARPEN)
    
    # Preprocess if cv2 available for better results
    if CV2_AVAILABLE:
        img_array = np.array(image)
        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            img_array, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        image = Image.fromarray(thresh)
    
    # Extract text with English support for Indian UPI apps
    try:
        text = pytesseract.image_to_string(image, lang='eng')
    except Exception:
        try:
            text = pytesseract.image_to_string(image)
        except Exception as e:
            # Tesseract binary missing/broken - fall back to RapidOCR
            if RAPIDOCR_AVAILABLE:
                return _rapidocr_image_to_text(Image.open(io.BytesIO(image_data)).convert('RGB'))
            raise RuntimeError(f"OCR failed: {e}")
    
    if not text.strip() and RAPIDOCR_AVAILABLE:
        # Tesseract returned nothing (e.g. dark-mode screenshots) - try RapidOCR
        return _rapidocr_image_to_text(Image.open(io.BytesIO(image_data)).convert('RGB'))
    
    return text


def parse_pdf_to_text(pdf_data: bytes) -> str:
    """Extract text from PDF. Falls back to OCR for scanned PDFs (no text layer)."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        
        # Scanned PDF fallback: if no text layer found, OCR each page
        if not text_parts:
            if not TESSERACT_AVAILABLE and not RAPIDOCR_AVAILABLE:
                raise RuntimeError(
                    "This PDF has no selectable text (it is a scanned document) "
                    "and no OCR engine is installed on this server."
                )
            for page in pdf.pages:
                page_image = page.to_image(resolution=200).original
                page_text = ''
                if TESSERACT_AVAILABLE:
                    try:
                        try:
                            page_text = pytesseract.image_to_string(page_image, lang='eng')
                        except Exception:
                            page_text = pytesseract.image_to_string(page_image)
                    except Exception:
                        page_text = ''  # binary missing - use RapidOCR below
                if not page_text.strip() and RAPIDOCR_AVAILABLE:
                    try:
                        page_text = _rapidocr_image_to_text(page_image.convert('RGB'))
                    except Exception as e:
                        raise RuntimeError(f"OCR failed while reading the PDF: {e}")
                if page_text and page_text.strip():
                    text_parts.append(page_text)
    
    if not text_parts:
        raise RuntimeError(
            "No text could be extracted from this PDF. "
            "If it is a scanned document, ensure OCR (Tesseract) is installed on the server."
        )
    return '\n'.join(text_parts)


def parse_csv_excel(file_data: bytes, file_type: str = 'csv') -> list[dict]:
    """Parse CSV or Excel file to list of transaction dicts."""
    try:
        if file_type == 'excel':
            df = pd.read_excel(io.BytesIO(file_data))
        else:
            df = pd.read_csv(io.BytesIO(file_data), encoding_errors='ignore')
        
        # Normalize column names
        df.columns = df.columns.str.lower().str.strip()
        
        # Map common column variations
        date_cols = ['date', 'transaction date', 'txn date', 'value date', 'posted date']
        amount_cols = ['amount', 'txn amount', 'transaction amount', 'debit', 'credit', 'value']
        desc_cols = ['description', 'particulars', 'narration', 'remarks', 'details', 'merchant', 'payee', 'beneficiary']
        type_cols = ['type', 'txn type', 'transaction type', 'debit/credit', 'd/c']
        
        # Find matching columns
        date_col = next((col for col in date_cols if col in df.columns), None)
        amount_col = next((col for col in amount_cols if col in df.columns), None)
        desc_col = next((col for col in desc_cols if col in df.columns), None)
        type_col = next((col for col in type_cols if col in df.columns), None)
        
        if not all([date_col, amount_col]):
            # Try to infer from data patterns
            for col in df.columns:
                if 'date' in col.lower() and not date_col:
                    date_col = col
                if 'amount' in col.lower() or 'value' in col.lower() and not amount_col:
                    amount_col = col
            
            if not date_col or not amount_col:
                raise ValueError("Could not identify date and amount columns. Please ensure your CSV has clear column headers.")
        
        transactions = []
        for _, row in df.iterrows():
            try:
                txn = {
                    'date': normalize_date(str(row[date_col])),
                    'amount': clean_amount(str(row[amount_col])),
                    'description': str(row.get(desc_col, '')) if desc_col else '',
                    'kind': infer_transaction_type(str(row.get(type_col, '')), str(row.get(desc_col, ''))),
                }
                if txn['date'] and txn['amount']:
                    transactions.append(txn)
            except Exception:
                continue
        
        return transactions
    
    except Exception as e:
        raise ValueError(f"Failed to parse CSV/Excel: {str(e)}")


def parse_sms_email_text(text: str) -> list[dict]:
    """Parse SMS or email text for UPI/bank transactions."""
    transactions = []
    
    # Common patterns for Indian banks and UPI apps
    patterns = [
        # UPI patterns
        r'(?:debited|paid|spent)[\s:]+Rs\.?\s*([\d,]+\.?\d*)\s*(?:from|in|at)\s*([^\n]+?)(?:\s*on\s*|\s*at\s*|\s*for\s*)(\d{1,2}[/-]\d{1,2}[/-]?\d{2,4})',
        r'([\d,]+\.?\d*)\s*(?:debited|paid)\s*(?:from|on)\s*([^\n]+?)(?:\s*on\s*|\s*at\s*)(\d{1,2}[/-]\d{1,2}[/-]?\d{2,4})',
        r'(?:credited|received)[\s:]+Rs\.?\s*([\d,]+\.?\d*)\s*(?:in|from|to)\s*([^\n]+?)(?:\s*on\s*|\s*at\s*)(\d{1,2}[/-]\d{1,2}[/-]?\d{2,4})',
        
        # Bank SMS patterns
        r'A/c\s+[\*X\d]+\s+(?:debited|credited)\s+with\s+Rs\.?\s*([\d,]+\.?\d*)\s+(?:on|at)\s+(\d{1,2}[/-]\d{1,2}[/-]?\d{2,4})\s+(?:towards|for)?\s*([^\n]+)?',
        r'INR\s*([\d,]+\.?\d*)\s+(?:debited|credited)\s+(?:from|to)\s+([^\n]+?)\s+(?:on|at)\s+(\d{1,2}[/-]\d{1,2}[/-]?\d{2,4})',
        
        # GPay/PhonePe specific
        r'(?:You paid|Paid to)\s+([^\n]+?)\s+of\s+Rs\.?\s*([\d,]+\.?\d*)\s+(?:on|at)\s+(\d{1,2}[/-]\d{1,2}[/-]?\d{2,4})',
        r'(?:Received|Got)\s+Rs\.?\s*([\d,]+\.?\d*)\s+(?:from|on)\s+([^\n]+?)\s+(?:on|at)\s+(\d{1,2}[/-]\d{1,2}[/-]?\d{2,4})',
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            groups = match.groups()
            if len(groups) >= 3:
                # Try to determine order based on pattern
                if 'credited' in match.group(0).lower() or 'received' in match.group(0).lower() or 'paid to' in match.group(0).lower():
                    # Income pattern
                    amount = clean_amount(groups[0])
                    desc = groups[1].strip() if len(groups) > 1 else ''
                    date_str = groups[2].strip() if len(groups) > 2 else ''
                    kind = 'income'
                else:
                    # Expense pattern
                    amount = clean_amount(groups[0])
                    desc = groups[1].strip() if len(groups) > 1 else ''
                    date_str = groups[2].strip() if len(groups) > 2 else ''
                    kind = 'expense'
                
                if amount and date_str:
                    transactions.append({
                        'date': normalize_date(date_str),
                        'amount': amount,
                        'description': desc,
                        'kind': kind,
                    })
    
    return transactions


def parse_paytm_screenshot(text: str) -> list[dict]:
    """Parse Paytm Payment History or Receipt screenshot format specifically."""
    transactions = []
    
    # OCR artifact fixes (RapidOCR merges the day with "Oct": "190 ct" -> "19 Oct")
    text = re.sub(r'\b(\d{2})\s*0\s+ct\b', r'\1 Oct', text)
    
    # Check if this is a Paytm Receipt screenshot
    # Use fuzzy matching for receipt indicators
    is_receipt = any(re.search(p, text, re.IGNORECASE) for p in [
        r'Paid Successfully', r'To:', r'UPI Ref No', r'Payment Successful', r'Sent Successfully'
    ])
    
    if is_receipt:
        # Restrict the amount search to the header area above the "To:"/UPI-ID
        # details: RapidOCR reads stray digits from UPI IDs / ref numbers
        # (e.g. "bharatpe.9 u 0 j..." -> 9), which must not become the amount.
        header = text
        stop = re.search(r'(?:UPI\s*ID|From\s*:|Ref\s*No)', text, re.IGNORECASE)
        if stop:
            header = text[:stop.start()]
        
        # Extract amount - look for a standalone number on its own line
        # (e.g. "~40%", "Rs 40", "₹40"). A standalone-line match avoids dates
        # ("22 Oct 2026") and reference numbers, which mix letters/digits.
        amount = None
        for m in re.finditer(r'^\s*(?:[^\d\s]*\s*)?([\d][\d,]*(?:\.\d{2})?)\s*[^\d\s]*\s*$', header, re.MULTILINE):
            candidate = clean_amount(m.group(1))
            if candidate and float(candidate) not in (2024, 2025, 2026, 2027):
                amount = candidate
                break
        
        # Extract recipient name
        name_match = re.search(r'(?:To:?|Paid to)\s*([^\n]+)', text, re.IGNORECASE)
        # Extract date - try multiple formats
        date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', text)
        if not date_match:
            date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3})', text)
            
        if amount:
            name = name_match.group(1).strip() if name_match else "Paytm Receipt"
            date_str = date_match.group(1) if date_match else date.today().isoformat()
            
            normalized_date = normalize_date(date_str) or date.today().isoformat()
            category = categorize_transaction(name)
            
            transactions.append({
                'date': normalized_date,
                'amount': str(amount),
                'description': name,
                'kind': 'expense',
                'category': category,
            })
            # Don't return early - continue parsing for history lists in the same PDF

    # Paytm history list parsing...
    # Split text into lines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    NOISE_NAME = re.compile(
        r'^(Payment\s+History|Balance|Total\s+Spent|October\s+\d{4}|UPI\s+Ref|Canara\s+Bank|'
        r'YES\s+BANK|Paid\s+Successfully|Rupees\s+\w+|Paytm\s*\|)', re.IGNORECASE)
    CAT_KEYWORDS = re.compile(
        r'(Fuel|Groceries|Food|Transport|Shopping|Entertainment|Travel|Education|'
        r'Healthcare|Recharge|Bill|Money\s*Received|Miscellaneous)', re.IGNORECASE)
    
    def is_clean_name(name):
        """Return True if a candidate name looks like a real merchant/person name."""
        if not name or len(name) < 2:
            return False
        if re.match(r'^[^\w\s]+$', name):
            return False
        if NOISE_NAME.search(name):
            return False
        if '@' in name or re.search(r'\d{5,}', name):
            return False
        # Mostly-OCR-gibberish check
        if len(re.sub(r'[\s\w]', '', name)) > len(name) * 0.3:
            return False
        # Too few letters (e.g. "> Oo")
        if len(re.findall(r'[A-Za-z]', name)) < 3:
            return False
        return True
    
    def build_transaction(block, sign, amount_line, amount):
        """Build a transaction dict from a block + amount info, or None if invalid."""
        if not is_clean_name(block['name']):
            return None
        
        # Determine kind
        is_income = sign in ['+', 'x', 'X']
        if not is_income:
            cat_l = block['category'].lower()
            if 'received' in cat_l or 'received' in (block['name'] or '').lower():
                is_income = True
            elif 'received' in amount_line.lower():
                is_income = True
        
        kind = 'income' if is_income else 'expense'
        
        # Normalize date - skip transactions with unparseable dates
        # Normalize date - handle Today/Yesterday, skip unparseable dates
        raw_date = block['date']
        if re.match(r'Today', raw_date, re.IGNORECASE):
            normalized_date = date.today().isoformat()
        elif re.match(r'Yesterday', raw_date, re.IGNORECASE):
            normalized_date = (date.today() - timedelta(days=1)).isoformat()
        else:
            normalized_date = normalize_date(raw_date.replace(',', '')) if raw_date else None
        if not normalized_date:
            return None
        
        # Auto-categorize
        category = block['category']
        cat_clean = re.sub(r'[^a-zA-Z\s]', '', category).strip().lower() if category else ''
        if cat_clean == 'fuel':
            category = 'Transport'
        elif cat_clean == 'food':
            category = 'Dining'
        elif cat_clean == 'groceries':
            category = 'Groceries'
        elif cat_clean in ('money received',):
            category = 'Other expense'
        elif cat_clean:
            category = categorize_transaction(block['name'])
        else:
            category = categorize_transaction(block['name'])
        
        valid_categories = ['Housing', 'Groceries', 'Transport', 'Utilities', 'Dining',
                            'Healthcare', 'Shopping', 'Entertainment', 'Travel', 'Education', 'Other expense']
        if category not in valid_categories:
            category = 'Other expense'
        
        return {
            'date': normalized_date,
            'amount': amount,
            'description': block['name'],
            'kind': kind,
            'category': category,
        }
    
    # Segment the text by page headers ("Payment History") so blocks and amounts
    # are paired within the same page. Tesseract reads the names column first and
    # then the amounts column, so within a segment we pair them in order.
    segments = [[]]
    for line in lines:
        if re.search(r'Payment\s*History', line, re.IGNORECASE) and len(segments[-1]) > 0:
            segments.append([])
        segments[-1].append(line)
    
    def parse_amount_line(line):
        """Return (sign, amount, match) if the line contains an amount, else None."""
        if re.match(r'^(From|In|To|UPI|Ref|Canara|Bank|Failed|Money|Payment|History|October|Total|Spent|Balance|Paytm|Powered|YES)\b', line, re.IGNORECASE):
            return None
        if len(line) < 3:
            return None
        if re.match(r'^[^\w\s]+$', line):
            return None
        # Skip date/time-only lines (e.g. "06:12 PM, 22 Oct 2026")
        if re.search(r'\d{1,2}:\d{2}', line) and not re.search(r'([+\-=]+)\s*[₹=%$xXnIlOo]?\s*[\d,]+', line):
            return None
        # Skip month-total lines (e.g. "October 2026 Total Spent", "crober 22,405")
        if re.search(r'\b(Oct|Octo|October|ober|crober|ctoper|cto?ber)\b\s*\d|Total\s*Spent', line, re.IGNORECASE):
            return None
        # Skip UPI ID / account lines
        if '@' in line or re.search(r'\d{5,}[a-zA-Z]|[a-zA-Z]\d{5,}', line):
            return None
        def _valid(amt):
            return amt and 1 <= float(amt) <= 999999999 and float(amt) not in (2024, 2025, 2026, 2027)

        # Paytm amounts carry a sign: - ₹10, + ₹50, - $150, += ₹2500, - %50...
        # The symbol may be an OCR replacement char or a stray 'R' (misread ₹).
        m = re.search(r'([+\-=]+)\s*(?:[^\w\s]|R)?\s*([\d,]+\.?\d*)', line)
        if m and _valid(clean_amount(m.group(2))):
            return ('+' if '+' in m.group(1) else '-'), clean_amount(m.group(2)), m.start()
        # RapidOCR sometimes drops the sign entirely: "Vinita Food And Beverages 20"
        # -> expense of 20. Bare amount must trail the line after a digit-free name.
        m = re.search(r"([A-Za-z][A-Za-z\s.,'&/-]*?)\s+(\d[\d,]*\.?\d*)\s*$", line)
        if m and _valid(clean_amount(m.group(2))):
            return '-', clean_amount(m.group(2)), m.start(2)
        return None
    
    def clean_name(s):
        """Strip trailing OCR junk symbols; return None if not a plausible name."""
        s = re.sub(r'[^\w\s]+$', '', s).strip()
        if not s or len(s) < 2 or re.search(r'\d', s):
            return None
        if re.search(r'[^\w\s.,\'&/-]', s):
            return None
        if re.fullmatch(r'[^\w]*\s*(?:Fuel|Groceries|Food|Transport|Shopping|Entertainment|Travel|Education|Healthcare|Recharge|Bill|Money\s*Received|Miscellaneous)\s*[^\w]*', s, re.IGNORECASE):
            return None
        if NOISE_NAME.search(s):
            return None
        if '@' in s:
            return None
        # Split CamelCase words joined by OCR (e.g. "VanshNew" -> "Vansh New")
        s = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', s)
        return s
    
    def find_name(seg, date_idx):
        """Find the merchant name for a date line, handling inline amounts."""
        inline_amount = None
        inline_name = None
        first_clean = None
        # Look back closest-first: the line immediately above the date belongs
        # to it; stop at the previous block's boundary (its date or category
        # line) so we never steal that row's amount.
        for j in range(date_idx - 1, max(0, date_idx - 4) - 1, -1):
            prev = seg[j]
            if (re.search(r'\d{1,2}\s+[A-Za-z]{3}', prev)
                    or re.match(r'(Today|Yesterday),\s*\d{1,2}:\d{2}', prev, re.IGNORECASE)
                    or CAT_KEYWORDS.fullmatch(prev.strip())):
                break
            parsed = parse_amount_line(prev)
            candidate = prev
            if parsed:
                sign, amt, amt_pos = parsed
                before = clean_name(prev[:amt_pos])
                if before:
                    # Inline amount on this line: definitive name line
                    return before, (sign, amt)
                if inline_amount is None:
                    inline_amount = (sign, amt)
                    inline_name = before
                continue
            candidate = clean_name(prev)
            if candidate and first_clean is None:
                first_clean = candidate
        if inline_amount and inline_name:
            return inline_name, inline_amount
        return first_clean or '', None
    
    for segment in segments:
        blocks = []
        for i, line in enumerate(segment):
            is_date_line = (
                re.search(r'\d{1,2}\s+[A-Za-z]{3}', line)
                or re.match(r'(Today|Yesterday),\s*\d{1,2}:\d{2}', line, re.IGNORECASE)
            )
            if not is_date_line:
                continue
            if re.search(r'\bFailed\b', line, re.IGNORECASE):
                continue  # failed payments are not real transactions
            name, inline_amount = find_name(segment, i)
            
            category = ''
            for j in range(i + 1, min(len(segment), i + 3)):
                if CAT_KEYWORDS.search(segment[j]):
                    category = segment[j]
                    break
            
            blocks.append({
                'name': name, 'date': line, 'category': category,
                'line_index': i, 'inline_amount': inline_amount,
            })
        
        # Only clean, named blocks participate in pairing
        pending_blocks = []
        has_inline = False
        for block in blocks:
            if block['inline_amount']:
                has_inline = True
                sign, amt = block['inline_amount']
                txn = build_transaction(block, sign, block['date'], amt)
                if txn:
                    transactions.append(txn)
            elif is_clean_name(block['name']):
                pending_blocks.append(block)
        
        # Column layout (names first, amounts in a group after) only applies to
        # segments where no row carried its own inline amount. In mixed segments,
        # leftover amounts cannot be reliably attributed, so skip them.
        if has_inline:
            continue
        
        amounts = []
        for line in segment:
            parsed = parse_amount_line(line)
            if parsed:
                amounts.append((parsed[0], parsed[1]))
        
        for (sign, amt), block in zip(amounts, pending_blocks):
            txn = build_transaction(block, sign, '', amt)
            if txn:
                transactions.append(txn)
    
    # Dedupe (merged PDFs often repeat the same row across pages)
    seen = set()
    deduped = []
    for txn in transactions:
        key = (txn['date'], txn['amount'], txn['description'], txn['kind'])
        if key not in seen:
            seen.add(key)
            deduped.append(txn)
    
    return deduped


def parse_raw_text(text: str) -> list[dict]:
    """Parse any raw text (OCR output, copied text, etc.) for transactions."""
    transactions = []
    
    # Clean and simplify OCR text (Tesseract can sometimes add artifacts)
    text = re.sub(r'[^\x00-\x7F]+', ' ', text) # Remove non-ascii
    
    # First try Paytm-specific parser
    paytm_transactions = parse_paytm_screenshot(text)
    if paytm_transactions:
        return paytm_transactions
    
    # Split into lines and process each
    lines = text.split('\n')
    
    current_date = None
    current_amount = None
    current_desc = None
    
    # Patterns to identify transaction lines
    amount_pattern = r'(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d{2})'
    date_pattern = r'(\d{1,2}[/-]\d{1,2}[/-]?\d{2,4})'
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check for amount
        amount_match = re.search(amount_pattern, line)
        if amount_match:
            amount = clean_amount(amount_match.group(1))
            if amount:
                current_amount = amount
        
        # Check for date
        date_match = re.search(date_pattern, line)
        if date_match:
            normalized = normalize_date(date_match.group(1))
            if normalized:
                current_date = normalized
        
        # Check for transaction type indicators
        line_lower = line.lower()
        if any(word in line_lower for word in ['debited', 'paid', 'spent', 'to', 'towards']):
            kind = 'expense'
        elif any(word in line_lower for word in ['credited', 'received', 'from', 'salary', 'refund']):
            kind = 'income'
        else:
            kind = None
        
        # Extract description (anything that's not amount/date/type indicator)
        desc = re.sub(amount_pattern, '', line)
        desc = re.sub(date_pattern, '', desc)
        desc = re.sub(r'(debited|credited|paid|received|Rs\.?|INR|₹)', '', desc, flags=re.IGNORECASE)
        desc = desc.strip()
        if desc:
            current_desc = desc
        
        # If we have all components, create transaction
        if current_date and current_amount:
            transactions.append({
                'date': current_date,
                'amount': current_amount,
                'description': current_desc or 'Unknown',
                'kind': kind or 'expense',
            })
            # Reset for next transaction
            current_date = None
            current_amount = None
            current_desc = None
    
    return transactions


def normalize_date(date_str: str) -> Optional[str]:
    """Normalize various date formats to YYYY-MM-DD."""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Common Indian date formats
    formats = [
        '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y',
        '%m/%d/%Y', '%m-%d-%Y', '%m/%d/%y', '%m-%d-%y',
        '%Y/%m/%d', '%Y-%m-%d', '%y/%m/%d', '%y-%m-%d',
        '%d %b %Y', '%d %B %Y', '%b %d %Y', '%B %d %Y',
        '%d %b', # e.g., 15 Oct
    ]
    
    for fmt in formats:
        try:
            # If format doesn't have year, assume current year
            if '%Y' not in fmt and '%y' not in fmt:
                parsed = datetime.strptime(date_str + ' ' + str(datetime.now().year), fmt + ' %Y')
            else:
                parsed = datetime.strptime(date_str, fmt)
            return parsed.strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    # Try to extract date components with regex
    match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-]?(\d{2,4})', date_str)
    if match:
        day, month, year = match.groups()
        day = int(day)
        month = int(month)
        year = int(year)
        
        # Handle 2-digit years
        if year < 100:
            year += 2000 if year < 50 else 1900
        
        # Validate
        if 1 <= day <= 31 and 1 <= month <= 12:
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                pass
    
    # Try to parse "15 Oct" format with regex
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    # Match "15 Oct" or "15 Oct, 05:56 PM"
    match = re.search(r'(\d{1,2})\s+([A-Za-z]{3,9})', date_str, re.IGNORECASE)
    if match:
        day = int(match.group(1))
        month_str = match.group(2).lower()
        
        if month_str in month_map:
            month = month_map[month_str]
            year = datetime.now().year
            
            # Try to extract year if present
            year_match = re.search(r'(\d{4})', date_str)
            if year_match:
                year = int(year_match.group(1))
            
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                pass
    
    return None


def clean_amount(amount_str: str) -> Optional[str]:
    """Clean and normalize amount string to decimal format."""
    if not amount_str:
        return None
    
    # Remove currency symbols and common prefixes
    amount_str = re.sub(r'[₹Rs\.INR\$,]', '', amount_str, flags=re.IGNORECASE)
    amount_str = amount_str.strip()
    
    # Remove thousands separators (commas)
    amount_str = amount_str.replace(',', '')
    
    # Try to parse as float
    try:
        amount = float(amount_str)
        if amount > 0:
            return f"{amount:.2f}"
    except ValueError:
        pass
    
    return None


def infer_transaction_type(type_str: str, desc_str: str) -> str:
    """Infer if transaction is income or expense based on text."""
    text = (type_str + ' ' + desc_str).lower()
    
    # Income indicators
    income_words = ['credited', 'received', 'salary', 'dividend', 'interest', 'refund', 'cashback', 'reward', 'gift', 'bonus']
    if any(word in text for word in income_words):
        return 'income'
    
    # Expense indicators
    expense_words = ['debited', 'paid', 'spent', 'purchase', 'bought', 'to', 'towards', 'payment']
    if any(word in text for word in expense_words):
        return 'expense'
    
    # Default to expense (most common)
    return 'expense'


def categorize_transaction(description: str) -> str:
    """Auto-categorize transaction based on merchant/description."""
    desc_lower = description.lower()
    
    # Check against known merchants
    for keyword, category in MERCHANT_CATEGORIES.items():
        if keyword in desc_lower:
            return category
    
    # Fallback categories based on patterns
    if any(word in desc_lower for word in ['atm', 'withdrawal', 'cash']):
        return 'Other expense'
    
    if any(word in desc_lower for word in ['transfer', 'upi', 'imps', 'neft', 'rtgs']):
        return 'Other expense'
    
    if any(word in desc_lower for word in ['fee', 'charge', 'penalty']):
        return 'Other expense'
    
    return 'Other expense'


def process_import(
    file_data: Optional[bytes] = None,
    file_type: Optional[str] = None,
    text_data: Optional[str] = None,
    user_currency: str = 'INR'
) -> dict[str, Any]:
    """
    Main entry point for processing imports.
    
    Args:
        file_data: Raw file bytes (for image/PDF/CSV)
        file_type: 'image', 'pdf', 'csv', 'excel'
        text_data: Raw text (for SMS/email paste)
        user_currency: User's display currency
    
    Returns:
        Dictionary with extracted transactions and metadata
    """
    result = {
        'transactions': [],
        'errors': [],
        'warnings': [],
        'metadata': {}
    }
    
    try:
        # Determine source and extract text/transactions
        if file_data and file_type:
            if file_type == 'image':
                if not TESSERACT_AVAILABLE and not RAPIDOCR_AVAILABLE:
                    result['errors'].append("OCR is not available. Please install Tesseract or use PDF/CSV import.")
                    return result
                
                try:
                    text = parse_image_to_text(file_data)
                    result['metadata']['source'] = 'image_ocr'
                    result['metadata']['ocr_confidence'] = 'medium'  # Could be enhanced with actual confidence
                except Exception as e:
                    result['errors'].append(f"OCR failed: {str(e)}")
                    return result
            
            elif file_type == 'pdf':
                try:
                    text = parse_pdf_to_text(file_data)
                    result['metadata']['source'] = 'pdf'
                except Exception as e:
                    result['errors'].append(f"PDF parsing failed: {str(e)}")
                    return result
            
            elif file_type in ['csv', 'excel']:
                try:
                    transactions = parse_csv_excel(file_data, file_type)
                    result['transactions'] = transactions
                    result['metadata']['source'] = file_type
                    result['metadata']['count'] = len(transactions)
                    
                    # Post-process: categorize and validate
                    for txn in result['transactions']:
                        if 'category' not in txn:
                            txn['category'] = categorize_transaction(txn.get('description', ''))
                        txn['currency'] = user_currency
                    
                    return result
                
                except Exception as e:
                    result['errors'].append(f"CSV/Excel parsing failed: {str(e)}")
                    return result
            
            else:
                result['errors'].append(f"Unsupported file type: {file_type}")
                return result
            
            # Parse extracted text (for image/PDF)
            text_transactions = parse_raw_text(text)
            if not text_transactions:
                # Try SMS/email patterns as fallback
                text_transactions = parse_sms_email_text(text)
            
            result['transactions'] = text_transactions
        
        elif text_data:
            # Direct text input (SMS/email paste)
            text_transactions = parse_sms_email_text(text_data)
            if not text_transactions:
                text_transactions = parse_raw_text(text_data)
            
            result['transactions'] = text_transactions
            result['metadata']['source'] = 'text'
        
        else:
            result['errors'].append("No file or text data provided")
            return result
        
        # Post-process all transactions
        processed = []
        for txn in result['transactions']:
            # Validate required fields
            if not txn.get('date') or not txn.get('amount'):
                result['warnings'].append(f"Skipped incomplete transaction: {txn.get('description', 'Unknown')}")
                continue
            
            # Auto-categorize
            if 'category' not in txn:
                txn['category'] = categorize_transaction(txn.get('description', ''))
            
            # Set currency
            txn['currency'] = user_currency
            
            # Ensure kind is set
            if 'kind' not in txn:
                txn['kind'] = 'expense'
            
            processed.append(txn)
        
        result['transactions'] = processed
        result['metadata']['count'] = len(processed)
        result['metadata']['currency'] = user_currency
        
    except Exception as e:
        result['errors'].append(f"Import failed: {str(e)}")
    
    return result