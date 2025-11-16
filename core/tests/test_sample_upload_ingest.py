"""Regression tests for the sample upload ingestion workflow."""

from __future__ import annotations

from io import BytesIO
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from openpyxl import Workbook

from core.forms import ProjectForm
from core.models import Project, UploadedSampleEntry
from core.services.sample_uploads import ingest_project_sample_upload


class SampleUploadIngestTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._media_root = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self._media_root, ignore_errors=True))

    def _build_upload(self) -> SimpleUploadedFile:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(['full_name', 'phone', 'city', 'age', 'gender'])
        worksheet.append(['Test User', '09120000000', 'Tehran', 30, 'female'])
        payload = BytesIO()
        workbook.save(payload)
        payload.seek(0)
        return SimpleUploadedFile(
            'sample.xlsx',
            payload.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_ingest_processes_uploaded_rows_without_value_error(self) -> None:
        today = timezone.now().date()
        upload = self._build_upload()
        form_data = {
            'name': 'Call campaign',
            'status': 'on',
            'types': 'survey',
            'start_date': today.isoformat(),
            'deadline': today.isoformat(),
            'sample_size': '10',
            'sample_source': Project.SampleSource.UPLOAD,
            'call_result_source': Project.CallResultSource.DEFAULT,
        }

        with self.settings(MEDIA_ROOT=self._media_root):
            form = ProjectForm(data=form_data, files={'sample_upload': upload})
            self.assertTrue(form.is_valid(), form.errors.as_json())
            project = form.save()
            stats = ingest_project_sample_upload(project)

        self.assertEqual(stats.total_rows, 1)
        self.assertEqual(stats.accepted_rows, 1)
        self.assertEqual(
            UploadedSampleEntry.objects.filter(project=project).count(),
            1,
        )
