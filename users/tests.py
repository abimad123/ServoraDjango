from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from users.models import UserProfile, ProviderSubscription
from decimal import Decimal


class AuthenticationAndRoleTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Create a sample provider user
        self.provider_user = User.objects.create_user(
            username='plumber_bob',
            email='bob@example.com',
            password='Password123!',
            first_name='Bob',
            last_name='Builder'
        )
        self.provider_user.profile.role = 'provider'
        self.provider_user.profile.city = 'Kannur'
        self.provider_user.profile.save()

        # Create a sample customer user
        self.customer_user = User.objects.create_user(
            username='alice_client',
            email='alice@example.com',
            password='Password123!',
            first_name='Alice',
            last_name='Wonder'
        )
        self.customer_user.profile.role = 'customer'
        self.customer_user.profile.save()

    def test_customer_registration(self):
        """Test customer registration via POST."""
        response = self.client.post(reverse('register'), {
            'username': 'new_customer',
            'first_name': 'Test',
            'last_name': 'Customer',
            'email': 'test_cust@example.com',
            'role': 'customer',
            'phone': '9876543210',
            'city': 'Kannur',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        # Should redirect to home on successful customer registration
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))
        new_user = User.objects.get(username='new_customer')
        self.assertEqual(new_user.profile.role, 'customer')

    def test_provider_registration(self):
        """Test provider registration via POST."""
        response = self.client.post(reverse('register'), {
            'username': 'new_electrician',
            'first_name': 'David',
            'last_name': 'Spark',
            'email': 'david@example.com',
            'role': 'provider',
            'phone': '9123456780',
            'city': 'Kannur',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 302)
        # Should redirect to provider dashboard
        self.assertEqual(response.url, reverse('provider_dashboard'))
        new_user = User.objects.get(username='new_electrician')
        self.assertEqual(new_user.profile.role, 'provider')
        self.assertTrue(new_user.profile.is_provider)

    def test_successful_provider_login(self):
        """Test that logging in as a provider redirects to provider dashboard."""
        response = self.client.post(reverse('login'), {
            'username': 'plumber_bob',
            'password': 'Password123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('provider_dashboard'))

    def test_successful_customer_login(self):
        """Test that logging in as a customer redirects to home."""
        response = self.client.post(reverse('login'), {
            'username': 'alice_client',
            'password': 'Password123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))

    def test_invalid_login(self):
        """Test that invalid login credentials re-render login with error."""
        response = self.client.post(reverse('login'), {
            'username': 'alice_client',
            'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid username or password')

    def test_logout(self):
        """Test logout clears session and redirects to home."""
        self.client.login(username='alice_client', password='Password123!')
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))
