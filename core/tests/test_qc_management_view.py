"""Tests for the QC management view defaults."""

import json
import shutil
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import DatabaseEntry, Membership, Profile, Project
from core.services.database_cache import get_entry_cache_path


class QCManagementViewTests(TestCase):
    """Ensure the QC management view loads default structures safely."""

    def setUp(self) -> None:
        self.user = User.objects.create_user('qc@example.com', password='secret123')
        Profile.objects.create(user=self.user, organization=True, phone='01234567890')
        self.client.force_login(self.user)

        self.project = Project.objects.create(
            name='QC Project',
            status=True,
            types=['Tracking'],
            start_date=timezone.now().date() - timedelta(days=1),
            deadline=timezone.now().date() + timedelta(days=10),
            sample_size=10,
            sample_source=Project.SampleSource.UPLOAD,
        )
        Membership.objects.create(user=self.user, project=self.project, is_owner=True, qc_management=True)

        self.entry = DatabaseEntry.objects.create(
            project=self.project,
            db_name='QC Source',
            token='token',
            asset_id='asset-123',
            status=True,
        )

    def _write_snapshot(self, records: list[dict[str, str]]) -> Path:
        """Persist a lightweight snapshot for ``self.entry``."""

        payload = {
            'metadata': {},
            'records': records,
            'synced_at': None,
            'entry': {},
            'stats': {'total': len(records), 'added': len(records), 'updated': 0},
        }
        path = get_entry_cache_path(self.entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding='utf-8')
        return path

    def tearDown(self) -> None:
        path = get_entry_cache_path(self.entry)
        if path.exists():
            path.unlink()
        # Clean up the parent cache folder if it is empty to avoid test bleed.
        if path.parent.exists():
            shutil.rmtree(path.parent, ignore_errors=True)

    def test_default_measure_used_when_session_empty(self) -> None:
        """The view should build a default QC measure when none is stored."""

        self._write_snapshot([{'_id': 1, 'city': 'Tehran'}])

        response = self.client.get(
            reverse('qc_management'),
            {'project': self.project.pk, 'entry': self.entry.pk},
        )

        self.assertEqual(response.status_code, 200)
        tree = response.context['qc_measure_tree']
        self.assertTrue(tree)
        self.assertEqual(tree[0]['label'], '_id')
        self.assertEqual(tree[0]['field'], '_id')

