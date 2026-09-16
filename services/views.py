from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q, Avg, Count, Sum, F, OuterRef, Exists
from .models import (
    Category, Service, Booking, Review, FeaturedListing, RevenueTransaction, 
    Notification, create_notification, PaymentTransaction, ProviderSettlement,
    BookingMaterial
)
from .forms import BookingCreateForm, ServiceForm, ReviewForm, ProviderPayoutSettingsForm, BookingMaterialForm
from .payment_service import PaymentService, TestGatewayAdapter
from users.models import UserProfile, ProviderSubscription
from users.forms import ProviderProfileForm
from users.decorators import provider_required, admin_required
from decimal import Decimal
from datetime import datetime, date, time, timedelta
import csv


def home_view(request):
    """
    Customer homepage rendering hero search bar, categories, and top services.
    """
    active_promo_subquery = FeaturedListing.objects.filter(
        service=OuterRef('pk'),
        is_active=True,
        end_date__gte=date.today()
    )
    categories = Category.objects.all()[:10]
    featured_services = Service.objects.filter(is_active=True).annotate(
        has_active_promo=Exists(active_promo_subquery)
    ).select_related('provider', 'category', 'provider__user').order_by('-has_active_promo', '-is_featured', '-created_at')[:6]
    return render(request, 'services/home.html', {
        'categories': categories,
        'featured_services': featured_services,
    })


def service_list_view(request):
    """
    Complete service catalog supporting multi-field search and flexible filtering.
    Accepts: search / q, location, category, min_price, max_price, min_rating, sort.
    """
    services = Service.objects.filter(is_active=True).select_related('provider', 'category', 'provider__user').prefetch_related('reviews')

    # Search Query
    search_query = request.GET.get('search') or request.GET.get('q') or ''
    if search_query.strip():
        q_term = search_query.strip()
        services = services.filter(
            Q(title__icontains=q_term) |
            Q(description__icontains=q_term) |
            Q(category__name__icontains=q_term) |
            Q(location__icontains=q_term) |
            Q(provider__user__first_name__icontains=q_term) |
            Q(provider__user__last_name__icontains=q_term)
        )

    # Filter: Location
    location_filter = request.GET.get('location', '').strip()
    if location_filter:
        services = services.filter(location__icontains=location_filter)

    # Filter: Category (slug or name)
    category_filter = request.GET.get('category', '').strip()
    if category_filter and category_filter.lower() != 'all':
        services = services.filter(
            Q(category__name__iexact=category_filter) | Q(category__slug__iexact=category_filter)
        )

    # Filter: Minimum Price
    min_price = request.GET.get('min_price', '').strip()
    if min_price:
        try:
            services = services.filter(price__gte=Decimal(min_price))
        except (ValueError, ArithmeticError):
            pass

    # Filter: Maximum Price
    max_price = request.GET.get('max_price', '').strip()
    if max_price:
        try:
            services = services.filter(price__lte=Decimal(max_price))
        except (ValueError, ArithmeticError):
            pass

    # Filter: Minimum Star Rating
    min_rating = request.GET.get('min_rating', '').strip()
    if min_rating:
        try:
            rating_val = float(min_rating)
            # Filter services where average review rating >= min_rating or if no reviews, consider default 5.0
            matching_ids = [s.id for s in services if s.average_rating >= rating_val]
            services = services.filter(id__in=matching_ids)
        except ValueError:
            pass

    # Sorting with dynamic active featured promotions priority
    active_promo_subquery = FeaturedListing.objects.filter(
        service=OuterRef('pk'),
        is_active=True,
        end_date__gte=date.today()
    )
    services = services.annotate(has_active_promo=Exists(active_promo_subquery))

    sort_option = request.GET.get('sort', 'recommended')
    if sort_option == 'price_asc':
        services = services.order_by('price')
    elif sort_option == 'price_desc':
        services = services.order_by('-price')
    elif sort_option == 'newest':
        services = services.order_by('-created_at')
    else:
        # Default: Recommended (Active promotions or is_featured first, then recent)
        services = services.order_by('-has_active_promo', '-is_featured', '-created_at')

    # Context helpers for filter dropdowns
    categories = Category.objects.all()
    available_locations = Service.objects.filter(is_active=True).values_list('location', flat=True).distinct()

    return render(request, 'services/service_list.html', {
        'services': services,
        'categories': categories,
        'available_locations': available_locations,
        'search_query': search_query,
        'location_filter': location_filter,
        'category_filter': category_filter,
        'min_price': min_price,
        'max_price': max_price,
        'min_rating': min_rating,
        'sort_option': sort_option,
        'total_count': services.count(),
    })


def category_services_view(request, name):
    """
    Dedicated category page displaying curated services for a specific category.
    Supports academic <str:name> converter.
    """
    category = get_object_or_404(Category, Q(name__iexact=name) | Q(slug__iexact=name))
    services = Service.objects.filter(category=category, is_active=True).select_related('provider', 'category', 'provider__user').prefetch_related('reviews')

    # Optional sorting
    sort_option = request.GET.get('sort', 'recommended')
    if sort_option == 'price_asc':
        services = services.order_by('price')
    elif sort_option == 'price_desc':
        services = services.order_by('-price')
    elif sort_option == 'rating':
        # Python sort or order by reviews count
        services = sorted(services, key=lambda s: s.average_rating, reverse=True)
    else:
        services = services.order_by('-is_featured', '-created_at')

    provider_count = Category.objects.filter(id=category.id).aggregate(
        count=Count('services__provider', distinct=True)
    )['count'] or 0

    return render(request, 'services/category_services.html', {
        'category': category,
        'services': services,
        'provider_count': provider_count,
        'sort_option': sort_option,
    })


def get_rating_distribution(reviews_qs):
    total = reviews_qs.count()
    distribution = []
    for star in range(5, 0, -1):
        c = reviews_qs.filter(rating=star).count()
        pct = int((c / total) * 100) if total > 0 else 0
        distribution.append({
            'star': star,
            'count': c,
            'percent': pct,
        })
    return distribution


def service_detail_view(request, id):
    """
    Rich service detail page with provider summary, reviews, and booking CTA.
    Supports academic <int:id> converter.
    """
    service = get_object_or_404(
        Service.objects.select_related('provider', 'category', 'provider__user'),
        id=id,
        is_active=True
    )
    reviews = service.reviews.select_related('customer').order_by('-created_at')
    other_services = Service.objects.filter(
        provider=service.provider,
        is_active=True
    ).exclude(id=service.id)[:3]

    rating_distribution = get_rating_distribution(reviews)

    return render(request, 'services/service_detail.html', {
        'service': service,
        'reviews': reviews,
        'other_services': other_services,
        'rating_distribution': rating_distribution,
    })


def service_slug_detail_view(request, slug):
    """
    Service detail view accessible via SEO-friendly URL slug.
    Supports academic <slug:slug> converter.
    """
    service = get_object_or_404(
        Service.objects.select_related('provider', 'category', 'provider__user'),
        slug=slug,
        is_active=True
    )
    reviews = service.reviews.select_related('customer').order_by('-created_at')
    other_services = Service.objects.filter(
        provider=service.provider,
        is_active=True
    ).exclude(id=service.id)[:3]

    rating_distribution = get_rating_distribution(reviews)

    return render(request, 'services/service_detail.html', {
        'service': service,
        'reviews': reviews,
        'other_services': other_services,
        'rating_distribution': rating_distribution,
    })


def provider_profile_view(request, id):
    """
    Customer-facing public profile for a verified service provider.
    Displays provider bio, credentials, completed jobs, reviews, and all offered services.
    """
    provider = get_object_or_404(
        UserProfile.objects.select_related('user'),
        id=id,
        role='provider'
    )
    services = provider.services.filter(is_active=True).select_related('category')
    all_provider_reviews = Review.objects.filter(service__provider=provider)
    reviews = all_provider_reviews.select_related('customer', 'service').order_by('-created_at')[:8]
    rating_distribution = get_rating_distribution(all_provider_reviews)

    return render(request, 'services/provider_profile.html', {
        'provider': provider,
        'services': services,
        'reviews': reviews,
        'completed_jobs': provider.completed_jobs_count,
        'average_rating': provider.average_rating,
        'total_reviews': provider.total_reviews_count,
        'rating_distribution': rating_distribution,
    })


def search_view(request):
    """
    Handles GET /search/ requests by seamlessly delegating to service_list_view.
    """
    return service_list_view(request)


