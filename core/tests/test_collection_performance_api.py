import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Interview, Membership, Profile, Project


class CollectionPerformanceAPITest(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username='owner', password='pass', first_name='Owner'
        )
        Profile.objects.create(user=self.owner, organization=True, phone='09120000000')
        self.project = Project.objects.create(
            name='Project A',
            status=True,
            types=['survey'],
            start_date=timezone.now().date(),
            deadline=timezone.now().date() + timedelta(days=30),
            sample_size=100,
        )
        Membership.objects.create(
            user=self.owner,
            project=self.project,
            is_owner=True,
            collection_performance=True,
        )
        self.interviewer = User.objects.create_user(
            username='interviewer', password='pass', first_name='Field'
        )
        Membership.objects.create(
            user=self.interviewer,
            project=self.project,
            collection_performance=True,
        )
        now = timezone.now()
        Interview.objects.create(
            project=self.project,
            user=self.interviewer,
            status=True,
            code=1,
            city='Tehran',
            age=30,
            start_form=now - timedelta(minutes=5),
            end_form=now - timedelta(minutes=1),
        )
        Interview.objects.create(
            project=self.project,
            user=self.interviewer,
            status=False,
            code=2,
            city='Tehran',
            age=28,
            start_form=now - timedelta(minutes=4),
            end_form=now - timedelta(minutes=2),
        )

    def test_payload_contains_all_rich_sections(self) -> None:
        self.client.force_login(self.owner)
        response = self.client.get(reverse('collection_performance_data'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        expected_sections = ['bar', 'donut', 'daily', 'top', 'codes', 'hourly', 'meta']
        for section in expected_sections:
            self.assertIn(section, payload)
        self.assertEqual(
            set(payload['bar'].keys()),
            {'labels', 'totals', 'successes', 'projects'},
        )
        self.assertEqual(set(payload['donut'].keys()), {'labels', 'values', 'segments'})
        self.assertEqual(set(payload['codes'].keys()), {'labels', 'values', 'items'})
        self.assertEqual(set(payload['hourly'].keys()), {'labels', 'totals', 'successes'})
        meta = payload['meta']
        for key in [
            'total_interviews',
            'successful_interviews',
            'success_rate',
            'status_breakdown',
            'code_breakdown',
            'average_duration_minutes',
            'average_duration_label',
            'duration_sample_size',
            'peak_hour',
            'peak_hour_label',
        ]:
            self.assertIn(key, meta)
        self.assertGreaterEqual(meta['total_interviews'], 2)
        self.assertIn('rows', payload['top'])
        self.assertTrue(isinstance(payload['top']['rows'], list))

    def test_top_rows_include_success_metrics(self) -> None:
        self.client.force_login(self.owner)
        response = self.client.get(reverse('collection_performance_data'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload.get('top', {}).get('rows', [])
        self.assertGreaterEqual(len(rows), 1)
        sample = rows[0]
        for key in ['project', 'user', 'total_calls', 'successful_calls', 'success_rate']:
            self.assertIn(key, sample)
        self.assertGreaterEqual(sample['total_calls'], sample['successful_calls'])

    def test_collection_performance_page_includes_export_endpoint(self) -> None:
        self.client.force_login(self.owner)
        response = self.client.get(reverse('collection_performance'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8')
        self.assertIn(reverse('table_export'), body)

    def test_table_export_without_context_returns_error(self) -> None:
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('table_export'), data=json.dumps({}), content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
