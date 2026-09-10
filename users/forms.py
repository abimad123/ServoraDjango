from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile


class UserRegisterForm(UserCreationForm):
    """
    Dual-role user registration form for Customers and Service Providers.
    Collects account credentials along with profile specifics (role, phone, city).
    """
    first_name = forms.CharField(
        max_length=30, 
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        max_length=30, 
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Last Name'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Email Address'})
    )
    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'role-radio'}),
        initial='customer'
    )
    phone = forms.CharField(
        max_length=20, 
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Phone Number (e.g. +91 98471 23456)'})
    )
    city = forms.CharField(
        max_length=100, 
        required=False,
        initial='Kannur',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'City (e.g. Kannur)'})
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'phone', 'city']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Choose a Username'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            profile = user.profile
            profile.role = self.cleaned_data['role']
            profile.phone = self.cleaned_data.get('phone', '')
            profile.city = self.cleaned_data.get('city', 'Kannur')
            profile.save()
        return user


class UserLoginForm(forms.Form):
    """
    Standard login form for existing users.
    """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Username', 'autocomplete': 'username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Password', 'autocomplete': 'current-password'})
    )


class ProviderProfileForm(forms.ModelForm):
    """
    Form for service providers to update their professional profile details.
    """
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Last Name'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Email Address'})
    )

    class Meta:
        model = UserProfile
        fields = ['phone', 'city', 'address', 'bio', 'avatar']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+91 98471 23456'}),
            'city': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'City (e.g. Kannur, Kochi)'}),
            'address': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'Office/Workshop or operating address'}),
            'bio': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4, 'placeholder': 'Tell clients about your trade experience, certifications, and specialties...'}),
            'avatar': forms.FileInput(attrs={'class': 'form-file-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['email'].initial = self.instance.user.email

    def save(self, commit=True):
        profile = super().save(commit=commit)
        user = profile.user
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return profile

