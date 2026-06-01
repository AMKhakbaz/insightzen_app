"""Tests for login authentication identifiers."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class LoginAuthenticationTests(TestCase):
    """Validate that the login page accepts both emails and usernames."""

    def test_superuser_can_login_with_email_when_username_differs(self) -> None:
        """A createsuperuser account should authenticate using its email address."""

        user = User.objects.create_superuser(
            username='superadmin',
            email='superadmin@gmail.com',
            password='secure-pass-123',
        )

        response = self.client.post(
            reverse('login'),
            {'email': 'superadmin@gmail.com', 'password': 'secure-pass-123'},
        )

        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_login_still_accepts_username(self) -> None:
        """Existing username-based authentication should keep working."""

        user = User.objects.create_user(
            username='regular-user',
            email='regular@example.com',
            password='secure-pass-123',
        )

        response = self.client.post(
            reverse('login'),
            {'email': 'regular-user', 'password': 'secure-pass-123'},
        )

        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
