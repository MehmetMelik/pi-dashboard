"""AI summaries for news articles, produced by the news-firebase pipeline.

Primary source is a local SQLite mirror that news-firebase writes on the same box
— zero network, zero Firestore reads. If that mirror file is unavailable, we fall
back to reading Firestore directly (which shares a limited free-tier read quota).

Both are keyed by sha256(url)[:16], matching news-firebase's document ids.
Read-only; degrades gracefully — unmatched articles stay unsummarized and get
retried on the next pass (by which point news-firebase has usually summarized
them). The firebase-admin SDK is blocking, so callers should run these in a
worker thread (asyncio.to_thread).
"""

import hashlib
import os
import sqlite3

from app.config import (
    SUMMARY_MIRROR_PATH,
    FIRESTORE_ENABLED,
    FIREBASE_CRED_PATH,
    FIRESTORE_COLLECTION,
)
from app.database import get_unsummarized_articles, set_ai_summary


def _doc_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


# --- Primary: local mirror (no Firestore reads) ---

def _mirror_available() -> bool:
    return bool(SUMMARY_MIRROR_PATH) and os.path.exists(SUMMARY_MIRROR_PATH)


def latest_article_ts() -> float | None:
    """Newest article pushed_at (epoch) from the local mirror — used as a
    liveness signal for the news pipeline. None if the mirror is unavailable."""
    if not _mirror_available():
        return None
    try:
        conn = sqlite3.connect(f"file:{SUMMARY_MIRROR_PATH}?mode=ro", uri=True, timeout=5)
        try:
            row = conn.execute("SELECT MAX(pushed_at) FROM recent").fetchone()
            return row[0] if row and row[0] else None
        finally:
            conn.close()
    except Exception:
        return None


def latest_summary_ts() -> float | None:
    """Newest ai_summary write time (epoch) from the local mirror. Compared with
    latest_article_ts() to detect the summariser stalling while articles flow."""
    if not _mirror_available():
        return None
    try:
        conn = sqlite3.connect(f"file:{SUMMARY_MIRROR_PATH}?mode=ro", uri=True, timeout=5)
        try:
            row = conn.execute("SELECT MAX(updated_at) FROM summaries").fetchone()
            return row[0] if row and row[0] else None
        finally:
            conn.close()
    except Exception:
        return None


def _enrich_from_mirror(articles: list[dict]) -> int:
    # Open read-only so we never interfere with news-firebase's writes.
    conn = sqlite3.connect(f"file:{SUMMARY_MIRROR_PATH}?mode=ro", uri=True, timeout=5)
    try:
        conn.execute("PRAGMA busy_timeout=3000")
        enriched = 0
        for a in articles:
            url = a.get("url")
            if not url:
                continue
            row = conn.execute(
                "SELECT ai_summary FROM summaries WHERE doc_id = ?",
                (_doc_id(url),),
            ).fetchone()
            if row and row[0]:
                set_ai_summary(a["id"], row[0])
                enriched += 1
        return enriched
    finally:
        conn.close()


# --- Fallback: Firestore (costs shared read quota) ---

_db = None
_init_failed = False


def _get_db():
    global _db, _init_failed
    if _db is not None:
        return _db
    if _init_failed:
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        try:
            app = firebase_admin.get_app("dashboard")
        except ValueError:
            cred = credentials.Certificate(FIREBASE_CRED_PATH)
            app = firebase_admin.initialize_app(cred, name="dashboard")
        _db = firestore.client(app)
        return _db
    except Exception as e:
        print(f"[firestore] init failed, Firestore fallback disabled: {e}")
        _init_failed = True
        return None


def _enrich_from_firestore(articles: list[dict]) -> int:
    db = _get_db()
    if db is None:
        return 0
    collection = db.collection(FIRESTORE_COLLECTION)
    by_doc: dict[str, int] = {}
    refs = []
    for a in articles:
        url = a.get("url")
        if not url:
            continue
        did = _doc_id(url)
        by_doc[did] = a["id"]
        refs.append(collection.document(did))
    if not refs:
        return 0

    enriched = 0
    for doc in db.get_all(refs, field_paths=["ai_summary"]):
        if not doc.exists:
            continue
        data = doc.to_dict() or {}
        summary = data.get("ai_summary")
        if summary:
            set_ai_summary(by_doc[doc.id], summary)
            enriched += 1
    return enriched


# --- Public API ---

def is_available() -> bool:
    if _mirror_available():
        return True
    return FIRESTORE_ENABLED and _get_db() is not None


def enrich_unsummarized(limit: int = 25) -> int:
    """Fill ai_summary on local articles. Returns count enriched.

    Uses the local mirror when present (no Firestore reads); otherwise falls back
    to Firestore. Raising on a Firestore quota error is intentional — the caller
    backs off — but the mirror path never raises for quota reasons.
    """
    articles = get_unsummarized_articles(limit=limit)
    if not articles:
        return 0
    if _mirror_available():
        return _enrich_from_mirror(articles)
    if FIRESTORE_ENABLED:
        return _enrich_from_firestore(articles)
    return 0
