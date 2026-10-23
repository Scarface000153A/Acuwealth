"""Test PDF parser with actual merged.pdf"""
import pdfplumber
import pytesseract
import os
import platform
from PIL import Image

if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

pdf_path = r'C:\Users\User\Downloads\merged.pdf'
if os.path.exists(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        all_text = ''
        for i, page in enumerate(pdf.pages):
            img = page.to_image(resolution=200).original
            text = pytesseract.image_to_string(img)
            all_text += text + '\n'
        
        print("=== OCR Output ===")
        print(all_text[:3000])
        print("\n\n=== Parser Test ===")
        from import_service import parse_paytm_screenshot
        transactions = parse_paytm_screenshot(all_text)
        print(f'Found {len(transactions)} transactions:')
        for txn in transactions:
            print(f"  {txn['date']} | {txn['kind']} | {txn['description']} | {txn['amount']} | {txn['category']}")
else:
    print('PDF not found')