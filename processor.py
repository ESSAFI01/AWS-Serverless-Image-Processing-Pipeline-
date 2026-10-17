"""Image operations shared by the legacy handler and orchestrated workflow."""
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageOps


MAX_PIXELS = 20_000_000


def _open_rgb(image_bytes):
    with Image.open(BytesIO(image_bytes)) as source:
        if source.width * source.height > MAX_PIXELS:
            raise ValueError("Decoded image exceeds 20 million pixels")
        image = ImageOps.exif_transpose(source).convert("RGBA")
    background = Image.new("RGBA", image.size, "white")
    return Image.alpha_composite(background, image).convert("RGB")


def resize_image(image_bytes: bytes, max_size=(1024, 1024)) -> bytes:
    image = _open_rgb(image_bytes)
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    result = BytesIO()
    image.save(result, format="PNG")
    return result.getvalue()


def watermark_image(image_bytes: bytes) -> bytes:
    image = _open_rgb(image_bytes)
    drawing = ImageDraw.Draw(image)
    drawing.text(
        (image.width - 20, image.height - 20), "Cloud & AI",
        font=ImageFont.load_default(size=min(30, max(8, image.width // 12))),
        fill="white", stroke_width=2, stroke_fill="black", anchor="rs",
    )
    result = BytesIO()
    image.save(result, format="JPEG", quality=85, optimize=True)
    return result.getvalue()


def process_image(image_bytes: bytes) -> bytes:
    return watermark_image(resize_image(image_bytes))
