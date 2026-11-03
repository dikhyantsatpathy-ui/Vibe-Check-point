"""Regression tests for session/document authorization boundaries.

The session soft-remove flow used to drop the report's `session_id` without
recording where it came from, so the restore endpoint could re-link any report
it was given into any open session the caller owned.  These tests pin the
ownership/provenance checks that make restore safe.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

import main
from main import (
    Base,
    ScreeningReport,
    ScreeningSession,
    SignerIdentity,
    app,
    make_session_token,
    now_utc,
)

OFFICER = "officer@ssb.gov.in"
OTHER_OFFICER = "other.officer@ssb.gov.in"


@pytest.fixture(autouse=True)
def _clear_screen_idempotency_cache():
    main._SCREEN_IDEMPOTENCY_CACHE.clear()
    yield
    main._SCREEN_IDEMPOTENCY_CACHE.clear()


@pytest.fixture
def client(monkeypatch):
    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(main, "SessionLocal", TestSession)
    db = TestSession()
    try:
        db.add_all([
            SignerIdentity(
                email=OFFICER,
                name="Officer One",
                institution="SSB",
                designation="Assistant Commandant",
                registered_at=now_utc(),
            ),
            SignerIdentity(
                email=OTHER_OFFICER,
                name="Officer Two",
                institution="SSB",
                designation="Inspector",
                registered_at=now_utc(),
            ),
        ])
        db.commit()
    finally:
        db.close()
    return TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})


def _seed_session(db, session_id: str) -> None:
    db.add(
        ScreeningSession(
            id=session_id,
            status="open",
            verdict="PENDING",
            risk_score=0,
            checkpoint="Sunauli",
            screener=OFFICER,
            comparison="{}",
            note="",
            created_at=now_utc(),
            updated_at=now_utc(),
        )
    )


def _synth_image(w: int = 160, h: int = 120) -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, w - 10, h - 10], outline="black", fill="lightblue")
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


def _seed_report(db, report_id: str, session_id: str) -> None:
    value = f"{session_id}:{report_id}"
    db.add(
        ScreeningReport(
            id=report_id,
            file_hash=hashlib.sha256(value.encode()).hexdigest(),
            filename="passport.jpg",
            doc_type="passport",
            checkpoint="Sunauli",
            verdict="CLEAR",
            risk_score=10,
            confidence=0.9,
            extracted_fields="{}",
            signals="[]",
            ai_detection="{}",
            modules=json.dumps({"validation": "PASS"}),
            screener=OFFICER,
            created_at=now_utc(),
            session_id=session_id,
            field_hashes="{}",
        )
    )


def test_restore_cannot_hijack_a_live_document_from_another_session(client):
    """A non-removed report must never be moved into another session."""
    with main.SessionLocal() as db:
        _seed_session(db, "sess-a")
        _seed_session(db, "sess-b")
        _seed_report(db, "doc-a", "sess-a")
        db.commit()

    resp = client.post("/api/sessions/sess-b/documents/doc-a/restore")
    assert resp.status_code == 400, resp.text

    with main.SessionLocal() as db:
        row = db.query(ScreeningReport).filter_by(id="doc-a").first()
        assert row.session_id == "sess-a"
        assert row.removed_at is None


def test_restore_rejects_a_document_removed_from_a_different_session(client):
    """Soft-remove provenance must stop cross-session restore."""
    with main.SessionLocal() as db:
        _seed_session(db, "sess-a")
        _seed_session(db, "sess-b")
        _seed_report(db, "doc-a", "sess-a")
        db.commit()

    removed = client.post("/api/sessions/sess-a/documents/doc-a/remove")
    assert removed.status_code == 200, removed.text

    resp = client.post("/api/sessions/sess-b/documents/doc-a/restore")
    assert resp.status_code in (400, 403), resp.text

    with main.SessionLocal() as db:
        row = db.query(ScreeningReport).filter_by(id="doc-a").first()
        assert row.removed_at is not None
        assert row.session_id is None


def test_officer_cannot_screen_into_another_officers_open_session(client, monkeypatch):
    """An open session is still owned by the officer who opened it."""
    with main.SessionLocal() as db:
        _seed_session(db, "sess-a")
        db.commit()

    called = []

    def _fake_screen(*args, **kwargs):
        called.append(kwargs)
        return {
            "id": "fake-report",
            "doc_hash": "0" * 64,
            "doc_type": "passport",
            "verdict": "REVIEW",
            "risk_score": 30,
            "checkpoint": "Sunauli",
            "created_at": now_utc(),
            "reasons": ["fake"],
        }

    monkeypatch.setattr(main, "run_screening", _fake_screen)

    other = TestClient(
        app, cookies={"nischay_session": make_session_token(OTHER_OFFICER)}
    )
    resp = other.post(
        "/api/screen",
        files={"file": ("doc.jpg", _synth_image(), "image/jpeg")},
        data={"session_id": "sess-a", "doc_type": "passport"},
    )
    assert resp.status_code == 403, resp.text
    assert called == []


def _fake_report(**kwargs):
    return {
        "id": "fake-report",
        "doc_hash": "0" * 64,
        "doc_type": kwargs.get("doc_type", "passport"),
        "verdict": "REVIEW",
        "risk_score": 30,
        "checkpoint": "Sunauli",
        "created_at": now_utc(),
        "declared": kwargs.get("declared") or {},
        "reasons": ["fake"],
    }


def _screen_spy(calls):
    def fake(*args, **kwargs):
        declared_map = kwargs.get("declared")
        if declared_map is None and len(args) > 4:
            declared_map = args[4]
        doc_type = args[2] if len(args) > 2 else kwargs.get("doc_type", "passport")
        calls.append({"declared": declared_map, "doc_type": doc_type})
        return _fake_report(declared=declared_map, doc_type=doc_type)

    return fake


def test_identical_screen_request_is_replayed_from_cache(client, monkeypatch):
    with main.SessionLocal() as db:
        _seed_session(db, "sess-a")
        db.commit()

    calls = []
    monkeypatch.setattr(main, "run_screening", _screen_spy(calls))

    payload = {
        "session_id": "sess-a",
        "doc_type": "passport",
        "declared": json.dumps({"passport_number": "A1234567"}),
    }
    for _ in range(2):
        resp = client.post(
            "/api/screen",
            files={"file": ("doc.jpg", _synth_image(), "image/jpeg")},
            data=payload,
        )
        assert resp.status_code == 200, resp.text

    assert len(calls) == 1


def test_changed_declared_fields_are_not_served_from_stale_cache(client, monkeypatch):
    """A corrected declaration is a new screening, not an idempotent replay."""
    with main.SessionLocal() as db:
        _seed_session(db, "sess-a")
        db.commit()

    calls = []
    monkeypatch.setattr(main, "run_screening", _screen_spy(calls))

    for value in ("A1234567", "B7654321"):
        resp = client.post(
            "/api/screen",
            files={"file": ("doc.jpg", _synth_image(), "image/jpeg")},
            data={
                "session_id": "sess-a",
                "doc_type": "passport",
                "declared": json.dumps({"passport_number": value}),
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["declared"]["passport_number"] == value

    assert len(calls) == 2
    assert [c["declared"]["passport_number"] for c in calls] == ["A1234567", "B7654321"]
