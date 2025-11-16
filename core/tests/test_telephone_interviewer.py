"""Regression tests for the telephone interviewer view."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Membership, Profile, Project


class TelephoneInterviewerViewTests(TestCase):
    """Ensure the telephone interviewer page renders with localisation context."""

    def setUp(self) -> None:
        self.user = User.objects.create_user('caller@example.com', password='secret123')
        Profile.objects.create(user=self.user, organization=False, phone='01234567890')
        self.project = Project.objects.create(
            name='Brand Tracker',
            status=True,
            types=['Tracking'],
            start_date=timezone.now().date() - timedelta(days=1),
            deadline=timezone.now().date() + timedelta(days=7),
            sample_size=50,
        )
        Membership.objects.create(
            user=self.user,
            project=self.project,
            is_owner=True,
            telephone_interviewer=True,
        )
        self.client.force_login(self.user)

    def test_get_telephone_page_returns_ok_and_includes_lang(self) -> None:
        """A permitted GET request should render successfully and expose lang."""

        session = self.client.session
        session['lang'] = 'fa'
        session.save()

        response = self.client.get(reverse('telephone_interviewer'), {'project': self.project.pk})

        self.assertEqual(response.status_code, 200)
        self.assertIn('lang', response.context)
        self.assertEqual(response.context['lang'], 'fa')
