"""Générateur de PDF minimal (texte seul, Helvetica, A4), sans bibliothèque externe."""

LINES_PER_PAGE = 48


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def create_pdf(lines: list[str]) -> bytes:
    enc = "latin-1"  # les lettres accentuées françaises passent en Latin-1
    pages = [lines[i:i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)] or [[]]

    # Objets PDF : 1 = catalogue, 2 = liste des pages, 3 = police,
    # puis pour chaque page i : 4 + 2i = la page, 5 + 2i = son contenu.
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(enc),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for i, page in enumerate(pages):
        text = "BT /F1 10 Tf 14 TL 50 800 Td\n" + "".join(f"({_escape(l)}) Tj T*\n" for l in page) + "ET"
        content = text.encode(enc, errors="replace")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode(enc)
        )
        objects.append(f"<< /Length {len(content)} >>\nstream\n".encode(enc) + content + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode(enc) + obj + b"\nendobj\n"

    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode(enc)
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode(enc)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode(enc)
    return bytes(out)
