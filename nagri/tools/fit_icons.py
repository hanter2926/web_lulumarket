from PIL import Image, ImageStat, ImageOps
import os


def estimate_background_color(im):
    # Sample corners to estimate background color
    w, h = im.size
    corners = [im.crop((0, 0, w//10, h//10)), im.crop((w - w//10, 0, w, h//10)),
               im.crop((0, h - h//10, w//10, h)), im.crop((w - w//10, h - h//10, w, h))]
    rs = gs = bs = 0.0
    count = 0
    for c in corners:
        stat = ImageStat.Stat(c)
        r, g, b = stat.mean[:3]
        rs += r; gs += g; bs += b
        count += 1
    return (rs/count, gs/count, bs/count)


def compute_foreground_bbox(im):
    # Convert to RGBA and compute mask of pixels that differ significantly from background
    rgba = im.convert('RGBA')
    arr = rgba.load()
    w, h = rgba.size
    bg_r, bg_g, bg_b = estimate_background_color(im)
    bbox = [w, h, 0, 0]
    found = False
    for y in range(h):
        for x in range(w):
            r, g, b, a = arr[x, y]
            # if alpha low treat as background
            if a < 16:
                continue
            # compute color distance from background
            dist = abs(r - bg_r) + abs(g - bg_g) + abs(b - bg_b)
            if dist > 30:  # threshold
                found = True
                if x < bbox[0]: bbox[0] = x
                if y < bbox[1]: bbox[1] = y
                if x > bbox[2]: bbox[2] = x
                if y > bbox[3]: bbox[3] = y
    if not found:
        return None
    # expand bbox slightly
    pad_x = max(2, int((bbox[2] - bbox[0]) * 0.04))
    pad_y = max(2, int((bbox[3] - bbox[1]) * 0.04))
    x0 = max(0, bbox[0] - pad_x)
    y0 = max(0, bbox[1] - pad_y)
    x1 = min(w, bbox[2] + pad_x)
    y1 = min(h, bbox[3] + pad_y)
    return (x0, y0, x1, y1)


def process_icon(src_path, target_size):
    print('Processing', src_path, '->', target_size)
    im = Image.open(src_path).convert('RGBA')
    w, h = im.size
    bbox = compute_foreground_bbox(im)
    if bbox:
        fg = im.crop(bbox)
    else:
        # fallback: trim whitespace using alpha, or use the center
        fg = ImageOps.fit(im, (int(w*0.8), int(h*0.8)), Image.LANCZOS)

    # compute scale to occupy ~85% of target canvas
    max_dim = max(fg.size)
    desired = int(target_size * 0.85)
    scale = desired / max_dim
    new_w = max(1, int(fg.width * scale))
    new_h = max(1, int(fg.height * scale))
    fg_resized = fg.resize((new_w, new_h), Image.LANCZOS)

    # create transparent canvas and paste centered
    canvas = Image.new('RGBA', (target_size, target_size), (0, 0, 0, 0))
    offset = ((target_size - new_w) // 2, (target_size - new_h) // 2)
    canvas.paste(fg_resized, offset, fg_resized)

    # Backup original
    bak = src_path + '.bak'
    if not os.path.exists(bak):
        try:
            Image.open(src_path).save(bak)
        except Exception:
            pass

    # Save PNG
    canvas.save(src_path, format='PNG')
    print('Saved', src_path)


if __name__ == '__main__':
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nagri', 'static', 'images', 'icons')
    # paths in repo: nagri/static/images/icons
    paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nagri', 'static', 'images', 'icons', 'icon-192x192.png'),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nagri', 'static', 'images', 'icons', 'icon-512x512.png'),
    ]
    # If path exists, process with corresponding sizes
    for p in paths:
        if os.path.exists(p):
            if '192' in p:
                process_icon(p, 192)
            elif '512' in p:
                process_icon(p, 512)
            else:
                # default to 512
                process_icon(p, 512)
        else:
            print('Not found:', p)
