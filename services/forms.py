from django import forms
from datetime import date, datetime, time
from decimal import Decimal
from .models import Booking, Service, Review

# Pre-defined allowable time slots matching the UI design specs
ALLOWED_TIME_SLOTS = [
    # Morning
    time(9, 0), time(9, 30), time(10, 0), time(10, 30), time(11, 0),
    # Afternoon
    time(13, 0), time(13, 30), time(14, 0), time(14, 30), time(15, 0),
    # Evening
    time(17, 0), time(17, 30), time(18, 0), time(18, 30), time(19, 0),
]

TIME_CHOICES = [
    (t.strftime('%H:%M:%S'), datetime.strptime(t.strftime('%H:%M:%S'), '%H:%M:%S').strftime('%I:%M %p'))
    for t in ALLOWED_TIME_SLOTS
]


class BookingCreateForm(forms.Form):
    """
    Validates customer booking submissions, ensuring proper future dates,
    valid pre-defined time slots, and absence of conflicting active bookings.
    """
    booking_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-input',
            'id': 'id_booking_date',
        })
    )
    booking_time = forms.ChoiceField(
        choices=[('', 'Select a time slot')] + TIME_CHOICES,
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_booking_time',
        })
    )
    address = forms.CharField(
        max_length=500,
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 3,
            'placeholder': 'Enter complete service address (House/Flat No, Street, Landmark, City)...',
            'id': 'id_address',
        })
    )
    notes = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 3,
            'placeholder': 'Special instructions or problem details for the service professional...',
            'id': 'id_notes',
        })
    )

    def __init__(self, *args, service=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = service

    def clean_booking_date(self):
        b_date = self.cleaned_data.get('booking_date')
        if b_date and b_date < date.today():
            raise forms.ValidationError("Booking date cannot be in the past. Please choose today or a future date.")
        return b_date

    def clean_booking_time(self):
        t_str = self.cleaned_data.get('booking_time')
        try:
            parsed_time = datetime.strptime(t_str, '%H:%M:%S').time()
        except (ValueError, TypeError):
            raise forms.ValidationError("Please select a valid scheduled time slot.")

        if parsed_time not in ALLOWED_TIME_SLOTS:
            raise forms.ValidationError("Selected time slot is not within valid service hours.")
        return parsed_time

    def clean(self):
        cleaned_data = super().clean()
        b_date = cleaned_data.get('booking_date')
        b_time = cleaned_data.get('booking_time')

        if b_date and b_time and self.service:
            # Server-side double booking protection against pending/accepted jobs
            existing_booking = Booking.objects.filter(
                service=self.service,
                booking_date=b_date,
                booking_time=b_time,
                status__in=['pending', 'accepted']
            ).exists()

            if existing_booking:
                time_display = datetime.strptime(b_time.strftime('%H:%M:%S'), '%H:%M:%S').strftime('%I:%M %p')
                raise forms.ValidationError(
                    f"The time slot {time_display} on {b_date.strftime('%B %d, %Y')} is already booked. Please pick another slot."
                )

        return cleaned_data


class ServiceForm(forms.ModelForm):
    """
    Form for service providers to create and edit their service offerings.
    """
    class Meta:
        model = Service
        fields = ['title', 'category', 'description', 'price', 'duration_estimate', 'location', 'image', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Master Bathroom Leak Diagnosis & Repair'
            }),
            'category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': 'Describe what is included in this service, your diagnostic steps, and guarantees...'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Starting price in ₹ (e.g. 1500.00)',
                'min': '1.00',
                'step': '50.00'
            }),
            'duration_estimate': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. 1-2 hours or Half day'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Kannur, Thalassery & suburbs'
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-file-input'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-checkbox'
            }),
        }

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price <= 0:
            raise forms.ValidationError("Service price must be greater than zero.")
        return price


class ReviewForm(forms.ModelForm):
    """
    Form for customers to submit star ratings and detailed service feedback.
    """
    rating = forms.ChoiceField(
        choices=[
            (5, '★★★★★ (5/5) — Excellent'),
            (4, '★★★★☆ (4/5) — Very Good'),
            (3, '★★★☆☆ (3/5) — Average'),
            (2, '★★☆☆☆ (2/5) — Below Average'),
            (1, '★☆☆☆☆ (1/5) — Poor'),
        ],
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_rating',
        })
    )
    comment = forms.CharField(
        required=True,
        min_length=10,
        max_length=1000,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 4,
            'placeholder': 'Share your experience with the service, punctuality, and quality of work (minimum 10 characters)...',
            'id': 'id_comment',
        }),
        error_messages={
            'required': 'Please share a comment explaining your review.',
            'min_length': 'Your review comment should be at least 10 characters long.',
        }
    )

    class Meta:
        model = Review
        fields = ['rating', 'comment']

    def clean_rating(self):
        rating = self.cleaned_data.get('rating')
        try:
            val = int(rating)
            if val < 1 or val > 5:
                raise forms.ValidationError("Rating must be between 1 and 5 stars.")
            return val
        except (ValueError, TypeError):
            raise forms.ValidationError("Please select a valid rating between 1 and 5.")

    def clean_comment(self):
        comment = self.cleaned_data.get('comment', '').strip()
        if not comment or len(comment) < 10:
            raise forms.ValidationError("Please provide at least 10 characters of detailed feedback.")
        return comment


