"""Tests for project type rendering on the project list view."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Membership, Profile, Project


class ProjectListTypesTests(TestCase):
    """Ensure project type arrays are rendered clearly in the table."""

    def setUp(self) -> None:
        self.user = User.objects.create_user('org@example.com', password='secret123')
        Profile.objects.create(user=self.user, organization=True, phone='01234567890')
        self.client.force_login(self.user)

    def _create_project(self, name: str, types: list[str]) -> Project:
        project = Project.objects.create(
            name=name,
            status=True,
            types=types,
            start_date=timezone.now().date(),
            deadline=timezone.now().date() + timedelta(days=30),
            sample_size=100,
        )
        Membership.objects.create(user=self.user, project=project, is_owner=True)
        return project

    def test_types_and_placeholder_render_in_project_table(self) -> None:
        """The project table should show joined types or a placeholder."""

        self._create_project('Research Alpha', ['Quantitative', 'Tracking'])
        self._create_project('Research Beta', [])

        response = self.client.get(reverse('project_list'))

        self.assertContains(response, 'Quantitative, Tracking')
        self.assertContains(response, 'Not specified')
