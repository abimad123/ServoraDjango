# Stage 7 Completion Report — Reviews & Database Notifications

**Project:** Servora – Local Home Services Marketplace  
**Framework:** Django 5.x + SQLite + Django ORM + Vanilla HTML/CSS/JavaScript  
**Date:** September 10, 2026  
**Status:** Completed & Fully Verified (81 Tests Passing)  

---

## 1. Stage 7 Overview

Stage 7 implements two core marketplace trust-and-engagement features:
1. **Customer Review and Rating System:** Allows customers who have completed a booking to submit a 1–5 star rating and detailed written review. Provider ratings are calculated dynamically via database aggregation, rating distribution charts are rendered on service and provider profiles, and strict authorization rules protect against unauthorized or duplicate reviews.
2. **Database-Backed Notification System:** A real-time, in-app notification engine that alerts both service providers and customers across the complete booking lifecycle, review submissions, Pro subscription activations, and featured service promotions. Includes a dedicated notification center (`/notifications/`), unread count badges in the customer navigation bar and provider sidebar, and single/bulk mark-as-read operations.

---

## 2. Review Architecture

- **Relationships:**
  - `Review` is tied to:
    - `Booking` (via `models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='review')`)
    - `Customer` (via `models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_reviews')`)
    - `Service` (via `models.ForeignKey(Service, on_delete=models.CASCADE, related_name='reviews')`)
    - `Provider` (accessible via `service.provider`)
- **Uniqueness Guarantee:**
  - **Database Level:** The `OneToOneField` between `Review` and `Booking` guarantees that no booking can ever have more than one review.
  - **Application Level:** The `leave_review_view` checks `hasattr(booking, 'review') and booking.review is not None` before presenting the form or saving POST data, giving friendly feedback if already reviewed.

---

## 3. Notification Architecture

- **Model:** `Notification` stored in the `services` application.
- **Fields:**
  - `recipient`: `ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')`
  - `notification_type`: `CharField` with 8 choice categories
  - `title`: Short headline (e.g., "New Booking Request", "Booking Accepted", "Service Completed")
  - `message`: Descriptive text with customer/service context
  - `booking`: `ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL)`
  - `service`: `ForeignKey(Service, null=True, blank=True, on_delete=models.SET_NULL)`
  - `is_read`: `BooleanField(default=False)`
  - `created_at`: `DateTimeField(auto_now_add=True)`
- **Helper Function (`create_notification`):**
  - Centralized utility `create_notification(recipient, notification_type, title, message, booking=None, service=None)`
  - Built-in duplicate protection: verifies whether an identical transition notification has already been issued for the given booking and recipient.
- **Global Context Processor (`notifications_context`):**
  - Injects `unread_notifications_count` and `recent_notifications` (top 5) across all templates for authenticated users without hardcoding.

---

## 4. Models Created & Modified

### `services/models.py`
- **`Notification` (Created):**
  - Database-backed model with indexed `recipient`, `is_read`, and `created_at`.
  - Proper `__str__` returning notification title, recipient username, and read status.
- **`Review` (Maintained & Verified):**
  - Maintained `OneToOneField` with `Booking`.
  - ForeignKeys to `Service` and `User` (`customer`).
  - Integer rating (1–5) and comment text.

### `users/models.py`
- **`UserProfile.average_rating` (Optimized):**
  - Implemented database aggregation using Django ORM:
    ```python
    @property
    def average_rating(self):
        agg = Review.objects.filter(
            service__provider=self
        ).aggregate(avg_rating=models.Avg('rating'))
        val = agg['avg_rating']
        return round(float(val), 1) if val is not None else 0.0
    ```

---

## 5. Review Eligibility Rules

A user may submit a review if and only if **all** of the following conditions are satisfied:
1. **Authenticated User:** Logged-out users are redirected to login.
2. **Customer Role:** Providers cannot submit customer reviews (redirected with an alert message).
3. **Booking Ownership:** `booking.customer == request.user` strictly enforced via `get_object_or_404(Booking, id=booking_id, customer=request.user)`. Another customer attempting to access the review URL receives an immediate **404 Not Found**.
4. **Completed Status:** `booking.status == 'completed'`. Pending, accepted, cancelled, or declined bookings are rejected with an explicit error.
5. **Single Submission:** Once a review exists for the booking, subsequent attempts are blocked.

---

## 6. Rating Calculation & Distribution

