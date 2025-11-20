"""Tests for the telephone interviewer dashboard data endpoints."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Interview, Membership, Profile, Project


class HomeDashboardDataTests(TestCase):
    """Validate aggregated call totals for the home dashboard."""

    def setUp(self) -> None:
        self.user = User.objects.create_user('caller@example.com', password='secret123')
        Profile.objects.create(user=self.user, organization=False, phone='01234567890')
        today = timezone.now().date()
        self.project_one = Project.objects.create(
            name='Alpha Study',
            status=True,
            types=['Tracking'],
            start_date=today - timedelta(days=10),
            deadline=today + timedelta(days=5),
            sample_size=100,
        )
        self.project_two = Project.objects.create(
            name='Beta Study',
            status=True,
            types=['Tracking'],
            start_date=today - timedelta(days=20),
            deadline=today + timedelta(days=3),
            sample_size=60,
        )
        Membership.objects.create(
            user=self.user,
            project=self.project_one,
            is_owner=True,
            telephone_interviewer=True,
        )
        Membership.objects.create(
            user=self.user,
            project=self.project_two,
            telephone_interviewer=True,
        )
        # Alpha: 3 success, 1 unsuccessful
        Interview.objects.create(project=self.project_one, user=self.user, status=True, code=200)
        Interview.objects.create(project=self.project_one, user=self.user, status=True, code=200)
        Interview.objects.create(project=self.project_one, user=self.user, status=True, code=200)
        Interview.objects.create(project=self.project_one, user=self.user, status=False, code=500)
        # Beta: 1 success, 2 unsuccessful
        Interview.objects.create(project=self.project_two, user=self.user, status=True, code=200)
        Interview.objects.create(project=self.project_two, user=self.user, status=False, code=400)
        Interview.objects.create(project=self.project_two, user=self.user, status=False, code=400)
        self.client.force_login(self.user)

    def test_dashboard_data_returns_totals_and_ranking(self) -> None:
        """Aggregated payload should include totals and a top project summary."""

        response = self.client.get(reverse('interviewer_dashboard_data'))
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['summary']['total_calls'], 7)
        self.assertEqual(data['summary']['success_calls'], 4)
        self.assertEqual(data['summary']['failed_calls'], 3)
        self.assertAlmostEqual(data['summary']['success_rate'], 57.1, places=1)
        self.assertEqual(data['projects'][0]['name'], 'Alpha Study')
        self.assertEqual(data['projects'][0]['rank'], 1)
        self.assertIn('Alpha Study', data['top_summary'])

    def test_dashboard_filter_limits_to_project(self) -> None:
        """Filtering by project should update totals for that project only."""

        response = self.client.get(reverse('interviewer_dashboard_data'), {'project': self.project_two.pk})
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['selected_project'], self.project_two.pk)
        self.assertEqual(data['summary']['total_calls'], 3)
        self.assertEqual(data['summary']['success_calls'], 1)
        self.assertEqual(data['summary']['failed_calls'], 2)
        self.assertAlmostEqual(data['summary']['success_rate'], 33.3, places=1)
        self.assertIn('project', data['top_summary'].lower())
