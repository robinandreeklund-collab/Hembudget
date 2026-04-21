"""Verifiera att PDF:er rasteriseras korrekt innan de skickas till vision-modellen."""
import io


def _make_pdf(num_pages: int = 2) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(num_pages):
        c.drawString(100, 750, f"Sida {i + 1}: testfaktura")
        c.drawString(100, 700, "Vattenfall 1 420 kr")
        c.drawString(100, 650, "Förfallodag 2026-04-30")
        c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf_rasterizes_each_page():
    from hembudget.api.upcoming import _rasterize_pdf

    pdf_bytes = _make_pdf(num_pages=3)
    images = _rasterize_pdf(pdf_bytes)
    assert len(images) == 3
    # Varje sida ska ge en icke-tom PNG (startar med PNG magic)
    for img in images:
        assert img.startswith(b"\x89PNG\r\n\x1a\n")


def test_pdf_respects_max_pages():
    from hembudget.api.upcoming import _rasterize_pdf

    pdf_bytes = _make_pdf(num_pages=10)
    images = _rasterize_pdf(pdf_bytes, max_pages=5)
    assert len(images) == 5


def test_file_to_images_detects_pdf_by_magic():
    from hembudget.api.upcoming import _file_to_images

    pdf_bytes = _make_pdf(num_pages=1)
    # Utan content-type → magic-bytes ska ändå trigga
    images, mime = _file_to_images(pdf_bytes, None)
    assert mime == "image/png"
    assert len(images) == 1


def test_png_passes_through():
    from hembudget.api.upcoming import _file_to_images
    from PIL import Image

    img = Image.new("RGB", (10, 10), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    images, mime = _file_to_images(buf.getvalue(), "image/png")
    assert len(images) == 1
    assert mime == "image/png"
    assert images[0] == buf.getvalue()
