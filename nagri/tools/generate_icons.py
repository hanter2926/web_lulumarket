from PIL import Image
import os

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(BASE, 'image-3.png')
OUT_DIR = os.path.join(BASE, 'nagri', 'static', 'images', 'icons')

os.makedirs(OUT_DIR, exist_ok=True)

if not os.path.exists(SRC):
    raise SystemExit(f"Source image not found: {SRC}")

with Image.open(SRC) as im:
    im = im.convert('RGBA')
    for size in (192, 512):
        # Compute scale preserving aspect ratio, fit inside size
        w, h = im.size
        scale = min(size / w, size / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        resized = im.resize((new_w, new_h), Image.LANCZOS)

        # Create square canvas with transparent background
        canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        paste_x = (size - new_w) // 2
        paste_y = (size - new_h) // 2
        canvas.paste(resized, (paste_x, paste_y), resized)

        out_path = os.path.join(OUT_DIR, f'icon-{size}x{size}.png')
        canvas.save(out_path, format='PNG', optimize=True)
        print('WROTE', out_path)
