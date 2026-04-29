"""Testes do cache de listings."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.agents.comparables.cache import is_listing_fresh, split_cached_vs_fresh


def test_is_fresh_recent_string() -> None:
    iso = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    assert is_listing_fresh(iso, ttl_days=30) is True


def test_is_fresh_too_old() -> None:
    iso = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    assert is_listing_fresh(iso, ttl_days=30) is False


def test_is_fresh_none() -> None:
    assert is_listing_fresh(None, ttl_days=30) is False


def test_is_fresh_naive_datetime_treated_as_utc() -> None:
    naive = (datetime.now(timezone.utc) - timedelta(days=2)).replace(tzinfo=None)
    assert is_listing_fresh(naive, ttl_days=30) is True


def test_is_fresh_invalid_string() -> None:
    assert is_listing_fresh("not-a-date", ttl_days=30) is False


def test_split_cached_vs_fresh_mixed() -> None:
    now = datetime.now(timezone.utc)
    cached = [
        {"source_url": "https://a", "scraped_at": (now - timedelta(days=2)).isoformat()},
        {"source_url": "https://b", "scraped_at": (now - timedelta(days=40)).isoformat()},
    ]
    cached_used, fresh = split_cached_vs_fresh(
        candidates=["https://a", "https://b", "https://c"],
        cached_listings=cached,
        ttl_days=30,
    )
    assert set(cached_used.keys()) == {"https://a"}
    assert set(fresh) == {"https://b", "https://c"}


def test_split_all_fresh_when_no_cache() -> None:
    cached_used, fresh = split_cached_vs_fresh(
        candidates=["https://x", "https://y"],
        cached_listings=[],
        ttl_days=30,
    )
    assert cached_used == {}
    assert fresh == ["https://x", "https://y"]


def test_split_all_cached_when_recent() -> None:
    now = datetime.now(timezone.utc).isoformat()
    cached = [
        {"source_url": "https://a", "scraped_at": now},
        {"source_url": "https://b", "scraped_at": now},
    ]
    cached_used, fresh = split_cached_vs_fresh(
        candidates=["https://a", "https://b"],
        cached_listings=cached,
        ttl_days=30,
    )
    assert len(cached_used) == 2
    assert fresh == []