- **Provider Average Rating:** Calculated on-the-fly using `Review.objects.filter(service__provider=self).aggregate(Avg('rating'))`.
- **Lightweight Rating Distribution Breakdown:**
  - Implemented in `service_detail_view`, `service_slug_detail_view`, and `provider_profile_view`.
  - Calculates count and percentage for 5★, 4★, 3★, 2★, and 1★.
  - Rendered with styled CSS progress bars directly within the page, with 0 external JavaScript libraries.

---

## 7. Notification Types

The system supports all 8 required notification events:
1. `booking_created`: Sent to provider when customer creates a new booking.
2. `booking_accepted`: Sent to customer when provider confirms the booking.
3. `booking_declined`: Sent to customer when provider declines the request.
4. `booking_cancelled`: Sent to provider when customer cancels their appointment.
5. `booking_completed`: Sent to customer when provider marks service complete (prompts to review).
6. `review_received`: Sent to provider when customer rates and reviews their service.
7. `subscription_activated`: Sent to provider when Pro subscription is upgraded (₹399/mo).
8. `featured_listing_activated`: Sent to provider when a service listing is featured (₹99 for 3 days).

---

## 8. Booking Notification Workflow

```text
CUSTOMER                          PROVIDER
   │                                 │
   │── Creates Booking ─────────────▶│ [Notification: New Booking Request]
   │                                 │
   │◀── Accepts Booking ─────────────│ [Notification: Booking Accepted]
   │                                 │
   │                          Performs Service
   │                                 │
   │◀── Marks Completed ─────────────│ [Notification: Service Completed + Review Link]
   │                                 │
   │── Submits 1-5★ Review ─────────▶│ [Notification: New Review Received]
   │                                 │
   │                     Provider Rating Auto-Updates (Avg 'rating')
```

---

## 9. Subscription & Featured Notifications

- **Pro Subscription Upgrade:** When a provider upgrades to Pro in `provider_subscription_view`, `subscription_activated` notification is created with benefits overview.
- **Featured Listing Promotion:** When a provider promotes a service in `provider_feature_service_view`, `featured_listing_activated` notification is created with the 3-day duration details.

---

## 10. Read / Unread System

- **Navbar Integration (`templates/base.html`):**
  - Bell icon with unread badge counter (`{{ unread_notifications_count }}`).
  - Dropdown showing recent notifications with quick links to view all.
- **Provider Sidebar (`templates/provider/base_provider.html`):**
  - "Notifications" navigation item with dynamic unread count badge.
- **Notification Center (`/notifications/`):**
  - Unread items styled with subtle blue highlight background and unread indicator dot.
  - Clickable "Mark as read" button per notification.
  - "Mark all as read" button utilizing secure POST request.

---

## 11. Security & Authorization

- **Review Ownership Enforcement:** Verified using `get_object_or_404(Booking, id=booking_id, customer=request.user)`. Customer B cannot view or submit reviews for Customer A's booking (HTTP 404).
- **Provider Self-Review Restriction:** Providers are blocked from reviewing their own or other services via customer review endpoints.
- **Notification Isolation:** Users can only query, read, or mark their own notifications. Notification ID lookup is scoped to `recipient=request.user`.
- **CSRF Protection:** All state-changing operations (`leave_review`, `notification_mark_read`, `notification_mark_all_read`, `cancel_booking`, `provider_job_accept`, etc.) use Django CSRF tokens.

---

## 12. New URLs

| URL Pattern | View Name | Description |
|---|---|---|
| `/my-bookings/<int:booking_id>/review/` | `leave_review` | Review form for completed booking |
| `/notifications/` | `notifications_list` | Reverse-chronological notification center |
| `/notifications/<int:id>/read/` | `notification_mark_read` | Mark individual notification as read |
| `/notifications/read-all/` | `notification_mark_all_read` | POST action to mark all notifications read |

---

## 13. Templates, CSS & UI

- **Created Templates:**
  - `templates/services/leave_review.html`: Clean, accessible review submission page showing booking summary, 1-5 star select, and feedback textarea.
  - `templates/notifications/list.html`: Notification center with filter indicators, empty states, and read/unread styles.
- **Updated Templates:**
  - `templates/base.html`: Added notification bell with live counter and footer link.
  - `templates/provider/base_provider.html`: Added Notifications item with badge in provider sidebar.
  - `templates/services/my_bookings.html`: Added "★ Review" button or "Reviewed" badge for completed bookings.
  - `templates/services/booking_detail.html`: Displays customer's review or prompt to leave a review.
  - `templates/services/service_detail.html`: Added 5★–1★ rating distribution bar chart.
  - `templates/services/provider_profile.html`: Added provider rating distribution chart.

