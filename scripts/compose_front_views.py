"""Assemble the ten simulator renders into a labeled 2-row, 5-column sheet."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import zipfile

out = Path(__file__).resolve().parents[1] / 'reports/front_views'
w, h, label, gap = 1280, 800, 64, 16
canvas = Image.new('RGB', (5*w+6*gap, 2*(h+label)+3*gap), '#eef1f5')
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 36)
draw = ImageDraw.Draw(canvas)
for i in range(10):
    path = out / f'T{i+1:02d}_front.png'
    with Image.open(path) as im:
        assert im.size == (w, h)
        x = gap + (i%5)*(w+gap)
        y = gap + (i//5)*(h+label+gap)
        draw.text((x+20, y+10), f'T{i+1}', font=font, fill='#17233b')
        canvas.paste(im, (x, y+label))
canvas.save(out / 'T1-T10_front_2x5.png')
preview = canvas.copy()
preview.thumbnail((2400, 2400))
preview.save(out / 'T1-T10_front_2x5_preview.jpg', quality=92)
with zipfile.ZipFile(out.parent / 'T1-T10_front_images.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for p in sorted(out.glob('T??_front.png')):
        z.write(p, p.name)
    z.write(out / 'T1-T10_front_2x5.png', 'T1-T10_front_2x5.png')
print(canvas.size)
