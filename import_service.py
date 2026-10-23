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
from datetime import datetime, date
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
    """Extract text from image using OCR."""
    if not TESSERACT_AVAILABLE:
        raise RuntimeError("Tesseract OCR is not installed. Please install it or use PDF/CSV import.")
    
    image = Image.open(io.BytesIO(image_data))
    
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
    # Use both eng and hin for better results with Indian text
    try:
        text = pytesseract.image_to_string(image, lang='eng')
    except:
        text = pytesseract.image_to_string(image)
    
    return text


def parse_pdf_to_text(pdf_data: bytes) -> str:
    """Extract text from PDF (bank statements, UPI exports)."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
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
    
    # Check if this is a Paytm Receipt screenshot
    # Use fuzzy matching for receipt indicators
    is_receipt = any(re.search(p, text, re.IGNORECASE) for p in [
        r'Paid Successfully', r'To:', r'UPI Ref No', r'Payment Successful', r'Sent Successfully'
    ])
    
    if is_receipt:
        # Extract amount - look for a large number following a currency symbol or near "Paid"
        # Matches: ₹40, Rs 40, 40, etc.
        amount_match = re.search(r'(?:₹|Rs\.?|[^\d\s\w])\s*(\d{1,10}(?:\.\d{2})?)', text)
        if not amount_match:
            # Try finding any large number if currency symbol is misread
            amounts = re.findall(r'\b\d{1,10}(?:\.\d{2})?\b', text)
            if amounts:
                # The largest number is usually the amount in a receipt
                amount = max(amounts, key=lambda x: float(x.replace(',', '')))
            else:
                amount = None
        else:
            amount = clean_amount(amount_match.group(1))
            
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
            return transactions

    # Paytm history list parsing...
    # Split text into lines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # First, collect all transaction blocks (Name + Date + Category)
    # Pattern: Name, Date, Category (with possible OCR noise)
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Look for date pattern (e.g., "15 Oct", "15 Oct, 05:56 PM")
        date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3})', line)
        if date_match:
            # Found a date - look backward for name, forward for category
            name = ''
            date_str = line
            category = ''
            
            # Look backward for name (up to 3 lines)
            for j in range(max(0, i-3), i):
                prev = lines[j]
                # Skip if it looks like a date, amount, or category
                if re.search(r'[\d₹+\-=xX]', prev):
                    continue
                if re.search(r'(Fuel|Groceries|Food|Transport|Shopping|Entertainment|Travel|Education|Healthcare|Recharge|Bill|Money Received|Miscellaneous|Groceries)', prev, re.IGNORECASE):
                    continue
                if len(prev) > 1:
                    name = prev
                    break
            
            # Look forward for category (up to 2 lines)
            for j in range(i+1, min(len(lines), i+3)):
                next_l = lines[j]
                cat_match = re.search(r'(Fuel|Groceries|Food|Transport|Shopping|Entertainment|Travel|Education|Healthcare|Recharge|Bill|Money Received|Miscellaneous|Groceries)', next_l, re.IGNORECASE)
                if cat_match:
                    category = next_l
                    break
            
            blocks.append({
                'name': name,
                'date': date_str,
                'category': category,
                'line_index': i
            })
        
        i += 1
    
    # Now find all amounts
    amounts = []
    for i, line in enumerate(lines):
        # Skip header/footer lines
        if re.match(r'^(From|In|To|UPI|Ref|Canara|Bank|Failed|Money|Payment|History|October|Total|Spent|Balance)', line, re.IGNORECASE):
            continue
        
        # Look for amount pattern
        amount_match = re.search(r'([+\-=xX])\s*(?:[₹=%xXnIlOo]?\s*)?([\d,]+\.?\d*)', line)
        if not amount_match:
            # Try just a number (might be amount without clear sign)
            amount_match = re.search(r'([\d,]+\.?\d{2})', line)
            if amount_match:
                sign = '-'
                amount = clean_amount(amount_match.group(1))
            else:
                continue
        else:
            sign = amount_match.group(1)
            amount = clean_amount(amount_match.group(2))
        
        # Skip if amount is too small or too large
        if not amount or float(amount) < 1 or float(amount) > 999999999:
            continue
        
        amounts.append({
            'line_index': i,
            'sign': sign,
            'amount': amount,
            'line': line
        })
    
    # Match amounts to blocks (nearest preceding block that hasn't been matched)
    matched_blocks = set()
    for amount_info in amounts:
        # Find the nearest preceding block that hasn't been matched yet
        best_block = None
        for block in blocks:
            if block['line_index'] < amount_info['line_index'] and id(block) not in matched_blocks:
                if best_block is None or block['line_index'] > best_block['line_index']:
                    best_block = block
        
        if best_block:
            matched_blocks.add(id(best_block))
            
            # Determine kind
            is_income = False
            if amount_info['sign'] in ['+', 'x', 'X']:
                is_income = True
            elif 'money received' in best_block['category'].lower() or 'received' in best_block['category'].lower():
                is_income = True
            elif 'money received' in amount_info['line'].lower() or 'money received' in (best_block['name'] or '').lower():
                is_income = True
            elif re.search(r'\bIn\b', amount_info['line'], re.IGNORECASE):
                is_income = True
            
            kind = 'income' if is_income else 'expense'
            
            # Normalize date
            normalized_date = normalize_date(best_block['date'].replace(',', '')) if best_block['date'] else date.today().isoformat()
            
            # Auto-categorize
            category = best_block['category']
            if not category:
                category = categorize_transaction(best_block['name'])
            else:
                cat_clean = re.sub(r'[^a-zA-Z\s]', '', category).strip()
                if cat_clean.lower() in ['fuel', 'food', 'groceries', 'miscellaneous', 'recharge', 'bill']:
                    if cat_clean.lower() == 'fuel': category = 'Transport'
                    elif cat_clean.lower() == 'food': category = 'Dining'
                    elif cat_clean.lower() == 'groceries': category = 'Groceries'
                    elif cat_clean.lower() == 'miscellaneous': category = 'Other expense'
                    else: category = 'Other expense'
                else:
                    category = categorize_transaction(best_block['name'])
            
            # Final category validation
            valid_categories = ['Housing', 'Groceries', 'Transport', 'Utilities', 'Dining', 
                              'Healthcare', 'Shopping', 'Entertainment', 'Travel', 'Education', 'Other expense']
            if category not in valid_categories:
                category = 'Other expense'
            
            transactions.append({
                'date': normalized_date,
                'amount': amount_info['amount'],
                'description': best_block['name'] or 'Paytm Transaction',
                'kind': kind,
                'category': category,
            })
    
    return transactions


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
                if not TESSERACT_AVAILABLE:
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