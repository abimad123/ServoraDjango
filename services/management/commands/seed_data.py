from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from users.models import UserProfile, ProviderSubscription
from services.models import Category, Service, Booking, Review, FeaturedListing, RevenueTransaction
from datetime import date, time, timedelta
from decimal import Decimal


class Command(BaseCommand):
    help = "Seeds the database with full realistic categories, providers, services, reviews, and subscriptions."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding comprehensive Servora marketplace data..."))

        # 1. Superuser
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@servora.com',
                'first_name': 'Platform',
                'last_name': 'Admin',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Created admin superuser (admin / admin123)"))

        # 2. Categories (All 10 required academic categories)
        categories_data = [
            ('Plumbing', 'wrench', 'Reliable pipe repairs, drain clearing, tap installation, geyser servicing, and leak fixing.', 1),
            ('Electrical', 'zap', 'Certified electricians for house wiring, fuse repairs, appliance setup, and safety installations.', 2),
            ('Cleaning', 'spark', 'Deep home cleaning, bathroom scrubbing, kitchen sanitization, and sofa shampooing.', 3),
            ('Painting', 'paint', 'Interior and exterior wall painting, waterproof coating, damp proofing, and texture designs.', 4),
            ('Carpentry', 'hammer', 'Custom furniture repair, door fixing, lock installation, modular fittings, and custom shelves.', 5),
            ('Home Repair', 'tool', 'General handyman fixes, tile realignment, door closer repairs, and wall drilling services.', 6),
            ('Gardening', 'leaf', 'Lawn mowing, landscaping, garden maintenance, weed clearing, and ornamental plant pruning.', 7),
            ('Tutoring', 'book', 'Private home tutors for mathematics, sciences, programming, and academic foundations.', 8),
            ('Photography', 'camera', 'Event photography, family portraits, newborn sessions, and real estate property shoots.', 9),
            ('Computer Repair', 'cpu', 'Laptop screen repair, desktop diagnostics, SSD upgrades, OS recovery, and virus removal.', 10),
        ]

        categories_map = {}
        for name, icon, desc, order in categories_data:
            cat, _ = Category.objects.get_or_create(
                name=name,
                defaults={'icon_name': icon, 'description': desc, 'order': order}
            )
            cat.icon_name = icon
            cat.description = desc
            cat.order = order
            cat.save()
            categories_map[name] = cat
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(categories_map)} categories."))

        # 3. Multiple Verified & Unverified Providers
        providers_data = [
            ('john_plumber', 'John', 'Mathew', 'john@servora.com', 'Kannur', '+91 98471 23456', True,
             'Master plumber with 14+ years of residential and commercial experience. Certified by Kerala Plumbing Association.'),
            ('rahul_electrician', 'Rahul', 'Kumar', 'rahul@servora.com', 'Kannur', '+91 97462 88990', True,
             'Licensed Grade-A wireman and electrical contractor. Specializes in safety switchboards, rewiring, and heavy appliance loads.'),
            ('anita_cleaner', 'Anita', 'Prasad', 'anita@servora.com', 'Kannur', '+91 94460 11223', True,
             'Professional hygiene specialist with an all-organic, pet-safe deep cleaning toolkit and 5-star customer ratings.'),
            ('suresh_carpenter', 'Suresh', 'Babu', 'suresh@servora.com', 'Kochi', '+91 98950 44556', True,
             'Specialist in traditional teakwood repairs, modular kitchen cabinets, and precision lock replacements.'),
            ('vikram_painter', 'Vikram', 'Shetty', 'vikram@servora.com', 'Bengaluru', '+91 98801 77889', True,
             'Professional Asian Paints certified painter offering dust-free mechanized sanding and premium emulsion coats.'),
            ('deepa_tutor', 'Deepa', 'Nair', 'deepa@servora.com', 'Kozhikode', '+91 94471 99881', True,
             'M.Sc. Mathematics with 8 years of home tutoring experience for CBSE, ICSE, and state syllabus high school students.'),
            ('arjun_tech', 'Arjun', 'Rao', 'arjun@servora.com', 'Bengaluru', '+91 98450 33221', False,
             'Certified hardware technician offering doorstep laptop troubleshooting, motherboard repair, and data recovery.'),
        ]

        provider_profiles = {}
        for username, fname, lname, email, city, phone, verified, bio in providers_data:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={'first_name': fname, 'last_name': lname, 'email': email}
            )
            user.set_password('provider123')
            user.first_name = fname
            user.last_name = lname
            user.email = email
            user.save()

            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = 'provider'
            profile.city = city
            profile.phone = phone
            profile.is_verified = verified
            profile.bio = bio
            profile.save()
            provider_profiles[username] = profile

        # 4. Customers
        customers_data = [
            ('arun_homeowner', 'Arun', 'Menon', 'arun@example.com', 'Kannur'),
            ('kavita_sharma', 'Kavita', 'Sharma', 'kavita@example.com', 'Bengaluru'),
            ('faisal_ahmed', 'Faisal', 'Ahmed', 'faisal@example.com', 'Kochi'),
        ]
        customers = []
        for username, fname, lname, email, city in customers_data:
            cust_u, _ = User.objects.get_or_create(
                username=username,
                defaults={'first_name': fname, 'last_name': lname, 'email': email}
            )
            cust_u.set_password('customer123')
            cust_u.save()
            cust_p, _ = UserProfile.objects.get_or_create(user=cust_u)
            cust_p.role = 'customer'
            cust_p.city = city
            cust_p.save()
            customers.append(cust_u)

        # 5. Services
        services_data = [
            # Plumbing
            (provider_profiles['john_plumber'], categories_map['Plumbing'],
             'Complete Bathroom Plumbing & Pipe Repair',
             'Comprehensive diagnosis of hidden leaks, precision faucet replacement, sanitaryware fittings, flush tank troubleshooting, and high-pressure drain clearing with 30-day service warranty.',
             Decimal('1500.00'), '1-2 hours', True),
            (provider_profiles['john_plumber'], categories_map['Plumbing'],
             'Water Tank Cleaning & Pump Inspection',
             'Thorough pressure descaling and sanitization of overhead and underground water storage tanks with chemical disinfection and motor float valve checking.',
             Decimal('2200.00'), '2-3 hours', False),

            # Electrical
            (provider_profiles['rahul_electrician'], categories_map['Electrical'],
             'Home Wiring Inspection & MCB Installation',
             'Full diagnostic check of switchboards, short circuit diagnostics, fuse box replacement with modern miniature circuit breakers (MCBs), and earthing test.',
             Decimal('1200.00'), '1-2 hours', True),
            (provider_profiles['rahul_electrician'], categories_map['Electrical'],
             'Inverter & Battery Setup with Safety Wiring',
             'Heavy-duty sine wave inverter installation, battery acid inspection, dedicated backup circuit wiring, and surge protection testing.',
             Decimal('1800.00'), '2-3 hours', False),

            # Cleaning
            (provider_profiles['anita_cleaner'], categories_map['Cleaning'],
             'Deep Home Cleaning & Kitchen Sanitization',
             'Intensive machine floor scrubbing, kitchen chimney oil degreasing, bathroom lime descaling, window frame wiping, and high-touch disinfection.',
             Decimal('2800.00'), '3-4 hours', True),
            (provider_profiles['anita_cleaner'], categories_map['Cleaning'],
             'Fabric Sofa & Mattress Shampooing',
             'Deep steam extraction cleaning for fabric sofas, recliners, and king-size mattresses. Removes dust mites, pet stains, and odors permanently.',
             Decimal('1400.00'), '1-2 hours', False),

            # Carpentry
            (provider_profiles['suresh_carpenter'], categories_map['Carpentry'],
             'Door Lock Installation & Hinge Realignment',
             'Precision installation of Godrej/Europa cylinder locks, wood shaving for stuck doors, and stainless steel hydraulic hinge alignment.',
             Decimal('850.00'), '1 hour', False),
            (provider_profiles['suresh_carpenter'], categories_map['Carpentry'],
             'Modular Kitchen Cabinet Repair & Shelf Fitting',
             'Replacement of rusted drawer channels, hydraulic soft-close hinges, and custom wall shelf mounting with sturdy anchors.',
             Decimal('1600.00'), '2-3 hours', True),

            # Painting
            (provider_profiles['vikram_painter'], categories_map['Painting'],
             'Interior Wall Painting & Waterproof Primer',
             'Mechanized dustless wall sanding, putty patching, anti-fungal primer coat, and double coats of premium royal luxury acrylic emulsion.',
             Decimal('4500.00'), '1-2 days', True),

            # Gardening
            (provider_profiles['john_plumber'], categories_map['Gardening'],
             'Residential Lawn Mowing & Landscape Trimming',
             'Professional lawn edge trimming, weed removal, soil loosening, hedge pruning, and organic vermicompost fertilization.',
             Decimal('1100.00'), '2 hours', False),

            # Tutoring
            (provider_profiles['deepa_tutor'], categories_map['Tutoring'],
             'High School Mathematics Home Tutoring',
             'One-on-one personalized tutoring for Class 9-12 CBSE/ICSE students. Concept clarity, problem-solving techniques, and exam prep.',
             Decimal('900.00'), '1 hour / session', True),

            # Computer Repair
            (provider_profiles['arjun_tech'], categories_map['Computer Repair'],
             'Doorstep Laptop Diagnostics & SSD Upgrade',
             'On-site performance diagnostics, high-speed NVMe SSD installation, thermal paste repasting, dust cleaning, and Windows optimization.',
             Decimal('1350.00'), '1-2 hours', False),
        ]

        created_services = []
        for prov, cat, title, desc, price, dur, feat in services_data:
            svc, _ = Service.objects.get_or_create(
                provider=prov,
                title=title,
                defaults={
                    'category': cat,
                    'description': desc,
                    'price': price,
                    'duration_estimate': dur,
                    'location': prov.city,
                    'is_featured': feat,
                    'is_active': True,
                }
            )
            svc.category = cat
            svc.description = desc
            svc.price = price
            svc.duration_estimate = dur
            svc.location = prov.city
            svc.is_featured = feat
            svc.is_active = True
            svc.save()
            created_services.append(svc)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(created_services)} services across 10 categories."))

        # 6. Provider Pro Subscriptions (5 Providers = ₹1,995 Subscription Revenue)
        pro_usernames = ['john_plumber', 'rahul_electrician', 'anita_cleaner', 'vikram_painter', 'suresh_carpenter']
        for prov_username in pro_usernames:
            prov = provider_profiles[prov_username]
            sub, _ = ProviderSubscription.objects.get_or_create(
                provider=prov,
                is_active=True,
                defaults={
                    'plan_name': 'pro',
                    'monthly_fee': Decimal('399.00'),
                    'end_date': date.today() + timedelta(days=30),
                }
            )
            sub.plan_name = 'pro'
            sub.monthly_fee = Decimal('399.00')
            sub.end_date = date.today() + timedelta(days=30)
            sub.is_active = True
            sub.save()

            # Record subscription revenue transaction idempotently
            if not RevenueTransaction.objects.filter(revenue_type='subscription', provider=prov).exists():
                RevenueTransaction.objects.create(
                    revenue_type='subscription',
                    amount=Decimal('399.00'),
                    provider=prov,
                    description=f"Pro Plan Monthly Subscription (₹399/mo) for {prov.user.get_full_name()}",
                    status='completed'
                )

        # 7. Featured Listings (7 Listings @ ₹99 = ₹693 Featured Revenue)
        featured_indices = [0, 2, 4, 7, 8, 10, 11]
        for idx in featured_indices:
            if idx < len(created_services):
                svc = created_services[idx]
                feat_listing, created_feat = FeaturedListing.objects.get_or_create(
                    service=svc,
                    is_active=True,
                    defaults={
                        'fee_paid': Decimal('99.00'),
                        'start_date': date.today() - timedelta(days=1),
                        'end_date': date.today() + timedelta(days=2),
                    }
                )
                svc.is_featured = True
                svc.save(update_fields=['is_featured'])

                if not RevenueTransaction.objects.filter(revenue_type='featured', service=svc).exists():
                    RevenueTransaction.objects.create(
                        revenue_type='featured',
                        amount=Decimal('99.00'),
                        provider=svc.provider,
                        service=svc,
                        description=f"3-Day Featured Promotion for '{svc.title}' (₹99)",
                        status='completed'
                    )

        # 8. Completed Bookings with 10% Commission (8 Bookings = ₹3,500 Commission Revenue)
        bookings_seed_specs = [
            # 1: John Mathew - Plumbing (₹500 commission)
            (created_services[0], customers[0], date.today() - timedelta(days=5), time(10, 0),
             Decimal('5000.00'), Decimal('500.00'), 'Fixed major bathroom pipe rupture under sink.',
             'House 14, Royal Greens, Kannur', 5, 'John Mathew was punctual, professional, and diagnosed the leak within 10 minutes.'),

            # 2: Anita Deep Cleaning (₹280 commission)
            (created_services[4], customers[1], date.today() - timedelta(days=3), time(9, 30),
             Decimal('2800.00'), Decimal('280.00'), 'Complete flat sanitization before housewarming.',
             'Flat 302, Palm Heights, Kannur', 5, 'Anita and her team did a spotless deep clean! Very happy with the freshness.'),

            # 3: Rahul Electrical (₹120 commission)
            (created_services[2], customers[2], date.today() - timedelta(days=1), time(14, 0),
             Decimal('1200.00'), Decimal('120.00'), 'MCB tripping issue inspection.',
             'Villa 7, Ocean View, Kannur', 5, 'Rahul identified the faulty earthing wire quickly. Very competent.'),

            # 4: Vikram Painter (₹450 commission)
            (created_services[8], customers[0], date.today() - timedelta(days=7), time(8, 30),
             Decimal('4500.00'), Decimal('450.00'), 'Living room accent wall painting.',
             'House 14, Royal Greens, Bengaluru', 4, 'Super clean finish! Vikram used dustless mechanized sanding.'),

            # 5: Vikram Painting Whole Apartment (₹800 commission)
            (created_services[8], customers[1], date.today() - timedelta(days=4), time(9, 0),
             Decimal('8000.00'), Decimal('800.00'), 'Full 2BHK interior repaint.',
             'Block B-402, Skyline Towers, Bengaluru', 5, 'Flawless work across all bedrooms and hall.'),

            # 6: John Mathew Water Tank (₹450 commission)
            (created_services[1], customers[2], date.today() - timedelta(days=2), time(11, 0),
             Decimal('4500.00'), Decimal('450.00'), 'Overhead water tank pressure descaling and pipe maintenance.',
             'Seaside Villa 12, Kannur', 5, 'Prompt and thorough. Water pressure restored completely.'),

            # 7: Anita Sofa & Kitchen Deep Clean (₹500 commission)
            (created_services[5], customers[0], date.today() - timedelta(days=1), time(13, 0),
             Decimal('5000.00'), Decimal('500.00'), 'Commercial grade kitchen and upholstery deep sanitization.',
             'Villa 14, Kannur', 5, 'Exceptional attention to detail by Anita and staff.'),

            # 8: Suresh Modular Kitchen Repair (₹400 commission)
            (created_services[7], customers[1], date.today(), time(15, 0),
             Decimal('4000.00'), Decimal('400.00'), 'Hinge realignment and drawer channel replacements.',
             'Flat 101, Green Meadows, Kochi', 5, 'Suresh restored our kitchen cabinets perfectly.'),
        ]

        for svc, cust, b_date, b_time, tot_amt, comm_amt, notes, addr, rating, review_text in bookings_seed_specs:
            b, _ = Booking.objects.get_or_create(
                service=svc,
                customer=cust,
                booking_date=b_date,
                booking_time=b_time,
                defaults={
                    'status': 'completed',
                    'total_amount': tot_amt,
                    'commission_rate': Decimal('10.00'),
                    'commission_amount': comm_amt,
                    'notes': notes,
                    'address': addr,
                }
            )
            b.status = 'completed'
            b.total_amount = tot_amt
            b.commission_rate = Decimal('10.00')
            b.commission_amount = comm_amt
            b.save()

            if review_text:
                Review.objects.get_or_create(
                    service=svc,
                    customer=cust,
                    booking=b,
                    defaults={
                        'rating': rating,
                        'comment': review_text,
                    }
                )

            # Record booking commission platform revenue transaction
            RevenueTransaction.objects.get_or_create(
                revenue_type='commission',
                booking=b,
                defaults={
                    'amount': comm_amt,
                    'provider': svc.provider,
                    'description': f"10% Platform Commission on Booking #SVR{b.id:05d} ({svc.title})",
                    'status': 'completed',
                }
            )

        self.stdout.write(self.style.SUCCESS(
            "Servora marketplace populated with full realistic data and INR 6,188 Stage 6 monetization revenue!"
        ))
