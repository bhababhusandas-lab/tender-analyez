import asyncio
import io

from starlette.datastructures import Headers, UploadFile

from app.core.tender_inputs import read_uploads, source_block


def _upload(name: str, data: bytes, ctype: str = "text/plain") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name, headers=Headers({"content-type": ctype}))


def test_reads_text_files_and_keeps_raw_bytes():
    docs, errors = asyncio.run(read_uploads([_upload("NIT.txt", b"EMD: Rs 50,000")]))
    assert errors == []
    assert docs[0].filename == "NIT.txt"
    assert docs[0].raw == b"EMD: Rs 50,000"
    assert "EMD: Rs 50,000" in docs[0].text
    assert source_block(docs[0]) == "--- SOURCE DOCUMENT: NIT.txt ---\n" + docs[0].text


def test_rejects_more_than_ten_files():
    uploads = [_upload(f"{i}.txt", b"x") for i in range(11)]
    docs, errors = asyncio.run(read_uploads(uploads))
    assert docs == []
    assert errors == ["Upload at most 10 files per analysis."]


def test_unreadable_file_reports_its_name():
    docs, errors = asyncio.run(read_uploads([_upload("scan.png", b"\x89PNG....", "image/png")]))
    assert docs == []
    assert errors and errors[0].startswith("scan.png:")


def _zip_bytes(files):
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    return buf.getvalue()


def test_zip_is_expanded_into_each_supported_file():
    import asyncio
    from app.core.tender_inputs import read_uploads
    zb = _zip_bytes({
        "NIT.txt": b"Bid Submission Deadline: 15.10.2026",
        "annex/Eligibility.txt": b"Turnover: Rs 5 crore",
        "__MACOSX/._NIT.txt": b"junk",
        ".hidden.txt": b"junk",
        "folder/": b"",
    })
    docs, errors = asyncio.run(read_uploads([_upload("tender.zip", zb, "application/zip")]))
    names = sorted(d.filename for d in docs)
    assert names == ["Eligibility.txt", "NIT.txt"]
    assert "15.10.2026" in next(d.text for d in docs if d.filename == "NIT.txt")
    assert errors == []


def test_zip_with_no_readable_files_reports_error():
    import asyncio
    from app.core.tender_inputs import read_uploads
    zb = _zip_bytes({"photo.png": b"\x89PNG not really"})
    docs, errors = asyncio.run(read_uploads([_upload("imgs.zip", zb, "application/zip")]))
    # png is unsupported -> that inner file errors, zip yields no docs
    assert docs == []
    assert any("png" in e.lower() for e in errors)


def test_corrupt_zip_is_reported():
    import asyncio
    from app.core.tender_inputs import read_uploads
    docs, errors = asyncio.run(read_uploads([_upload("bad.zip", b"PK\x03\x04garbage", "application/zip")]))
    assert docs == []
    assert errors and "zip" in errors[0].lower()
