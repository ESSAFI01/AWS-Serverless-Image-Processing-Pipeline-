from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

output = Path("output")
output.mkdir(exist_ok=True)

image = Image.new("RGB", (2400, 1600), "#234766")
drawing = ImageDraw.Draw(image)
drawing.ellipse((1400, 200, 2100, 900), fill="#f3ad45")
drawing.polygon(
    [(200, 1400), (1000, 400), (1800, 1400)],
    fill="#56b7b2",
)
image.save(output / "original.jpg")

image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
drawing = ImageDraw.Draw(image)
drawing.text(
    (image.width - 20, image.height - 20),
    "Cloud & AI",
    font=ImageFont.load_default(size=30),
    fill="white",
    stroke_width=2,
    stroke_fill="black",
    anchor="rs",
)
image.save(output / "processed.jpg", quality=85, optimize=True)