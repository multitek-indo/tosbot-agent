"""Synthetic test-only pictures. Never publish the company logo or real signature."""
from pathlib import Path
from PIL import Image, ImageDraw

def create_test_assets(root):
    root = Path(root)
    logo = root / 'fake-logo.png'
    signature = root / 'fake-signature.png'
    im = Image.new('RGB', (100, 50), 'white')
    ImageDraw.Draw(im).rectangle((10, 10, 90, 40), outline='black', width=3)
    im.save(logo)
    sig = Image.new('RGB', (160, 35), 'white')
    ImageDraw.Draw(sig).line([(5, 20), (30, 7), (60, 26), (90, 8), (150, 22)], fill='black', width=2)
    sig.save(signature)
    return logo, signature
