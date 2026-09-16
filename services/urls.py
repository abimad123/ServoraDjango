from django.urls import path, re_path
from . import views

urlpatterns = [
    # Customer routes
    path('', views.home_view, name='home'),
    path('services/', views.service_list_view, name='service_list'),
    path('services/<int:id>/', views.service_detail_view, name='service_detail'),
    path('service/<slug:slug>/', views.service_slug_detail_view, name='service_slug_detail'),
    path('category/<str:name>/', views.category_services_view, name='category_services'),
    path('provider/<int:id>/', views.provider_profile_view, name='provider_profile'),
    path('search/', views.search_view, name='search'),
    path('book/<int:service_id>/', views.book_service_view, name='book_service'),
    path('booking/<int:booking_id>/success/', views.booking_success_view, name='booking_success'),
    path('my-bookings/', views.my_bookings_view, name='my_bookings'),
    path('my-bookings/<int:booking_id>/', views.booking_detail_view, name='booking_detail'),
    path('my-bookings/<int:booking_id>/cancel/', views.cancel_booking_view, name='cancel_booking'),
    path('my-bookings/<int:booking_id>/review/', views.leave_review_view, name='leave_review'),
    path('my-bookings/<int:booking_id>/receipt/', views.commercial_receipt_view, name='booking_receipt'),
    path('notifications/', views.notifications_list_view, name='notifications_list'),
    path('notifications/<int:id>/read/', views.notification_mark_read_view, name='notification_mark_read'),
    path('notifications/read-all/', views.notification_mark_all_read_view, name='notification_mark_all_read'),
    path('provider/bookings/', views.provider_bookings_view, name='provider_bookings'),
    path('api/availability/', views.api_availability_view, name='api_availability'),

    # Provider portal routes
    path('provider/dashboard/', views.provider_dashboard_view, name='provider_dashboard'),
    path('provider/services/', views.provider_services_view, name='provider_services'),
    path('provider/services/add/', views.provider_service_create_view, name='provider_service_add'),
    path('provider/services/edit/<int:id>/', views.provider_service_edit_view, name='provider_service_edit'),
    path('provider/services/delete/<int:id>/', views.provider_service_delete_view, name='provider_service_delete'),
    path('provider/jobs/', views.provider_jobs_view, name='provider_jobs'),
    path('provider/jobs/<int:booking_id>/', views.provider_job_detail_view, name='provider_job_detail'),
    path('provider/jobs/<int:booking_id>/accept/', views.provider_job_accept_view, name='provider_job_accept'),
    path('provider/jobs/<int:booking_id>/decline/', views.provider_job_decline_view, name='provider_job_decline'),
    path('provider/jobs/<int:booking_id>/complete/', views.provider_job_complete_view, name='provider_job_complete'),
    path('provider/schedule/', views.provider_schedule_view, name='provider_schedule'),
    path('provider/earnings/', views.provider_earnings_view, name='provider_earnings'),
    path('provider/subscription/', views.provider_subscription_view, name='provider_subscription'),
    path('provider/services/<int:service_id>/feature/', views.provider_feature_service_view, name='provider_feature_service'),
    path('provider/profile/', views.provider_profile_settings_view, name='provider_profile_settings'),

    # Platform revenue & executive monetization routes
    path('platform/revenue/', views.platform_revenue_dashboard_view, name='platform_revenue'),
    path('platform/revenue/transactions/', views.platform_revenue_transactions_view, name='platform_revenue_transactions'),
    path('platform/revenue/evidence/', views.platform_revenue_evidence_view, name='platform_revenue_evidence'),
    path('platform/payments/', views.platform_payments_dashboard_view, name='platform_payments'),

    # Stage 8A/8B: Customer Checkout, Payments & Provider Settlements
    path('checkout/<int:booking_id>/', views.checkout_view, name='checkout'),
    path('checkout/<int:booking_id>/qr/', views.checkout_qr_view, name='checkout_qr'),
    path('payments/status/<int:booking_id>/', views.payment_status_view, name='payment_status'),
    path('payments/simulate/<int:booking_id>/', views.payment_simulate_view, name='payment_simulate'),
    path('payments/create/<int:booking_id>/', views.payment_create_view, name='payment_create'),
    path('payments/success/<int:booking_id>/', views.payment_success_view, name='payment_success'),
    path('payments/failed/<int:booking_id>/', views.payment_failed_view, name='payment_failed'),
    path('payments/webhook/', views.payment_webhook_view, name='payment_webhook'),
    path('payments/history/', views.customer_payment_history_view, name='customer_payment_history'),
    path('provider/payout-settings/', views.provider_payout_settings_view, name='provider_payout_settings'),
    path('provider/settlements/', views.provider_settlements_view, name='provider_settlements'),

    # Stage 8B: Dynamic Pricing & Materials Workflow Routes
    path('provider/bookings/<int:booking_id>/materials/', views.provider_booking_materials_view, name='provider_booking_materials'),
    path('provider/bookings/<int:booking_id>/materials/add/', views.provider_add_material_view, name='provider_add_material'),
    path('provider/materials/<int:material_id>/edit/', views.provider_edit_material_view, name='provider_edit_material'),
    path('provider/materials/<int:material_id>/delete/', views.provider_delete_material_view, name='provider_delete_material'),
    path('materials/<int:material_id>/receipt/', views.secure_material_receipt_view, name='secure_material_receipt'),
    path('my-bookings/<int:booking_id>/materials/approve/', views.customer_approve_materials_view, name='customer_approve_materials'),
    path('my-bookings/<int:booking_id>/materials/reject/', views.customer_reject_materials_view, name='customer_reject_materials'),

    # Academic requirements: JSON API and re_path
    path('api/services/', views.api_services_list, name='api_services_list'),
    re_path(r'^archive/(?P<year>[0-9]{4})/(?P<month>[0-9]{2})/$', views.archive_bookings_view, name='archive_bookings'),
]
