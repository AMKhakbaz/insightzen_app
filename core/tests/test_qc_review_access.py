"""Access tests for the QC review views."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    DatabaseEntry,
    Membership,
    Profile,
    Project,
    ReviewRow,
    ReviewTask,
)


class QCReviewAccessTests(TestCase):
    """Ensure QC review pages admit assigned reviewers without membership flags."""

    def setUp(self) -> None:
        self.project = Project.objects.create(
            name='QC Project',
            status=True,
            types=['Tracking'],
            start_date=timezone.now().date() - timedelta(days=1),
            deadline=timezone.now().date() + timedelta(days=10),
            sample_size=5,
            sample_source=Project.SampleSource.UPLOAD,
        )
        self.entry = DatabaseEntry.objects.create(
            project=self.project,
            db_name='QC Source',
            token='token',
            asset_id='asset-123',
            status=True,
        )

    def _create_user(self, email: str) -> User:
        user = User.objects.create_user(email, password='secret123')
        Profile.objects.create(user=user, organization=True, phone='0123456789')
        return user

    def test_assigned_reviewer_without_membership_can_access(self) -> None:
        """A reviewer with assignments but no review_data membership may access QC review."""

        reviewer = self._create_user('reviewer@example.com')
        # Explicitly create a membership without review_data permissions to mirror the reported issue.
        Membership.objects.create(user=reviewer, project=self.project, is_owner=False, review_data=False)
        task = ReviewTask.objects.create(
            entry=self.entry,
            reviewer=reviewer,
            task_size=1,
            measure_definition=[{'id': 'q1', 'label': 'Q1', 'field': 'q1', 'children': []}],
            columns=['q1'],
        )
        ReviewRow.objects.create(task=task, submission_id='sub-1', data={'q1': True})

        self.client.force_login(reviewer)

        list_response = self.client.get(reverse('qc_review'))
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.context['tasks']), 1)

        detail_response = self.client.get(reverse('qc_review_detail', args=[task.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.context['task'].pk, task.pk)

    def test_unassigned_user_without_permissions_is_redirected(self) -> None:
        """Users without review_data rights or assignments are redirected away."""

        unauthorized_user = self._create_user('unauthorized@example.com')
        # A task exists, but is assigned to someone else.
        other_reviewer = self._create_user('other@example.com')
        other_task = ReviewTask.objects.create(entry=self.entry, reviewer=other_reviewer, task_size=1)

        self.client.force_login(unauthorized_user)

        list_response = self.client.get(reverse('qc_review'))
        self.assertEqual(list_response.status_code, 302)
        self.assertEqual(list_response.url, reverse('home'))

        detail_response = self.client.get(reverse('qc_review_detail', args=[other_task.pk]))
        self.assertEqual(detail_response.status_code, 302)
        self.assertEqual(detail_response.url, reverse('home'))