def book_service_view(request, service_id):
    """
    Multi-step booking flow (Service & Provider -> Date & Time -> Details -> Confirm).
    Guarded so only authenticated customers can book.
    """
    service = get_object_or_404(
        Service.objects.select_related('provider', 'category', 'provider__user'),
        id=service_id,
        is_active=True
    )

    # 1. Unauthenticated users are redirected to login with ?next=
    if not request.user.is_authenticated:
        messages.info(request, "Please log in to your customer account to book this service.")
        return redirect(f"{reverse('login')}?next={request.path}")

    # 2. Providers cannot create customer bookings
    if hasattr(request.user, 'profile') and request.user.profile.is_provider:
        messages.error(request, "Service provider accounts cannot place bookings. Please log in with a homeowner/customer account.")
        return redirect('service_detail', id=service.id)

    # Time slot groupings for UI
    morning_slots = [
        ('09:00:00', '9:00 AM'), ('09:30:00', '9:30 AM'),
        ('10:00:00', '10:00 AM'), ('10:30:00', '10:30 AM'),
        ('11:00:00', '11:00 AM')
    ]
    afternoon_slots = [
        ('13:00:00', '1:00 PM'), ('13:30:00', '1:30 PM'),
        ('14:00:00', '2:00 PM'), ('14:30:00', '2:30 PM'),
        ('15:00:00', '3:00 PM')
    ]
    evening_slots = [
        ('17:00:00', '5:00 PM'), ('17:30:00', '5:30 PM'),
        ('18:00:00', '6:00 PM'), ('18:30:00', '6:30 PM'),
        ('19:00:00', '7:00 PM')
    ]

    if request.method == 'POST':
        form = BookingCreateForm(request.POST, service=service)
        if form.is_valid():
            booking = Booking(
                service=service,
                customer=request.user,
                booking_date=form.cleaned_data['booking_date'],
                booking_time=form.cleaned_data['booking_time'],
                address=form.cleaned_data['address'],
                notes=form.cleaned_data.get('notes', ''),
                total_amount=service.price,
                commission_rate=Decimal('10.00'),
                status='pending'
            )
            # Automatically calculates 10% commission on save
            booking.save()

            # Create notification for service provider
            create_notification(
                recipient=service.provider.user,
                notification_type='booking_created',
                title='New Booking Request',
                message=f"{request.user.get_full_name() or request.user.username} requested {service.title} for {booking.booking_date.strftime('%b %d')} at {booking.booking_time.strftime('%I:%M %p')}.",
                booking=booking,
                service=service
            )

            messages.success(request, f"Booking request #{booking.id} created successfully!")
            return redirect('booking_success', booking_id=booking.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        # Pre-fill address from customer profile if available
        initial_data = {}
        if hasattr(request.user, 'profile') and request.user.profile.address:
            initial_data['address'] = request.user.profile.address
        form = BookingCreateForm(service=service, initial=initial_data)

    return render(request, 'services/booking.html', {
        'service': service,
        'form': form,
        'morning_slots': morning_slots,
        'afternoon_slots': afternoon_slots,
        'evening_slots': evening_slots,
    })


def booking_success_view(request, booking_id):
    """
    Booking confirmation screen showing receipt ticket and scheduled details.
    """
    if not request.user.is_authenticated:
        return redirect('login')

    booking = get_object_or_404(
        Booking.objects.select_related('service', 'service__provider', 'service__provider__user', 'service__category'),
        id=booking_id
    )

    # Security check: Only customer or provider can view
    if booking.customer != request.user and booking.service.provider.user != request.user:
        return render(request, '404.html', status=404)

    return render(request, 'services/booking_success.html', {
        'booking': booking,
    })


def my_bookings_view(request):
    """
    Customer portal displaying all historical and active bookings placed by the logged-in customer.
    """
    if not request.user.is_authenticated:
        messages.info(request, "Please log in to view your bookings.")
        return redirect('login')

    bookings = Booking.objects.filter(customer=request.user).select_related(
        'service', 'service__provider', 'service__provider__user', 'service__category'
    ).order_by('-created_at')

    return render(request, 'services/my_bookings.html', {
        'bookings': bookings,
        'total_bookings': bookings.count(),
    })


def booking_detail_view(request, booking_id):
    """
    Detailed receipt and status page for an individual booking.
    Guarded so users can only view their own bookings.
    """
    if not request.user.is_authenticated:
        return redirect('login')

    booking = get_object_or_404(
        Booking.objects.select_related('service', 'service__provider', 'service__provider__user', 'service__category'),
        id=booking_id
    )

    # Security: Only owner customer or recipient provider can view
    is_customer_owner = (booking.customer == request.user)
    is_provider_recipient = (booking.service.provider.user == request.user)

    if not (is_customer_owner or is_provider_recipient or request.user.is_staff):
        return render(request, '404.html', status=404)

    materials = booking.materials.all().select_related('added_by')
    has_pending = materials.filter(status='pending').exists()
    pending_total = materials.filter(status='pending').aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
    approved_materials = materials.filter(status='approved')
    approved_total = approved_materials.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')

    return render(request, 'services/booking_detail.html', {
        'booking': booking,
        'is_customer_owner': is_customer_owner,
        'is_provider_recipient': is_provider_recipient,
        'materials': materials,
        'has_pending': has_pending,
        'pending_total': pending_total,
        'approved_materials': approved_materials,
        'approved_total': approved_total,
    })



def cancel_booking_view(request, booking_id):
    """
    Allows a customer to cancel a pending booking via POST request.
    Frees up the slot for future bookings.
    """
    if not request.user.is_authenticated:
        return redirect('login')

    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('my_bookings')

    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)

    if booking.status != 'pending':
        messages.warning(request, f"Booking #{booking.id} cannot be cancelled because it is already {booking.get_status_display()}.")
        return redirect('booking_detail', booking_id=booking.id)

    booking.status = 'cancelled'
    booking.save()

    # If the booking was already paid, handle refund and void settlement
    if booking.payment_status == 'paid':
        PaymentService.handle_refund(booking, reason="Customer cancelled pending booking")


    create_notification(
        recipient=booking.service.provider.user,
        notification_type='booking_cancelled',
        title='Booking Cancelled',
        message=f"{request.user.get_full_name() or request.user.username} cancelled the booking for {booking.service.title}.",
        booking=booking,
        service=booking.service
    )

    messages.success(request, f"Booking #{booking.id} has been cancelled successfully. The time slot is now open.")
    return redirect('my_bookings')


def provider_bookings_view(request):
    """
    Basic provider booking visibility list (Stage 4 baseline).
    """
    if not request.user.is_authenticated:
        return redirect('login')

    if not hasattr(request.user, 'profile') or not request.user.profile.is_provider:
        messages.error(request, "Access restricted to service providers.")
        return redirect('home')

    bookings = Booking.objects.filter(service__provider=request.user.profile).select_related(
        'service', 'customer'
    ).order_by('-created_at')

    return render(request, 'services/provider_bookings.html', {
        'bookings': bookings,
        'total_bookings': bookings.count(),
    })


def api_availability_view(request):
    """
    Returns JSON list of booked time slots for a specific service and date.
    Protects against double-bookings in real-time on the client side.
    """
    service_id = request.GET.get('service_id')
    date_str = request.GET.get('date')

    if not service_id or not date_str:
        return JsonResponse({'booked_slots': []})

    try:
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'booked_slots': []})

    booked_times = Booking.objects.filter(
        service_id=service_id,
        booking_date=parsed_date,
        status__in=['pending', 'accepted']
    ).values_list('booking_time', flat=True)

    formatted_slots = [t.strftime('%H:%M:%S') for t in booked_times]
    return JsonResponse({'booked_slots': formatted_slots})


@provider_required
def provider_dashboard_view(request):
    """
    Main provider workspace featuring 4 real-time KPI metrics, pending job requests,
    and upcoming schedule snippets.
    """
    provider = request.user.profile
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    completed_bookings = Booking.objects.filter(
        service__provider=provider,
        status='completed'
    )

    today_earnings = completed_bookings.filter(booking_date=today).aggregate(
        earn=Sum(F('total_amount') - F('commission_amount'))
    )['earn'] or Decimal('0.00')

    week_earnings = completed_bookings.filter(booking_date__gte=week_start).aggregate(
        earn=Sum(F('total_amount') - F('commission_amount'))
    )['earn'] or Decimal('0.00')

    month_earnings = completed_bookings.filter(booking_date__gte=month_start).aggregate(
        earn=Sum(F('total_amount') - F('commission_amount'))
    )['earn'] or Decimal('0.00')

    completed_jobs_count = completed_bookings.count()

    pending_requests = Booking.objects.filter(
        service__provider=provider,
        status='pending'
    ).select_related('service', 'customer').order_by('-created_at')[:5]

    upcoming_jobs = Booking.objects.filter(
        service__provider=provider,
        status='accepted',
        booking_date__gte=today
    ).select_related('service', 'customer').order_by('booking_date', 'booking_time')[:5]

    total_services_count = Service.objects.filter(provider=provider, is_active=True).count()

    # Stage 8A: Provider Settlements & Financial Summary
    settlements = ProviderSettlement.objects.filter(provider=provider)
    pending_payouts = settlements.filter(status='pending').aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')
    paid_payouts = settlements.filter(status='paid').aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')
    gbv_settlements = settlements.filter(status__in=['pending', 'paid']).aggregate(total=Sum('gross_amount'))['total'] or Decimal('0.00')
    comm_settlements = settlements.filter(status__in=['pending', 'paid']).aggregate(total=Sum('commission_amount'))['total'] or Decimal('0.00')
    total_settlement_earnings = pending_payouts + paid_payouts

    return render(request, 'provider/dashboard.html', {
        'provider': provider,
        'today_earnings': today_earnings,
        'week_earnings': week_earnings,
        'month_earnings': month_earnings,
        'completed_jobs_count': completed_jobs_count,
        'pending_requests': pending_requests,
        'upcoming_jobs': upcoming_jobs,
        'total_services_count': total_services_count,
        'pending_payouts': pending_payouts,
        'paid_payouts': paid_payouts,
        'gbv_settlements': gbv_settlements,
        'comm_settlements': comm_settlements,
        'total_settlement_earnings': total_settlement_earnings,
        'active_tab': 'dashboard',
    })


