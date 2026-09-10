from django.contrib import admin
from .models import Category, Service, Booking, Review, FeaturedListing


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
    list_display = ('id', 'service', 'customer', 'booking_date', 'booking_time', 'total_amount', 'commission_amount', 'status', 'created_at')
    list_filter = ('status', 'booking_date', 'service__category')
    search_fields = ('service__title', 'customer__username', 'customer__first_name', 'customer__last_name')
    date_hierarchy = 'booking_date'
    list_editable = ('status',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('service', 'customer', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('service__title', 'customer__username', 'comment')


@admin.register(FeaturedListing)
class FeaturedListingAdmin(admin.ModelAdmin):
    list_display = ('service', 'fee_paid', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active',)
