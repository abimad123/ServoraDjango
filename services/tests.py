from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from users.models import UserProfile, ProviderSubscription
from services.models import (
    Category, Service, Booking, Review, FeaturedListing, RevenueTransaction, 
    Notification, PaymentTransaction, ProviderSettlement, BookingMaterial
)
from services.payment_service import PaymentService, TestGatewayAdapter
from datetime import date, time, timedelta
from decimal import Decimal


class ServiceMarketplaceTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create provider 1
        self.provider_user1 = User.objects.create_user(
            username='plumber_john',
            password='password123',
            first_name='John',
            last_name='Mathew'
        )
        self.profile1 = self.provider_user1.profile
        self.profile1.role = 'provider'
        self.profile1.city = 'Kannur'
        self.profile1.is_verified = True
        self.profile1.bio = 'Expert master plumber with 14 years experience.'
        self.profile1.save()

        # Create provider 2
        self.provider_user2 = User.objects.create_user(
            username='electrician_rahul',
            password='password123',
            first_name='Rahul',
            last_name='Kumar'
        )
        self.profile2 = self.provider_user2.profile
        self.profile2.role = 'provider'
        self.profile2.city = 'Kochi'
        self.profile2.is_verified = True
        self.profile2.save()

        # Create customer
        self.customer = User.objects.create_user(
            username='customer_arun',
            password='password123',
            first_name='Arun',
            last_name='Menon'
        )

        # Create categories
        self.cat_plumbing = Category.objects.create(
            name='Plumbing',
            icon_name='wrench',
            description='Pipe repairs and plumbing installations.'
        )
        self.cat_electrical = Category.objects.create(
            name='Electrical',
            icon_name='zap',
            description='Wiring diagnostics and safety switches.'
        )

        # Create services
        self.svc_plumbing = Service.objects.create(
            provider=self.profile1,
            category=self.cat_plumbing,
            title='Bathroom Leak Diagnosis & Pipe Repair',
            description='Emergency leak detection, tap replacement, and pipe sealing.',
            price=Decimal('1500.00'),
            duration_estimate='1-2 hours',
            location='Kannur',
            is_featured=True
        )

        self.svc_electrical = Service.objects.create(
            provider=self.profile2,
            category=self.cat_electrical,
            title='Home Wiring Inspection & MCB Setup',
            description='Short circuit troubleshooting and modern breaker fitting.',
            price=Decimal('1200.00'),
            duration_estimate='2 hours',
            location='Kochi',
            is_featured=False
        )

        # Create review
        Review.objects.create(
            service=self.svc_plumbing,
            customer=self.customer,
            rating=5,
            comment='John was quick, skilled, and clean. Resolved the issue within an hour.'
        )

    def test_homepage_renders(self):
        """Test customer homepage renders with status 200 and loads categories & services."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'services/home.html')
        self.assertContains(response, 'Bathroom Leak Diagnosis')
        self.assertContains(response, 'Plumbing')

    def test_services_list_loads(self):
        """Test /services/ catalog page loads and displays all active services."""
        response = self.client.get(reverse('service_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'services/service_list.html')
        self.assertContains(response, 'Bathroom Leak Diagnosis')
        self.assertContains(response, 'Home Wiring Inspection')

    def test_service_detail_by_id(self):
        """Test /services/<int:id>/ detail view displays full details, inclusions, and reviews."""
        response = self.client.get(reverse('service_detail', kwargs={'id': self.svc_plumbing.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'services/service_detail.html')
        self.assertContains(response, 'Bathroom Leak Diagnosis')
        self.assertContains(response, 'John Mathew')
        self.assertContains(response, '₹1500')
        self.assertContains(response, 'What\'s Included in This Service')
        self.assertContains(response, 'John was quick, skilled, and clean.')

    def test_service_detail_by_slug(self):
        """Test /service/<slug:slug>/ detail view displays correctly via slug converter."""
        response = self.client.get(reverse('service_slug_detail', kwargs={'slug': self.svc_plumbing.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bathroom Leak Diagnosis')

    def test_invalid_service_returns_404(self):
        """Test that requesting a non-existent service ID returns 404 status."""
        response = self.client.get(reverse('service_detail', kwargs={'id': 999999}))
        self.assertEqual(response.status_code, 404)

    def test_category_page_filters_services(self):
        """Test /category/<str:name>/ only lists services belonging to that category."""
        response = self.client.get(reverse('category_services', kwargs={'name': 'Plumbing'}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'services/category_services.html')
        self.assertContains(response, 'Bathroom Leak Diagnosis')
        self.assertNotContains(response, 'Home Wiring Inspection')

    def test_search_returns_matching_services(self):
        """Test searching returns matching services and filters out non-matching ones."""
        response = self.client.get(reverse('service_list'), {'search': 'wiring'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Home Wiring Inspection')
        self.assertNotContains(response, 'Bathroom Leak Diagnosis')

    def test_filter_by_price_and_location(self):
        """Test filtering services by max price and location."""
        response = self.client.get(reverse('service_list'), {'max_price': '1300', 'location': 'Kochi'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Home Wiring Inspection')
        self.assertNotContains(response, 'Bathroom Leak Diagnosis')

    def test_provider_profile_loads(self):
        """Test /provider/<int:id>/ customer-facing provider profile page."""
        response = self.client.get(reverse('provider_profile', kwargs={'id': self.profile1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'services/provider_profile.html')
        self.assertContains(response, 'John Mathew')
        self.assertContains(response, 'Services Offered by John')
        self.assertContains(response, 'Bathroom Leak Diagnosis')

    def test_commission_calculation_on_booking(self):
        """Test Booking model 10% platform commission calculation."""
        booking = Booking.objects.create(
            service=self.svc_plumbing,
            customer=self.customer,
            booking_date=date.today(),
            booking_time=time(10, 0),
            total_amount=Decimal('5000.00'),
            commission_rate=Decimal('10.00')
        )
        self.assertEqual(booking.commission_amount, Decimal('500.00'))

    def test_json_api_services_endpoint(self):
        """Test /api/services/ returns HTTP 200 and JSON array with active services."""
        response = self.client.get(reverse('api_services_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertIn('services', data)
        self.assertGreaterEqual(len(data['services']), 2)


class BookingSystemTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Provider
        self.provider_user = User.objects.create_user(
            username='provider_mike',
            password='password123',
            first_name='Mike',
            last_name='Fixer'
        )
        self.provider_profile = self.provider_user.profile
        self.provider_profile.role = 'provider'
        self.provider_profile.city = 'Kannur'
        self.provider_profile.save()

        # Customer 1
        self.customer1 = User.objects.create_user(
            username='cust_alex',
            password='password123',
            first_name='Alex',
            last_name='Homeowner'
        )

        # Customer 2
        self.customer2 = User.objects.create_user(
            username='cust_sarah',
            password='password123',
            first_name='Sarah',
            last_name='Client'
        )

        # Category and Service
        self.category = Category.objects.create(name='Plumbing', icon_name='wrench')
        self.service = Service.objects.create(
            provider=self.provider_profile,
            category=self.category,
            title='Kitchen Sink Pipe Repair',
            description='Fix broken drainage pipes.',
            price=Decimal('2000.00'),
            duration_estimate='1 hour',
            location='Kannur'
        )

    def test_unauthenticated_user_redirected_to_login(self):
        """Unauthenticated user booking a service must be redirected to login with next parameter."""
        response = self.client.get(reverse('book_service', kwargs={'service_id': self.service.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)
        self.assertIn(f'next={reverse("book_service", kwargs={"service_id": self.service.id})}', response.url)

    def test_provider_cannot_create_customer_booking(self):
        """Service providers must not be allowed to place customer bookings."""
        self.client.login(username='provider_mike', password='password123')
        response = self.client.get(reverse('book_service', kwargs={'service_id': self.service.id}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('service_detail', kwargs={'id': self.service.id}))

    def test_customer_can_access_booking_page(self):
        """Authenticated customer can access the multi-step booking page."""
        self.client.login(username='cust_alex', password='password123')
        response = self.client.get(reverse('book_service', kwargs={'service_id': self.service.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'services/booking.html')
        self.assertContains(response, 'Kitchen Sink Pipe Repair')
        self.assertContains(response, 'Mike Fixer')

    def test_past_date_is_rejected(self):
        """Booking a service on a past date must be rejected by server validation."""
        self.client.login(username='cust_alex', password='password123')
        past_date = '2020-01-01'
        response = self.client.post(reverse('book_service', kwargs={'service_id': self.service.id}), {
            'booking_date': past_date,
            'booking_time': '10:00:00',
            'address': 'House 10, Royal Gardens, Kannur',
            'notes': 'Urgent repair',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cannot be in the past')
        self.assertEqual(Booking.objects.count(), 0)

    def test_booking_successfully_created_with_commission(self):
        """Valid customer booking submission successfully stores record and computes 10% commission."""
        self.client.login(username='cust_alex', password='password123')
        future_date = '2026-10-15'
        response = self.client.post(reverse('book_service', kwargs={'service_id': self.service.id}), {
            'booking_date': future_date,
            'booking_time': '10:00:00',
            'address': 'House 10, Royal Gardens, Kannur',
            'notes': 'Please ring gate bell.',
        })
        self.assertEqual(response.status_code, 302)
        booking = Booking.objects.get(service=self.service, customer=self.customer1)
        self.assertEqual(booking.status, 'pending')
        self.assertEqual(booking.total_amount, Decimal('2000.00'))
        # 10% commission of 2000 = 200.00
        self.assertEqual(booking.commission_amount, Decimal('200.00'))
        self.assertEqual(response.url, reverse('booking_success', kwargs={'booking_id': booking.id}))

    def test_duplicate_booking_for_same_slot_prevented(self):
        """Submitting a booking for an already-booked time slot must be blocked."""
        future_date = date(2026, 10, 15)
        slot_time = time(10, 0)

        # Existing active booking
        Booking.objects.create(
            service=self.service,
            customer=self.customer1,
            booking_date=future_date,
            booking_time=slot_time,
            total_amount=Decimal('2000.00'),
            status='pending',
            address='House 10, Kannur'
        )

        # Customer 2 attempts to book the same slot
        self.client.login(username='cust_sarah', password='password123')
        response = self.client.post(reverse('book_service', kwargs={'service_id': self.service.id}), {
            'booking_date': '2026-10-15',
            'booking_time': '10:00:00',
            'address': 'Flat 204, Kannur',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already booked')
        # Total bookings remain 1
        self.assertEqual(Booking.objects.count(), 1)

    def test_customer_can_view_own_booking(self):
        """Customer can access their own booking detail view."""
        booking = Booking.objects.create(
            service=self.service,
            customer=self.customer1,
            booking_date=date(2026, 10, 15),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            status='pending',
            address='House 10, Kannur'
        )
        self.client.login(username='cust_alex', password='password123')
        response = self.client.get(reverse('booking_detail', kwargs={'booking_id': booking.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'services/booking_detail.html')
        self.assertContains(response, 'Kitchen Sink Pipe Repair')

    def test_customer_cannot_view_another_customer_booking(self):
        """Customer cannot view another customer's booking."""
        booking = Booking.objects.create(
            service=self.service,
            customer=self.customer1,
            booking_date=date(2026, 10, 15),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            status='pending',
            address='House 10, Kannur'
        )
        # Login as customer 2
        self.client.login(username='cust_sarah', password='password123')
        response = self.client.get(reverse('booking_detail', kwargs={'booking_id': booking.id}))
        self.assertEqual(response.status_code, 404)

    def test_customer_can_cancel_pending_booking(self):
        """Customer can cancel their pending booking via POST."""
        booking = Booking.objects.create(
            service=self.service,
            customer=self.customer1,
            booking_date=date(2026, 10, 15),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            status='pending',
            address='House 10, Kannur'
        )
        self.client.login(username='cust_alex', password='password123')
        response = self.client.post(reverse('cancel_booking', kwargs={'booking_id': booking.id}))
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')

    def test_cancelled_slot_becomes_available_again(self):
        """After cancellation, the same slot can be booked by another customer."""
        booking = Booking.objects.create(
            service=self.service,
            customer=self.customer1,
            booking_date=date(2026, 10, 15),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            status='cancelled',
            address='House 10, Kannur'
        )
        # Customer 2 books this same cancelled slot
        self.client.login(username='cust_sarah', password='password123')
        response = self.client.post(reverse('book_service', kwargs={'service_id': self.service.id}), {
            'booking_date': '2026-10-15',
            'booking_time': '10:00:00',
            'address': 'Flat 204, Kannur',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Booking.objects.filter(service=self.service, status='pending').count(), 1)

    def test_provider_can_see_bookings(self):
        """Provider can view the list of bookings on their services."""
        Booking.objects.create(
            service=self.service,
            customer=self.customer1,
            booking_date=date(2026, 10, 15),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            status='pending',
            address='House 10, Kannur'
        )
        self.client.login(username='provider_mike', password='password123')
        response = self.client.get(reverse('provider_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'services/provider_bookings.html')
        self.assertContains(response, 'Alex Homeowner')

    def test_api_availability_endpoint(self):
        """Availability API returns list of booked slots for given date."""
        Booking.objects.create(
            service=self.service,
            customer=self.customer1,
            booking_date=date(2026, 10, 15),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            status='pending',
            address='House 10, Kannur'
        )
        response = self.client.get(reverse('api_availability'), {
            'service_id': self.service.id,
            'date': '2026-10-15'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('10:00:00', data['booked_slots'])


class ProviderDashboardTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Provider 1
        self.provider1_user = User.objects.create_user(
            username='pro_sam',
            password='password123',
            first_name='Sam',
            last_name='Plumber'
        )
        self.pro1 = self.provider1_user.profile
        self.pro1.role = 'provider'
        self.pro1.city = 'Kannur'
        self.pro1.save()

        # Provider 2
        self.provider2_user = User.objects.create_user(
            username='pro_dave',
            password='password123',
            first_name='Dave',
            last_name='Electrician'
        )
        self.pro2 = self.provider2_user.profile
        self.pro2.role = 'provider'
        self.pro2.city = 'Kochi'
        self.pro2.save()

        # Customer
        self.customer_user = User.objects.create_user(
            username='cust_rachel',
            password='password123',
            first_name='Rachel',
            last_name='Green'
        )

        # Categories
        self.category = Category.objects.create(name='Plumbing', icon_name='wrench')

        # Services
        self.svc1 = Service.objects.create(
            provider=self.pro1,
            category=self.category,
            title='Emergency Pipe Leak Repair',
            description='Rapid response leak sealing.',
            price=Decimal('2000.00'),
            duration_estimate='1-2 hours',
            location='Kannur'
        )
        self.svc2 = Service.objects.create(
            provider=self.pro2,
            category=self.category,
            title='Main Electrical Panel Rewiring',
            description='Complete circuit diagnostic.',
            price=Decimal('5000.00'),
            duration_estimate='3 hours',
            location='Kochi'
        )

    def test_provider_can_access_dashboard(self):
        """Authenticated provider user can access /provider/dashboard/."""
        self.client.login(username='pro_sam', password='password123')
        response = self.client.get(reverse('provider_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'provider/dashboard.html')
        self.assertContains(response, 'Good morning, Sam')

    def test_customer_cannot_access_provider_dashboard(self):
        """Customer/Homeowner account is rejected from provider dashboard."""
        self.client.login(username='cust_rachel', password='password123')
        response = self.client.get(reverse('provider_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))

    def test_unauthenticated_redirect_to_login(self):
        """Unauthenticated visitor is redirected to login."""
        response = self.client.get(reverse('provider_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_provider_sees_only_own_bookings(self):
        """Provider only views bookings booked for their own services."""
        Booking.objects.create(
            service=self.svc1,
            customer=self.customer_user,
            booking_date=date(2026, 10, 15),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            status='pending',
            address='House 1, Kannur'
        )
        Booking.objects.create(
            service=self.svc2,
            customer=self.customer_user,
            booking_date=date(2026, 10, 16),
            booking_time=time(14, 0),
            total_amount=Decimal('5000.00'),
            status='pending',
            address='House 2, Kochi'
        )

        self.client.login(username='pro_sam', password='password123')
        response = self.client.get(reverse('provider_jobs'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Emergency Pipe Leak Repair')
        self.assertNotContains(response, 'Main Electrical Panel Rewiring')

    def test_provider_can_accept_pending_booking(self):
        """Provider accepting a pending booking sets status to accepted."""
        booking = Booking.objects.create(
            service=self.svc1,
            customer=self.customer_user,
            booking_date=date(2026, 10, 15),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            status='pending',
            address='House 1, Kannur'
        )
        self.client.login(username='pro_sam', password='password123')
        response = self.client.post(reverse('provider_job_accept', kwargs={'booking_id': booking.id}))
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'accepted')

    def test_provider_can_decline_pending_booking(self):
        """Provider declining a pending booking sets status to declined."""
        booking = Booking.objects.create(
            service=self.svc1,
            customer=self.customer_user,
            booking_date=date(2026, 10, 15),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            status='pending',
            address='House 1, Kannur'
        )
        self.client.login(username='pro_sam', password='password123')
        response = self.client.post(reverse('provider_job_decline', kwargs={'booking_id': booking.id}))
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'declined')

    def test_provider_can_complete_accepted_booking(self):
        """Provider marks an accepted booking as completed."""
        booking = Booking.objects.create(
            service=self.svc1,
            customer=self.customer_user,
            booking_date=date(2026, 10, 15),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            status='accepted',
            address='House 1, Kannur'
        )
        self.client.login(username='pro_sam', password='password123')
        response = self.client.post(reverse('provider_job_complete', kwargs={'booking_id': booking.id}))
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'completed')

    def test_invalid_booking_state_transition_blocked(self):
        """Attempting to complete a pending or declined booking is blocked."""
        booking = Booking.objects.create(
            service=self.svc1,
            customer=self.customer_user,
            booking_date=date(2026, 10, 15),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            status='pending',
            address='House 1, Kannur'
        )
        self.client.login(username='pro_sam', password='password123')
        # Complete should fail because status is pending, not accepted
        response = self.client.post(reverse('provider_job_complete', kwargs={'booking_id': booking.id}))
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending')

    def test_provider_can_create_own_service(self):
        """Provider can add a new service listing linked to their profile."""
        self.client.login(username='pro_sam', password='password123')
        response = self.client.post(reverse('provider_service_add'), {
            'title': 'Solar Water Heater Installation',
            'category': self.category.id,
            'description': 'High efficiency rooftop solar installation.',
            'price': '8500.00',
            'duration_estimate': '1 day',
            'location': 'Kannur',
            'is_active': True,
        })
        self.assertEqual(response.status_code, 302)
        svc = Service.objects.get(title='Solar Water Heater Installation')
        self.assertEqual(svc.provider, self.pro1)
        self.assertEqual(svc.price, Decimal('8500.00'))

    def test_provider_can_edit_own_service(self):
        """Provider can edit title and price of their own service."""
        self.client.login(username='pro_sam', password='password123')
        response = self.client.post(reverse('provider_service_edit', kwargs={'id': self.svc1.id}), {
            'title': 'Emergency Pipe Leak Repair (Updated)',
            'category': self.category.id,
            'description': 'Updated description.',
            'price': '2500.00',
            'duration_estimate': '2 hours',
            'location': 'Kannur',
            'is_active': True,
        })
        self.assertEqual(response.status_code, 302)
        self.svc1.refresh_from_db()
        self.assertEqual(self.svc1.title, 'Emergency Pipe Leak Repair (Updated)')
        self.assertEqual(self.svc1.price, Decimal('2500.00'))

    def test_provider_cannot_edit_another_provider_service(self):
        """Provider Dave cannot edit Provider Sam's service."""
        self.client.login(username='pro_dave', password='password123')
        response = self.client.post(reverse('provider_service_edit', kwargs={'id': self.svc1.id}), {
            'title': 'Hacked Title',
            'category': self.category.id,
            'description': 'Hacked.',
            'price': '100.00',
            'duration_estimate': '1 hour',
            'location': 'Kannur',
            'is_active': True,
        })
        self.assertEqual(response.status_code, 404)
        self.svc1.refresh_from_db()
        self.assertNotEqual(self.svc1.title, 'Hacked Title')

    def test_provider_cannot_delete_another_provider_service(self):
        """Provider Dave cannot delete Provider Sam's service."""
        self.client.login(username='pro_dave', password='password123')
        response = self.client.post(reverse('provider_service_delete', kwargs={'id': self.svc1.id}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Service.objects.filter(id=self.svc1.id).exists())

    def test_provider_earnings_calculation(self):
        """Earnings page correctly sums (total_amount - commission_amount) for completed bookings."""
        # Booking 1: 2000 total, 200 commission -> 1800 net
        Booking.objects.create(
            service=self.svc1,
            customer=self.customer_user,
            booking_date=date.today(),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            commission_rate=Decimal('10.00'),
            status='completed',
            address='House 1, Kannur'
        )
        # Booking 2: 5000 total, 500 commission -> 4500 net
        Booking.objects.create(
            service=self.svc1,
            customer=self.customer_user,
            booking_date=date.today(),
            booking_time=time(14, 0),
            total_amount=Decimal('5000.00'),
            commission_rate=Decimal('10.00'),
            status='completed',
            address='House 1, Kannur'
        )

        self.client.login(username='pro_sam', password='password123')
        response = self.client.get(reverse('provider_earnings'))
        self.assertEqual(response.status_code, 200)
        # 1800 + 4500 = 6300 net provider earnings
        self.assertEqual(response.context['total_earnings'], Decimal('6300.00'))
        self.assertEqual(response.context['completed_jobs_count'], 2)

    def test_only_completed_bookings_contribute_to_earnings(self):
        """Pending and accepted bookings must not count toward completed provider earnings."""
        # 1 Completed: 3000 total, 300 commission -> 2700 net
        Booking.objects.create(
            service=self.svc1,
            customer=self.customer_user,
            booking_date=date.today(),
            booking_time=time(10, 0),
            total_amount=Decimal('3000.00'),
            commission_rate=Decimal('10.00'),
            status='completed',
            address='House 1, Kannur'
        )
        # 1 Pending: 4000 total
        Booking.objects.create(
            service=self.svc1,
            customer=self.customer_user,
            booking_date=date.today(),
            booking_time=time(13, 0),
            total_amount=Decimal('4000.00'),
            commission_rate=Decimal('10.00'),
            status='pending',
            address='House 1, Kannur'
        )
        # 1 Accepted: 2000 total
        Booking.objects.create(
            service=self.svc1,
            customer=self.customer_user,
            booking_date=date.today(),
            booking_time=time(16, 0),
            total_amount=Decimal('2000.00'),
            commission_rate=Decimal('10.00'),
            status='accepted',
            address='House 1, Kannur'
        )

        self.client.login(username='pro_sam', password='password123')
        response = self.client.get(reverse('provider_earnings'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_earnings'], Decimal('2700.00'))
        self.assertEqual(response.context['completed_jobs_count'], 1)


class PlatformRevenueTests(TestCase):
    """
    Stage 6 — Platform Revenue & Monetization Automated Test Suite.
    Verifies:
    1. Role-based security on /platform/revenue/ & /platform/revenue/transactions/
    2. Automatic 10% commission generation on booking completion and idempotency
    3. Provider Pro subscription upgrades (₹399/mo) and revenue logging
    4. Featured service listings (₹99 / 3 days) and active date expiry
    5. Database-driven platform revenue totals (₹6,000+ demo capability)
    """

    def setUp(self):
        self.client = Client()

        # 1. Admin / Staff User
        self.admin_user = User.objects.create_user(
            username='platform_admin',
            password='adminpassword',
            first_name='Admin',
            last_name='User',
            is_staff=True,
            is_superuser=True
        )

        # 2. Providers
        self.provider1_user = User.objects.create_user(
            username='prov_rohit',
            password='password123',
            first_name='Rohit',
            last_name='Sharma'
        )
        self.pro1 = self.provider1_user.profile
        self.pro1.role = 'provider'
        self.pro1.city = 'Kannur'
        self.pro1.save()

        self.provider2_user = User.objects.create_user(
            username='prov_karan',
            password='password123',
            first_name='Karan',
            last_name='Verma'
        )
        self.pro2 = self.provider2_user.profile
        self.pro2.role = 'provider'
        self.pro2.city = 'Kochi'
        self.pro2.save()

        # 3. Customer
        self.customer_user = User.objects.create_user(
            username='cust_neha',
            password='password123',
            first_name='Neha',
            last_name='Kapoor'
        )
        self.cust = self.customer_user.profile
        self.cust.role = 'customer'
        self.cust.save()

        # 4. Service Category & Services
        self.category = Category.objects.create(name='Plumbing', icon_name='wrench')

        self.service1 = Service.objects.create(
            provider=self.pro1,
            category=self.category,
            title='Full House Water Leakage Diagnosis',
            description='Acoustic pipe leak detection and waterproofing.',
            price=Decimal('2000.00'),
            duration_estimate='2 hours',
            location='Kannur'
        )

        self.service2 = Service.objects.create(
            provider=self.pro2,
            category=self.category,
            title='Kitchen Tap and Sink Valve Fitting',
            description='Modern quarter-turn brass tap installation.',
            price=Decimal('1000.00'),
            duration_estimate='1 hour',
            location='Kochi'
        )

    # -------------------------------------------------------------
    # A. REVENUE ACCESS TESTS
    # -------------------------------------------------------------
    def test_admin_can_access_revenue_dashboard(self):
        """Platform staff/superuser can successfully view /platform/revenue/ and /transactions/."""
        self.client.login(username='platform_admin', password='adminpassword')
        resp_dashboard = self.client.get(reverse('platform_revenue'))
        self.assertEqual(resp_dashboard.status_code, 200)
        self.assertTemplateUsed(resp_dashboard, 'platform/revenue_dashboard.html')

        resp_tx = self.client.get(reverse('platform_revenue_transactions'))
        self.assertEqual(resp_tx.status_code, 200)
        self.assertTemplateUsed(resp_tx, 'platform/transactions.html')

    def test_provider_cannot_access_revenue_dashboard(self):
        """Service providers must NOT have access to platform revenue dashboard."""
        self.client.login(username='prov_rohit', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))

    def test_customer_cannot_access_revenue_dashboard(self):
        """Customers must NOT have access to platform revenue dashboard."""
        self.client.login(username='cust_neha', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))

    # -------------------------------------------------------------
    # B. COMMISSION REVENUE TESTS
    # -------------------------------------------------------------
    def test_completed_booking_creates_commission_revenue(self):
        """When an accepted booking is marked completed, 10% platform commission is automatically logged."""
        booking = Booking.objects.create(
            service=self.service1,
            customer=self.customer_user,
            booking_date=date.today(),
            booking_time=time(10, 0),
            total_amount=Decimal('5000.00'),
            commission_rate=Decimal('10.00'),
            status='accepted',
            address='Villa 5, Kannur'
        )
        self.client.login(username='prov_rohit', password='password123')
        response = self.client.post(reverse('provider_job_complete', kwargs={'booking_id': booking.id}))
        self.assertEqual(response.status_code, 302)

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'completed')

        # Verify commission RevenueTransaction exists
        tx = RevenueTransaction.objects.filter(revenue_type='commission', booking=booking).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('500.00'))
        self.assertEqual(tx.provider, self.pro1)
        self.assertEqual(tx.status, 'completed')

    def test_pending_booking_does_not_create_commission_revenue(self):
        """Pending bookings must not generate realized platform revenue transactions."""
        booking = Booking.objects.create(
            service=self.service1,
            customer=self.customer_user,
            booking_date=date.today(),
            booking_time=time(10, 0),
            total_amount=Decimal('3000.00'),
            commission_rate=Decimal('10.00'),
            status='pending',
            address='Villa 5, Kannur'
        )
        self.assertFalse(
            RevenueTransaction.objects.filter(revenue_type='commission', booking=booking).exists()
        )

    def test_cancelled_booking_does_not_create_commission_revenue(self):
        """Cancelled bookings must not generate platform revenue transactions."""
        booking = Booking.objects.create(
            service=self.service1,
            customer=self.customer_user,
            booking_date=date.today() + timedelta(days=2),
            booking_time=time(10, 0),
            total_amount=Decimal('2000.00'),
            commission_rate=Decimal('10.00'),
            status='pending',
            address='Villa 5, Kannur'
        )
        self.client.login(username='cust_neha', password='password123')
        self.client.post(reverse('cancel_booking', kwargs={'booking_id': booking.id}))

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertFalse(
            RevenueTransaction.objects.filter(revenue_type='commission', booking=booking).exists()
        )

    def test_commission_transaction_not_duplicated(self):
        """Prevent duplicate commission transactions even if complete trigger is invoked repeatedly."""
        booking = Booking.objects.create(
            service=self.service1,
            customer=self.customer_user,
            booking_date=date.today(),
            booking_time=time(10, 0),
            total_amount=Decimal('4000.00'),
            commission_rate=Decimal('10.00'),
            status='accepted',
            address='Villa 5, Kannur'
        )
        self.client.login(username='prov_rohit', password='password123')

        # First completion
        self.client.post(reverse('provider_job_complete', kwargs={'booking_id': booking.id}))
        # Attempt second completion
        self.client.post(reverse('provider_job_complete', kwargs={'booking_id': booking.id}))

        count = RevenueTransaction.objects.filter(revenue_type='commission', booking=booking).count()
        self.assertEqual(count, 1)

    # -------------------------------------------------------------
    # C. REVENUE CALCULATIONS TESTS
    # -------------------------------------------------------------
    def test_total_platform_revenue(self):
        """Total platform revenue must correctly aggregate all completed commission, subscription, and featured transactions."""
        # 1. Commission (₹400)
        RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('400.00'),
            provider=self.pro1,
            description='Commission',
            status='completed'
        )
        # 2. Subscription (₹399)
        RevenueTransaction.objects.create(
            revenue_type='subscription',
            amount=Decimal('399.00'),
            provider=self.pro1,
            description='Pro Sub',
            status='completed'
        )
        # 3. Featured (₹99)
        RevenueTransaction.objects.create(
            revenue_type='featured',
            amount=Decimal('99.00'),
            provider=self.pro1,
            service=self.service1,
            description='Featured',
            status='completed'
        )

        self.client.login(username='platform_admin', password='adminpassword')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.status_code, 200)
        # 400 + 399 + 99 = 898.00
        self.assertEqual(response.context['total_revenue'], Decimal('898.00'))

    def test_commission_revenue_total(self):
        """Dashboard accurately isolates booking commission revenue."""
        RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('300.00'),
            provider=self.pro1,
            description='Commission 1',
            status='completed'
        )
        RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('250.00'),
            provider=self.pro2,
            description='Commission 2',
            status='completed'
        )
        self.client.login(username='platform_admin', password='adminpassword')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.context['commission_revenue'], Decimal('550.00'))

    def test_subscription_revenue_total(self):
        """Dashboard accurately isolates Pro subscription revenue."""
        RevenueTransaction.objects.create(
            revenue_type='subscription',
            amount=Decimal('399.00'),
            provider=self.pro1,
            description='Pro Sub 1',
            status='completed'
        )
        RevenueTransaction.objects.create(
            revenue_type='subscription',
            amount=Decimal('399.00'),
            provider=self.pro2,
            description='Pro Sub 2',
            status='completed'
        )
        self.client.login(username='platform_admin', password='adminpassword')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.context['subscription_revenue'], Decimal('798.00'))

    def test_featured_listing_revenue_total(self):
        """Dashboard accurately isolates featured listing revenue."""
        RevenueTransaction.objects.create(
            revenue_type='featured',
            amount=Decimal('99.00'),
            provider=self.pro1,
            service=self.service1,
            description='Featured 1',
            status='completed'
        )
        RevenueTransaction.objects.create(
            revenue_type='featured',
            amount=Decimal('99.00'),
            provider=self.pro2,
            service=self.service2,
            description='Featured 2',
            status='completed'
        )
        self.client.login(username='platform_admin', password='adminpassword')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.context['featured_revenue'], Decimal('198.00'))

    # -------------------------------------------------------------
    # D. SUBSCRIPTION TESTS
    # -------------------------------------------------------------
    def test_provider_can_upgrade_to_pro(self):
        """Provider can upgrade their account to Pro subscription tier."""
        self.client.login(username='prov_rohit', password='password123')
        response = self.client.post(reverse('provider_subscription'), {'action': 'upgrade_pro'})
        self.assertEqual(response.status_code, 302)

        sub = ProviderSubscription.objects.get(provider=self.pro1)
        self.assertEqual(sub.plan_name, 'pro')
        self.assertEqual(sub.monthly_fee, Decimal('399.00'))
        self.assertTrue(sub.is_active)
        self.assertTrue(self.pro1.is_pro)

    def test_pro_subscription_creates_revenue_transaction(self):
        """Upgrading to Pro creates an associated ₹399 revenue transaction."""
        self.client.login(username='prov_rohit', password='password123')
        self.client.post(reverse('provider_subscription'), {'action': 'upgrade_pro'})

        tx = RevenueTransaction.objects.filter(revenue_type='subscription', provider=self.pro1).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('399.00'))
        self.assertEqual(tx.status, 'completed')

    def test_free_subscription_does_not_create_revenue(self):
        """Free plan default does not generate platform revenue transactions."""
        ProviderSubscription.objects.create(
            provider=self.pro1,
            plan_name='free',
            monthly_fee=Decimal('0.00'),
            is_active=True
        )
        self.assertFalse(
            RevenueTransaction.objects.filter(revenue_type='subscription', provider=self.pro1).exists()
        )

    # -------------------------------------------------------------
    # E. FEATURED LISTING TESTS
    # -------------------------------------------------------------
    def test_provider_can_feature_own_service(self):
        """Provider can feature their own service for ₹99 for 3 days."""
        self.client.login(username='prov_rohit', password='password123')
        response = self.client.post(reverse('provider_feature_service', kwargs={'service_id': self.service1.id}))
        self.assertEqual(response.status_code, 302)

        self.service1.refresh_from_db()
        self.assertTrue(self.service1.is_featured)
        self.assertTrue(self.service1.has_active_featured_listing)

        promo = FeaturedListing.objects.filter(service=self.service1, is_active=True).first()
        self.assertIsNotNone(promo)
        self.assertEqual(promo.fee_paid, Decimal('99.00'))
        self.assertEqual(promo.end_date, date.today() + timedelta(days=3))

    def test_featured_listing_creates_revenue_transaction(self):
        """Featuring a service creates a ₹99 platform revenue transaction."""
        self.client.login(username='prov_rohit', password='password123')
        self.client.post(reverse('provider_feature_service', kwargs={'service_id': self.service1.id}))

        tx = RevenueTransaction.objects.filter(revenue_type='featured', service=self.service1).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('99.00'))
        self.assertEqual(tx.provider, self.pro1)
        self.assertEqual(tx.status, 'completed')

    def test_provider_cannot_feature_another_provider_service(self):
        """Provider Karan cannot feature Provider Rohit's service."""
        self.client.login(username='prov_karan', password='password123')
        response = self.client.post(reverse('provider_feature_service', kwargs={'service_id': self.service1.id}))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(FeaturedListing.objects.filter(service=self.service1).exists())

    def test_expired_featured_listing_is_not_active(self):
        """An expired featured promotion dynamically reports inactive without requiring a background worker."""
        # Create an expired promotion ending yesterday
        FeaturedListing.objects.create(
            service=self.service1,
            fee_paid=Decimal('99.00'),
            start_date=date.today() - timedelta(days=4),
            end_date=date.today() - timedelta(days=1),
            is_active=True
        )
        self.assertFalse(self.service1.has_active_featured_listing)


