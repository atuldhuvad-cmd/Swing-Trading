"""Build small, valid, text-based PDFs for tests (synthetic content only)."""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")


def make_pdf(pages: list[list[str]]) -> bytes:
    """One PDF page per list; each string becomes one text line (Helvetica, WinAnsi)."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    pages_id = len(objects) + 1 + 2 * len(pages)  # placeholder id computed below
    page_ids = []
    for lines in pages:
        ops = []
        y = 800
        for line in lines:
            ops.append(f"BT /F1 9 Tf 1 0 0 1 40 {y} Tm ({_escape(line)}) Tj ET")
            y -= 14
        stream = "\n".join(ops).encode("cp1252", errors="replace")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_ids.append(add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (pages_id, font, content)
        ))
    kids = " ".join(f"{p} 0 R" for p in page_ids).encode()
    assert add(b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(page_ids)) == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    return bytes(out)


def make_slow_pdf(ops_per_page: int = 20000, pages: int = 60) -> bytes:
    """A tiny PDF that is slow to read: every page shares one compressed stream of many text operators."""
    import zlib

    ops = b"BT /F1 9 Tf 40 800 Td " + b"(a) Tj 1 0 Td " * ops_per_page + b"ET"
    comp = zlib.compress(ops, 9)
    objects = [b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comp) + comp + b"\nendstream"]
    pages_id = 3 + pages
    kids = []
    for _ in range(pages):
        objects.append(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] "
                       b"/Resources << /Font << /F1 1 0 R >> >> /Contents 2 0 R >>" % pages_id)
        kids.append(b"%d 0 R" % len(objects))
    objects.append(b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count %d >>" % pages)
    objects.append(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, len(objects), xref)
    return bytes(out)
