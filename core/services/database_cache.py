"""Utilities for caching Kobo payloads as JSON snapshots.

This module centralises the logic required to fetch Kobo submissions for a
``DatabaseEntry`` and persist them to disk as JSON payloads.  A lightweight
diff/merge routine keeps previously cached submissions intact while merging in
new or updated records.  The resulting cache files are stored underneath the
``DATABASE_CACHE_ROOT`` path configured in Django settings, defaulting to
``media/database_cache`` inside the project directory.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from django.conf import settings
from django.utils import timezone

from core.models import DatabaseEntry


class DatabaseCacheError(Exception):
    """Raised when synchronising the local cache fails."""


class EnketoLinkError(DatabaseCacheError):
    """Raised when requesting an Enketo edit URL fails."""


@dataclass
class EntrySnapshot:
    """Represents the cached payload for a ``DatabaseEntry``."""

    path: Path
    metadata: Dict[str, Any]
    records: List[Dict[str, Any]]
    synced_at: Optional[str]
    entry_info: Dict[str, Any]
    stats: Dict[str, Any]


@dataclass
class CacheSyncResult:
    """Result of refreshing the cache for a ``DatabaseEntry``."""

    path: Path
    added: int
    updated: int
    total: int
    snapshot: EntrySnapshot


def get_cache_root() -> Path:
    """Return the root directory used for cached payloads."""

    root = getattr(settings, 'DATABASE_CACHE_ROOT', settings.BASE_DIR / 'media' / 'database_cache')
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    return root_path


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_.-]+', '_', str(value).strip())
    return cleaned or 'entry'


def get_entry_cache_path(entry: DatabaseEntry) -> Path:
    """Compute the cache path for a given ``DatabaseEntry``."""

    project_dir = get_cache_root() / f"project_{entry.project_id}"
    project_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe_segment(entry.asset_id)}.json"
    return project_dir / filename


def load_entry_snapshot(entry: DatabaseEntry) -> EntrySnapshot:
    """Load the cached payload for ``entry`` if available."""

    path = get_entry_cache_path(entry)
    if not path.exists():
        return EntrySnapshot(
            path=path,
            metadata={},
            records=[],
            synced_at=None,
            entry_info={},
            stats={'total': 0, 'added': 0, 'updated': 0},
        )
    try:
        with path.open('r', encoding='utf-8') as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:  # pragma: no cover - indicates manual tampering
        raise DatabaseCacheError(f'Failed to parse cached payload for entry {entry.pk}: {exc}')
    metadata = data.get('metadata', {})
    records = data.get('records', [])
    synced_at = data.get('synced_at')
    entry_info = data.get('entry', {})
    stats = data.get('stats', {})
    stats.setdefault('total', len(records))
    stats.setdefault('added', 0)
    stats.setdefault('updated', 0)
    return EntrySnapshot(
        path=path,
        metadata=metadata,
        records=records,
        synced_at=synced_at,
        entry_info=entry_info,
        stats=stats,
    )


def delete_entry_cache(entry: DatabaseEntry) -> None:
    """Remove the cached payload for ``entry`` if it exists."""

    path = get_entry_cache_path(entry)
    try:
        path.unlink()
    except FileNotFoundError:
        return


def refresh_entry_cache(entry: DatabaseEntry, refresh_ids: Optional[Iterable[str]] = None) -> CacheSyncResult:
    """Fetch Kobo submissions and persist them to the local cache.

    Args:
        entry: The database entry whose payload should be refreshed.
        refresh_ids: Optional iterable of submission identifiers that should
            be forcefully re-synchronised alongside new records.  This is
            useful when manual edits were triggered for historical rows.
    """

    metadata, submissions = _fetch_remote_payload(entry.token, entry.asset_id)
    if refresh_ids:
        query_ids = _prepare_submission_query(refresh_ids)
        if query_ids:
            _, targeted = _fetch_remote_payload(
                entry.token,
                entry.asset_id,
                query={'_id': {'$in': query_ids}},
            )
            if targeted:
                submissions.extend(targeted)
    snapshot = load_entry_snapshot(entry)
    merged_records, added, updated = _merge_records(snapshot.records, submissions)
    now_iso = timezone.now().isoformat()
    payload = {
        'entry': {
            'entry_id': entry.pk,
            'project_id': entry.project_id,
            'asset_id': entry.asset_id,
            'db_name': entry.db_name,
        },
        'metadata': metadata,
        'records': merged_records,
        'record_count': len(merged_records),
        'stats': {'added': added, 'updated': updated, 'total': len(merged_records)},
        'synced_at': now_iso,
    }
    path = get_entry_cache_path(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    new_snapshot = EntrySnapshot(
        path=path,
        metadata=metadata,
        records=merged_records,
        synced_at=now_iso,
        entry_info=payload['entry'],
        stats=payload['stats'],
    )
    return CacheSyncResult(
        path=path,
        added=added,
        updated=updated,
        total=len(merged_records),
        snapshot=new_snapshot,
    )


def request_enketo_edit_url(entry: DatabaseEntry, submission_id: str, return_url: Optional[str] = None) -> str:
    """Request an Enketo edit URL for a specific submission."""

    session = requests.Session()
    session.headers.update({'Authorization': f'Token {entry.token}', 'Accept': 'application/json'})
    timeout = getattr(settings, 'KOBO_HTTP_TIMEOUT', 60)
    verify_param = getattr(settings, 'KOBO_TLS_CERT', None) or getattr(settings, 'KOBO_VERIFY_TLS', True)
    api_base = getattr(settings, 'KOBO_API_BASE', None)
    if not api_base:
        raise EnketoLinkError('KOBO_API_BASE setting is not configured.')
    submission_segment = str(submission_id).strip()
    if not submission_segment:
        raise EnketoLinkError('A valid submission identifier is required to request an edit link.')
    endpoint = f"{api_base.rstrip('/')}/assets/{entry.asset_id}/data/{submission_segment}/enketo/edit/"
    params: Dict[str, Any] = {}
    if return_url is not None:
        params['return_url'] = return_url
    try:
        response = session.get(endpoint, params=params, timeout=timeout, verify=verify_param)
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - depends on network
        raise EnketoLinkError(f'Failed to request Enketo edit link: {exc}')
    payload = response.json()
    url = payload.get('url')
    if not url:
        raise EnketoLinkError('Enketo edit URL was not returned by the Kobo API.')
    return url


def infer_columns(records: Iterable[Dict[str, Any]]) -> List[str]:
    """Derive an ordered set of columns from a sequence of records."""

    priority = ['_id', '_uuid', '_submission_time', '_submitted_by', '_last_edit', '_version']
    seen: List[str] = []
    for record in records:
        for key in record.keys():
            if key not in seen:
                seen.append(key)
    ordered: List[str] = []
    for key in priority:
        if key in seen:
            ordered.append(key)
            seen.remove(key)
    ordered.extend(seen)
    return ordered


def _fetch_remote_payload(
    token: str,
    asset_id: str,
    query: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Retrieve asset metadata and submissions from the Kobo API."""

    session = requests.Session()
    session.headers.update({'Authorization': f'Token {token}', 'Accept': 'application/json'})
    timeout = getattr(settings, 'KOBO_HTTP_TIMEOUT', 60)
    verify_param = getattr(settings, 'KOBO_TLS_CERT', None) or getattr(settings, 'KOBO_VERIFY_TLS', True)
    api_base = getattr(settings, 'KOBO_API_BASE', None)
    if not api_base:
        raise DatabaseCacheError('KOBO_API_BASE setting is not configured.')
    asset_url = f"{api_base.rstrip('/')}/assets/{asset_id}/"
    data_url = f"{api_base.rstrip('/')}/assets/{asset_id}/data/"
    try:
        meta_resp = session.get(asset_url, timeout=timeout, verify=verify_param)
        meta_resp.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network dependent
        raise DatabaseCacheError(f'Failed to download asset metadata: {exc}')
    metadata = meta_resp.json()
    records: List[Dict[str, Any]] = []
    next_url: Optional[str] = data_url
    params: Optional[Dict[str, Any]] = {'format': 'json'}
    if query:
        params['query'] = json.dumps(query)
    while next_url:
        try:
            resp = session.get(next_url, params=params, timeout=timeout, verify=verify_param)
            resp.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network dependent
            raise DatabaseCacheError(f'Failed to download submissions: {exc}')
        payload = resp.json()
        results = payload.get('results') or payload.get('data') or []
        if not isinstance(results, list):
            raise DatabaseCacheError('Unexpected data format received from Kobo API.')
        records.extend(results)
        next_url = payload.get('next')
        params = None  # Only include params on the first request
    return metadata, records


