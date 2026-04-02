from PIL import Image, ImageEnhance
import base64
import os


def enhance_image(image_path: str) -> str:
    """
    Apply contrast + sharpness boost for low-quality images.
    Saves enhanced image to {image_path}_enhanced.jpg.
    Returns new path.
    """
    img = Image.open(image_path).convert("RGB")

    # Boost contrast
    contrast_enhancer = ImageEnhance.Contrast(img)
    img = contrast_enhancer.enhance(1.8)

    # Boost sharpness
    sharpness_enhancer = ImageEnhance.Sharpness(img)
    img = sharpness_enhancer.enhance(2.0)

    enhanced_path = f"{image_path}_enhanced.jpg"
    img.save(enhanced_path, format="JPEG", quality=95)
    return enhanced_path


def pdf_to_jpeg(pdf_path: str) -> str:
    """Convert first page of PDF to JPEG. Return path to JPEG."""
    from pdf2image import convert_from_path

    pages = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=200)
    if not pages:
        raise ValueError(f"Could not convert PDF to image: {pdf_path}")

    jpeg_path = f"{pdf_path}_converted.jpg"
    pages[0].save(jpeg_path, format="JPEG", quality=95)
    return jpeg_path


def image_to_base64(image_path: str) -> tuple[str, str]:
    """
    Read image file, return (base64_string, media_type).
    If file is a PDF: convert first page to JPEG using pdf2image,
    save as {image_path}_converted.jpg, then encode.
    media_type is "image/jpeg" or "image/png" based on file extension.
    """
    ext = os.path.splitext(image_path)[1].lower()

    if ext == ".pdf":
        image_path = pdf_to_jpeg(image_path)
        media_type = "image/jpeg"
    elif ext == ".png":
        media_type = "image/png"
    else:
        # Treat everything else (jpg, jpeg, webp, etc.) as jpeg
        media_type = "image/jpeg"

    with open(image_path, "rb") as f:
        raw_bytes = f.read()

    b64 = base64.standard_b64encode(raw_bytes).decode("utf-8")
    return b64, media_type
