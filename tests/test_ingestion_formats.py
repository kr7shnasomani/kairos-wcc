"""Spreadsheet + email-archive ingestion (services/ocr.py fast paths).

The problem statement names spreadsheets and email archives as source types; these
paths need no OCR model, so they are testable offline.
"""

import io
from email.message import EmailMessage

import pytest

from api.services.ocr import OCRService

svc = OCRService()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EML_MIME = "message/rfc822"


def _workbook() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "WorkOrders"
    ws.append(["work_order", "asset_tag", "failure_code", "technician"])
    ws.append(["WO-2026-0714", "EQ-101", "SEAL-FAIL", "Ravi Kumar"])
    ws.append([None, None, None, None])  # blank row must be dropped
    second = wb.create_sheet("Assets")
    second.append(["asset_tag", "equipment_class"])
    second.append(["HE-301", "heat_exchanger"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_spreadsheet_rows_and_sheet_names_extracted():
    result = await svc.extract_text(_workbook(), mime_type=XLSX_MIME)
    text = result["text"]

    assert result["extraction_method"] == "spreadsheet"
    assert result["requires_review"] is False
    # Both sheets, with their names, so downstream NER has context.
    assert "# Sheet: WorkOrders" in text and "# Sheet: Assets" in text
    # Cell values survive — these are the entities NER must find.
    for value in ("WO-2026-0714", "EQ-101", "SEAL-FAIL", "Ravi Kumar", "HE-301"):
        assert value in text, f"{value} missing from extracted spreadsheet text"
    # Blank rows are not emitted as empty tab runs.
    assert "\t\t\t" not in text


async def test_unreadable_spreadsheet_degrades_without_raising():
    result = await svc.extract_text(b"not a zip archive at all", mime_type=XLSX_MIME)
    assert result["text"] == ""
    assert result["requires_review"] is True


def _email() -> bytes:
    msg = EmailMessage()
    msg["From"] = "priya.nair@refinery.example"
    msg["To"] = "maintenance@refinery.example"
    msg["Subject"] = "EQ-101 seal replacement — OEM bulletin MS-4471-B"
    msg["Date"] = "Tue, 14 Jul 2026 09:15:00 +0530"
    msg.set_content("Confirming the seal spec change for EQ-101. Use P/N MS-4471-B.")
    msg.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf", filename="bulletin.pdf")
    return msg.as_bytes()


async def test_email_headers_body_and_attachment_names():
    result = await svc.extract_text(_email(), mime_type=EML_MIME)
    text = result["text"]

    assert result["extraction_method"] == "email"
    for value in ("From:", "Subject:", "priya.nair@refinery.example", "EQ-101", "MS-4471-B"):
        assert value in text, f"{value} missing from extracted email text"
    # Attachments are listed, not inlined as decoded bytes.
    assert "bulletin.pdf" in text
    assert "%PDF" not in text


async def test_mbox_archive_yields_every_message():
    one, two = _email(), _email().replace(b"EQ-101", b"HE-301")
    mbox = b"From sender@example 1\n" + one + b"\nFrom sender@example 2\n" + two

    result = await svc.extract_text(mbox, mime_type="application/mbox")
    assert result["extraction_method"] == "email"
    assert "EQ-101" in result["text"] and "HE-301" in result["text"]
    assert result["text"].count("Subject:") == 2
