"""
product_catalog.py
------------------
Product catalog loader and fuzzy product-name matcher for the Site Audit Agent.

Provides three public functions:

    load_catalog(catalog_path)   — Load and in-memory cache products.json
    match_products(text, catalog) — Fuzzy substring match against product names
                                    and aliases; returns enriched match records.
    resolve_pds_url(product_name, catalog) — Return catalog PDS URL or SW
                                              search fallback URL.

Uses Python stdlib only (json, re, urllib.parse, logging).
No external fuzzy-match libraries are required or used.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level catalog cache
# A sentinel of None means "not yet loaded"; an empty list means "tried and
# failed (file missing or malformed)."
# ---------------------------------------------------------------------------
_CATALOG_CACHE: list[dict] | None = None
_CATALOG_PATH_LOADED: str | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_catalog(catalog_path: str = "data/products.json") -> list[dict]:
    """
    Load the product catalog from *catalog_path* and return it as a list of
    product dicts.

    The result is cached in module-level memory after the first successful
    load so that subsequent calls incur no disk I/O.  If a different path is
    supplied, the cache is invalidated and the new file is loaded.

    Returns an empty list (and logs an error) on any I/O or JSON parse error
    — never raises.

    Parameters
    ----------
    catalog_path : str
        Path to ``products.json``, relative to the working directory or
        absolute.  Defaults to ``"data/products.json"``.

    Returns
    -------
    list[dict]
        List of product entry dicts.  Empty on error.
    """
    global _CATALOG_CACHE, _CATALOG_PATH_LOADED

    # Return cached copy if the same path was already loaded
    if _CATALOG_CACHE is not None and _CATALOG_PATH_LOADED == catalog_path:
        return _CATALOG_CACHE

    try:
        with open(catalog_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logger.error(
            "Product catalog not found at '%s'. "
            "Ensure data/products.json is present in the project directory.",
            catalog_path,
        )
        _CATALOG_CACHE = []
        _CATALOG_PATH_LOADED = catalog_path
        return []
    except json.JSONDecodeError as exc:
        logger.error(
            "Product catalog at '%s' contains invalid JSON: %s",
            catalog_path,
            exc,
        )
        _CATALOG_CACHE = []
        _CATALOG_PATH_LOADED = catalog_path
        return []
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error loading product catalog: %s", exc)
        _CATALOG_CACHE = []
        _CATALOG_PATH_LOADED = catalog_path
        return []

    if not isinstance(data, list):
        logger.error(
            "Product catalog at '%s' is not a JSON array. Got: %s",
            catalog_path,
            type(data).__name__,
        )
        _CATALOG_CACHE = []
        _CATALOG_PATH_LOADED = catalog_path
        return []

    logger.debug("Loaded %d products from '%s'.", len(data), catalog_path)
    _CATALOG_CACHE = data
    _CATALOG_PATH_LOADED = catalog_path
    return _CATALOG_CACHE


def match_products(
    text: str | None,
    catalog: list[dict] | None = None,
) -> list[dict]:
    """
    Scan *text* for product names and aliases from *catalog* using
    case-insensitive substring matching.

    Algorithm
    ---------
    1. Normalize input text and every product token to lowercase.
    2. Build a search list of ``(token_lower, entry, confidence)`` tuples,
       sorted by token length **descending** so that the longest (most
       specific) match wins when names overlap (e.g. "Zinc Clad IV" beats
       any shorter "Zinc Clad" token).
    3. Scan the normalized input with ``re.search`` for each token.
       Track matched character spans to prevent overlapping matches — once a
       span is consumed by a longer token, shorter tokens that would overlap
       are skipped.
    4. Return results sorted by the position (start index) at which each
       match appeared in *text*, preserving reading order.

    Confidence levels
    -----------------
    ``"exact"``   — token matches the canonical ``product_name``
    ``"alias"``   — token matches one of the ``aliases``
    ``"partial"`` — not used in current algorithm (reserved for future
                    edit-distance matching)

    Parameters
    ----------
    text : str | None
        Free-text input to scan (e.g. APM coating system specification).
        Returns ``[]`` on empty string, ``None``, or whitespace-only input.
    catalog : list[dict] | None
        Product catalog.  If *None*, ``load_catalog()`` is called with the
        default path.

    Returns
    -------
    list[dict]
        Each item contains:
        ``product_name``, ``product_number``, ``pds_url``, ``category``,
        ``matched_on`` (the token that triggered the match),
        ``match_confidence`` (``"exact"`` or ``"alias"``).
        Empty list if no matches or on error — never raises.
    """
    # Guard: empty / None input
    if not text or not str(text).strip():
        return []

    if catalog is None:
        catalog = load_catalog()

    if not catalog:
        return []

    try:
        return _run_match(str(text), catalog)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in match_products: %s", exc)
        return []


def resolve_pds_url(
    product_name: str,
    catalog: list[dict] | None = None,
) -> str:
    """
    Return the PDS URL for *product_name*.

    Looks up the product in *catalog* (loading the default catalog if
    *catalog* is ``None``).  If found, returns the ``pds_url`` field.
    If not found, returns a parameterized Sherwin-Williams search URL:

        https://www.sherwin-williams.com/en-us/search#q={encoded_name}&t=coveoSearch

    Parameters
    ----------
    product_name : str
        Canonical product name to resolve.
    catalog : list[dict] | None
        Product catalog.  If *None*, ``load_catalog()`` is called.

    Returns
    -------
    str
        PDS URL from catalog, or SW search fallback URL.
    """
    if catalog is None:
        catalog = load_catalog()

    name_lower = product_name.strip().lower()

    for entry in catalog:
        if entry.get("product_name", "").lower() == name_lower:
            pds_url = entry.get("pds_url", "").strip()
            if pds_url:
                return pds_url

    # Fallback: parameterized SW search URL
    encoded = quote_plus(product_name.strip())
    return (
        f"https://www.sherwin-williams.com/en-us/search"
        f"#q={encoded}&t=coveoSearch"
    )


# ---------------------------------------------------------------------------
# Internal matching implementation
# ---------------------------------------------------------------------------


def _build_token_list(catalog: list[dict]) -> list[tuple[str, dict, str]]:
    """
    Build and return a list of ``(token_lower, entry, confidence)`` tuples,
    sorted by token length descending.

    Each product contributes:
    - Its canonical ``product_name`` → confidence ``"exact"``
    - Each entry in ``aliases``      → confidence ``"alias"``
    """
    tokens: list[tuple[str, dict, str]] = []

    for entry in catalog:
        name = entry.get("product_name", "").strip()
        if name:
            tokens.append((name.lower(), entry, "exact"))

        for alias in entry.get("aliases", []):
            alias_str = str(alias).strip()
            if alias_str:
                tokens.append((alias_str.lower(), entry, "alias"))

    # Sort longest-first so more specific tokens win on overlap
    tokens.sort(key=lambda t: len(t[0]), reverse=True)
    return tokens


def _run_match(text: str, catalog: list[dict]) -> list[dict]:
    """
    Core matching loop.  Returns enriched match dicts sorted by position
    of first appearance in *text*.
    """
    text_lower = text.lower()
    token_list = _build_token_list(catalog)

    # Track which character spans have already been claimed by a longer match.
    # We record (start, end) intervals and skip any new match whose span
    # overlaps an already-claimed interval.
    claimed_spans: list[tuple[int, int]] = []

    # Map product_name → result dict to deduplicate (one match per product)
    seen_products: dict[str, dict] = {}

    # Map product_name → position in text (for final sort)
    match_positions: dict[str, int] = {}

    for token_lower, entry, confidence in token_list:
        product_name = entry.get("product_name", "")

        # Skip if this product already matched via a longer token
        if product_name in seen_products:
            continue

        # Escape for safe regex usage (product names can contain parentheses etc.)
        escaped_token = re.escape(token_lower)

        m = re.search(escaped_token, text_lower)
        if m is None:
            continue

        start, end = m.start(), m.end()

        # Check for overlap with already-claimed spans
        if _overlaps(start, end, claimed_spans):
            continue

        # Claim the span and record the match
        claimed_spans.append((start, end))
        match_positions[product_name] = start

        seen_products[product_name] = {
            "product_name": product_name,
            "product_number": entry.get("product_number", ""),
            "pds_url": entry.get("pds_url", ""),
            "category": entry.get("category", ""),
            "matched_on": token_lower,
            "match_confidence": confidence,
        }

    # Return results in order of appearance in text
    results = list(seen_products.values())
    results.sort(key=lambda r: match_positions.get(r["product_name"], 0))
    return results


def _overlaps(start: int, end: int, claimed: list[tuple[int, int]]) -> bool:
    """Return True if [start, end) overlaps any interval in *claimed*."""
    for cs, ce in claimed:
        # Intervals overlap if one starts before the other ends
        if start < ce and end > cs:
            return True
    return False
