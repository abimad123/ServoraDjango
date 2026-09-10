from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from users.models import UserProfile, ProviderSubscription
from services.models import Category, Service, Booking, Review, FeaturedListing, RevenueTransaction
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