@provider_required
def provider_jobs_view(request):
    """
    Job requests & appointments manager with database filtering by status.
    """
    provider = request.user.profile
    status_filter = request.GET.get('status', 'all').lower()

    all_provider_bookings = Booking.objects.filter(
        service__provider=provider
    ).select_related('service', 'customer', 'customer__profile')

    all_count = all_provider_bookings.count()
    pending_count = all_provider_bookings.filter(status='pending').count()
    accepted_count = all_provider_bookings.filter(status='accepted').count()
    completed_count = all_provider_bookings.filter(status='completed').count()
    declined_count = all_provider_bookings.filter(status='declined').count()
    cancelled_count = all_provider_bookings.filter(status='cancelled').count()

    if status_filter in ['pending', 'accepted', 'completed', 'declined', 'cancelled']:
        bookings = all_provider_bookings.filter(status=status_filter).order_by('-created_at')
    else:
        status_filter = 'all'
        bookings = all_provider_bookings.order_by('-created_at')

    return render(request, 'provider/jobs.html', {
        'bookings': bookings,
        'status_filter': status_filter,
        'all_count': all_count,
        'pending_count': pending_count,
        'accepted_count': accepted_count,
        'completed_count': completed_count,
        'declined_count': declined_count,
        'cancelled_count': cancelled_count,
        'active_tab': 'jobs',
    })


@provider_required
def provider_job_detail_view(request, booking_id):
    """
    Comprehensive job request inspector with customer details and status action triggers.
    """
    provider = request.user.profile
    booking = get_object_or_404(
        Booking.objects.select_related('service', 'customer', 'customer__profile', 'service__category'),
        id=booking_id,
        service__provider=provider
    )
    provider_earning = booking.provider_earning
    materials = booking.materials.all().order_by('-created_at')
    approved_materials_total = booking.approved_materials_total
    pending_materials_total = booking.pending_materials_total

    return render(request, 'provider/job_detail.html', {
        'booking': booking,
        'provider_earning': provider_earning,
        'materials': materials,
        'approved_materials_total': approved_materials_total,
        'pending_materials_total': pending_materials_total,
        'active_tab': 'jobs',
    })



@provider_required
def provider_job_accept_view(request, booking_id):
    """
    POST action: Accepts a pending booking request (status -> accepted).
    """
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('provider_jobs')

    provider = request.user.profile
    booking = get_object_or_404(Booking, id=booking_id, service__provider=provider)

    if booking.status != 'pending':
        messages.error(request, f"Cannot accept Job #{booking.id} because it is currently {booking.get_status_display()}.")
        return redirect('provider_job_detail', booking_id=booking.id)

    booking.status = 'accepted'
    booking.save()

    create_notification(
        recipient=booking.customer,
        notification_type='booking_accepted',
        title='Booking Accepted',
        message=f"{request.user.get_full_name() or request.user.username} accepted your {booking.service.title} booking.",
        booking=booking,
        service=booking.service
    )

    messages.success(request, f"Job #{booking.id} accepted successfully! It is now scheduled in your calendar.")
    return redirect('provider_job_detail', booking_id=booking.id)


@provider_required
def provider_job_decline_view(request, booking_id):
    """
    POST action: Declines a pending booking request (status -> declined).
    Releases the time slot so another customer can book.
    """
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('provider_jobs')

    provider = request.user.profile
    booking = get_object_or_404(Booking, id=booking_id, service__provider=provider)

    if booking.status != 'pending':
        messages.error(request, f"Cannot decline Job #{booking.id} because it is currently {booking.get_status_display()}.")
        return redirect('provider_job_detail', booking_id=booking.id)

    booking.status = 'declined'
    booking.save()

    create_notification(
        recipient=booking.customer,
        notification_type='booking_declined',
        title='Booking Declined',
        message=f"Unfortunately, {request.user.get_full_name() or request.user.username} declined your booking request for {booking.service.title}.",
        booking=booking,
        service=booking.service
    )

    messages.info(request, f"Job #{booking.id} has been declined. The appointment time slot has been freed.")
    return redirect('provider_job_detail', booking_id=booking.id)


@provider_required
def provider_job_complete_view(request, booking_id):
    """
    POST action: Marks an accepted job as completed (status -> completed).
    Updates provider earnings.
    """
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('provider_jobs')

    provider = request.user.profile
    booking = get_object_or_404(Booking, id=booking_id, service__provider=provider)

    if booking.status != 'accepted':
        messages.error(request, f"Cannot complete Job #{booking.id} because only accepted jobs can be completed.")
        return redirect('provider_job_detail', booking_id=booking.id)

    booking.status = 'completed'
    booking.save()
    provider_earning = booking.total_amount - booking.commission_amount

    # Automatically and idempotently capture 10% platform commission revenue
    RevenueTransaction.objects.get_or_create(
        revenue_type='commission',
        booking=booking,
        defaults={
            'provider': booking.service.provider,
            'amount': booking.commission_amount,
            'description': f"10% Platform Commission on Booking #SVR{booking.id:05d} ({booking.service.title})",
            'status': 'completed',
        }
    )

    create_notification(
        recipient=booking.customer,
        notification_type='booking_completed',
        title='Service Completed',
        message=f"Your {booking.service.title} booking has been marked completed. You can now leave a review.",
        booking=booking,
        service=booking.service
    )

    messages.success(request, f"Job #{booking.id} marked as Completed! ₹{provider_earning} has been added to your earnings ledger.")
    return redirect('provider_job_detail', booking_id=booking.id)


@provider_required
def provider_services_view(request):
    """
    Service listings catalog managed by the logged-in provider.
    """
    provider = request.user.profile
    services = Service.objects.filter(provider=provider).select_related('category').prefetch_related('featured_promotions').annotate(
        bookings_count=Count('bookings')
    ).order_by('-created_at')

    return render(request, 'provider/services.html', {
        'services': services,
        'total_count': services.count(),
        'active_tab': 'services',
    })


@provider_required
def provider_service_create_view(request):
    """
    Creates a new service listing owned by the logged-in provider.
    """
    provider = request.user.profile

    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES)
        if form.is_valid():
            service = form.save(commit=False)
            service.provider = provider
            service.save()
            messages.success(request, f"Service '{service.title}' created and published successfully!")
            return redirect('provider_services')
        else:
            messages.error(request, "Please correct the errors below to publish your service.")
    else:
        form = ServiceForm(initial={'location': provider.city})

    return render(request, 'provider/service_form.html', {
        'form': form,
        'page_title': 'Add New Service Listing',
        'submit_label': 'Publish Service',
        'active_tab': 'services',
    })


@provider_required
def provider_service_edit_view(request, id):
    """
    Edits an existing service offering owned by the provider.
    """
    provider = request.user.profile
    service = get_object_or_404(Service, id=id, provider=provider)

    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, f"Service '{service.title}' updated successfully!")
            return redirect('provider_services')
        else:
            messages.error(request, "Please correct the form errors below.")
    else:
        form = ServiceForm(instance=service)

    return render(request, 'provider/service_form.html', {
        'form': form,
        'service': service,
        'page_title': f"Edit '{service.title}'",
        'submit_label': 'Save Changes',
        'active_tab': 'services',
    })


@provider_required
def provider_service_delete_view(request, id):
    """
    Deletes or deactivates a service owned by the provider with safeguards for active bookings.
    """
    provider = request.user.profile
    service = get_object_or_404(Service, id=id, provider=provider)

    active_bookings_count = service.bookings.filter(status__in=['pending', 'accepted']).count()
    total_bookings_count = service.bookings.count()

    if request.method == 'POST':
        if active_bookings_count > 0:
            messages.error(
                request,
                f"Cannot delete '{service.title}' because it has {active_bookings_count} active (pending or accepted) job(s). Please resolve those bookings first."
            )
            return redirect('provider_services')

        if total_bookings_count > 0:
            # Safely archive / deactivate to preserve historical booking records
            service.is_active = False
            service.save()
            messages.info(request, f"Service '{service.title}' has {total_bookings_count} past bookings and was safely deactivated/archived from the marketplace.")
        else:
            service.delete()
            messages.success(request, f"Service '{service.title}' was permanently deleted.")

        return redirect('provider_services')

    return render(request, 'provider/service_confirm_delete.html', {
        'service': service,
        'active_bookings_count': active_bookings_count,
        'total_bookings_count': total_bookings_count,
        'active_tab': 'services',
    })


