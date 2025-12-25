import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import DatabaseEntry, Membership, Project, ReviewRow, ReviewTask


class QCPerformanceDashboardTest(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(username='owner', password='pass', first_name='Owner')
        self.reviewer = User.objects.create_user(username='reviewer', password='pass', first_name='Reviewer')
        self.project = Project.objects.create(
            name='QC Project',
            status=True,
            types=['survey'],
            start_date=timezone.now().date(),
            deadline=timezone.now().date() + timedelta(days=10),
            sample_size=50,
        )
        Membership.objects.create(
            user=self.owner,
            project=self.project,
            is_owner=True,
            qc_performance=True,
            review_data=True,
        )
        Membership.objects.create(
            user=self.reviewer,
            project=self.project,
            qc_performance=True,
            review_data=True,
        )
        entry = DatabaseEntry.objects.create(project=self.project, db_name='Primary')
        self.task = ReviewTask.objects.create(entry=entry, reviewer=self.reviewer, task_size=2)
        now = timezone.now()
        ReviewRow.objects.create(
            task=self.task,
            submission_id='row-1',
            created_at=now - timedelta(hours=1),
            started_at=now - timedelta(minutes=50),
            completed_at=now - timedelta(minutes=10),
            review_started_at=now - timedelta(minutes=50),
            review_submitted_at=now - timedelta(minutes=10),
        )
        ReviewRow.objects.create(
            task=self.task,
            submission_id='row-2',
            created_at=now - timedelta(hours=1),
            started_at=now - timedelta(minutes=45),
            review_started_at=now - timedelta(minutes=45),
        )

    def test_dashboard_context_contains_rollups(self) -> None:
        self.client.force_login(self.owner)
        response = self.client.get(reverse('qc_performance_dashboard'))
        self.assertEqual(response.status_code, 200)
        context = response.context
        summary = context['summary']
        self.assertEqual(summary['total_tasks'], 1)
        self.assertEqual(summary['total_rows'], 2)
        self.assertEqual(summary['completed_rows'], 1)
        self.assertIn('reviewer_rows', context)
        self.assertIn('project_rows', context)
        self.assertEqual(len(context['reviewer_rows']), 1)
        self.assertEqual(len(context['project_rows']), 1)

    def test_table_export_uses_qc_contexts(self) -> None:
        self.client.force_login(self.owner)
        payload = {
            'context': 'qc_performance_reviewers',
            'format': 'csv',
            'params': {'projects': str(self.project.id)},
        }
        response = self.client.post(
            reverse('table_export'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

    def test_dashboard_accepts_multiple_project_filters(self) -> None:
        extra_project = Project.objects.create(
            name='QC Project 2',
            status=True,
            types=['survey'],
            start_date=timezone.now().date(),
            deadline=timezone.now().date() + timedelta(days=5),
            sample_size=30,
        )
        Membership.objects.create(
            user=self.owner,
            project=extra_project,
            is_owner=True,
            qc_performance=True,
            review_data=True,
        )
        entry = DatabaseEntry.objects.create(project=extra_project, db_name='Secondary')
        ReviewTask.objects.create(entry=entry, reviewer=self.reviewer, task_size=1)

        self.client.force_login(self.owner)

        response = self.client.get(reverse('qc_performance_dashboard'), {'projects': [extra_project.id]})
        self.assertEqual(response.status_code, 200)
        summary = response.context['summary']
        self.assertEqual(summary['total_tasks'], 1)
        self.assertEqual(response.context['selected_projects'], [extra_project.id])

        response = self.client.get(
            reverse('qc_performance_dashboard'),
            {'projects': [self.project.id, extra_project.id]},
        )
        self.assertEqual(response.context['summary']['total_tasks'], 2)
