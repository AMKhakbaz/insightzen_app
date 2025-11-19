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
from core.models import Mobile, Person, Project, UploadedSampleEntry
from core.services.sample_uploads import (
    append_project_respondent_bank,
    append_project_sample_upload,
    ingest_project_sample_upload,
)


class SampleUploadIngestTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._media_root = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self._media_root, ignore_errors=True))

    def _build_upload(self, rows=None) -> SimpleUploadedFile:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(['full_name', 'phone', 'city', 'age', 'gender'])
        rows = rows or [['Test User', '09120000000', 'Tehran', 30, 'female']]
        for row in rows:
            worksheet.append(row)
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

    def test_append_project_sample_upload_adds_only_new_numbers(self) -> None:
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
            ingest_project_sample_upload(project)
            append_file = self._build_upload(
                [
                    ['New Person', '09120000001', 'Mashhad', 28, 'male'],
                    ['Duplicate', '09120000000', 'Tehran', 30, 'female'],
                ]
            )
            result = append_project_sample_upload(project, uploaded_file=append_file)
        self.assertEqual(result.appended_rows, 1)
        self.assertEqual(result.duplicate_rows, 1)
        phones = set(
            UploadedSampleEntry.objects.filter(project=project).values_list('phone', flat=True)
        )
        self.assertEqual(phones, {'09120000000', '09120000001'})

    def test_append_project_respondent_bank_creates_person_and_mobile(self) -> None:
        project = Project.objects.create(
            name='Bank project',
            status=True,
            types=['survey'],
            start_date=timezone.now().date(),
            deadline=timezone.now().date(),
            sample_size=5,
            sample_source=Project.SampleSource.DATABASE,
            call_result_source=Project.CallResultSource.DEFAULT,
        )
        append_file = self._build_upload(
            [
                ['Alpha', '09123330000', 'Qom', 35, 'female'],
                ['Beta', '09123330000', 'Qom', 35, 'female'],
                ['Gamma', '09124440000', 'Karaj', 40, 'male'],
            ]
        )
        result = append_project_respondent_bank(project, uploaded_file=append_file)
        self.assertEqual(result.appended_rows, 2)
        self.assertEqual(result.duplicate_rows, 1)
        self.assertEqual(Person.objects.count(), 2)
        self.assertEqual(Mobile.objects.count(), 2)