@provider_required
def provider_schedule_view(request):
    """
    Calendar and chronological day-by-day appointment timeline.
    """
    provider = request.user.profile
    today = date.today()

    bookings = Booking.objects.filter(
        service__provider=provider,
        status__in=['pending', 'accepted'],
        booking_date__gte=today
    ).select_related('service', 'customer', 'customer__profile').order_by('booking_date', 'booking_time')

    # Group bookings by date
    grouped_schedule = {}
    for b in bookings:
        if b.booking_date not in grouped_schedule:
            grouped_schedule[b.booking_date] = []
        grouped_schedule[b.booking_date].append(b)

    # Convert to sorted list of (date, list_of_bookings)
    schedule_days = sorted(grouped_schedule.items(), key=lambda x: x[0])

    return render(request, 'provider/schedule.html', {
        'schedule_days': schedule_days,
        'total_scheduled': bookings.count(),
        'today': today,
        'active_tab': 'schedule',
    })


@provider_required
def provider_earnings_view(request):
    """
    Earnings analytics with 4 metric cards, weekly visual bar chart, and completed booking ledger.
    """
    provider = request.user.profile
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    completed_bookings = Booking.objects.filter(
        service__provider=provider,
        status='completed'
    ).select_related('service', 'customer').order_by('-booking_date', '-booking_time')

    total_earnings = completed_bookings.aggregate(
        earn=Sum(F('total_amount') - F('commission_amount'))
    )['earn'] or Decimal('0.00')

    month_earnings = completed_bookings.filter(booking_date__gte=month_start).aggregate(
        earn=Sum(F('total_amount') - F('commission_amount'))
    )['earn'] or Decimal('0.00')

    week_earnings = completed_bookings.filter(booking_date__gte=week_start).aggregate(
        earn=Sum(F('total_amount') - F('commission_amount'))
    )['earn'] or Decimal('0.00')

    completed_jobs_count = completed_bookings.count()

    # Build weekly chart data (Monday to Sunday)
    day_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    weekly_bars = []
    max_day_earning = Decimal('1.00')

    for i in range(7):
        day_date = week_start + timedelta(days=i)
        day_earn = completed_bookings.filter(booking_date=day_date).aggregate(
            earn=Sum(F('total_amount') - F('commission_amount'))
        )['earn'] or Decimal('0.00')
        if day_earn > max_day_earning:
            max_day_earning = day_earn
        weekly_bars.append({
            'day_name': day_labels[i],
            'date': day_date,
            'earning': day_earn,
            'is_today': (day_date == today),
        })

    for bar in weekly_bars:
        bar['height_percent'] = int((bar['earning'] / max_day_earning) * 100) if max_day_earning > 0 else 0

    return render(request, 'provider/earnings.html', {
        'total_earnings': total_earnings,
        'month_earnings': month_earnings,
        'week_earnings': week_earnings,
        'completed_jobs_count': completed_jobs_count,
        'weekly_bars': weekly_bars,
        'completed_bookings': completed_bookings,
        'active_tab': 'earnings',
    })


@provider_required
def provider_profile_settings_view(request):
    """
    Provider profile settings & credentials editor.
    """
    profile = request.user.profile

    if request.method == 'POST':
        form = ProviderProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Your professional profile has been updated successfully!")
            return redirect('provider_profile_settings')
        else:
            messages.error(request, "Please correct the errors in the profile form.")
    else:
        form = ProviderProfileForm(instance=profile)

    return render(request, 'provider/profile.html', {
        'form': form,
        'profile': profile,
        'active_tab': 'profile',
    })


@provider_required
def provider_subscription_view(request):
    """
    Allows service providers to view subscription tiers (Free vs Pro at ₹399/month)
    and upgrade with simulated instant checkout.
    """
    provider = request.user.profile
    current_sub = ProviderSubscription.objects.filter(provider=provider, is_active=True).order_by('-id').first()
    is_pro = bool(current_sub and current_sub.plan_name == 'pro')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'upgrade_pro':
            end_date = date.today() + timedelta(days=30)
            sub, _ = ProviderSubscription.objects.get_or_create(
                provider=provider,
                is_active=True,
                defaults={
                    'plan_name': 'pro',
                    'monthly_fee': Decimal('399.00'),
                    'end_date': end_date,
                }
            )
            sub.plan_name = 'pro'
            sub.monthly_fee = Decimal('399.00')
            sub.end_date = end_date
            sub.is_active = True
            sub.save()

            # Record simulated platform revenue transaction
            RevenueTransaction.objects.create(
                revenue_type='subscription',
                amount=Decimal('399.00'),
                provider=provider,
                description=f"Pro Plan Monthly Subscription (₹399/mo) for {request.user.get_full_name() or request.user.username}",
                status='completed'
            )

            create_notification(
                recipient=request.user,
                notification_type='subscription_activated',
                title='Pro Activated',
                message='Your Servora Pro subscription is now active with verified badge and priority placement.',
            )

            messages.success(request, "Congratulations! You have successfully upgraded to the Pro Plan for ₹399/month. Your verified Pro badge and priority placement are now active.")
            return redirect('provider_subscription')

    return render(request, 'provider/subscription.html', {
        'provider': provider,
        'current_sub': current_sub,
        'is_pro': is_pro,
        'active_tab': 'subscription',
    })


@provider_required
def provider_feature_service_view(request, service_id):
    """
    Promote a service listing as Featured for ₹99 (3 days).
    Provides top-ranking search placement on customer marketplace.
    """
    provider = request.user.profile
    service = get_object_or_404(Service, id=service_id, provider=provider)

    active_promo = service.featured_promotions.filter(is_active=True, end_date__gte=date.today()).order_by('-end_date').first()

    if request.method == 'POST':
        end_date = date.today() + timedelta(days=3)
        FeaturedListing.objects.create(
            service=service,
            fee_paid=Decimal('99.00'),
            end_date=end_date,
            is_active=True
        )
        service.is_featured = True
        service.save(update_fields=['is_featured'])

        # Record simulated platform revenue transaction
        RevenueTransaction.objects.create(
            revenue_type='featured',
            amount=Decimal('99.00'),
            provider=provider,
            service=service,
            description=f"3-Day Featured Promotion for '{service.title}' (₹99)",
            status='completed'
        )

        create_notification(
            recipient=request.user,
            notification_type='featured_listing_activated',
            title='Service Featured',
            message=f"Your {service.title} service is now featured for 3 days.",
            service=service
        )
        messages.success(request, f"Success! '{service.title}' is now featured on the marketplace for the next 3 days (until {end_date.strftime('%d %b %Y')}).")
        return redirect('provider_services')

    return render(request, 'provider/feature_service.html', {
        'service': service,
        'active_promo': active_promo,
        'active_tab': 'services',
    })


