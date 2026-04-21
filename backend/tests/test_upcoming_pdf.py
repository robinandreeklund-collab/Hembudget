"""Verifiera att PDF:er rasteriseras korrekt innan de skickas till vision-modellen.
Bilderna ska nedskalas till JPEG för att passa i LM Studios kontextfönster."""
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


JPEG_MAGIC = b"\xff\xd8\xff"


def test_pdf_rasterizes_each_page():
    from hembudget.api.upcoming import _rasterize_pdf

    pdf_bytes = _make_pdf(num_pages=3)
    images = _rasterize_pdf(pdf_bytes)
    assert len(images) == 3
    # Varje sida ska ge en icke-tom JPEG
    for img in images:
        assert img.startswith(JPEG_MAGIC)
        # Nedskalat ska vara mycket mindre än en full-res render
        assert len(img) < 100_000   # typiskt 10-40 kB


def test_pdf_respects_max_pages():
    from hembudget.api.upcoming import _rasterize_pdf

    pdf_bytes = _make_pdf(num_pages=10)
    images = _rasterize_pdf(pdf_bytes, max_pages=2)
    assert len(images) == 2


def test_file_to_images_detects_pdf_by_magic():
    from hembudget.api.upcoming import _file_to_images

    pdf_bytes = _make_pdf(num_pages=1)
    images, mime = _file_to_images(pdf_bytes, None)
    assert mime == "image/jpeg"
    assert len(images) == 1
    assert images[0].startswith(JPEG_MAGIC)


def test_png_gets_downscaled_and_converted():
    """En stor PNG ska skalas ned och konverteras till JPEG."""
    from hembudget.api.upcoming import IMAGE_MAX_DIM, _file_to_images
    from PIL import Image

    # Skapa en "pseudo-foto" med brus så PNG inte trivialt komprimerar
    import random
    random.seed(42)
    img = Image.new("RGB", (2000, 2000))
    img.putdata([
        (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        for _ in range(2000 * 2000)
    ])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    original_size = len(buf.getvalue())

    images, mime = _file_to_images(buf.getvalue(), "image/png")
    assert len(images) == 1
    assert mime == "image/jpeg"
    assert images[0].startswith(JPEG_MAGIC)

    # Verifiera att bilden är nedskalad
    out = Image.open(io.BytesIO(images[0]))
    assert max(out.size) <= IMAGE_MAX_DIM
    # Resultatet ska vara mycket mindre än originalet (typisk reduktion 90 %+)
    assert len(images[0]) < original_size / 5