def _merge_records(
    existing: Iterable[Dict[str, Any]],
    incoming: Iterable[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Merge new submissions into the cached record set."""

    def record_key(record: Dict[str, Any]) -> Optional[str]:
        for key in ('_id', '_uuid', 'uuid'):
            value = record.get(key)
            if value is not None:
                return str(value)
        return None

    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    added = 0
    updated = 0
    # Seed with existing records preserving their order
    for record in existing:
        key = record_key(record)
        if key is None:
            key = f"_idx_{len(order)}"
        if key not in merged:
            merged[key] = record
            order.append(key)
    # Merge incoming submissions
    for record in incoming:
        key = record_key(record)
        if key is None:
            key = f"_auto_{len(order)}"
        if key in merged:
            if merged[key] != record:
                merged[key] = record
                updated += 1
        else:
            merged[key] = record
            order.append(key)
            added += 1
    # Sort by submission time or fallback identifier for deterministic output
    def sort_key(key: str) -> Tuple[Any, Any]:
        record = merged[key]
        submission_time = record.get('_submission_time') or record.get('end') or record.get('start')
        return (submission_time or '', record.get('_id') or key)

    ordered_keys = sorted(order, key=sort_key)
    merged_records = [merged[k] for k in ordered_keys]
    return merged_records, added, updated


def _prepare_submission_query(refresh_ids: Iterable[str]) -> List[Any]:
    """Normalise submission identifiers for use in Kobo API queries."""

    query_ids: List[Any] = []
    for value in refresh_ids:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        try:
            query_ids.append(int(text))
        except (TypeError, ValueError):
            query_ids.append(text)
    return query_ids


__all__ = [
    'CacheSyncResult',
    'DatabaseCacheError',
    'EnketoLinkError',
    'EntrySnapshot',
    'delete_entry_cache',
    'get_entry_cache_path',
    'infer_columns',
    'load_entry_snapshot',
    'request_enketo_edit_url',
    'refresh_entry_cache',
]