@admin_required
def platform_revenue_dashboard_view(request):
    """
    Platform Revenue & SCRGM Pilot Verifiable Tracking Overview.
    Displays total platform revenue, verifiable pilot revenue, Gross Booking Value,
    provider earnings, RGM INR 10k-INR 25k target tracker, 4 KPI cards, stream breakdowns,
    weekly chart, and recent transactions.
    """
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    completed_tx = RevenueTransaction.objects.filter(status='completed')

    # Total all-time realized revenue across all records
    total_revenue = completed_tx.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    today_revenue = completed_tx.filter(created_at__date=today).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    week_revenue = completed_tx.filter(created_at__date__gte=week_start).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    month_revenue = completed_tx.filter(created_at__date__gte=month_start).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Stream breakdown (All completed)
    commission_revenue = completed_tx.filter(revenue_type='commission').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    subscription_revenue = completed_tx.filter(revenue_type='subscription').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    featured_revenue = completed_tx.filter(revenue_type='featured').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    commission_count = completed_tx.filter(revenue_type='commission').count()
    subscription_count = completed_tx.filter(revenue_type='subscription').count()
    featured_count = completed_tx.filter(revenue_type='featured').count()
    total_transactions_count = completed_tx.count()

    # Stage 7.5: Verifiable Pilot Revenue (SCRGM Strict Standard)
    # Transaction must strictly be: is_demo=False, status='completed', verification_status='verified',
    # has_evidence=True, and possess a valid non-empty transaction reference / UTR
    verified_tx = completed_tx.filter(
        is_demo=False,
        verification_status='verified',
        has_evidence=True
    ).exclude(
        Q(transaction_reference__isnull=True) | Q(transaction_reference__exact='')
    )
    verified_revenue = verified_tx.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    verified_commission_revenue = verified_tx.filter(revenue_type='commission').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    verified_subscription_revenue = verified_tx.filter(revenue_type='subscription').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    verified_featured_revenue = verified_tx.filter(revenue_type='featured').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    verified_count = verified_tx.count()

    # Demonstration / Seeded data separation
    demo_tx = completed_tx.filter(is_demo=True)
    demo_revenue = demo_tx.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    demo_count = demo_tx.count()

    # Pending verification transactions (Actual pilot but awaiting verification)
    pending_audit_count = completed_tx.filter(is_demo=False, verification_status='pending').count()

    # Gross Booking Value (GBV) & Provider Earnings separation (from completed bookings)
    completed_bookings = Booking.objects.filter(status='completed')
    gross_booking_value = completed_bookings.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    total_booking_commissions = completed_bookings.aggregate(total=Sum('commission_amount'))['total'] or Decimal('0.00')
    provider_earnings_total = gross_booking_value - total_booking_commissions

    # RGM Target Tracker: Target bracket is INR 10,000 - INR 24,999 (target threshold = INR 10,000)
    target_revenue = Decimal('10000.00')
    remaining_to_target = max(Decimal('0.00'), target_revenue - verified_revenue)
    target_progress_percent = min(100, int((verified_revenue / target_revenue) * 100)) if target_revenue > 0 else 0

    # Weekly chart: Mon-Sun daily revenue
    day_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    weekly_chart = []
    max_day_rev = Decimal('1.00')
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        day_rev = completed_tx.filter(created_at__date=day_date).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        if day_rev > max_day_rev:
            max_day_rev = day_rev
        weekly_chart.append({
            'day_name': day_labels[i],
            'date': day_date,
            'revenue': day_rev,
            'is_today': (day_date == today),
        })

    for bar in weekly_chart:
        bar['height_percent'] = int((bar['revenue'] / max_day_rev) * 100) if max_day_rev > 0 else 0

    recent_transactions = completed_tx.select_related(
        'provider', 'provider__user', 'booking', 'service'
    ).order_by('-created_at')[:10]

    return render(request, 'platform/revenue_dashboard.html', {
        'total_revenue': total_revenue,
        'today_revenue': today_revenue,
        'week_revenue': week_revenue,
        'month_revenue': month_revenue,
        'commission_revenue': commission_revenue,
        'subscription_revenue': subscription_revenue,
        'featured_revenue': featured_revenue,
        'commission_count': commission_count,
        'subscription_count': subscription_count,
        'featured_count': featured_count,
        'total_transactions_count': total_transactions_count,

        # Stage 7.5 Verifiable Metrics
        'verified_revenue': verified_revenue,
        'verified_commission_revenue': verified_commission_revenue,
        'verified_subscription_revenue': verified_subscription_revenue,
        'verified_featured_revenue': verified_featured_revenue,
        'verified_count': verified_count,
        'demo_revenue': demo_revenue,
        'demo_count': demo_count,
        'pending_audit_count': pending_audit_count,

        # Gross Booking Value vs Provider Earnings
        'gross_booking_value': gross_booking_value,
        'provider_earnings_total': provider_earnings_total,

        # RGM Target Tracker
        'target_revenue': target_revenue,
        'remaining_to_target': remaining_to_target,
        'target_progress_percent': target_progress_percent,

        'weekly_chart': weekly_chart,
        'recent_transactions': recent_transactions,
        'active_tab': 'overview',
    })


@admin_required
def platform_revenue_transactions_view(request):
    """
    Dedicated financial transaction ledger with type and status filtering.
    """
    type_filter = request.GET.get('type', 'all').lower()
    status_filter = request.GET.get('status', 'all').lower()

    transactions = RevenueTransaction.objects.all().select_related(
        'provider', 'provider__user', 'booking', 'service'
    ).order_by('-created_at')

    if type_filter in ['commission', 'subscription', 'featured']:
        transactions = transactions.filter(revenue_type=type_filter)
    else:
        type_filter = 'all'

    if status_filter in ['completed', 'pending', 'failed']:
        transactions = transactions.filter(status=status_filter)
    else:
        status_filter = 'all'

    all_tx = RevenueTransaction.objects.all()
    all_count = all_tx.count()
    commission_count = all_tx.filter(revenue_type='commission').count()
    subscription_count = all_tx.filter(revenue_type='subscription').count()
    featured_count = all_tx.filter(revenue_type='featured').count()

    total_filtered_sum = transactions.filter(status='completed').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    return render(request, 'platform/transactions.html', {
        'transactions': transactions,
        'type_filter': type_filter,
        'status_filter': status_filter,
        'all_count': all_count,
        'commission_count': commission_count,
        'subscription_count': subscription_count,
        'featured_count': featured_count,
        'total_filtered_sum': total_filtered_sum,
        'active_tab': 'transactions',
    })


