"""Tests for the telephone interviewer dashboard data endpoints."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    DatabaseEntry,
    Interview,
    Membership,
    Profile,
    Project,
    ReviewAction,
    ReviewRow,
    ReviewTask,
)


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
            survey_link='https://example.com/survey',
        )
        self.project_two = Project.objects.create(
            name='Beta Study',
            status=True,
            types=['Tracking'],
            start_date=today - timedelta(days=20),
            deadline=today + timedelta(days=3),
            sample_size=60,
            survey_link='https://example.com/survey',
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


class HomeDashboardVisibilityTests(TestCase):
    """Ensure the home view only renders the dashboard when data exists."""

    def setUp(self) -> None:
        today = timezone.now().date()
        self.project = Project.objects.create(
            name='Gamma Study',
            status=True,
            types=['Tracking'],
            start_date=today - timedelta(days=7),
            deadline=today + timedelta(days=14),
            sample_size=50,
            survey_link='https://example.com/survey',
        )

    def _create_user(self, username: str = 'user@example.com') -> User:
        user = User.objects.create_user(username, password='secret123')
        Profile.objects.create(user=user, organization=False, phone='01234567890')
        return user

    def _record_call(self, user: User) -> None:
        Interview.objects.create(project=self.project, user=user, status=True, code=200)

    def _record_review(self, user: User) -> None:
        entry = DatabaseEntry.objects.create(project=self.project, db_name='Main')
        task = ReviewTask.objects.create(entry=entry, reviewer=user, task_size=1, reviewed_count=0)
        row = ReviewRow.objects.create(task=task, submission_id='s1', data={})
        ReviewAction.objects.create(row=row, action=ReviewAction.Action.STARTED, metadata={})

    def test_dashboard_shown_when_user_has_call_and_review_activity(self) -> None:
        user = self._create_user('caller-reviewer@example.com')
        self._record_call(user)
        self._record_review(user)
        self.client.force_login(user)

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['show_dashboard'])
        self.assertContains(response, 'data-dashboard-root')

    def test_dashboard_hidden_when_only_call_activity(self) -> None:
        user = self._create_user('caller-only@example.com')
        self._record_call(user)
        self.client.force_login(user)

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['show_dashboard'])
        self.assertNotContains(response, 'data-dashboard-root')

    def test_dashboard_hidden_when_only_review_activity(self) -> None:
        user = self._create_user('reviewer-only@example.com')
        self._record_review(user)
        self.client.force_login(user)

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['show_dashboard'])
        self.assertNotContains(response, 'data-dashboard-root')
