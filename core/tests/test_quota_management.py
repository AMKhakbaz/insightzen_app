"""Regression tests for the quota management view."""

import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Membership, Profile, Project, Quota


class QuotaManagementViewTests(TestCase):
    """Ensure quota management handles localisation context safely."""

    def setUp(self) -> None:
        self.user = User.objects.create_user('org@example.com', password='secret123')
        Profile.objects.create(user=self.user, organization=True, phone='01234567890')
        self.client.force_login(self.user)
        self.project = Project.objects.create(
            name='Consumer Insights',
            status=True,
            types=['Tracking'],
            start_date=timezone.now().date() - timedelta(days=1),
            deadline=timezone.now().date() + timedelta(days=10),
            sample_size=100,
            sample_source=Project.SampleSource.UPLOAD,
        )
        Membership.objects.create(
            user=self.user,
            project=self.project,
            is_owner=True,
            quota_management=True,
        )

    def test_get_quota_page_with_existing_quota_renders(self) -> None:
        """A GET request with an existing quota should include lang context."""

        Quota.objects.create(
            project=self.project,
            city='Tehran',
            age_start=18,
            age_end=35,
            gender='male',
            target_count=10,
        )
        session = self.client.session
        session['lang'] = 'fa'
        session.save()

        response = self.client.get(reverse('quota_management'), {'project': self.project.pk})

        self.assertEqual(response.status_code, 200)
        self.assertIn('lang', response.context)
        self.assertEqual(response.context['lang'], 'fa')

    def test_post_quota_configuration_returns_ok(self) -> None:
        """Posting valid quota payload should succeed without NameError."""

        payload = {
            'project': str(self.project.pk),
            'enable_city': 'on',
            'enable_age': 'on',
            'enable_gender': 'on',
            'city_data': json.dumps([{'city': 'Tehran', 'quota': 100}]),
            'age_data': json.dumps([{'start': 18, 'end': 65, 'quota': 100}]),
            'gender_data': json.dumps([
                {'value': 'male', 'quota': 50},
                {'value': 'female', 'quota': 50},
            ]),
        }

        response = self.client.post(reverse('quota_management'), payload, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertGreater(Quota.objects.filter(project=self.project).count(), 0)