@admin_required
def platform_revenue_evidence_view(request):
    """
    RGM Audit & Revenue Evidence Summary.
    Enables administrative auditing, filtering by demo/actual status and verification,
    and supports print layout and CSV export for university SCRGM submission.
    """
    data_filter = request.GET.get('data', 'actual').lower()  # 'actual' (is_demo=False), 'demo', 'all'
    verif_filter = request.GET.get('verification', 'all').lower()
    type_filter = request.GET.get('type', 'all').lower()

    queryset = RevenueTransaction.objects.all().select_related(
        'provider', 'provider__user', 'booking', 'service', 'booking__customer'
    ).order_by('-created_at')

    if data_filter == 'actual':
        queryset = queryset.filter(is_demo=False)
    elif data_filter == 'demo':
        queryset = queryset.filter(is_demo=True)
    else:
        data_filter = 'all'

    if verif_filter in ['verified', 'pending', 'rejected']:
        queryset = queryset.filter(verification_status=verif_filter)
    else:
        verif_filter = 'all'

    if type_filter in ['commission', 'subscription', 'featured']:
        queryset = queryset.filter(revenue_type=type_filter)
    else:
        type_filter = 'all'

    # CSV Export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="servora_rgm_evidence_audit.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Transaction ID',
            'Date',
            'Revenue Source',
            'Servora Revenue (INR)',
            'Status',
            'Verification Status',
            'Transaction Reference / UTR',
            'Payment Method',
            'Evidence Available',
            'Provider Username',
            'Provider Name',
            'Booking/Service Ref',
            'Evidence Notes',
            'Data Type',
        ])
        for tx in queryset:
            writer.writerow([
                f"TXN#{tx.id:05d}",
                tx.created_at.strftime('%Y-%m-%d %H:%M'),
                tx.get_revenue_type_display(),
                f"{tx.amount:.2f}",
                tx.get_status_display(),
                tx.get_verification_status_display(),
                tx.transaction_reference or 'N/A',
                tx.get_payment_method_display() if tx.payment_method else 'N/A',
                'Yes' if tx.has_evidence else 'No',
                tx.provider.user.username,
                tx.provider.user.get_full_name() or tx.provider.user.username,
                f"Booking #SVR{tx.booking.id:05d}" if tx.booking else (tx.service.title if tx.service else 'N/A'),
                tx.evidence_note or '',
                'Demonstration (Synthetic)' if tx.is_demo else 'Actual Pilot Record',
            ])
        return response

    total_amount = queryset.filter(status='completed').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    verified_sum = queryset.filter(
        status='completed',
        is_demo=False,
        verification_status='verified',
        has_evidence=True
    ).exclude(
        Q(transaction_reference__isnull=True) | Q(transaction_reference__exact='')
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    return render(request, 'platform/evidence.html', {
        'transactions': queryset,
        'total_amount': total_amount,
        'verified_sum': verified_sum,
        'data_filter': data_filter,
        'verif_filter': verif_filter,
        'type_filter': type_filter,
        'total_count': queryset.count(),
        'active_tab': 'evidence',
    })


@login_required
def commercial_receipt_view(request, booking_id):
    """
    Renders a clean, official SERVORA COMMERCIAL SERVICE RECEIPT.
    Available for completed bookings.
    Strictly free from fake GSTIN, fake tax registrations, or false government claims.
    Accessible by booking customer, service provider, or platform staff.
    """
    booking = get_object_or_404(
        Booking.objects.select_related('service', 'service__provider', 'service__provider__user', 'customer'),
        id=booking_id
    )

    # Security check: only customer, provider, or staff can view
    is_cust = (request.user == booking.customer)
    is_prov = (hasattr(request.user, 'profile') and request.user.profile == booking.service.provider)
    if not (is_cust or is_prov or request.user.is_staff):
        messages.error(request, "You are not authorized to view this receipt.")
        return redirect('my_bookings')

    if booking.status != 'completed':
        messages.warning(request, "Commercial receipts are generated only for completed service bookings.")
        return redirect('booking_detail', booking_id=booking.id)

    provider_earning = booking.provider_earning
    review = getattr(booking, 'review', None)
    payment_txn = booking.payment_transactions.filter(status='captured').first()
    approved_materials = booking.materials.filter(status='approved')

    return render(request, 'services/receipt.html', {
        'booking': booking,
        'service': booking.service,
        'customer': booking.customer,
        'provider': booking.service.provider,
        'provider_earning': provider_earning,
        'review': review,
        'payment_txn': payment_txn,
        'approved_materials': approved_materials,
    })



@login_required
def leave_review_view(request, booking_id):
    """
    Customer review and rating submission view for a completed booking.
    Strictly verifies customer ownership and booking completion.
    """
    # 1. Reject provider accounts attempting customer reviews
    if hasattr(request.user, 'profile') and request.user.profile.is_provider:
        messages.error(request, "Service provider accounts cannot submit customer reviews.")
        return redirect('home')

    booking = get_object_or_404(
        Booking.objects.select_related('service', 'service__provider', 'service__provider__user', 'service__category'),
        id=booking_id,
        customer=request.user
    )

    if booking.status != 'completed':
        messages.error(request, "Reviews can only be submitted for completed bookings.")
        return redirect('booking_detail', booking_id=booking.id)

    # 2. Prevent duplicate reviews for the same booking
    if hasattr(booking, 'review') and booking.review is not None:
        messages.info(request, "You have already reviewed this service booking. Thank you for your feedback!")
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.booking = booking
            review.customer = request.user
            review.service = booking.service
            review.save()

            # Notify the service provider about the new review
            create_notification(
                recipient=booking.service.provider.user,
                notification_type='review_received',
                title='New Review Received',
                message=f"{request.user.get_full_name() or request.user.username} gave your {booking.service.title} service {review.rating} stars: \"{review.comment[:60]}...\"",
                booking=booking,
                service=booking.service
            )

            messages.success(request, f"Thank you for reviewing {booking.service.title}! Your rating helps our local community.")
            return redirect('booking_detail', booking_id=booking.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        form = ReviewForm()

    return render(request, 'services/leave_review.html', {
        'booking': booking,
        'service': booking.service,
        'form': form,
    })


@login_required
def notifications_list_view(request):
    """
    Reverse-chronological notification center for customer and provider alerts.
    """
    notifications = Notification.objects.filter(
        recipient=request.user
    ).select_related('booking', 'service').order_by('-created_at')

    unread_count = notifications.filter(is_read=False).count()

    return render(request, 'notifications/list.html', {
        'notifications': notifications,
        'unread_count': unread_count,
        'active_tab': 'notifications',
    })


@login_required
def notification_mark_read_view(request, id):
    """
    Marks a single notification as read and redirects to relevant target or notifications list.
    """
    notif = get_object_or_404(Notification, id=id, recipient=request.user)
    notif.is_read = True
    notif.save(update_fields=['is_read'])

    next_url = request.GET.get('next')
    if next_url:
        return redirect(next_url)

    if notif.booking:
        if hasattr(request.user, 'profile') and request.user.profile.is_provider:
            return redirect('provider_job_detail', booking_id=notif.booking.id)
        return redirect('booking_detail', booking_id=notif.booking.id)
    elif notif.service:
        return redirect('service_detail', id=notif.service.id)

    return redirect('notifications_list')


@login_required
def notification_mark_all_read_view(request):
    """
    POST action: Marks all unread notifications for the logged-in user as read.
    """
    if request.method == 'POST':
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        messages.success(request, "All notifications marked as read.")
    return redirect('notifications_list')


def api_services_list(request):
    """
    JSON response endpoint returning database service information.
    Fulfills the academic JSON response requirement.
    """
    services = list(Service.objects.filter(is_active=True).values('id', 'title', 'price', 'location'))
    return JsonResponse({'services': services, 'count': len(services)})


def archive_bookings_view(request, year, month):
    """
    Archive view accessed via regex re_path URL converter.
    Fulfills the academic re_path requirement.
    """
    bookings = Booking.objects.filter(booking_date__year=year, booking_date__month=month)
    return HttpResponse(f"Archived bookings for {year}-{month}: {bookings.count()} found.")


def custom_404_view(request, exception=None):
    """
    Branded 404 error page matching the Servora luxury design system.
    """
    return render(request, '404.html', status=404)


def custom_500_view(request):
    """
    Branded 500 server error page matching the Servora luxury design system.
    """
    return render(request, '500.html', status=500)


# ============================================================
# STAGE 8A: PAYMENT SYSTEM, CHECKOUT & PROVIDER SETTLEMENTS
# ============================================================

@login_required
def checkout_view(request, booking_id):
    """
    Customer checkout screen for a booking.
    Validates customer ownership and displays transparent price breakdown:
    Total to Pay = Base Service + Approved Materials (no hidden surcharges).
    Platform commission (10% on service only) and 100% material reimbursement are shown transparently.
    Real dynamic QR code is generated with server-side final_amount and configured merchant VPA.
    """
    booking = get_object_or_404(
        Booking.objects.select_related('service', 'service__provider', 'service__provider__user', 'customer'),
        id=booking_id
    )

    # Security: Service providers cannot place/checkout customer bookings
    if hasattr(request.user, 'profile') and request.user.profile.is_provider:
        messages.error(request, "Service provider accounts cannot perform customer checkouts.")
        return redirect('service_detail', id=booking.service.id)

    # Security: Only booking customer can checkout
    if booking.customer != request.user:
        messages.error(request, "You are not authorized to checkout for this booking.")
        return redirect('my_bookings')

    # If already paid, notify and redirect to booking detail
    if booking.payment_status == 'paid':
        messages.info(request, f"Booking #SVR{booking.id:05d} has already been paid.")
        return redirect('booking_detail', booking_id=booking.id)

    final_amt = getattr(booking, 'final_amount', booking.total_amount)
    split = PaymentService.calculate_split(
        gross_amount=final_amt,
        materials_amount=getattr(booking, 'materials_amount', Decimal('0.00')),
        service_amount=getattr(booking, 'service_amount', final_amt)
    )
    active_txn = PaymentService.create_payment_order(booking, payment_method='upi')

    # NPCI UPI Intent URI and Real Dynamic QR Code Image (Base64)
    upi_intent = TestGatewayAdapter.generate_upi_qr_data(active_txn.gateway_order_id, final_amt)
    qr_base64 = TestGatewayAdapter.generate_qr_image_base64(upi_intent)
    approved_materials = booking.materials.filter(status='approved')
    is_test_mode = (getattr(settings, 'PAYMENT_GATEWAY_MODE', 'test') == 'test')
    merchant_vpa = TestGatewayAdapter.get_merchant_vpa()
    merchant_name = TestGatewayAdapter.get_merchant_name()

    test_payment_id = f"pay_test_{booking.id}_{int(timezone.now().timestamp())}"
    test_signature = TestGatewayAdapter.generate_signature(active_txn.gateway_order_id, test_payment_id)

    return render(request, 'services/checkout.html', {
        'booking': booking,
        'service': booking.service,
        'split': split,
        'active_txn': active_txn,
        'test_payment_id': test_payment_id,
        'test_signature': test_signature,
        'gateway_key_id': TestGatewayAdapter.get_key_id(),
        'upi_intent': upi_intent,
        'upi_vpa': merchant_vpa,
        'merchant_name': merchant_name,
        'qr_base64': qr_base64,
        'is_test_mode': is_test_mode,
        'approved_materials': approved_materials,
    })


@login_required
def checkout_qr_view(request, booking_id):
    """
    Streams the raw PNG image bytes of the dynamic UPI QR code.
    Strictly restricted to the booking customer or staff.
    """
    booking = get_object_or_404(Booking, id=booking_id)
    if booking.customer != request.user and not request.user.is_staff:
        return HttpResponse("Forbidden", status=403)

    active_txn = PaymentService.create_payment_order(booking, payment_method='upi')
    final_amt = getattr(booking, 'final_amount', booking.total_amount)
    upi_intent = TestGatewayAdapter.generate_upi_qr_data(active_txn.gateway_order_id, final_amt)
    png_bytes = TestGatewayAdapter.generate_qr_image_bytes(upi_intent)
    return HttpResponse(png_bytes, content_type='image/png')


@login_required
def payment_status_view(request, booking_id):
    """
    Pollable status endpoint for automatic payment verification.
    Retrieves current payment status from the database without mutating state.
    """
    booking = get_object_or_404(Booking, id=booking_id)
    if booking.customer != request.user and not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    return JsonResponse({
        'booking_id': booking.id,
        'payment_status': booking.payment_status,
        'is_paid': (booking.payment_status == 'paid'),
        'final_amount': str(getattr(booking, 'final_amount', booking.total_amount)),
    })


@login_required
def payment_simulate_view(request, booking_id):
    """
    POST-only endpoint for test-mode payment gateway simulation.
    Triggers the authentic webhook HMAC-SHA256 signature and verification pipeline.
    Explicitly disabled in live mode.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    if getattr(settings, 'PAYMENT_GATEWAY_MODE', 'test') != 'test':
        return JsonResponse({'error': 'Simulation is disabled in live gateway mode.'}, status=403)

    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    if booking.payment_status == 'paid':
        return JsonResponse({'success': True, 'message': 'Booking has already been paid.', 'is_paid': True})

    result = TestGatewayAdapter.simulate_gateway_payment_webhook(booking)
    booking.refresh_from_db()

    return JsonResponse({
        'success': result.get('success', False),
        'status': result.get('status', 200),
        'is_paid': (booking.payment_status == 'paid'),
        'payment_status': booking.payment_status,
        'message': result.get('message', ''),
        'error': result.get('error', ''),
    })


@login_required
def payment_create_view(request, booking_id):
    """
    POST endpoint to initialize or re-generate a payment gateway order.
    Server strictly determines the transaction amount from booking.final_amount.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)

    if booking.payment_status == 'paid':
        return JsonResponse({'error': 'Booking has already been paid.'}, status=400)

    payment_method = request.POST.get('payment_method', 'upi')
    txn = PaymentService.create_payment_order(booking, payment_method=payment_method)
    
    test_payment_id = f"pay_test_{booking.id}_{int(timezone.now().timestamp())}"
    test_signature = TestGatewayAdapter.generate_signature(txn.gateway_order_id, test_payment_id)

    return JsonResponse({
        'success': True,
        'order_id': txn.gateway_order_id,
        'amount': str(txn.amount),
        'currency': txn.currency,
        'payment_method': txn.payment_method,
        'test_payment_id': test_payment_id,
        'test_signature': test_signature,
    })


@login_required
def payment_success_view(request, booking_id):
    """
    Gateway payment verification and landing view.
    Never marks a booking as paid merely because the URL was visited or parameter supplied.
    Reads verified payment status from the database.
    """
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)

    if request.method == 'POST':
        gateway_order_id = request.POST.get('gateway_order_id')
        gateway_payment_id = request.POST.get('gateway_payment_id')
        gateway_signature = request.POST.get('gateway_signature')
        payment_method = request.POST.get('payment_method', 'upi')

        if not (gateway_order_id and gateway_payment_id and gateway_signature):
            messages.error(request, "Incomplete payment verification parameters.")
            return redirect('checkout', booking_id=booking.id)

        try:
            PaymentService.verify_and_capture_payment(
                booking=booking,
                gateway_order_id=gateway_order_id,
                gateway_payment_id=gateway_payment_id,
                gateway_signature=gateway_signature,
                payment_method=payment_method
            )

            create_notification(
                recipient=booking.service.provider.user,
                notification_type='payment_received',
                title='Payment Received',
                message=f"Customer {booking.customer.get_full_name() or booking.customer.username} paid ₹{booking.final_amount:.2f} for Booking #SVR{booking.id:05d}.",
                booking=booking,
                service=booking.service
            )

            messages.success(
                request, 
                f"Payment of ₹{booking.final_amount:.2f} confirmed successfully! Reference: {gateway_payment_id}."
            )
            return redirect('booking_detail', booking_id=booking.id)
        except ValueError as e:
            messages.error(request, f"Payment verification failed: {str(e)}")
            return redirect('checkout', booking_id=booking.id)

    # GET request: Never self-declares payment paid; reads state strictly from database
    if booking.payment_status == 'paid':
        messages.success(request, f"Payment of ₹{booking.final_amount:.2f} is verified and confirmed!")
        return redirect('booking_detail', booking_id=booking.id)

    messages.info(request, "Payment verification in progress. Awaiting confirmation from your UPI app.")
    return redirect('checkout', booking_id=booking.id)


