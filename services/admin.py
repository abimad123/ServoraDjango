from django.contrib import admin
from .models import (
    Category, Service, Booking, Review, FeaturedListing, RevenueTransaction, 
    Notification, PaymentTransaction, ProviderSettlement
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon_name', 'order')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('title', 'provider', 'category', 'price', 'location', 'is_featured', 'is_active', 'created_at')
    list_filter = ('category', 'is_featured', 'is_active', 'location')
    search_fields = ('title', 'description', 'provider__user__username', 'location')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('price', 'is_featured', 'is_active')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'service', 'customer', 'booking_date', 'booking_time', 'total_amount', 'commission_amount', 'status', 'payment_status', 'created_at')
    list_filter = ('status', 'payment_status', 'booking_date', 'service__category')
    search_fields = ('service__title', 'customer__username', 'customer__first_name', 'customer__last_name')
    date_hierarchy = 'booking_date'
    list_editable = ('status', 'payment_status')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('service', 'customer', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('service__title', 'customer__username', 'comment')


@admin.register(FeaturedListing)
class FeaturedListingAdmin(admin.ModelAdmin):
    list_display = ('service', 'fee_paid', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active',)


@admin.register(RevenueTransaction)
class RevenueTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'revenue_type', 'amount', 'provider', 'status',
        'is_demo', 'verification_status', 'payment_method', 'has_evidence',
        'transaction_reference', 'created_at'
    )
    list_filter = (
        'is_demo', 'verification_status', 'revenue_type', 'status',
        'payment_method', 'has_evidence', 'created_at'
    )
    search_fields = (
        'transaction_reference', 'provider__user__username',
        'provider__user__first_name', 'provider__user__last_name',
        'description', 'booking__id', 'evidence_note'
    )
    list_editable = ('verification_status', 'has_evidence')
    actions = ['mark_as_verified', 'mark_as_rejected', 'mark_as_actual_pilot', 'mark_as_demo']

    @admin.action(description="Mark selected transactions as Verified (with evidence confirmed)")
    def mark_as_verified(self, request, queryset):
        updated = queryset.update(verification_status='verified', has_evidence=True)
        self.message_user(request, f"{updated} transaction(s) marked as Verified.")

    @admin.action(description="Mark selected transactions as Rejected")
    def mark_as_rejected(self, request, queryset):
        updated = queryset.update(verification_status='rejected')
        self.message_user(request, f"{updated} transaction(s) marked as Rejected.")

    @admin.action(description="Mark selected as Actual Pilot transactions (is_demo=False)")
    def mark_as_actual_pilot(self, request, queryset):
        updated = queryset.update(is_demo=False)
        self.message_user(request, f"{updated} transaction(s) flagged as Actual Pilot records.")

    @admin.action(description="Mark selected as Demo/Synthetic transactions (is_demo=True)")
    def mark_as_demo(self, request, queryset):
        updated = queryset.update(is_demo=True)
        self.message_user(request, f"{updated} transaction(s) flagged as Demo records.")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notification_type', 'title', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('recipient__username', 'title', 'message')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'booking', 'customer', 'provider', 'amount', 'currency',
        'payment_method', 'status', 'gateway_payment_id', 'gateway_order_id',
        'is_demo', 'paid_at', 'created_at'
    )
    list_filter = ('status', 'payment_method', 'gateway', 'is_demo', 'created_at')
    search_fields = (
        'gateway_order_id', 'gateway_payment_id', 'customer__username',
        'provider__user__username', 'booking__id'
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProviderSettlement)
class ProviderSettlementAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'booking', 'provider', 'gross_amount', 'commission_amount',
        'payout_amount', 'status', 'payout_reference', 'settlement_date', 'created_at'
    )
    list_filter = ('status', 'settlement_date', 'created_at')
    search_fields = (
        'payout_reference', 'provider__user__username',
        'booking__id', 'payment_transaction__gateway_payment_id'
    )
    list_editable = ('status', 'payout_reference')