class ReviewAndNotificationTests(TestCase):
    """
    Stage 7 — Customer Reviews and Database Notifications Automated Test Suite.
    Verifies:
    1. Review eligibility: completed bookings only, customer ownership enforcement, provider restrictions
    2. Review validation: rating 1-5 required, comment min length, one review per booking
    3. Rating calculations: dynamic provider average_rating ORM aggregation
    4. Service detail and provider profile review displays and distribution
    5. Database notification triggers across complete booking lifecycle:
       - booking_created
       - booking_accepted
       - booking_declined
       - booking_cancelled
       - booking_completed
       - review_received
    6. Notification security: user isolation, mark as read, mark all as read
    """

    def setUp(self):
        self.client = Client()

        # 1. Provider
        self.provider1_user = User.objects.create_user(
            username='prov_ramesh',
            password='password123',
            first_name='Ramesh',
            last_name='Kumar'
        )
        self.pro1 = self.provider1_user.profile
        self.pro1.role = 'provider'
        self.pro1.city = 'Kannur'
        self.pro1.save()

        # 2. Customer 1 (Owner of test bookings)
        self.cust1_user = User.objects.create_user(
            username='cust_priya',
            password='password123',
            first_name='Priya',
            last_name='Nair'
        )
        self.cust1 = self.cust1_user.profile
        self.cust1.role = 'customer'
        self.cust1.save()

        # 3. Customer 2 (Separate user for security isolation tests)
        self.cust2_user = User.objects.create_user(
            username='cust_amit',
            password='password123',
            first_name='Amit',
            last_name='Patel'
        )
        self.cust2 = self.cust2_user.profile
        self.cust2.role = 'customer'
        self.cust2.save()

        # 4. Service Category & Service
        self.category = Category.objects.create(name='Plumbing', icon_name='wrench')
        self.service = Service.objects.create(
            provider=self.pro1,
            category=self.category,
            title='Tap Repair & Leakage Fixing',
            description='Professional tap repair and cartridge replacement.',
            price=Decimal('500.00'),
            duration_estimate='1 hour',
            location='Kannur'
        )

        # 5. Completed Booking for Customer 1
        self.booking_completed = Booking.objects.create(
            service=self.service,
            customer=self.cust1_user,
            booking_date=date.today() - timedelta(days=2),
            booking_time=time(10, 0),
            total_amount=Decimal('500.00'),
            commission_rate=Decimal('10.00'),
            status='completed',
            address='House 12, Seaside, Kannur'
        )

        # 6. Pending Booking for Customer 1
        self.booking_pending = Booking.objects.create(
            service=self.service,
            customer=self.cust1_user,
            booking_date=date.today() + timedelta(days=1),
            booking_time=time(11, 0),
            total_amount=Decimal('500.00'),
            commission_rate=Decimal('10.00'),
            status='pending',
            address='House 12, Seaside, Kannur'
        )

        # 7. Accepted Booking for Customer 1
        self.booking_accepted = Booking.objects.create(
            service=self.service,
            customer=self.cust1_user,
            booking_date=date.today() + timedelta(days=2),
            booking_time=time(14, 0),
            total_amount=Decimal('500.00'),
            commission_rate=Decimal('10.00'),
            status='accepted',
            address='House 12, Seaside, Kannur'
        )

        # 8. Cancelled Booking for Customer 1
        self.booking_cancelled = Booking.objects.create(
            service=self.service,
            customer=self.cust1_user,
            booking_date=date.today() - timedelta(days=5),
            booking_time=time(16, 0),
            total_amount=Decimal('500.00'),
            commission_rate=Decimal('10.00'),
            status='cancelled',
            address='House 12, Seaside, Kannur'
        )

    # -------------------------------------------------------------------------
    # A. REVIEW ELIGIBILITY & VALIDATION TESTS
    # -------------------------------------------------------------------------
    def test_customer_can_review_completed_booking(self):
        """Customer who completed a booking can submit a 1-5 star review with comment."""
        self.client.login(username='cust_priya', password='password123')
        resp_get = self.client.get(reverse('leave_review', kwargs={'booking_id': self.booking_completed.id}))
        self.assertEqual(resp_get.status_code, 200)
        self.assertTemplateUsed(resp_get, 'services/leave_review.html')

        resp_post = self.client.post(reverse('leave_review', kwargs={'booking_id': self.booking_completed.id}), {
            'rating': 5,
            'comment': 'Exceptional service provided on time! Very polite and skilled.',
        })
        self.assertEqual(resp_post.status_code, 302)

        # Verify review stored in database
        review = Review.objects.filter(booking=self.booking_completed).first()
        self.assertIsNotNone(review)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.customer, self.cust1_user)
        self.assertEqual(review.service, self.service)

    def test_customer_cannot_review_pending_booking(self):
        """Customer cannot review a booking that is still in pending status."""
        self.client.login(username='cust_priya', password='password123')
        response = self.client.post(reverse('leave_review', kwargs={'booking_id': self.booking_pending.id}), {
            'rating': 5,
            'comment': 'Attempting early review.',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Review.objects.filter(booking=self.booking_pending).exists())

    def test_customer_cannot_review_accepted_booking(self):
        """Customer cannot review a booking that is in accepted (in-progress) status."""
        self.client.login(username='cust_priya', password='password123')
        response = self.client.post(reverse('leave_review', kwargs={'booking_id': self.booking_accepted.id}), {
            'rating': 4,
            'comment': 'Attempting in-progress review.',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Review.objects.filter(booking=self.booking_accepted).exists())

    def test_customer_cannot_review_cancelled_booking(self):
        """Customer cannot review a cancelled booking."""
        self.client.login(username='cust_priya', password='password123')
        response = self.client.post(reverse('leave_review', kwargs={'booking_id': self.booking_cancelled.id}), {
            'rating': 1,
            'comment': 'Attempting cancelled booking review.',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Review.objects.filter(booking=self.booking_cancelled).exists())

    def test_customer_cannot_review_another_customers_booking(self):
        """Customer Amit cannot review Customer Priya's completed booking (strictly returns 404)."""
        self.client.login(username='cust_amit', password='password123')
        response = self.client.get(reverse('leave_review', kwargs={'booking_id': self.booking_completed.id}))
        self.assertEqual(response.status_code, 404)

        resp_post = self.client.post(reverse('leave_review', kwargs={'booking_id': self.booking_completed.id}), {
            'rating': 5,
            'comment': 'Unauthorized review attempt.',
        })
        self.assertEqual(resp_post.status_code, 404)
        self.assertFalse(Review.objects.filter(booking=self.booking_completed).exists())

    def test_provider_cannot_submit_customer_review(self):
        """Provider accounts are rejected from submitting customer reviews."""
        self.client.login(username='prov_ramesh', password='password123')
        response = self.client.post(reverse('leave_review', kwargs={'booking_id': self.booking_completed.id}), {
            'rating': 5,
            'comment': 'Provider attempting self-review.',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))
        self.assertFalse(Review.objects.filter(booking=self.booking_completed).exists())

    def test_review_requires_rating(self):
        """Submitting a review without selecting a rating must be rejected."""
        self.client.login(username='cust_priya', password='password123')
        response = self.client.post(reverse('leave_review', kwargs={'booking_id': self.booking_completed.id}), {
            'rating': '',
            'comment': 'Great service without rating.',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Review.objects.filter(booking=self.booking_completed).exists())

    def test_review_requires_comment(self):
        """Submitting a review with empty or too short comment (<10 chars) must be rejected."""
        self.client.login(username='cust_priya', password='password123')
        response = self.client.post(reverse('leave_review', kwargs={'booking_id': self.booking_completed.id}), {
            'rating': 5,
            'comment': 'Short',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Review.objects.filter(booking=self.booking_completed).exists())

    def test_customer_cannot_submit_duplicate_review(self):
        """A booking can have at most one customer review; duplicate reviews are prevented."""
        self.client.login(username='cust_priya', password='password123')
        # First review submission
        self.client.post(reverse('leave_review', kwargs={'booking_id': self.booking_completed.id}), {
            'rating': 5,
            'comment': 'First review submitted successfully.',
        })
        self.assertEqual(Review.objects.filter(booking=self.booking_completed).count(), 1)

        # Second review attempt on same booking
        response = self.client.post(reverse('leave_review', kwargs={'booking_id': self.booking_completed.id}), {
            'rating': 4,
            'comment': 'Duplicate review attempt.',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Review.objects.filter(booking=self.booking_completed).count(), 1)

    # -------------------------------------------------------------------------
    # B. RATING AGGREGATION & DISPLAY TESTS
    # -------------------------------------------------------------------------
    def test_provider_average_rating_updates(self):
        """Provider average_rating dynamically aggregates reviews using Avg('rating') from DB."""
        # Booking 1 with 5 stars
        Review.objects.create(
            service=self.service,
            customer=self.cust1_user,
            booking=self.booking_completed,
            rating=5,
            comment='Superb professional service!'
        )

        # Booking 2 with 3 stars
        booking2 = Booking.objects.create(
            service=self.service,
            customer=self.cust2_user,
            booking_date=date.today() - timedelta(days=1),
            booking_time=time(15, 0),
            total_amount=Decimal('500.00'),
            commission_rate=Decimal('10.00'),
            status='completed',
            address='Apartment 204, Kannur'
        )
        Review.objects.create(
            service=self.service,
            customer=self.cust2_user,
            booking=booking2,
            rating=3,
            comment='Satisfactory, but arrived 15 minutes late.'
        )

        self.pro1.refresh_from_db()
        # (5 + 3) / 2 = 4.0
        self.assertEqual(self.pro1.average_rating, 4.0)

    def test_service_reviews_display_correctly(self):
        """Reviews and rating distribution appear cleanly on the service detail page."""
        Review.objects.create(
            service=self.service,
            customer=self.cust1_user,
            booking=self.booking_completed,
            rating=5,
            comment='Superb professional service with clean workmanship!'
        )

        response = self.client.get(reverse('service_detail', kwargs={'id': self.service.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Superb professional service with clean workmanship!')
        self.assertIn('rating_distribution', response.context)
        self.assertEqual(response.context['rating_distribution'][0]['star'], 5)
        self.assertEqual(response.context['rating_distribution'][0]['count'], 1)

    # -------------------------------------------------------------------------
    # C. NOTIFICATION LIFECYCLE TESTS
    # -------------------------------------------------------------------------
    def test_booking_creation_notifies_provider(self):
        """Creating a new booking request notifies the service provider."""
        self.client.login(username='cust_priya', password='password123')
        response = self.client.post(reverse('book_service', kwargs={'service_id': self.service.id}), {
            'booking_date': (date.today() + timedelta(days=4)).strftime('%Y-%m-%d'),
            'booking_time': '09:00:00',
            'address': 'Villa 99, Beach Road, Kannur',
            'notes': 'Please check main bathroom line.',
        })
        self.assertEqual(response.status_code, 302)

        notif = Notification.objects.filter(
            recipient=self.provider1_user,
            notification_type='booking_created'
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn('Priya', notif.message)
        self.assertFalse(notif.is_read)

    def test_booking_acceptance_notifies_customer(self):
        """Provider accepting a booking sends a booking_accepted notification to the customer."""
        self.client.login(username='prov_ramesh', password='password123')
        response = self.client.post(reverse('provider_job_accept', kwargs={'booking_id': self.booking_pending.id}))
        self.assertEqual(response.status_code, 302)

        notif = Notification.objects.filter(
            recipient=self.cust1_user,
            notification_type='booking_accepted'
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.title, 'Booking Accepted')
        self.assertEqual(notif.booking, self.booking_pending)

    def test_booking_decline_notifies_customer(self):
        """Provider declining a booking sends a booking_declined notification to the customer."""
        self.client.login(username='prov_ramesh', password='password123')
        response = self.client.post(reverse('provider_job_decline', kwargs={'booking_id': self.booking_pending.id}))
        self.assertEqual(response.status_code, 302)

        notif = Notification.objects.filter(
            recipient=self.cust1_user,
            notification_type='booking_declined'
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.title, 'Booking Declined')

    def test_booking_cancellation_notifies_provider(self):
        """Customer cancelling a pending booking sends a booking_cancelled notification to provider."""
        self.client.login(username='cust_priya', password='password123')
        response = self.client.post(reverse('cancel_booking', kwargs={'booking_id': self.booking_pending.id}))
        self.assertEqual(response.status_code, 302)

        notif = Notification.objects.filter(
            recipient=self.provider1_user,
            notification_type='booking_cancelled'
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.title, 'Booking Cancelled')

    def test_booking_completion_notifies_customer(self):
        """Provider marking a job completed sends a booking_completed notification with review prompt to customer."""
        self.client.login(username='prov_ramesh', password='password123')
        response = self.client.post(reverse('provider_job_complete', kwargs={'booking_id': self.booking_accepted.id}))
        self.assertEqual(response.status_code, 302)

        notif = Notification.objects.filter(
            recipient=self.cust1_user,
            notification_type='booking_completed'
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.title, 'Service Completed')
        self.assertIn('review', notif.message.lower())

    def test_review_creates_provider_notification(self):
        """Customer submitting a review sends a review_received notification to the provider."""
        self.client.login(username='cust_priya', password='password123')
        self.client.post(reverse('leave_review', kwargs={'booking_id': self.booking_completed.id}), {
            'rating': 5,
            'comment': 'Outstanding speed and quality!',
        })

        notif = Notification.objects.filter(
            recipient=self.provider1_user,
            notification_type='review_received'
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.title, 'New Review Received')
        self.assertIn('5 stars', notif.message)

    # -------------------------------------------------------------------------
    # D. NOTIFICATION CENTER & SECURITY TESTS
    # -------------------------------------------------------------------------
    def test_notification_belongs_to_correct_user(self):
        """Users can only view their own notifications in the notification center."""
        # Notification for Priya
        Notification.objects.create(
            recipient=self.cust1_user,
            notification_type='booking_accepted',
            title='Priya Private Alert',
            message='Confidential message for Priya.'
        )
        # Notification for Amit
        Notification.objects.create(
            recipient=self.cust2_user,
            notification_type='booking_accepted',
            title='Amit Private Alert',
            message='Confidential message for Amit.'
        )

        self.client.login(username='cust_priya', password='password123')
        response = self.client.get(reverse('notifications_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Priya Private Alert')
        self.assertNotContains(response, 'Amit Private Alert')

    def test_user_can_mark_notification_as_read(self):
        """User can mark their own notification as read via POST endpoint."""
        notif = Notification.objects.create(
            recipient=self.cust1_user,
            notification_type='booking_completed',
            title='Service Completed',
            message='Please review.',
            is_read=False
        )

        self.client.login(username='cust_priya', password='password123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'id': notif.id}))
        self.assertEqual(response.status_code, 302)

        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_user_can_mark_all_notifications_as_read(self):
        """POST to /notifications/read-all/ marks only the current user's unread notifications as read."""
        notif1 = Notification.objects.create(
            recipient=self.cust1_user,
            notification_type='booking_created',
            title='Alert 1',
            message='Msg 1',
            is_read=False
        )
        notif2 = Notification.objects.create(
            recipient=self.cust1_user,
            notification_type='booking_accepted',
            title='Alert 2',
            message='Msg 2',
            is_read=False
        )
        notif_other = Notification.objects.create(
            recipient=self.cust2_user,
            notification_type='booking_created',
            title='Other User Alert',
            message='Other Msg',
            is_read=False
        )

        self.client.login(username='cust_priya', password='password123')
        response = self.client.post(reverse('notification_mark_all_read'))
        self.assertEqual(response.status_code, 302)

        notif1.refresh_from_db()
        notif2.refresh_from_db()
        notif_other.refresh_from_db()

        self.assertTrue(notif1.is_read)
        self.assertTrue(notif2.is_read)
        self.assertFalse(notif_other.is_read)


class RGMVerifiableRevenueTests(TestCase):
    """
    Stage 7.5 — RGM Revenue Pilot & Verifiable Revenue Tracking Automated Test Suite.
    Verifies:
    1. Demo transactions excluded from verified revenue
    2. Verified actual commission included in verified revenue
    3. Unverified transactions excluded from verified revenue
    4. Completed booking commission calculated correctly (10%)
    5. Duplicate commission prevented
    6. Subscription revenue calculated correctly (₹399)
    7. Featured listing revenue calculated correctly (₹99)
    8. Gross booking value separated from platform revenue
    9. Provider earnings calculated correctly (90%)
    10. Unauthorized users blocked from revenue evidence
    11. Providers blocked from platform-wide revenue
    12. Revenue target calculation (₹10,000 threshold)
    13. Remaining revenue to target calculation
    14. Verification status filtering (verified/pending/rejected)
    15. Transaction reference and UTR handling
    16. Admin revenue evidence filtering
    17. Commercial receipt generation without fake GST/tax claims
    """

    def setUp(self):
        self.client = Client()

        # 1. Platform Admin
        self.admin_user = User.objects.create_user(
            username='rgm_admin',
            password='password123',
            first_name='RGM',
            last_name='Auditor',
            is_staff=True,
            is_superuser=True
        )

        # 2. Provider
        self.provider_user = User.objects.create_user(
            username='rgm_provider',
            password='password123',
            first_name='Kishore',
            last_name='Electric'
        )
        self.provider_profile = self.provider_user.profile
        self.provider_profile.role = 'provider'
        self.provider_profile.city = 'Kannur'
        self.provider_profile.save()

        # 3. Customer 1 (Booking Owner)
        self.customer_user = User.objects.create_user(
            username='rgm_customer',
            password='password123',
            first_name='Ananya',
            last_name='Sharma'
        )
        self.cust_profile = self.customer_user.profile
        self.cust_profile.role = 'customer'
        self.cust_profile.save()

        # 4. Customer 2 (Unauthorized User)
        self.other_customer = User.objects.create_user(
            username='other_customer',
            password='password123',
            first_name='Rahul',
            last_name='Roy'
        )

        # 5. Category & Service
        self.category = Category.objects.create(name='Electrical', icon_name='zap')
        self.service = Service.objects.create(
            provider=self.provider_profile,
            category=self.category,
            title='Inverter Wiring & Diagnostic',
            description='Pure sinewave inverter wiring.',
            price=Decimal('2500.00'),
            duration_estimate='2 hours',
            location='Kannur'
        )

        # 6. Completed Booking
        self.booking_completed = Booking.objects.create(
            service=self.service,
            customer=self.customer_user,
            booking_date=date.today() - timedelta(days=3),
            booking_time=time(10, 0),
            total_amount=Decimal('5000.00'),
            commission_rate=Decimal('10.00'),
            commission_amount=Decimal('500.00'),
            status='completed',
            address='Villa 44, Kannur'
        )

    # 1. Demo transactions excluded from verified revenue
    def test_demo_transactions_excluded_from_verified_revenue(self):
        """Synthetic demonstration transactions (is_demo=True) must not count toward verified pilot revenue."""
        RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('500.00'),
            provider=self.provider_profile,
            booking=self.booking_completed,
            description='Demo Commission',
            status='completed',
            is_demo=True,
            verification_status='verified'
        )
        self.client.login(username='rgm_admin', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['verified_revenue'], Decimal('0.00'))
        self.assertEqual(response.context['demo_revenue'], Decimal('500.00'))

    # 2. Verified actual commission included
    def test_verified_actual_commission_included(self):
        """An actual transaction (is_demo=False) with verification_status='verified', has_evidence=True, and UTR must contribute to verified revenue."""
        RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('350.00'),
            provider=self.provider_profile,
            booking=self.booking_completed,
            description='Actual Commission',
            status='completed',
            is_demo=False,
            verification_status='verified',
            has_evidence=True,
            transaction_reference='UPI-UTR-987654321012',
            payment_method='upi'
        )
        self.client.login(username='rgm_admin', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.context['verified_revenue'], Decimal('350.00'))
        self.assertEqual(response.context['verified_commission_revenue'], Decimal('350.00'))

    # 2b. Actual transaction without evidence excluded
    def test_actual_transaction_without_evidence_excluded_from_verified_revenue(self):
        """Transactions marked verified but lacking external audit evidence (has_evidence=False) must be excluded from verified revenue."""
        RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('500.00'),
            provider=self.provider_profile,
            booking=self.booking_completed,
            description='Missing Evidence Commission',
            status='completed',
            is_demo=False,
            verification_status='verified',
            has_evidence=False,
            transaction_reference='UPI-UTR-987654321012'
        )
        self.client.login(username='rgm_admin', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.context['verified_revenue'], Decimal('0.00'))

    # 2c. Actual transaction without reference excluded
    def test_actual_transaction_without_reference_excluded_from_verified_revenue(self):
        """Transactions marked verified with evidence but lacking a valid transaction reference/UTR must be excluded."""
        RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('500.00'),
            provider=self.provider_profile,
            booking=self.booking_completed,
            description='Missing UTR Commission',
            status='completed',
            is_demo=False,
            verification_status='verified',
            has_evidence=True,
            transaction_reference=''
        )
        self.client.login(username='rgm_admin', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.context['verified_revenue'], Decimal('0.00'))

    # 3. Unverified transaction excluded
    def test_unverified_transaction_excluded(self):
        """Actual transactions awaiting audit (verification_status='pending') must not count as verified revenue."""
        RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('400.00'),
            provider=self.provider_profile,
            booking=self.booking_completed,
            description='Pending Commission',
            status='completed',
            is_demo=False,
            verification_status='pending'
        )
        self.client.login(username='rgm_admin', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.context['verified_revenue'], Decimal('0.00'))
        self.assertEqual(response.context['pending_audit_count'], 1)

    # 4. Completed booking commission calculated correctly
    def test_completed_booking_commission_calculated_correctly(self):
        """When an accepted booking is completed, 10% platform commission is accurately recorded."""
        booking = Booking.objects.create(
            service=self.service,
            customer=self.customer_user,
            booking_date=date.today(),
            booking_time=time(11, 0),
            total_amount=Decimal('4000.00'),
            commission_rate=Decimal('10.00'),
            status='accepted',
            address='Villa 44, Kannur'
        )
        self.client.login(username='rgm_provider', password='password123')
        self.client.post(reverse('provider_job_complete', kwargs={'booking_id': booking.id}))

        booking.refresh_from_db()
        self.assertEqual(booking.status, 'completed')
        self.assertEqual(booking.commission_amount, Decimal('400.00'))

        tx = RevenueTransaction.objects.filter(revenue_type='commission', booking=booking).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('400.00'))
        self.assertEqual(tx.provider, self.provider_profile)

    # 5. Duplicate commission prevented
    def test_duplicate_commission_prevented(self):
        """Repeated completion attempts on the same booking must not generate duplicate commission transactions."""
        booking = Booking.objects.create(
            service=self.service,
            customer=self.customer_user,
            booking_date=date.today(),
            booking_time=time(11, 0),
            total_amount=Decimal('3000.00'),
            commission_rate=Decimal('10.00'),
            status='accepted',
            address='Villa 44, Kannur'
        )
        self.client.login(username='rgm_provider', password='password123')
        self.client.post(reverse('provider_job_complete', kwargs={'booking_id': booking.id}))
        self.client.post(reverse('provider_job_complete', kwargs={'booking_id': booking.id}))

        count = RevenueTransaction.objects.filter(revenue_type='commission', booking=booking).count()
        self.assertEqual(count, 1)

    # 6. Subscription revenue calculated correctly
    def test_subscription_revenue_calculated_correctly(self):
        """Provider Pro upgrade must generate an exact ₹399 subscription revenue transaction."""
        self.client.login(username='rgm_provider', password='password123')
        self.client.post(reverse('provider_subscription'), {'action': 'upgrade_pro'})

        tx = RevenueTransaction.objects.filter(revenue_type='subscription', provider=self.provider_profile).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('399.00'))

    # 7. Featured listing revenue calculated correctly
    def test_featured_listing_revenue_calculated_correctly(self):
        """Promoting a service must generate an exact ₹99 featured listing transaction."""
        self.client.login(username='rgm_provider', password='password123')
        self.client.post(reverse('provider_feature_service', kwargs={'service_id': self.service.id}))

        tx = RevenueTransaction.objects.filter(revenue_type='featured', service=self.service).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('99.00'))

    # 8. Gross booking value separated from revenue
    def test_gross_booking_value_separated_from_revenue(self):
        """Gross Booking Value must reflect total customer payment, strictly separate from Servora commission."""
        self.client.login(username='rgm_admin', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        # Booking total is ₹5,000, while commission is ₹500
        self.assertEqual(response.context['gross_booking_value'], Decimal('5000.00'))
        self.assertNotEqual(response.context['gross_booking_value'], response.context['commission_revenue'])

    # 9. Provider earnings calculated correctly
    def test_provider_earnings_calculated_correctly(self):
        """Provider net earnings must be exactly (Gross Booking Value - 10% Commission)."""
        self.client.login(username='rgm_admin', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        # ₹5,000 - ₹500 = ₹4,500
        self.assertEqual(response.context['provider_earnings_total'], Decimal('4500.00'))

    # 10. Unauthorized user cannot access revenue evidence
    def test_unauthorized_user_cannot_access_revenue_evidence(self):
        """Regular customer accounts cannot access the RGM revenue evidence dashboard."""
        self.client.login(username='rgm_customer', password='password123')
        response = self.client.get(reverse('platform_revenue_evidence'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))

    # 11. Provider cannot access platform-wide revenue
    def test_provider_cannot_access_platform_wide_revenue(self):
        """Service provider accounts cannot access platform revenue or evidence."""
        self.client.login(username='rgm_provider', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))

    # 12. Revenue target calculation
    def test_revenue_target_calculation(self):
        """Target progress percentage must accurately reflect verified revenue against the ₹10,000 threshold."""
        RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('2500.00'),
            provider=self.provider_profile,
            description='Pilot Commission',
            status='completed',
            is_demo=False,
            verification_status='verified',
            has_evidence=True,
            transaction_reference='UPI-UTR-250000000000'
        )
        self.client.login(username='rgm_admin', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        self.assertEqual(response.context['target_revenue'], Decimal('10000.00'))
        # 2,500 / 10,000 = 25%
        self.assertEqual(response.context['target_progress_percent'], 25)

    # 13. Remaining revenue calculation
    def test_remaining_revenue_calculation(self):
        """Remaining target calculation must equal max(0, target - verified_revenue)."""
        RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('3000.00'),
            provider=self.provider_profile,
            description='Pilot Commission',
            status='completed',
            is_demo=False,
            verification_status='verified',
            has_evidence=True,
            transaction_reference='UPI-UTR-300000000000'
        )
        self.client.login(username='rgm_admin', password='password123')
        response = self.client.get(reverse('platform_revenue'))
        # 10,000 - 3,000 = 7,000
        self.assertEqual(response.context['remaining_to_target'], Decimal('7000.00'))

    # 14. Verification status filtering
    def test_verification_status_filtering(self):
        """Evidence page must accurately filter records by verification status."""
        RevenueTransaction.objects.create(
            revenue_type='commission', amount=Decimal('100.00'),
            provider=self.provider_profile, status='completed',
            is_demo=False, verification_status='verified',
            has_evidence=True, transaction_reference='UPI-UTR-100000000000'
        )
        RevenueTransaction.objects.create(
            revenue_type='commission', amount=Decimal('200.00'),
            provider=self.provider_profile, status='completed',
            is_demo=False, verification_status='pending'
        )
        RevenueTransaction.objects.create(
            revenue_type='commission', amount=Decimal('300.00'),
            provider=self.provider_profile, status='completed',
            is_demo=False, verification_status='rejected'
        )

        self.client.login(username='rgm_admin', password='password123')
        resp_verified = self.client.get(reverse('platform_revenue_evidence'), {'verification': 'verified'})
        self.assertEqual(resp_verified.context['transactions'].count(), 1)

        resp_rejected = self.client.get(reverse('platform_revenue_evidence'), {'verification': 'rejected'})
        self.assertEqual(resp_rejected.context['transactions'].count(), 1)

    # 15. Transaction reference handling
    def test_transaction_reference_handling(self):
        """Audit CSV export must properly include UTR and payment method for scrutiny."""
        RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('500.00'),
            provider=self.provider_profile,
            description='Test UTR Commission',
            status='completed',
            is_demo=False,
            verification_status='verified',
            transaction_reference='UPI-UTR-987654321012',
            payment_method='upi',
            has_evidence=True
        )
        self.client.login(username='rgm_admin', password='password123')
        response = self.client.get(reverse('platform_revenue_evidence'), {'export': 'csv'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode('utf-8')
        self.assertIn('UPI-UTR-987654321012', content)
        self.assertIn('UPI / QR Transfer', content)

    # 16. Admin revenue filtering
    def test_admin_revenue_filtering(self):
        """Admin can toggle between actual pilot records and demo seed records."""
        RevenueTransaction.objects.create(
            revenue_type='commission', amount=Decimal('100.00'),
            provider=self.provider_profile, status='completed', is_demo=False
        )
        RevenueTransaction.objects.create(
            revenue_type='commission', amount=Decimal('200.00'),
            provider=self.provider_profile, status='completed', is_demo=True
        )

        self.client.login(username='rgm_admin', password='password123')
        resp_actual = self.client.get(reverse('platform_revenue_evidence'), {'data': 'actual'})
        self.assertEqual(resp_actual.context['transactions'].count(), 1)

        resp_demo = self.client.get(reverse('platform_revenue_evidence'), {'data': 'demo'})
        self.assertEqual(resp_demo.context['transactions'].count(), 1)

    # 17. No fake GST information generated
    def test_no_fake_gst_information_generated(self):
        """Commercial receipt page must accurately display transaction details without fake GSTIN or tax compliance claims."""
        self.client.login(username='rgm_customer', password='password123')
        response = self.client.get(reverse('booking_receipt', kwargs={'booking_id': self.booking_completed.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'services/receipt.html')
        self.assertContains(response, 'SERVORA COMMERCIAL SERVICE RECEIPT')
        self.assertNotContains(response, 'GSTIN')
        self.assertNotContains(response, '18% GST')
        self.assertNotContains(response, 'Tax Invoice')


# ============================================================
# STAGE 8A: PAYMENT SYSTEM, CHECKOUT & SETTLEMENT TESTS
# ============================================================

class PaymentAndSettlementTests(TestCase):
    """
    Automated test suite verifying the Stage 8A payment system:
    Customer checkout, server-side amount calculation, 10% commission split,
    provider settlements (90%), test gateway adapter, webhook idempotency,
    refund protocol, and strict separation between payment, platform revenue,
    and RGM verified revenue.
    """

    def setUp(self):
        self.client = Client()

        # Create platform admin
        self.admin_user = User.objects.create_superuser(
            username='pay_admin',
            email='admin@servora.in',
            password='password123'
        )

        # Create Customer 1
        self.customer1 = User.objects.create_user(
            username='pay_customer_1',
            password='password123',
            first_name='Ananya',
            last_name='Nair'
        )

        # Create Customer 2
        self.customer2 = User.objects.create_user(
            username='pay_customer_2',
            password='password123',
            first_name='Karthik',
            last_name='Menon'
        )

        # Create Provider 1
        self.provider_user1 = User.objects.create_user(
            username='pay_provider_1',
            password='password123',
            first_name='Suresh',
            last_name='Kumar'
        )
        self.provider_profile1 = self.provider_user1.profile
        self.provider_profile1.role = 'provider'
        self.provider_profile1.city = 'Kannur'
        self.provider_profile1.is_verified = True
        self.provider_profile1.payout_upi_id = 'suresh@okhdfcbank'
        self.provider_profile1.payout_upi_name = 'Suresh Kumar'
        self.provider_profile1.payout_status = 'ready'
        self.provider_profile1.save()

        # Create Provider 2
        self.provider_user2 = User.objects.create_user(
            username='pay_provider_2',
            password='password123',
            first_name='Ramesh',
            last_name='Babu'
        )
        self.provider_profile2 = self.provider_user2.profile
        self.provider_profile2.role = 'provider'
        self.provider_profile2.city = 'Kochi'
        self.provider_profile2.is_verified = True
        self.provider_profile2.payout_upi_id = 'ramesh@icici'
        self.provider_profile2.payout_upi_name = 'Ramesh Babu'
        self.provider_profile2.payout_status = 'ready'
        self.provider_profile2.save()

        # Category & Service
        self.category = Category.objects.create(
            name='Home Electrical',
            slug='home-electrical',
            icon_name='zap',
            description='Electrical repair and installations.'
        )

        self.service1 = Service.objects.create(
            provider=self.provider_profile1,
            category=self.category,
            title='Ceiling Fan Installation & Wiring',
            slug='ceiling-fan-installation',
            description='Professional ceiling fan mounting with balanced blade testing.',
            price=Decimal('2000.00'),
            duration_estimate='1.5 Hours',
            location='Kannur',
            is_active=True
        )

        # Booking for Customer 1
        self.booking1 = Booking.objects.create(
            service=self.service1,
            customer=self.customer1,
            booking_date=date.today() + timedelta(days=2),
            booking_time=time(10, 0),
            status='pending',
            payment_status='unpaid',
            total_amount=Decimal('2000.00'),
            address='Skyline City View, Flat 4B, Kannur'
        )

    # 1. Customer can access own checkout
    def test_customer_can_access_own_checkout(self):
        self.client.login(username='pay_customer_1', password='password123')
        response = self.client.get(reverse('checkout', kwargs={'booking_id': self.booking1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'services/checkout.html')
        self.assertContains(response, 'Customer Checkout')
        self.assertContains(response, '2000')

    # 2. Customer cannot access another customer's checkout
    def test_customer_cannot_access_other_customer_checkout(self):
        self.client.login(username='pay_customer_2', password='password123')
        response = self.client.get(reverse('checkout', kwargs={'booking_id': self.booking1.id}))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('my_bookings'))

    # 3. Provider cannot access customer checkout
    def test_provider_cannot_access_customer_checkout(self):
        self.client.login(username='pay_provider_1', password='password123')
        response = self.client.get(reverse('checkout', kwargs={'booking_id': self.booking1.id}))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('service_detail', kwargs={'id': self.service1.id}))

    # 4. Server calculates payment amount
    def test_server_calculates_payment_amount(self):
        split = PaymentService.calculate_split(self.booking1.total_amount)
        self.assertEqual(split['gross_amount'], Decimal('2000.00'))
        self.assertEqual(split['commission_amount'], Decimal('200.00'))
        self.assertEqual(split['payout_amount'], Decimal('1800.00'))

    # 5. Amount cannot be manipulated from POST
    def test_amount_cannot_be_manipulated_from_post(self):
        self.client.login(username='pay_customer_1', password='password123')
        txn = PaymentService.create_payment_order(self.booking1, payment_method='upi')
        test_sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, 'pay_tamper_123')

        # Tampered POST data claiming amount is 1.00
        response = self.client.post(reverse('payment_success', kwargs={'booking_id': self.booking1.id}), {
            'gateway_order_id': txn.gateway_order_id,
            'gateway_payment_id': 'pay_tamper_123',
            'gateway_signature': test_sig,
            'payment_method': 'upi',
            'amount': '1.00'
        })
        self.assertEqual(response.status_code, 302)

        # Verify recorded transaction reflects server amount of 2000.00
        captured_txn = PaymentTransaction.objects.get(gateway_payment_id='pay_tamper_123')
        self.assertEqual(captured_txn.amount, Decimal('2000.00'))

    # 6. 10% commission calculated correctly
    def test_ten_percent_commission_calculated_correctly(self):
        split = PaymentService.calculate_split(Decimal('5000.00'))
        self.assertEqual(split['commission_amount'], Decimal('500.00'))

    # 7. Provider payout calculated correctly (90%)
    def test_provider_payout_calculated_correctly(self):
        split = PaymentService.calculate_split(Decimal('5000.00'))
        self.assertEqual(split['payout_amount'], Decimal('4500.00'))

    # 8. Successful payment creates PaymentTransaction
    def test_successful_payment_creates_payment_transaction(self):
        self.client.login(username='pay_customer_1', password='password123')
        txn = PaymentService.create_payment_order(self.booking1, payment_method='upi')
        test_sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, 'pay_success_001')

        response = self.client.post(reverse('payment_success', kwargs={'booking_id': self.booking1.id}), {
            'gateway_order_id': txn.gateway_order_id,
            'gateway_payment_id': 'pay_success_001',
            'gateway_signature': test_sig,
            'payment_method': 'upi'
        })
        self.assertEqual(response.status_code, 302)

        self.booking1.refresh_from_db()
        self.assertEqual(self.booking1.payment_status, 'paid')
        captured = PaymentTransaction.objects.filter(booking=self.booking1, status='captured').first()
        self.assertIsNotNone(captured)
        self.assertEqual(captured.gateway_payment_id, 'pay_success_001')

    # 9. Failed payment does not create revenue or settlement
    def test_failed_payment_does_not_create_revenue_or_settlement(self):
        self.client.login(username='pay_customer_1', password='password123')
        txn = PaymentService.create_payment_order(self.booking1, payment_method='upi')

        response = self.client.post(reverse('payment_failed', kwargs={'booking_id': self.booking1.id}), {
            'gateway_order_id': txn.gateway_order_id,
            'failure_reason': 'User bank server timed out'
        })
        self.assertEqual(response.status_code, 302)

        self.booking1.refresh_from_db()
        self.assertEqual(self.booking1.payment_status, 'failed')
        self.assertFalse(ProviderSettlement.objects.filter(booking=self.booking1).exists())
        self.assertFalse(RevenueTransaction.objects.filter(booking=self.booking1).exists())

    # 10. Duplicate payment callback is idempotent
    def test_duplicate_payment_callback_is_idempotent(self):
        txn = PaymentService.create_payment_order(self.booking1, payment_method='upi')
        test_sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, 'pay_idem_001')

        # First capture
        PaymentService.verify_and_capture_payment(
            booking=self.booking1,
            gateway_order_id=txn.gateway_order_id,
            gateway_payment_id='pay_idem_001',
            gateway_signature=test_sig,
            payment_method='upi'
        )

        # Second capture re-call
        PaymentService.verify_and_capture_payment(
            booking=self.booking1,
            gateway_order_id=txn.gateway_order_id,
            gateway_payment_id='pay_idem_001',
            gateway_signature=test_sig,
            payment_method='upi'
        )

        # Must have exactly 1 PaymentTransaction and 1 ProviderSettlement
        self.assertEqual(PaymentTransaction.objects.filter(booking=self.booking1, status='captured').count(), 1)
        self.assertEqual(ProviderSettlement.objects.filter(booking=self.booking1).count(), 1)

    # 11. Duplicate webhook is idempotent
    def test_duplicate_webhook_is_idempotent(self):
        txn = PaymentService.create_payment_order(self.booking1, payment_method='upi')
        test_sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, 'pay_wh_001')

        import json
        payload = json.dumps({
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'order_id': txn.gateway_order_id,
                        'id': 'pay_wh_001',
                        'method': 'upi',
                        'signature': test_sig
                    }
                }
            }
        }).encode('utf-8')
        wh_sig = TestGatewayAdapter.generate_webhook_signature(payload)

        # Send webhook 1
        resp1 = self.client.post(
            reverse('payment_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_X_PAYMENT_SIGNATURE=wh_sig
        )
        self.assertEqual(resp1.status_code, 200)

        # Send webhook 2 (identical re-delivery)
        resp2 = self.client.post(
            reverse('payment_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_X_PAYMENT_SIGNATURE=wh_sig
        )
        self.assertEqual(resp2.status_code, 200)

        self.assertEqual(PaymentTransaction.objects.filter(booking=self.booking1, status='captured').count(), 1)
        self.assertEqual(ProviderSettlement.objects.filter(booking=self.booking1).count(), 1)

    # 12. Payment reference stored correctly
    def test_payment_reference_stored_correctly(self):
        txn = PaymentService.create_payment_order(self.booking1, payment_method='upi')
        test_sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, 'pay_ref_test_999')

        captured = PaymentService.verify_and_capture_payment(
            booking=self.booking1,
            gateway_order_id=txn.gateway_order_id,
            gateway_payment_id='pay_ref_test_999',
            gateway_signature=test_sig,
            payment_method='upi'
        )
        self.assertEqual(captured.gateway_payment_id, 'pay_ref_test_999')
        self.assertEqual(captured.gateway_order_id, txn.gateway_order_id)
        self.assertEqual(captured.gateway_signature, test_sig)

    # 13. Booking payment status changes correctly
    def test_booking_payment_status_changes_correctly(self):
        self.assertEqual(self.booking1.payment_status, 'unpaid')
        txn = PaymentService.create_payment_order(self.booking1)
        sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, 'pay_status_123')
        PaymentService.verify_and_capture_payment(self.booking1, txn.gateway_order_id, 'pay_status_123', sig)
        self.booking1.refresh_from_db()
        self.assertEqual(self.booking1.payment_status, 'paid')

    # 14. Provider settlement created correctly
    def test_provider_settlement_created_correctly(self):
        txn = PaymentService.create_payment_order(self.booking1)
        sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, 'pay_set_test')
        PaymentService.verify_and_capture_payment(self.booking1, txn.gateway_order_id, 'pay_set_test', sig)

        settlement = ProviderSettlement.objects.get(booking=self.booking1)
        self.assertEqual(settlement.gross_amount, Decimal('2000.00'))
        self.assertEqual(settlement.commission_amount, Decimal('200.00'))
        self.assertEqual(settlement.payout_amount, Decimal('1800.00'))
        self.assertEqual(settlement.status, 'pending')

    # 15. Provider sees only own settlements
    def test_provider_sees_only_own_settlements(self):
        # Create settlement for provider 1
        ProviderSettlement.objects.create(
            booking=self.booking1,
            provider=self.provider_profile1,
            gross_amount=Decimal('2000.00'),
            commission_amount=Decimal('200.00'),
            payout_amount=Decimal('1800.00'),
            status='pending'
        )

        # Create service & booking for provider 2
        service2 = Service.objects.create(
            provider=self.provider_profile2,
            category=self.category,
            title='Inverter Installation',
            slug='inverter-installation',
            description='Home power backup setup.',
            price=Decimal('3000.00'),
            location='Kochi'
        )
        booking2 = Booking.objects.create(
            service=service2,
            customer=self.customer2,
            booking_date=date.today(),
            booking_time=time(14, 0),
            total_amount=Decimal('3000.00'),
            status='pending'
        )
        ProviderSettlement.objects.create(
            booking=booking2,
            provider=self.provider_profile2,
            gross_amount=Decimal('3000.00'),
            commission_amount=Decimal('300.00'),
            payout_amount=Decimal('2700.00'),
            status='pending'
        )

        # Provider 1 views settlements
        self.client.login(username='pay_provider_1', password='password123')
        response = self.client.get(reverse('provider_settlements'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['settlements'].count(), 1)
        self.assertEqual(response.context['settlements'].first().provider, self.provider_profile1)

    # 16. Customer sees own payment history
    def test_customer_sees_own_payment_history(self):
        PaymentTransaction.objects.create(
            booking=self.booking1,
            customer=self.customer1,
            provider=self.provider_profile1,
            amount=Decimal('2000.00'),
            status='captured'
        )
        self.client.login(username='pay_customer_1', password='password123')
        response = self.client.get(reverse('customer_payment_history'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['payments'].count(), 1)

    # 17. Unauthorized user cannot access platform payment dashboard
    def test_unauthorized_user_cannot_access_platform_payment_dashboard(self):
        # Unauthenticated
        resp_anon = self.client.get(reverse('platform_payments'))
        self.assertEqual(resp_anon.status_code, 302)

        # Customer
        self.client.login(username='pay_customer_1', password='password123')
        resp_cust = self.client.get(reverse('platform_payments'))
        self.assertEqual(resp_cust.status_code, 302)

    # 18. Provider cannot access platform payment dashboard
    def test_provider_cannot_access_platform_payment_dashboard(self):
        self.client.login(username='pay_provider_1', password='password123')
        response = self.client.get(reverse('platform_payments'))
        self.assertEqual(response.status_code, 302)

    # 19. Refund changes payment status
    def test_refund_changes_payment_status(self):
        txn = PaymentService.create_payment_order(self.booking1)
        sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, 'pay_ref_abc')
        PaymentService.verify_and_capture_payment(self.booking1, txn.gateway_order_id, 'pay_ref_abc', sig)

        result = PaymentService.handle_refund(self.booking1, reason='Customer requested refund')
        self.assertTrue(result['success'])

        self.booking1.refresh_from_db()
        self.assertEqual(self.booking1.payment_status, 'refunded')
        captured_txn = PaymentTransaction.objects.get(gateway_payment_id='pay_ref_abc')
        self.assertEqual(captured_txn.status, 'refunded')
        settlement = ProviderSettlement.objects.get(booking=self.booking1)
        self.assertEqual(settlement.status, 'refunded')

    # 20. Refunded payment does not remain valid revenue
    def test_refunded_payment_does_not_remain_valid_revenue(self):
        # Setup completed booking with commission revenue
        self.booking1.status = 'completed'
        self.booking1.payment_status = 'paid'
        self.booking1.save()

        rev = RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('200.00'),
            provider=self.provider_profile1,
            booking=self.booking1,
            description='10% Platform Commission',
            status='completed',
            verification_status='verified',
            has_evidence=True,
            transaction_reference='UTR_REF_123456'
        )

        PaymentService.handle_refund(self.booking1, reason='Refunded job')
        rev.refresh_from_db()
        self.assertEqual(rev.status, 'refunded')
        self.assertFalse(rev.is_rgm_verified)

    # 21. Demo revenue remains excluded from RGM verified revenue
    def test_demo_revenue_remains_excluded_from_rgm_verified_revenue(self):
        demo_tx = RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('500.00'),
            provider=self.provider_profile1,
            is_demo=True,
            status='completed',
            verification_status='verified',
            has_evidence=True,
            transaction_reference='DEMO_REF'
        )
        self.assertFalse(demo_tx.is_rgm_verified)

    # 22. Successful payment alone does not mark RGM transaction verified
    def test_successful_payment_alone_does_not_mark_rgm_verified(self):
        txn = PaymentService.create_payment_order(self.booking1)
        sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, 'pay_rgm_check')
        PaymentService.verify_and_capture_payment(self.booking1, txn.gateway_order_id, 'pay_rgm_check', sig)

        # Check that no RevenueTransaction exists yet because service is not completed
        self.assertFalse(RevenueTransaction.objects.filter(booking=self.booking1).exists())

    # 23. Evidence requirements remain enforced
    def test_evidence_requirements_remain_enforced(self):
        actual_tx = RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('200.00'),
            provider=self.provider_profile1,
            booking=self.booking1,
            status='completed',
            verification_status='verified',
            has_evidence=False,  # No evidence!
            transaction_reference='UTR_NO_EVIDENCE'
        )
        self.assertFalse(actual_tx.is_rgm_verified)

    # 24. Existing receipt displays payment reference
    def test_existing_receipt_displays_payment_reference(self):
        self.booking1.status = 'completed'
        self.booking1.payment_status = 'paid'
        self.booking1.save()

        PaymentTransaction.objects.create(
            booking=self.booking1,
            customer=self.customer1,
            provider=self.provider_profile1,
            amount=Decimal('2000.00'),
            gateway_payment_id='pay_receipt_disp_123',
            status='captured'
        )

        self.client.login(username='pay_customer_1', password='password123')
        response = self.client.get(reverse('booking_receipt', kwargs={'booking_id': self.booking1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pay_receipt_disp_123')

    # 25. No fake GSTIN or tax information generated
    def test_no_fake_gstin_generated(self):
        self.booking1.status = 'completed'
        self.booking1.save()
        self.client.login(username='pay_customer_1', password='password123')
        response = self.client.get(reverse('booking_receipt', kwargs={'booking_id': self.booking1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'GSTIN')
        self.assertNotContains(response, 'Tax Invoice')

    # 26. Provider UPI ID is not publicly exposed
    def test_provider_upi_id_not_publicly_exposed(self):
        response = self.client.get(reverse('provider_profile', kwargs={'id': self.provider_profile1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'suresh@okhdfcbank')

    # 27. Payout status cannot be marked paid incorrectly
    def test_payout_status_cannot_be_marked_paid_incorrectly(self):
        settlement = PaymentService.create_provider_settlement(self.booking1)
        self.assertEqual(settlement.status, 'pending')
        self.assertNotEqual(settlement.status, 'paid')

    # 28. Existing commission idempotency remains intact
    def test_existing_commission_idempotency_remains_intact(self):
        self.client.login(username='pay_provider_1', password='password123')
        self.booking1.status = 'accepted'
        self.booking1.save()

        # Complete booking
        self.client.post(reverse('provider_job_complete', kwargs={'booking_id': self.booking1.id}))
        count1 = RevenueTransaction.objects.filter(booking=self.booking1, revenue_type='commission').count()
        self.assertEqual(count1, 1)

        # Try completing again (should be rejected/prevented)
        self.client.post(reverse('provider_job_complete', kwargs={'booking_id': self.booking1.id}))
        count2 = RevenueTransaction.objects.filter(booking=self.booking1, revenue_type='commission').count()
        self.assertEqual(count2, 1)

    # 29. Existing booking lifecycle remains intact
    def test_existing_booking_lifecycle_remains_intact(self):
        self.assertEqual(self.booking1.status, 'pending')
        self.client.login(username='pay_provider_1', password='password123')
        self.client.post(reverse('provider_job_accept', kwargs={'booking_id': self.booking1.id}))
        self.booking1.refresh_from_db()
        self.assertEqual(self.booking1.status, 'accepted')

    # 30. Webhook signature verification rejects invalid signatures
    def test_webhook_signature_verification_rejects_invalid(self):
        payload = b'{"event": "payment.captured"}'
        response = self.client.post(
            reverse('payment_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_X_PAYMENT_SIGNATURE='invalid_tampered_signature_123'
        )
        self.assertEqual(response.status_code, 400)


class DynamicPricingAndUPITests(TestCase):
    """
    Stage 8B Comprehensive Automated Test Suite:
    - Dynamic Job Pricing & Materials Lifecycle
    - Server-Side Price Calculation & Tamper Protection
    - Customer Materials Approval & Rejection Workflows
    - 10% Platform Commission Strictly on Service Charge (0% on Materials)
    - 100% Provider Material Reimbursement in Settlements
    - UPI-Only Checkout Architecture (Removal of Cards/NetBanking)
    - UPI QR Intent Data Generation & Sandbox Payments
    - File Security & Access Control for Purchase Receipts
    - Notifications & Financial Ledger Integrity
    """

    def setUp(self):
        self.client = Client()

        # Provider user
        self.provider_user = User.objects.create_user(
            username='stage8b_provider',
            password='password123',
            first_name='Anand',
            last_name='Kumar'
        )
        self.provider_profile = self.provider_user.profile
        self.provider_profile.role = 'provider'
        self.provider_profile.payout_upi_id = 'anand@okhdfcbank'
        self.provider_profile.payout_upi_name = 'Anand Kumar'
        self.provider_profile.payout_status = 'ready'
        self.provider_profile.save()

        # Other provider user (for cross-tenant checks)
        self.other_provider_user = User.objects.create_user(
            username='stage8b_other_provider',
            password='password123'
        )
        self.other_provider_profile = self.other_provider_user.profile
        self.other_provider_profile.role = 'provider'
        self.other_provider_profile.save()

        # Customer user
        self.customer_user = User.objects.create_user(
            username='stage8b_customer',
            password='password123',
            first_name='Rahul',
            last_name='Nair'
        )
        self.customer_profile = self.customer_user.profile
        self.customer_profile.role = 'customer'
        self.customer_profile.save()

        # Other customer user (for cross-tenant checks)
        self.other_customer_user = User.objects.create_user(
            username='stage8b_other_customer',
            password='password123'
        )
        self.other_customer_profile = self.other_customer_user.profile
        self.other_customer_profile.role = 'customer'
        self.other_customer_profile.save()

        # Staff user
        self.staff_user = User.objects.create_superuser(
            username='stage8b_admin',
            password='password123',
            email='admin@servora.local'
        )

        # Category and Service (Base Price: ₹1,000)
        self.category = Category.objects.create(name='Plumbing Care', slug='plumbing-care', icon_name='wrench')
        self.service = Service.objects.create(
            provider=self.provider_profile,
            category=self.category,
            title='Main Line Pipe Fitting',
            price=Decimal('1000.00'),
            duration_estimate='2 hours',
            location='Kannur'
        )

        # In-progress accepted booking
        self.booking = Booking.objects.create(
            service=self.service,
            customer=self.customer_user,
            booking_date=date.today() + timedelta(days=2),
            booking_time=time(10, 0),
            service_amount=Decimal('1000.00'),
            total_amount=Decimal('1000.00'),
            status='accepted',
            payment_status='unpaid',
            address='Fort Road, Kannur'
        )

    # 1. Material creation & server-side total_price calculation
    def test_material_creation_server_side_calculation(self):
        mat = BookingMaterial.objects.create(
            booking=self.booking,
            name='1-Inch PVC Pipe (3m)',
            quantity=2,
            unit_price=Decimal('150.00'),
            added_by=self.provider_user
        )
        # 2 * 150.00 = 300.00 calculated strictly server-side
        self.assertEqual(mat.total_price, Decimal('300.00'))
        self.assertEqual(mat.status, 'pending')

    # 2. Material ownership: Provider can add materials to own accepted booking
    def test_material_ownership_provider_only(self):
        self.client.login(username='stage8b_provider', password='password123')
        response = self.client.post(reverse('provider_add_material', kwargs={'booking_id': self.booking.id}), {
            'name': 'Sealant Compound',
            'description': 'Waterproof silicone paste',
            'quantity': 1,
            'unit_price': '50.00',
        })
        self.assertEqual(response.status_code, 302)
        mat = BookingMaterial.objects.filter(booking=self.booking, name='Sealant Compound').first()
        self.assertIsNotNone(mat)
        self.assertEqual(mat.total_price, Decimal('50.00'))

    # 3. Other provider cannot add materials to another provider's booking
    def test_other_provider_cannot_add_materials(self):
        self.client.login(username='stage8b_other_provider', password='password123')
        response = self.client.post(reverse('provider_add_material', kwargs={'booking_id': self.booking.id}), {
            'name': 'Unauthorized Item',
            'quantity': 1,
            'unit_price': '100.00',
        })
        self.assertEqual(response.status_code, 404)
        self.assertFalse(BookingMaterial.objects.filter(name='Unauthorized Item').exists())

    # 4. Customer cannot access provider add material view
    def test_customer_cannot_add_materials(self):
        self.client.login(username='stage8b_customer', password='password123')
        response = self.client.get(reverse('provider_add_material', kwargs={'booking_id': self.booking.id}))
        # provider_required redirects non-providers to home
        self.assertEqual(response.status_code, 302)

    # 5. Quantity and unit price validations reject zero or negative inputs
    def test_quantity_and_price_validation(self):
        self.client.login(username='stage8b_provider', password='password123')
        # Negative quantity
        response = self.client.post(reverse('provider_add_material', kwargs={'booking_id': self.booking.id}), {
            'name': 'Invalid Item',
            'quantity': -2,
            'unit_price': '50.00',
        })
        self.assertFalse(BookingMaterial.objects.filter(name='Invalid Item').exists())

        # Zero unit price
        response2 = self.client.post(reverse('provider_add_material', kwargs={'booking_id': self.booking.id}), {
            'name': 'Zero Price Item',
            'quantity': 1,
            'unit_price': '0.00',
        })
        self.assertFalse(BookingMaterial.objects.filter(name='Zero Price Item').exists())

    # 6. Multiple materials aggregation calculates correct pending materials total
    def test_multiple_materials_aggregation(self):
        BookingMaterial.objects.create(booking=self.booking, name='PVC Pipe', quantity=1, unit_price=Decimal('180.00'))
        BookingMaterial.objects.create(booking=self.booking, name='Connector', quantity=1, unit_price=Decimal('70.00'))
        BookingMaterial.objects.create(booking=self.booking, name='Sealant', quantity=1, unit_price=Decimal('50.00'))

        self.assertEqual(self.booking.materials.count(), 3)
        self.assertEqual(self.booking.pending_materials_total, Decimal('300.00'))
        self.assertEqual(self.booking.approved_materials_total, Decimal('0.00'))

    # 7. Customer approval workflow approves materials and locks new final amount
    def test_customer_approval_workflow(self):
        BookingMaterial.objects.create(booking=self.booking, name='PVC Pipe', quantity=1, unit_price=Decimal('180.00'))
        BookingMaterial.objects.create(booking=self.booking, name='Connector', quantity=1, unit_price=Decimal('70.00'))
        BookingMaterial.objects.create(booking=self.booking, name='Sealant', quantity=1, unit_price=Decimal('50.00'))

        self.client.login(username='stage8b_customer', password='password123')
        response = self.client.post(reverse('customer_approve_materials', kwargs={'booking_id': self.booking.id}))
        self.assertEqual(response.status_code, 302)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.materials_amount, Decimal('300.00'))
        self.assertEqual(self.booking.total_amount, Decimal('1300.00'))
        self.assertEqual(self.booking.final_amount, Decimal('1300.00'))
        self.assertEqual(self.booking.materials.filter(status='approved').count(), 3)

    # 8. Another customer cannot approve another customer's materials
    def test_other_customer_cannot_approve_materials(self):
        BookingMaterial.objects.create(booking=self.booking, name='PVC Pipe', quantity=1, unit_price=Decimal('180.00'))
        self.client.login(username='stage8b_other_customer', password='password123')
        response = self.client.post(reverse('customer_approve_materials', kwargs={'booking_id': self.booking.id}))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.booking.materials.filter(status='approved').count(), 0)

    # 9. Customer rejection preserves base service amount and marks materials rejected
    def test_customer_rejection_workflow(self):
        BookingMaterial.objects.create(booking=self.booking, name='PVC Pipe', quantity=1, unit_price=Decimal('180.00'))
        self.client.login(username='stage8b_customer', password='password123')
        response = self.client.post(reverse('customer_reject_materials', kwargs={'booking_id': self.booking.id}))
        self.assertEqual(response.status_code, 302)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.materials_amount, Decimal('0.00'))
        self.assertEqual(self.booking.total_amount, Decimal('1000.00'))
        self.assertEqual(self.booking.materials.filter(status='rejected').count(), 1)

    # 10. Final amount is server-controlled and rejects client tampering
    def test_tampered_final_amount_ignored(self):
        self.client.login(username='stage8b_customer', password='password123')
        response = self.client.post(reverse('payment_create', kwargs={'booking_id': self.booking.id}), {
            'amount': '1.00',  # Malicious tampered amount
            'payment_method': 'upi'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Server must enforce actual booking.total_amount (1000.00), not the tampered 1.00
        self.assertEqual(data['amount'], '1000.00')

    # 11. Platform commission is calculated strictly on service charge (10% of 1000 = 100)
    def test_commission_calculated_only_on_service(self):
        self.booking.materials_amount = Decimal('300.00')
        self.booking.save()
        self.assertEqual(self.booking.total_amount, Decimal('1300.00'))
        self.assertEqual(self.booking.commission_amount, Decimal('100.00'))

    # 12. Materials are 100% excluded from platform commission in PaymentService.calculate_split
    def test_materials_excluded_from_commission(self):
        split = PaymentService.calculate_split(
            gross_amount=Decimal('1300.00'),
            materials_amount=Decimal('300.00'),
            service_amount=Decimal('1000.00')
        )
        self.assertEqual(split['gross_amount'], Decimal('1300.00'))
        self.assertEqual(split['service_amount'], Decimal('1000.00'))
        self.assertEqual(split['materials_amount'], Decimal('300.00'))
        self.assertEqual(split['commission_amount'], Decimal('100.00'))
        self.assertEqual(split['payout_amount'], Decimal('1200.00'))

    # 13. Provider payout calculation: 90% service earnings + 100% materials reimbursement
    def test_provider_payout_calculation(self):
        self.booking.materials_amount = Decimal('300.00')
        self.booking.save()
        # (1000 - 100) + 300 = 1200.00
        self.assertEqual(self.booking.provider_earning, Decimal('1200.00'))

    # 14. Checkout UI is UPI-only (No Card, No Net Banking, No Wallet)
    def test_checkout_is_upi_only(self):
        self.client.login(username='stage8b_customer', password='password123')
        response = self.client.get(reverse('checkout', kwargs={'booking_id': self.booking.id}))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('Pay Securely Using UPI', content)
        self.assertIn('Scan UPI QR', content)
        self.assertIn('UPI ID / VPA', content)
        self.assertNotIn('Credit / Debit Card', content)
        self.assertNotIn('Net Banking', content)

    # 15. UPI QR intent data generation matches standard NPCI UPI format
    def test_upi_qr_intent_generation(self):
        order_id = 'order_test_999'
        qr_uri = TestGatewayAdapter.generate_upi_qr_data(order_id, Decimal('1300.00'), vpa='servora.sandbox@upi')
        self.assertTrue(qr_uri.startswith('upi://pay?'))
        self.assertIn('pa=servora.sandbox%40upi', qr_uri)
        self.assertIn('am=1300.00', qr_uri)
        self.assertIn('cu=INR', qr_uri)

    # 16. Successful test UPI payment marks booking paid and creates ProviderSettlement
    def test_successful_test_upi_payment_capture(self):
        self.booking.materials_amount = Decimal('300.00')
        self.booking.save()

        txn = PaymentService.create_payment_order(self.booking, payment_method='upi')
        payment_id = 'pay_test_upi_captured_001'
        sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, payment_id)

        self.client.login(username='stage8b_customer', password='password123')
        response = self.client.post(reverse('payment_success', kwargs={'booking_id': self.booking.id}), {
            'gateway_order_id': txn.gateway_order_id,
            'gateway_payment_id': payment_id,
            'gateway_signature': sig,
            'payment_method': 'upi'
        })
        self.assertEqual(response.status_code, 302)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, 'paid')

        settlement = ProviderSettlement.objects.filter(booking=self.booking).first()
        self.assertIsNotNone(settlement)
        self.assertEqual(settlement.gross_amount, Decimal('1300.00'))
        self.assertEqual(settlement.service_amount, Decimal('1000.00'))
        self.assertEqual(settlement.materials_amount, Decimal('300.00'))
        self.assertEqual(settlement.commission_amount, Decimal('100.00'))
        self.assertEqual(settlement.payout_amount, Decimal('1200.00'))
        self.assertEqual(settlement.status, 'pending')

    # 17. Failed payment does not create revenue or settlement
    def test_failed_payment_does_not_create_settlement(self):
        self.client.login(username='stage8b_customer', password='password123')
        response = self.client.post(reverse('payment_failed', kwargs={'booking_id': self.booking.id}), {
            'failure_reason': 'User aborted UPI pin entry'
        })
        self.assertEqual(response.status_code, 302)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, 'failed')
        self.assertEqual(ProviderSettlement.objects.filter(booking=self.booking).count(), 0)
        self.assertEqual(RevenueTransaction.objects.filter(booking=self.booking).count(), 0)

    # 18. Customer can retry payment after failure
    def test_retry_payment_after_failure(self):
        PaymentService.handle_payment_failure(self.booking, failure_reason='Timeout')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, 'failed')

        # Retry and capture successfully
        txn = PaymentService.create_payment_order(self.booking, payment_method='upi')
        payment_id = 'pay_retry_success_999'
        sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, payment_id)

        PaymentService.verify_and_capture_payment(
            booking=self.booking,
            gateway_order_id=txn.gateway_order_id,
            gateway_payment_id=payment_id,
            gateway_signature=sig,
            payment_method='upi'
        )

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, 'paid')
        self.assertEqual(ProviderSettlement.objects.filter(booking=self.booking).count(), 1)

    # 19. Duplicate webhook processing is idempotent
    def test_duplicate_webhook_idempotency(self):
        txn = PaymentService.create_payment_order(self.booking, payment_method='upi')
        payment_id = 'pay_webhook_idem_123'
        sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, payment_id)

        import json
        payload = json.dumps({
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'order_id': txn.gateway_order_id,
                        'id': payment_id,
                        'signature': sig,
                        'method': 'upi'
                    }
                }
            }
        }).encode('utf-8')
        wh_sig = TestGatewayAdapter.generate_webhook_signature(payload)

        # First webhook call
        resp1 = self.client.post(reverse('payment_webhook'), data=payload, content_type='application/json', HTTP_X_PAYMENT_SIGNATURE=wh_sig)
        self.assertEqual(resp1.status_code, 200)

        # Duplicate webhook call
        resp2 = self.client.post(reverse('payment_webhook'), data=payload, content_type='application/json', HTTP_X_PAYMENT_SIGNATURE=wh_sig)
        self.assertEqual(resp2.status_code, 200)

        # Must have exactly 1 settlement and 1 captured transaction
        self.assertEqual(ProviderSettlement.objects.filter(booking=self.booking).count(), 1)
        self.assertEqual(PaymentTransaction.objects.filter(booking=self.booking, status='captured').count(), 1)

    # 20. Full refund refunds entire customer payment (service + approved materials)
    def test_full_refund_includes_approved_materials(self):
        self.booking.materials_amount = Decimal('300.00')
        self.booking.save()

        txn = PaymentService.create_payment_order(self.booking, payment_method='upi')
        payment_id = 'pay_refund_test_777'
        sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, payment_id)
        PaymentService.verify_and_capture_payment(self.booking, txn.gateway_order_id, payment_id, sig)

        # Process refund
        refund_result = PaymentService.handle_refund(self.booking, reason='Service cancelled by client')
        self.assertTrue(refund_result['success'])

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, 'refunded')

        settlement = ProviderSettlement.objects.filter(booking=self.booking).first()
        self.assertEqual(settlement.status, 'refunded')

        captured_txn = PaymentTransaction.objects.filter(booking=self.booking, gateway_payment_id=payment_id).first()
        self.assertEqual(captured_txn.status, 'refunded')

    # 21. Provider payout settings are private (never shown to customer)
    def test_provider_upi_privacy_not_public(self):
        self.client.login(username='stage8b_customer', password='password123')
        response = self.client.get(reverse('service_detail', kwargs={'id': self.service.id}))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('anand@okhdfcbank', response.content.decode('utf-8'))

    # 22. Material purchase receipt access control rejects unauthorized users
    def test_receipt_access_control(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        test_file = SimpleUploadedFile("bill.pdf", b"%PDF-1.4 test invoice receipt content", content_type="application/pdf")
        mat = BookingMaterial.objects.create(
            booking=self.booking,
            name='Valve',
            quantity=1,
            unit_price=Decimal('200.00'),
            receipt_image=test_file
        )

        # Unauthorized other customer gets 403
        self.client.login(username='stage8b_other_customer', password='password123')
        resp_unauth = self.client.get(reverse('secure_material_receipt', kwargs={'material_id': mat.id}))
        self.assertEqual(resp_unauth.status_code, 403)

        # Authorized booking customer can access
        self.client.login(username='stage8b_customer', password='password123')
        resp_auth = self.client.get(reverse('secure_material_receipt', kwargs={'material_id': mat.id}))
        self.assertEqual(resp_auth.status_code, 200)

    # 23. Notification created for customer when provider adds materials
    def test_notification_on_material_addition(self):
        self.client.login(username='stage8b_provider', password='password123')
        self.client.post(reverse('provider_add_material', kwargs={'booking_id': self.booking.id}), {
            'name': 'Gasket Set',
            'quantity': 1,
            'unit_price': '120.00',
        })
        notif = Notification.objects.filter(recipient=self.customer_user, notification_type='materials_added').first()
        self.assertIsNotNone(notif)
        self.assertIn('Gasket Set', notif.message)

    # 24. Notification created for provider when customer approves materials
    def test_notification_on_material_approval(self):
        BookingMaterial.objects.create(booking=self.booking, name='Filter', quantity=1, unit_price=Decimal('150.00'))
        self.client.login(username='stage8b_customer', password='password123')
        self.client.post(reverse('customer_approve_materials', kwargs={'booking_id': self.booking.id}))

        notif = Notification.objects.filter(recipient=self.provider_user, notification_type='materials_approved').first()
        self.assertIsNotNone(notif)
        self.assertIn('approved material costs', notif.message)

    # 25. Notification created for provider when customer rejects materials
    def test_notification_on_material_rejection(self):
        BookingMaterial.objects.create(booking=self.booking, name='Extra Pipe', quantity=1, unit_price=Decimal('250.00'))
        self.client.login(username='stage8b_customer', password='password123')
        self.client.post(reverse('customer_reject_materials', kwargs={'booking_id': self.booking.id}))

        notif = Notification.objects.filter(recipient=self.provider_user, notification_type='materials_rejected').first()
        self.assertIsNotNone(notif)
        self.assertIn('declined the additional material costs', notif.message)

    # 26. Provider cannot edit approved materials
    def test_provider_cannot_edit_approved_materials(self):
        mat = BookingMaterial.objects.create(booking=self.booking, name='Valve', quantity=1, unit_price=Decimal('200.00'), status='approved')
        self.client.login(username='stage8b_provider', password='password123')
        response = self.client.post(reverse('provider_edit_material', kwargs={'material_id': mat.id}), {
            'name': 'Tampered Valve Name',
            'quantity': 2,
            'unit_price': '400.00'
        })
        mat.refresh_from_db()
        self.assertEqual(mat.name, 'Valve')
        self.assertEqual(mat.total_price, Decimal('200.00'))

    # 27. Provider cannot delete approved materials
    def test_provider_cannot_delete_approved_materials(self):
        mat = BookingMaterial.objects.create(booking=self.booking, name='Locked Part', quantity=1, unit_price=Decimal('100.00'), status='approved')
        self.client.login(username='stage8b_provider', password='password123')
        self.client.post(reverse('provider_delete_material', kwargs={'material_id': mat.id}))
        self.assertTrue(BookingMaterial.objects.filter(id=mat.id).exists())

    # 28. Provider cannot add materials to a completed booking
    def test_provider_cannot_add_materials_to_completed_booking(self):
        self.booking.status = 'completed'
        self.booking.save()
        self.client.login(username='stage8b_provider', password='password123')
        response = self.client.post(reverse('provider_add_material', kwargs={'booking_id': self.booking.id}), {
            'name': 'Late Item',
            'quantity': 1,
            'unit_price': '100.00'
        })
        self.assertFalse(BookingMaterial.objects.filter(name='Late Item').exists())

    # 29. Provider cannot add materials to a paid booking
    def test_provider_cannot_add_materials_to_paid_booking(self):
        self.booking.payment_status = 'paid'
        self.booking.save()
        self.client.login(username='stage8b_provider', password='password123')
        response = self.client.post(reverse('provider_add_material', kwargs={'booking_id': self.booking.id}), {
            'name': 'Post-Payment Item',
            'quantity': 1,
            'unit_price': '100.00'
        })
        self.assertFalse(BookingMaterial.objects.filter(name='Post-Payment Item').exists())

    # 30. Commercial receipt accurately displays dynamic pricing breakdown
    def test_commercial_receipt_breakdown(self):
        self.booking.status = 'completed'
        self.booking.payment_status = 'paid'
        self.booking.materials_amount = Decimal('300.00')
        self.booking.save()
        BookingMaterial.objects.create(booking=self.booking, name='Fittings', quantity=1, unit_price=Decimal('300.00'), status='approved')

        self.client.login(username='stage8b_customer', password='password123')
        response = self.client.get(reverse('booking_receipt', kwargs={'booking_id': self.booking.id}))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('Base Service Fee', content)
        self.assertIn('Approved Materials', content)
        self.assertIn('1300', content)

    # 31. Provider settlement list shows materials and service amounts
    def test_provider_settlements_ledger_view(self):
        ProviderSettlement.objects.create(
            booking=self.booking,
            provider=self.provider_profile,
            service_amount=Decimal('1000.00'),
            materials_amount=Decimal('300.00'),
            gross_amount=Decimal('1300.00'),
            commission_amount=Decimal('100.00'),
            payout_amount=Decimal('1200.00'),
            status='pending'
        )
        self.client.login(username='stage8b_provider', password='password123')
        response = self.client.get(reverse('provider_settlements'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('1200', content)
        self.assertIn('300', content)

    # 32. Demo revenue remains isolated from RGM verified revenue
    def test_rgm_verified_revenue_isolation(self):
        # Demo revenue transaction must remain demo
        demo_rev = RevenueTransaction.objects.create(
            revenue_type='commission',
            amount=Decimal('100.00'),
            provider=self.provider_profile,
            description='Demo test commission',
            is_demo=True,
            status='completed',
            verification_status='verified',
            has_evidence=True,
            transaction_reference='DEMO123'
        )
        self.assertFalse(demo_rev.is_rgm_verified)


# ============================================================
# STAGE 8B: SECURITY & PAYMENT HARDENING TESTS (20 TESTS)
# ============================================================

class Stage8BSecurityAndPaymentHardeningTests(TestCase):
    """
    Comprehensive security and verification test suite for Stage 8B UPI payments:
    1. Customer cannot mark payment paid manually.
    2. Customer cannot change final amount through POST.
    3. Customer cannot change payment amount through hidden form fields.
    4. Invalid webhook signature is rejected.
    5. Valid webhook marks payment paid.
    6. Wrong amount webhook does not mark payment paid.
    7. Wrong order ID does not mark payment paid.
    8. Wrong currency does not mark payment paid.
    9. Duplicate webhook does not duplicate transaction.
    10. Duplicate webhook does not duplicate settlement.
    11. Duplicate webhook does not duplicate notification.
    12. Provider UPI ID cannot become merchant VPA.
    13. QR contains correct merchant VPA.
    14. QR contains correct dynamic amount.
    15. Rejected materials are excluded from QR amount.
    16. Approved materials are included in QR amount.
    17. Opening UPI intent does not mark payment paid.
    18. Returning to success URL does not mark payment paid without verification.
    19. Test payment remains marked as test/simulated.
    20. UPI-only checkout does not expose card/netbanking payment options.
    """

    def setUp(self):
        import json
        from django.utils import timezone
        from django.conf import settings

        self.client = Client()
        self.customer = User.objects.create_user(
            username='sec_customer',
            password='password123',
            first_name='Rohan',
            last_name='Varma'
        )
        self.provider_user = User.objects.create_user(
            username='sec_provider',
            password='password123',
            first_name='Manoj',
            last_name='Pillai'
        )
        self.provider_profile = self.provider_user.profile
        self.provider_profile.role = 'provider'
        self.provider_profile.city = 'Kochi'
        self.provider_profile.payout_upi_id = 'manoj.personal@hdfcbank'
        self.provider_profile.payout_upi_name = 'Manoj Pillai'
        self.provider_profile.save()

        self.category = Category.objects.create(name='Carpentry Work', slug='carpentry-work')
        self.service = Service.objects.create(
            provider=self.provider_profile,
            category=self.category,
            title='Door Fitting & Lock Repair',
            slug='door-fitting-lock-repair',
            price=Decimal('1000.00'),
            description='Door fitting and lock repair service.'
        )
        self.booking = Booking.objects.create(
            customer=self.customer,
            service=self.service,
            booking_date=timezone.now().date() + timedelta(days=2),
            booking_time=time(10, 0),
            address='MG Road, Kochi',
            status='accepted',
            payment_status='unpaid',
            service_amount=Decimal('1000.00'),
            materials_amount=Decimal('0.00'),
            final_amount=Decimal('1000.00'),
            total_amount=Decimal('1000.00')
        )

    # 1. Customer cannot mark payment paid manually
    def test_customer_cannot_mark_paid_manually(self):
        self.client.login(username='sec_customer', password='password123')
        # Attempting POST with invalid signature fails
        response = self.client.post(reverse('payment_success', kwargs={'booking_id': self.booking.id}), {
            'gateway_order_id': 'fake_order_123',
            'gateway_payment_id': 'fake_pay_123',
            'gateway_signature': 'forged_invalid_signature'
        })
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, 'unpaid')

    # 2. Customer cannot change final amount through POST
    def test_customer_cannot_change_final_amount_through_post(self):
        self.client.login(username='sec_customer', password='password123')
        response = self.client.post(reverse('payment_create', kwargs={'booking_id': self.booking.id}), {
            'amount': '1.00',  # Malicious tampered amount
            'payment_method': 'upi'
        })
        data = response.json()
        self.assertEqual(Decimal(data['amount']), Decimal('1000.00'))

    # 3. Customer cannot change payment amount through hidden form fields
    def test_customer_cannot_change_payment_amount_through_hidden_fields(self):
        self.client.login(username='sec_customer', password='password123')
        response = self.client.get(reverse('checkout', kwargs={'booking_id': self.booking.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_txn'].amount, Decimal('1000.00'))

    # 4. Invalid webhook signature is rejected
    def test_invalid_webhook_signature_is_rejected(self):
        import json
        payload = json.dumps({'event': 'payment.captured'}).encode('utf-8')
        resp = self.client.post(
            reverse('payment_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_X_PAYMENT_SIGNATURE='forged_tampered_signature'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Invalid webhook signature', resp.json().get('error', ''))

    # 5. Valid webhook marks payment paid
    def test_valid_webhook_marks_payment_paid(self):
        import json
        txn = PaymentService.create_payment_order(self.booking, payment_method='upi')
        pid = 'pay_sec_valid_555'
        sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, pid)
        payload = json.dumps({
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': pid,
                        'order_id': txn.gateway_order_id,
                        'amount': 1000.00,
                        'currency': 'INR',
                        'status': 'captured',
                        'method': 'upi',
                        'signature': sig
                    }
                }
            }
        }).encode('utf-8')
        wh_sig = TestGatewayAdapter.generate_webhook_signature(payload)
        resp = self.client.post(
            reverse('payment_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_X_PAYMENT_SIGNATURE=wh_sig
        )
        self.assertEqual(resp.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, 'paid')

    # 6. Wrong amount webhook does not mark payment paid
    def test_wrong_amount_webhook_does_not_mark_payment_paid(self):
        import json
        txn = PaymentService.create_payment_order(self.booking, payment_method='upi')
        pid = 'pay_underpaid_999'
        sig = TestGatewayAdapter.generate_signature(txn.gateway_order_id, pid)
        payload = json.dumps({
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': pid,
                        'order_id': txn.gateway_order_id,
                        'amount': 500.00,  # Underpaid
                        'currency': 'INR',
                        'status': 'captured',
                        'method': 'upi',
                        'signature': sig
                    }
                }
            }
        }).encode('utf-8')
        wh_sig = TestGatewayAdapter.generate_webhook_signature(payload)
        resp = self.client.post(
            reverse('payment_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_X_PAYMENT_SIGNATURE=wh_sig
        )
        self.assertEqual(resp.status_code, 400)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, 'unpaid')

    # 7. Wrong order ID does not mark payment paid
    def test_wrong_order_id_does_not_mark_payment_paid(self):
        import json
        payload = json.dumps({
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': 'pay_bogus_order',
                        'order_id': 'order_nonexistent_xyz_999',
                        'amount': 1000.00,
                        'currency': 'INR'
                    }
                }
            }
        }).encode('utf-8')
        wh_sig = TestGatewayAdapter.generate_webhook_signature(payload)
        resp = self.client.post(
            reverse('payment_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_X_PAYMENT_SIGNATURE=wh_sig
        )
        self.assertEqual(resp.status_code, 404)

    # 8. Wrong currency does not mark payment paid
    def test_wrong_currency_does_not_mark_payment_paid(self):
        import json
        txn = PaymentService.create_payment_order(self.booking, payment_method='upi')
        payload = json.dumps({
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': 'pay_usd_currency',
                        'order_id': txn.gateway_order_id,
                        'amount': 1000.00,
                        'currency': 'USD'  # Invalid currency
                    }
                }
            }
        }).encode('utf-8')
        wh_sig = TestGatewayAdapter.generate_webhook_signature(payload)
        resp = self.client.post(
            reverse('payment_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_X_PAYMENT_SIGNATURE=wh_sig
        )
        self.assertEqual(resp.status_code, 400)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, 'unpaid')

    # 9. Duplicate webhook does not duplicate transaction
    def test_duplicate_webhook_does_not_duplicate_transaction(self):
        TestGatewayAdapter.simulate_gateway_payment_webhook(self.booking)
        TestGatewayAdapter.simulate_gateway_payment_webhook(self.booking)
        self.assertEqual(PaymentTransaction.objects.filter(booking=self.booking, status='captured').count(), 1)

    # 10. Duplicate webhook does not duplicate settlement
    def test_duplicate_webhook_does_not_duplicate_settlement(self):
        TestGatewayAdapter.simulate_gateway_payment_webhook(self.booking)
        TestGatewayAdapter.simulate_gateway_payment_webhook(self.booking)
        self.assertEqual(ProviderSettlement.objects.filter(booking=self.booking).count(), 1)

    # 11. Duplicate webhook does not duplicate notification
    def test_duplicate_webhook_does_not_duplicate_notification(self):
        TestGatewayAdapter.simulate_gateway_payment_webhook(self.booking)
        TestGatewayAdapter.simulate_gateway_payment_webhook(self.booking)
        count = Notification.objects.filter(
            booking=self.booking,
            recipient=self.provider_user,
            notification_type='payment_received'
        ).count()
        self.assertEqual(count, 1)

    # 12. Provider UPI ID cannot become merchant VPA
    def test_provider_upi_id_cannot_become_merchant_vpa(self):
        from django.conf import settings
        merchant_vpa = TestGatewayAdapter.get_merchant_vpa()
        self.assertNotEqual(merchant_vpa, self.provider_profile.payout_upi_id)
        self.assertEqual(merchant_vpa, getattr(settings, 'SERVORA_UPI_ID', 'servora.sandbox@upi'))

    # 13. QR contains correct merchant VPA
    def test_qr_contains_correct_merchant_vpa(self):
        import urllib.parse
        from django.conf import settings
        self.client.login(username='sec_customer', password='password123')
        resp = self.client.get(reverse('checkout', kwargs={'booking_id': self.booking.id}))
        expected_vpa = getattr(settings, 'SERVORA_UPI_ID', 'servora.sandbox@upi')
        decoded_intent = urllib.parse.unquote(resp.context['upi_intent'])
        self.assertIn(f"pa={expected_vpa}", decoded_intent)

    # 14. QR contains correct dynamic amount
    def test_qr_contains_correct_dynamic_amount(self):
        self.client.login(username='sec_customer', password='password123')
        resp = self.client.get(reverse('checkout', kwargs={'booking_id': self.booking.id}))
        self.assertIn("am=1000.00", resp.context['upi_intent'])
        self.assertIn("cu=INR", resp.context['upi_intent'])

    # 15. Rejected materials are excluded from QR amount
    def test_rejected_materials_excluded_from_qr_amount(self):
        BookingMaterial.objects.create(
            booking=self.booking,
            name='Faulty Lock',
            quantity=1,
            unit_price=Decimal('300.00'),
            status='rejected'
        )
        self.client.login(username='sec_customer', password='password123')
        resp = self.client.get(reverse('checkout', kwargs={'booking_id': self.booking.id}))
        self.assertIn("am=1000.00", resp.context['upi_intent'])

    # 16. Approved materials are included in QR amount
    def test_approved_materials_included_in_qr_amount(self):
        BookingMaterial.objects.create(
            booking=self.booking,
            name='Heavy Brass Lock',
            quantity=1,
            unit_price=Decimal('300.00'),
            status='pending'
        )
        self.client.login(username='sec_customer', password='password123')
        self.client.post(reverse('customer_approve_materials', kwargs={'booking_id': self.booking.id}))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.final_amount, Decimal('1300.00'))
        resp = self.client.get(reverse('checkout', kwargs={'booking_id': self.booking.id}))
        self.assertIn("am=1300.00", resp.context['upi_intent'])

    # 17. Opening UPI intent does not mark payment paid
    def test_opening_upi_intent_does_not_mark_payment_paid(self):
        self.client.login(username='sec_customer', password='password123')
        self.client.get(reverse('checkout', kwargs={'booking_id': self.booking.id}))
        self.client.get(reverse('checkout_qr', kwargs={'booking_id': self.booking.id}))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, 'unpaid')

    # 18. Returning to success URL does not mark payment paid without verification
    def test_returning_to_success_url_does_not_mark_payment_paid_without_verification(self):
        self.client.login(username='sec_customer', password='password123')
        resp = self.client.get(reverse('payment_success', kwargs={'booking_id': self.booking.id}))
        self.assertEqual(resp.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.payment_status, 'unpaid')

    # 19. Test payment remains marked as test simulated
    def test_test_payment_remains_marked_as_test_simulated(self):
        TestGatewayAdapter.simulate_gateway_payment_webhook(self.booking)
        txn = PaymentTransaction.objects.get(booking=self.booking)
        self.assertEqual(txn.gateway, 'test_gateway')
        self.assertFalse(RevenueTransaction.objects.filter(booking=self.booking, is_demo=False, verification_status='verified').exists())

    # 20. UPI-only checkout does not expose card netbanking
    def test_upi_only_checkout_does_not_expose_card_netbanking(self):
        self.client.login(username='sec_customer', password='password123')
        resp = self.client.get(reverse('checkout', kwargs={'booking_id': self.booking.id}))
        content = resp.content.decode('utf-8')
        self.assertNotIn('Card Number', content)
        self.assertNotIn('CVV', content)
        self.assertNotIn('Net Banking', content)
        self.assertIn('Scan UPI QR', content)
        self.assertIn('UPI ID / VPA', content)