@login_required
def payment_failed_view(request, booking_id):
    """
    Handles payment failure or user checkout abandonment.
    Updates transaction status to 'failed' without creating revenue or settlement.
    """
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    reason = request.POST.get('failure_reason', 'Transaction was cancelled or declined.')
    order_id = request.POST.get('gateway_order_id')

    PaymentService.handle_payment_failure(booking, failure_reason=reason, gateway_order_id=order_id)

    messages.warning(request, f"Payment was not completed: {reason}. You can retry anytime.")
    return redirect('checkout', booking_id=booking.id)


@csrf_exempt
def payment_webhook_view(request):
    """
    Payment gateway webhook receiver.
    Verifies webhook HMAC signature and delegates idempotent processing.
    """
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)

    signature = (
        request.headers.get('X-Razorpay-Signature') 
        or request.headers.get('X-Payment-Signature') 
        or request.META.get('HTTP_X_PAYMENT_SIGNATURE', '')
    )

    result = PaymentService.process_webhook_event(request.body, signature)
    return JsonResponse(result, status=result.get('status', 200))


@login_required
def customer_payment_history_view(request):
    """
    Customer portal view displaying full payment history, methods, and receipt links.
    """
    if hasattr(request.user, 'profile') and request.user.profile.is_provider:
        messages.info(request, "Providers can track settlements under Provider Financials.")
        return redirect('provider_settlements')

    payments = PaymentTransaction.objects.filter(customer=request.user).select_related(
        'booking', 'booking__service', 'provider', 'provider__user'
    ).order_by('-created_at')

    total_paid = payments.filter(status='captured').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    return render(request, 'services/payment_history.html', {
        'payments': payments,
        'total_paid': total_paid,
        'total_count': payments.count(),
    })


@provider_required
def provider_payout_settings_view(request):
    """
    Allows service providers to configure their payout disbursement preferences (UPI ID / Bank details).
    Enforces strict security notice against disclosing sensitive credentials.
    """
    profile = request.user.profile

    if request.method == 'POST':
        form = ProviderPayoutSettingsForm(request.POST)
        if form.is_valid():
            profile.payout_upi_id = form.cleaned_data['payout_upi_id']
            profile.payout_upi_name = form.cleaned_data['payout_upi_name']
            profile.payout_preference = form.cleaned_data['payout_preference']
            profile.payout_status = 'ready'
            profile.save()
            messages.success(request, "Payout disbursement settings updated successfully!")
            return redirect('provider_payout_settings')
    else:
        form = ProviderPayoutSettingsForm(initial={
            'payout_upi_id': profile.payout_upi_id,
            'payout_upi_name': profile.payout_upi_name,
            'payout_preference': profile.payout_preference,
        })

    return render(request, 'provider/payout_settings.html', {
        'form': form,
        'profile': profile,
        'active_tab': 'payout_settings',
    })


@provider_required
def provider_settlements_view(request):
    """
    Provider settlement ledger displaying pending and paid disbursements
    for completed customer bookings, itemizing service earnings vs materials reimbursement.
    """
    profile = request.user.profile
    settlements = ProviderSettlement.objects.filter(provider=profile).select_related(
        'booking', 'booking__service', 'booking__customer', 'payment_transaction'
    ).order_by('-created_at')

    pending_total = settlements.filter(status='pending').aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')
    paid_total = settlements.filter(status='paid').aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')
    gross_total = settlements.filter(status__in=['pending', 'paid']).aggregate(total=Sum('gross_amount'))['total'] or Decimal('0.00')
    commission_total = settlements.filter(status__in=['pending', 'paid']).aggregate(total=Sum('commission_amount'))['total'] or Decimal('0.00')
    service_total = settlements.filter(status__in=['pending', 'paid']).aggregate(total=Sum('service_amount'))['total'] or Decimal('0.00')
    materials_total = settlements.filter(status__in=['pending', 'paid']).aggregate(total=Sum('materials_amount'))['total'] or Decimal('0.00')

    return render(request, 'provider/settlements.html', {
        'settlements': settlements,
        'pending_total': pending_total,
        'paid_total': paid_total,
        'gross_total': gross_total,
        'commission_total': commission_total,
        'service_total': service_total,
        'materials_total': materials_total,
        'active_tab': 'settlements',
    })


@admin_required
def platform_payments_dashboard_view(request):
    """
    Staff-only platform payment administration dashboard.
    Visualizes Gross Booking Value, platform commissions, provider settlements, materials reimbursements,
    and gateway ledger.
    """
    all_payments = PaymentTransaction.objects.select_related('booking', 'customer', 'provider__user').all()
    all_settlements = ProviderSettlement.objects.select_related('booking', 'provider__user').all()

    total_payments_count = all_payments.count()
    successful_payments = all_payments.filter(status='captured')
    successful_count = successful_payments.count()
    failed_count = all_payments.filter(status='failed').count()
    pending_count = all_payments.filter(status__in=['created', 'pending']).count()
    refunded_count = all_payments.filter(status='refunded').count()

    gross_booking_value = successful_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    service_revenue_basis = all_settlements.filter(status__in=['pending', 'paid']).aggregate(total=Sum('service_amount'))['total'] or Decimal('0.00')
    materials_reimbursements_total = all_settlements.filter(status__in=['pending', 'paid']).aggregate(total=Sum('materials_amount'))['total'] or Decimal('0.00')
    platform_commission = all_settlements.filter(status__in=['pending', 'paid']).aggregate(total=Sum('commission_amount'))['total'] or Decimal('0.00')
    if not platform_commission and gross_booking_value:
        platform_commission = (service_revenue_basis * Decimal('0.10')).quantize(Decimal('0.01'))
    provider_payout_total = all_settlements.filter(status__in=['pending', 'paid']).aggregate(total=Sum('payout_amount'))['total'] or (gross_booking_value - platform_commission)

    pending_settlements_amount = all_settlements.filter(status='pending').aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')
    completed_settlements_amount = all_settlements.filter(status='paid').aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')
    pending_material_approvals_count = BookingMaterial.objects.filter(status='pending').count()

    return render(request, 'platform/payments_dashboard.html', {
        'payments': all_payments[:25],
        'settlements': all_settlements[:25],
        'total_payments_count': total_payments_count,
        'successful_count': successful_count,
        'failed_count': failed_count,
        'pending_count': pending_count,
        'refunded_count': refunded_count,
        'gross_booking_value': gross_booking_value,
        'service_revenue_basis': service_revenue_basis,
        'materials_reimbursements_total': materials_reimbursements_total,
        'platform_commission': platform_commission,
        'provider_payout_total': provider_payout_total,
        'pending_settlements_amount': pending_settlements_amount,
        'completed_settlements_amount': completed_settlements_amount,
        'pending_material_approvals_count': pending_material_approvals_count,
        'active_tab': 'payments',
    })


