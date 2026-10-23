"""Simulate Render (no Tesseract) - force RapidOCR path through the real parser."""
import import_service

# Simulate Render: no Tesseract binary
import_service.TESSERACT_AVAILABLE = False

with open(r'C:\Users\User\Downloads\merged.pdf', 'rb') as f:
    pdf_data = f.read()

result = import_service.process_import(
    file_data=pdf_data, file_type='pdf', user_currency='INR'
)
print('Errors:', result['errors'])
print('Transactions:', len(result['transactions']))
for txn in result['transactions']:
    print(f"  {txn['date']} | {txn['kind']} | {txn['description']} | {txn['amount']} | {txn.get('category')}")
