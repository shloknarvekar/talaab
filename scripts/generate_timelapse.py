import glob
import os
import sys
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

INPUT_PATTERN = "web/public/imagery/latur-2024/P003/*.jpg"
OUTPUT_GIF = "web/public/imagery/latur-2024/P003-timelapse.gif"
WIDTH = 512
HEIGHT = 512
TAGLINE = "Watch the sun drink the pond"
DURATION_MS = 270

files = sorted(glob.glob(INPUT_PATTERN))
if not files:
    print(f"Error: No input JPEG files found matching pattern '{INPUT_PATTERN}'", file=sys.stderr)
    sys.exit(1)

print(f"Generating time-lapse from {len(files)} files...")

try:
    font_date = ImageFont.truetype("arial.ttf", 26)
    font_sub = ImageFont.truetype("arial.ttf", 16)
    font_tagline = ImageFont.truetype("arialbd.ttf", 20)
    font_credit = ImageFont.truetype("arial.ttf", 13)
except Exception:
    font_date = ImageFont.load_default()
    font_sub = ImageFont.load_default()
    font_tagline = ImageFont.load_default()
    font_credit = ImageFont.load_default()

frames = []
dates_processed = []

for f in files:
    dt_str = os.path.splitext(os.path.basename(f))[0]
    dt_obj = datetime.strptime(dt_str, "%Y-%m-%d")
    dates_processed.append(dt_obj)
    formatted_date = dt_obj.strftime("%d %b %Y")  # e.g. 16 Jan 2024

    im = Image.open(f).convert("RGB")
    im = im.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

    date_text = formatted_date
    sub_text = "Sentinel-2 L2A · Latur P003"

    badge_x0, badge_y0 = 16, 16
    badge_x1, badge_y1 = 260, 72

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)

    ov_draw.rounded_rectangle([badge_x0, badge_y0, badge_x1, badge_y1], radius=8, fill=(15, 23, 42, 220))
    banner_h = 48
    ov_draw.rectangle([0, HEIGHT - banner_h, WIDTH, HEIGHT], fill=(15, 23, 42, 230))

    im = Image.alpha_composite(im.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(im)

    draw.text((badge_x0 + 12, badge_y0 + 6), date_text, fill=(255, 255, 255), font=font_date)
    draw.text((badge_x0 + 12, badge_y0 + 36), sub_text, fill=(148, 163, 184), font=font_sub)

    tag_bbox = draw.textbbox((0, 0), TAGLINE, font=font_tagline)
    tag_w = tag_bbox[2] - tag_bbox[0]
    draw.text(((WIDTH - tag_w) // 2, HEIGHT - banner_h + 12), TAGLINE, fill=(254, 215, 170), font=font_tagline)

    frames.append(im.convert("RGB"))

os.makedirs(os.path.dirname(OUTPUT_GIF), exist_ok=True)
frames[0].save(
    OUTPUT_GIF,
    save_all=True,
    append_images=frames[1:],
    duration=DURATION_MS,
    loop=0,
    optimize=False
)

file_size_kb = os.path.getsize(OUTPUT_GIF) / 1024
total_dur_ms = len(frames) * DURATION_MS
print(f"Saved {OUTPUT_GIF}:")
print(f"  Frames: {len(frames)}")
print(f"  Dimensions: {WIDTH}x{HEIGHT}")
print(f"  Duration: {total_dur_ms} ms ({total_dur_ms/1000:.2f} s)")
print(f"  Date range: {dates_processed[0].strftime('%Y-%m-%d')} to {dates_processed[-1].strftime('%Y-%m-%d')}")
print(f"  File size: {file_size_kb:.1f} KB")