# ============================================================
# STAGE 8B: DYNAMIC PRICING & MATERIALS WORKFLOW VIEWS
# ============================================================

@provider_required
def provider_booking_materials_view(request, booking_id):
    """
    Lists and manages dynamic material cost proposals for a specific job.
    """
    provider = request.user.profile
    booking = get_object_or_404(
        Booking.objects.select_related('service', 'customer'),
        id=booking_id,
        service__provider=provider
    )
    materials = booking.materials.all().order_by('-created_at')
    approved_total = materials.filter(status='approved').aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
    pending_total = materials.filter(status='pending').aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')

    return render(request, 'provider/booking_materials.html', {
        'booking': booking,
        'materials': materials,
        'approved_total': approved_total,
        'pending_total': pending_total,
        'active_tab': 'jobs',
    })


@provider_required
def provider_add_material_view(request, booking_id):
    """
    Allows service providers to propose on-the-job physical parts and materials.
    Enforces positive quantity, minimum unit price, and file security checks.
    Materials proposal requires customer review and approval.
    """
    provider = request.user.profile
    booking = get_object_or_404(
        Booking.objects.select_related('service', 'customer'),
        id=booking_id,
        service__provider=provider
    )

    # Security check: Can only add materials while job is in progress ('accepted') and unpaid
    if booking.status != 'accepted':
        messages.warning(request, f"Cannot propose materials for a booking in '{booking.get_status_display()}' status.")
        return redirect('provider_job_detail', booking_id=booking.id)

    if booking.payment_status == 'paid':
        messages.warning(request, "Cannot propose additional materials for a booking that has already been paid.")
        return redirect('provider_job_detail', booking_id=booking.id)

    if request.method == 'POST':
        form = BookingMaterialForm(request.POST, request.FILES)
        if form.is_valid():
            material = form.save(commit=False)
            material.booking = booking
            material.added_by = request.user
            material.status = 'pending'
            material.save()

            create_notification(
                recipient=booking.customer,
                notification_type='materials_added',
                title='Additional Costs Requested',
                message=f"Provider {request.user.get_full_name() or request.user.username} requested approval for materials: {material.name} (₹{material.total_price:.2f}) on Booking #SVR{booking.id:05d}.",
                booking=booking,
                service=booking.service
            )

            messages.success(request, f"Material '{material.name}' (₹{material.total_price:.2f}) added! Awaiting customer review and approval.")
            return redirect('provider_job_detail', booking_id=booking.id)
    else:
        form = BookingMaterialForm()

    return render(request, 'provider/material_form.html', {
        'booking': booking,
        'form': form,
        'action_title': 'Add Material / Replacement Part',
        'active_tab': 'jobs',
    })


@provider_required
def provider_edit_material_view(request, material_id):
    """
    Allows service provider to edit a pending material proposal before customer approval.
    Approved or rejected materials cannot be edited.
    """
    provider = request.user.profile
    material = get_object_or_404(
        BookingMaterial.objects.select_related('booking', 'booking__service', 'booking__service__provider'),
        id=material_id,
        booking__service__provider=provider
    )

    if material.status != 'pending':
        messages.error(request, f"Cannot edit material item because it is already {material.get_status_display().lower()}.")
        return redirect('provider_job_detail', booking_id=material.booking.id)

    if request.method == 'POST':
        form = BookingMaterialForm(request.POST, request.FILES, instance=material)
        if form.is_valid():
            form.save()
            messages.success(request, f"Material item '{material.name}' updated successfully.")
            return redirect('provider_job_detail', booking_id=material.booking.id)
    else:
        form = BookingMaterialForm(instance=material)

    return render(request, 'provider/material_form.html', {
        'booking': material.booking,
        'material': material,
        'form': form,
        'action_title': f"Edit Material: {material.name}",
        'active_tab': 'jobs',
    })


@provider_required
def provider_delete_material_view(request, material_id):
    """
    Allows service provider to remove an unapproved material item.
    """
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('provider_jobs')

    provider = request.user.profile
    material = get_object_or_404(
        BookingMaterial.objects.select_related('booking', 'booking__service', 'booking__service__provider'),
        id=material_id,
        booking__service__provider=provider
    )

    if material.status == 'approved':
        messages.error(request, "Cannot delete an approved material item.")
        return redirect('provider_job_detail', booking_id=material.booking.id)

    name = material.name
    booking_id = material.booking.id
    material.delete()
    messages.success(request, f"Material item '{name}' was removed.")
    return redirect('provider_job_detail', booking_id=booking_id)


@login_required
def secure_material_receipt_view(request, material_id):
    """
    Access-controlled endpoint to view material purchase receipt images/proofs.
    Accessible strictly by the booking customer, assigned provider, or authorized staff.
    """
    material = get_object_or_404(
        BookingMaterial.objects.select_related('booking', 'booking__customer', 'booking__service__provider__user'),
        id=material_id
    )

    is_customer = (material.booking.customer == request.user)
    is_provider = (material.booking.service.provider.user == request.user)
    is_staff = request.user.is_staff or request.user.is_superuser

    if not (is_customer or is_provider or is_staff):
        return HttpResponseForbidden("Access Denied: You are not authorized to view this material receipt.")

    if not material.receipt_image:
        messages.info(request, "No receipt file is attached to this material item.")
        if is_provider:
            return redirect('provider_job_detail', booking_id=material.booking.id)
        return redirect('booking_detail', booking_id=material.booking.id)

    return FileResponse(material.receipt_image.open('rb'))


@login_required
def customer_approve_materials_view(request, booking_id):
    """
    Customer approval action: approves all pending materials on their booking.
    Recalculates booking.materials_amount, locks booking.final_amount,
    and updates notification for provider.
    """
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('booking_detail', booking_id=booking_id)

    booking = get_object_or_404(
        Booking.objects.select_related('service', 'service__provider__user'),
        id=booking_id,
        customer=request.user
    )

    if booking.payment_status == 'paid':
        messages.info(request, "Booking is already paid.")
        return redirect('booking_detail', booking_id=booking.id)

    pending_items = booking.materials.filter(status='pending')
    if not pending_items.exists():
        messages.info(request, "There are no pending material costs to approve.")
        return redirect('booking_detail', booking_id=booking.id)

    pending_items.update(status='approved')

    # Recalculate materials_amount from all approved items
    approved_total = booking.materials.filter(status='approved').aggregate(
        total=Sum('total_price')
    )['total'] or Decimal('0.00')

    booking.materials_amount = approved_total
    booking.save()

    create_notification(
        recipient=booking.service.provider.user,
        notification_type='materials_approved',
        title='Materials Approved by Customer',
        message=f"Customer {request.user.get_full_name() or request.user.username} approved material costs (₹{approved_total:.2f}) for Booking #SVR{booking.id:05d}. Final payable total: ₹{booking.total_amount:.2f}.",
        booking=booking,
        service=booking.service
    )

    messages.success(
        request, 
        f"Approved ₹{approved_total:.2f} in material costs. Final payable amount is now ₹{booking.total_amount:.2f}."
    )
    return redirect('booking_detail', booking_id=booking.id)


@login_required
def customer_reject_materials_view(request, booking_id):
    """
    Customer rejection action: rejects all pending materials on their booking.
    Preserves original service charge, does not delete rejected records,
    and notifies provider.
    """
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('booking_detail', booking_id=booking_id)

    booking = get_object_or_404(
        Booking.objects.select_related('service', 'service__provider__user'),
        id=booking_id,
        customer=request.user
    )

    if booking.payment_status == 'paid':
        messages.info(request, "Booking is already paid.")
        return redirect('booking_detail', booking_id=booking.id)

    pending_items = booking.materials.filter(status='pending')
    if not pending_items.exists():
        messages.info(request, "There are no pending material costs to reject.")
        return redirect('booking_detail', booking_id=booking.id)

    pending_total = pending_items.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
    pending_items.update(status='rejected')

    # Retain only previously approved materials (or 0)
    approved_total = booking.materials.filter(status='approved').aggregate(
        total=Sum('total_price')
    )['total'] or Decimal('0.00')
    booking.materials_amount = approved_total
    booking.save()

    create_notification(
        recipient=booking.service.provider.user,
        notification_type='materials_rejected',
        title='Materials Proposal Declined',
        message=f"Customer {request.user.get_full_name() or request.user.username} declined the additional material costs (₹{pending_total:.2f}) for Booking #SVR{booking.id:05d}. Payable total remains ₹{booking.total_amount:.2f}.",
        booking=booking,
        service=booking.service
    )

    messages.info(request, "Additional material costs were declined. Your payable amount remains unchanged.")
    return redirect('booking_detail', booking_id=booking.id)


