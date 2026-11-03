"""Regression tests for the graceful-degradation response of /api/screen.

When the screening pipeline raises, the route must still return a FLAGGED
report (never CLEAR) that carries the same canonical keys as a successful run.
The fallback used to emit `doc_hash` while every other screening path, the
frontend and the verify endpoint use `file_hash`, so a degraded result showed
no document fingerprint at the desk.
"""

from __future__ import annotations

import hashlib
import io
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

import main
from main import Base, SignerIdentity, app, make_session_token, now_utc

OFFICER = "officer@ssb.gov.in"


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
        db.add(
            SignerIdentity(
                email=OFFICER,
                name="Officer One",
                institution="SSB",
                designation="Assistant Commandant",
                registered_at=now_utc(),
            )
        )
        db.commit()
    finally:
        db.close()
    return TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})


def _synth_image() -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (160, 120), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, 150, 110], outline="black", fill="lightblue")
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


def test_degraded_screening_returns_canonical_file_hash(client, monkeypatch):
    """A pipeline exception must still identify the document by file_hash."""
    payload = _synth_image()
    expected_hash = hashlib.sha256(payload).hexdigest()

    def _boom(*args, **kwargs):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(main, "run_screening", _boom)

    resp = client.post(
        "/api/screen",
        files={"file": ("doc.jpg", payload, "image/jpeg")},
        data={"doc_type": "passport", "checkpoint": "Sunauli"},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()

    # Invariant FS: a failure may never produce an automatic CLEAR.
    assert report["verdict"] == "FLAGGED"
    assert report["file_hash"] == expected_hash
    assert "doc_hash" not in report
