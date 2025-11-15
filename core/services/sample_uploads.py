"""Helpers for ingesting Excel-based respondent samples per project."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from django.db import transaction
from django.utils import timezone

try:  # pragma: no cover - optional dependency guarded at runtime
    from openpyxl import load_workbook  # type: ignore
except Exception:  # pragma: no cover - openpyxl always available in prod, but guard for tests
    load_workbook = None

from ..models import Project, UploadedSampleEntry
from .gender_utils import normalize_gender_value

SAMPLE_REQUIRED_HEADERS = ['full_name', 'phone', 'city', 'age', 'gender']
HEADER_ALIASES = {
    'name': 'full_name',
    'full name': 'full_name',
    'fullname': 'full_name',
    'mobile': 'phone',
    'mobile_number': 'phone',
    'city_name': 'city',
    'province': 'city',
    'age_years': 'age',
    'sex': 'gender',
}


class SampleUploadError(Exception):
    """Raised when an uploaded workbook cannot be processed."""


@dataclass
class SampleUploadStats:
    total_rows: int
    accepted_rows: int

    @property
    def skipped_rows(self) -> int:
        return max(self.total_rows - self.accepted_rows, 0)


def _normalise_header(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ''


def _normalise_phone(value: Any) -> str:
    text = str(value).strip() if value is not None else ''
    # Remove trailing .0 that Excel might append to numeric strings
    if text.endswith('.0') and text.replace('.', '', 1).isdigit():
        text = text[:-2]
    return text


def _coerce_int(value: Any) -> int | None:
    if value in (None, ''):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _coerce_text(value: Any) -> str:
    return str(value).strip() if value not in (None, '') else ''


@transaction.atomic
def ingest_project_sample_upload(project: Project) -> SampleUploadStats:
    """Parse the project's uploaded workbook and materialise sample entries."""

    if load_workbook is None:
        raise SampleUploadError('Excel support is not available on this server.')
    upload = project.sample_upload
    if not upload:
        raise SampleUploadError('No workbook is attached to this project.')

    upload.open('rb')
    try:
        workbook = load_workbook(upload, read_only=True, data_only=True)
    except Exception as exc:  # pragma: no cover - delegated to UI message
        raise SampleUploadError('The uploaded workbook could not be read.') from exc
    finally:
        upload.close()

    worksheet = workbook.active
    header_row = next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_row:
        raise SampleUploadError('The uploaded workbook does not contain any rows.')

    header_map: Dict[str, int] = {}
    for idx, raw_header in enumerate(header_row):
        header_name = HEADER_ALIASES.get(_normalise_header(raw_header), _normalise_header(raw_header))
        if header_name:
            header_map[header_name] = idx

    missing = [col for col in SAMPLE_REQUIRED_HEADERS if col not in header_map]
    if missing:
        raise SampleUploadError(
            'Missing required columns: ' + ', '.join(missing)
        )

    seen_numbers: set[str] = set()
    entries: List[UploadedSampleEntry] = []
    total_rows = 0
    for excel_row_index, row in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
        total_rows += 1
        phone = _normalise_phone(row[header_map['phone']] if header_map.get('phone') is not None else None)
        if not phone or phone in seen_numbers:
            continue
        seen_numbers.add(phone)
        entry = UploadedSampleEntry(
            project=project,
            phone=phone,
            full_name=_coerce_text(row[header_map['full_name']]) if header_map.get('full_name') is not None else '',
            city=_coerce_text(row[header_map['city']]) if header_map.get('city') is not None else '',
            age=_coerce_int(row[header_map['age']]) if header_map.get('age') is not None else None,
            gender=normalize_gender_value(
                row[header_map['gender']] if header_map.get('gender') is not None else None
            ) or '',
            metadata={'source': 'upload'},
            created_from_row=excel_row_index,
        )
        entries.append(entry)

    if not entries:
        raise SampleUploadError('No valid rows were found in the uploaded workbook.')

    UploadedSampleEntry.objects.filter(project=project).delete()
    UploadedSampleEntry.objects.bulk_create(entries, batch_size=500)

    stats = SampleUploadStats(total_rows=total_rows, accepted_rows=len(entries))
    project.sample_upload_refreshed_at = timezone.now()
    project.sample_upload_metadata = {
        'total_rows': stats.total_rows,
        'accepted_rows': stats.accepted_rows,
        'skipped_rows': stats.skipped_rows,
        'required_headers': SAMPLE_REQUIRED_HEADERS,
    }
    project.save(update_fields=['sample_upload_refreshed_at', 'sample_upload_metadata'])
    return stats
