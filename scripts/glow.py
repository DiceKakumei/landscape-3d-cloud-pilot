"""ブルーム風のグロー後処理: python glow.py in.png out.png"""
import sys
import numpy as np
from PIL import Image, ImageFilter

src, dst = sys.argv[1], sys.argv[2]
img = Image.open(src).convert("RGB")
a = np.asarray(img).astype(np.float32) / 255
mask = np.clip((a.max(2) - 0.55) / 0.45, 0, 1)[..., None]
bright = Image.fromarray((a * mask * 255).astype(np.uint8))
w = max(img.size) / 720
glow = sum(np.asarray(bright.filter(ImageFilter.GaussianBlur(r * w))).astype(np.float32) / 255 * k
           for r, k in ((4, 0.5), (14, 0.5), (40, 0.6)))
out = 1 - (1 - a) * (1 - np.clip(glow, 0, 1))
Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(dst)