---

## 14. Database Migrations

- Generated migration: `services/migrations/0003_notification.py`
- Successfully applied with:
  ```bash
  python manage.py migrate
  ```

---

## 15. Seed Data

- Updated `services/management/commands/seed_data.py`:
  - Added notification seeding for Pro subscriptions, featured listings, completed bookings, and reviews.
  - Verified full command idempotency using `Notification.objects.get_or_create(...)`.
  - Execution output:
    ```text
    Seeding comprehensive Servora marketplace data...
    Seeded 10 categories.
    Seeded 12 services across 10 categories.
    Servora marketplace populated with full realistic data, INR 6,188 Stage 6 monetization revenue, and Stage 7 reviews & notifications!
    ```

---

## 16. Automated Tests Added

Created `ReviewAndNotificationTests` in `services/tests.py` containing **20 new comprehensive automated tests**:

1. `test_customer_can_review_completed_booking`: Customer can submit 1-5 star review for completed booking.
2. `test_customer_cannot_review_pending_booking`: Pending bookings cannot be reviewed.
3. `test_customer_cannot_review_accepted_booking`: Accepted bookings cannot be reviewed.
4. `test_customer_cannot_review_cancelled_booking`: Cancelled bookings cannot be reviewed.
5. `test_customer_cannot_review_another_customers_booking`: Cross-user review attempts return HTTP 404.
6. `test_provider_cannot_submit_customer_review`: Providers are blocked from customer review submissions.
7. `test_review_requires_rating`: Validation enforces non-empty rating selection.
8. `test_review_requires_comment`: Validation enforces minimum 10-character comment.
9. `test_customer_cannot_submit_duplicate_review`: One review per booking enforced at app and DB levels.
10. `test_provider_average_rating_updates`: Dynamic `Avg('rating')` ORM aggregation updates accurately.
11. `test_service_reviews_display_correctly`: Review cards and rating distribution render on service detail.
12. `test_booking_creation_notifies_provider`: Creating a booking sends `booking_created` notification to provider.
13. `test_booking_acceptance_notifies_customer`: Accepting a booking sends `booking_accepted` notification to customer.
14. `test_booking_decline_notifies_customer`: Declining a booking sends `booking_declined` notification to customer.
15. `test_booking_cancellation_notifies_provider`: Cancelling a booking sends `booking_cancelled` notification to provider.
16. `test_booking_completion_notifies_customer`: Completing a booking sends `booking_completed` notification to customer.
17. `test_review_creates_provider_notification`: Review submission sends `review_received` notification to provider.
18. `test_notification_belongs_to_correct_user`: Strict privacy isolation in notification list.
19. `test_user_can_mark_notification_as_read`: User can mark individual notification as read.
20. `test_user_can_mark_all_notifications_as_read`: POST bulk mark-all-read updates only current user's items.

---

## 17. Total Test Count & Verification Output

- **Previous Test Total:** 61 tests
- **Tests Added in Stage 7:** 20 tests
- **Total Passing Tests:** **81 tests** (exceeding 79+ target)

```text
Found 81 test(s).
System check identified no issues (0 silenced).
Creating test database for alias 'default'...
.................................................................................
----------------------------------------------------------------------
Ran 81 tests in 180.521s

OK
Destroying test database for alias 'default'...
```

---

## 18. Manual Verification

- **Review Submission Flow:**
  - Customer logs in -> "My Bookings" -> Completed booking -> Click "★ Review" -> Form renders with 1–5 stars and comment -> Submit -> Redirects with success flash message -> Review displays on service and provider profile.
- **Provider Rating Update:**
  - Verified average rating updates from `5.0` to aggregate average on provider profile and service detail.
  - Verified 5★–1★ distribution bar charts reflect review counts and percentages.
- **Notification Lifecycle:**
  - Customer books service -> Provider notification count increments -> Provider dashboard shows notification -> Provider accepts -> Customer receives `booking_accepted` -> Provider marks complete -> Customer receives `booking_completed` with review prompt -> Customer submits review -> Provider receives `review_received`.
- **Security Check:**
  - Customer Amit accessing Customer Priya's `/my-bookings/<id>/review/` receives immediate 404.
  - Provider accounts accessing review form are redirected with error.
  - Notification mark-read and list endpoints strictly verify ownership.

---

## 19. Remaining Issues / Next Steps

- **None:** Stage 7 is 100% complete, fully tested, and cleanly integrated.
- **Stage 8 Preparation:** Final platform polish, comprehensive end-to-end integration, performance optimization, and academic submission readiness.
