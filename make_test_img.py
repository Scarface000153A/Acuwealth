"""Create a small Paytm-receipt-like PNG for live-upload testing."""
from PIL import Image, ImageDraw, ImageFont

W, H = 540, 960
img = Image.new('RGB', (W, H), '#0f1115')
d = ImageDraw.Draw(img)

def font(sz):
    try:
        return ImageFont.truetype('arial.ttf', sz)
    except Exception:
        return ImageFont.load_default()

d.text((30, 40), 'Paid Successfully', fill='#4caf50', font=font(34))
d.text((30, 120), 'Rs 40', fill='#ffffff', font=font(56))
d.text((30, 220), 'To: Satya Narayan', fill='#e0e0e0', font=font(28))
d.text((30, 300), 'UPI ID: bharatpe@ptyes', fill='#9e9e9e', font=font(22))
d.text((30, 360), 'From: Robin Robert', fill='#e0e0e0', font=font(26))
d.text((30, 430), '22 Oct 2026', fill='#9e9e9e', font=font(24))

img.save(r'C:\Users\User\Desktop\Acuwealth\test_receipt.png')
print('saved')
