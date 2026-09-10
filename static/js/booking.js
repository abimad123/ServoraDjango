/**
 * Servora Booking Flow & Calendar Interaction
 * Handles multi-step progression, dynamic calendar generation, and time slot selection.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const stepItems = document.querySelectorAll('.step-item');
  const stepSections = document.querySelectorAll('.booking-step-section');
  const nextButtons = document.querySelectorAll('.btn-next-step');
  const prevButtons = document.querySelectorAll('.btn-prev-step');

  const dateInput = document.getElementById('id_booking_date');
  const timeInput = document.getElementById('id_booking_time');
  const addressInput = document.getElementById('id_address');
  const notesInput = document.getElementById('id_notes');

  const summaryDate = document.getElementById('summary-date');
  const summaryTime = document.getElementById('summary-time');
  const summaryAddress = document.getElementById('summary-address');
  const reviewDate = document.getElementById('review-date');
  const reviewTime = document.getElementById('review-time');
  const reviewAddress = document.getElementById('review-address');
  const reviewNotes = document.getElementById('review-notes');

  let currentStep = 1;

  // Step Switcher
  function goToStep(step) {
    if (step < 1 || step > 4) return;
    currentStep = step;

    stepSections.forEach(sec => {
      sec.classList.toggle('active', parseInt(sec.dataset.step) === currentStep);
    });

    stepItems.forEach(item => {
      const itemStep = parseInt(item.dataset.step);
      item.classList.toggle('active', itemStep === currentStep);
      item.classList.toggle('completed', itemStep < currentStep);
    });

    // Scroll to top of booking card smoothly
    const mainCard = document.querySelector('.booking-main-card');
    if (mainCard) {
      mainCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  nextButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetStep = parseInt(btn.dataset.next);

      // Validation before moving forward
      if (targetStep === 3) {
        if (!dateInput.value) {
          alert('Please select a service date from the calendar.');
          return;
        }
        if (!timeInput.value) {
          alert('Please select a preferred time slot.');
          return;
        }
      }

      if (targetStep === 4) {
        if (!addressInput.value.trim()) {
          alert('Please enter your service address.');
          addressInput.focus();
          return;
        }
        // Update review screen
        if (reviewDate) reviewDate.textContent = summaryDate.textContent;
        if (reviewTime) reviewTime.textContent = summaryTime.textContent;
        if (reviewAddress) reviewAddress.textContent = addressInput.value.trim();
        if (reviewNotes) reviewNotes.textContent = notesInput.value.trim() || 'None specified';
      }

      goToStep(targetStep);
    });
  });

  prevButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      goToStep(parseInt(btn.dataset.prev));
    });
  });

  // Calendar Engine
  const monthTitle = document.getElementById('calendar-month-title');
  const calendarGrid = document.getElementById('calendar-days-container');
  const prevMonthBtn = document.getElementById('calendar-prev-month');
  const nextMonthBtn = document.getElementById('calendar-next-month');

  let activeDate = new Date();
  let currentMonth = activeDate.getMonth();
  let currentYear = activeDate.getFullYear();

  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ];

  function renderCalendar(month, year) {
    if (!calendarGrid || !monthTitle) return;

    monthTitle.textContent = `${monthNames[month]} ${year}`;
    calendarGrid.innerHTML = '';

    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Padding empty cells for first day of week
    for (let i = 0; i < firstDay; i++) {
      const emptyCell = document.createElement('div');
      emptyCell.className = 'calendar-day-cell disabled';
      calendarGrid.appendChild(emptyCell);
    }

    // Days in current month
    for (let day = 1; day <= daysInMonth; day++) {
      const cellDate = new Date(year, month, day);
      cellDate.setHours(0, 0, 0, 0);

      const cell = document.createElement('div');
      cell.className = 'calendar-day-cell';
      cell.textContent = day;

      const dateString = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      cell.dataset.date = dateString;

      if (cellDate < today) {
        cell.classList.add('disabled');
      } else {
        if (dateInput && dateInput.value === dateString) {
          cell.classList.add('selected');
        }

        cell.addEventListener('click', () => {
          document.querySelectorAll('.calendar-day-cell').forEach(c => c.classList.remove('selected'));
          cell.classList.add('selected');

          if (dateInput) dateInput.value = dateString;
          if (summaryDate) {
            const formatted = cellDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
            summaryDate.textContent = formatted;
          }

          // Fetch booked slots for the selected date
          fetchBookedSlots(dateString);
        });
      }

      calendarGrid.appendChild(cell);
    }
  }

  if (prevMonthBtn && nextMonthBtn) {
    prevMonthBtn.addEventListener('click', () => {
      currentMonth--;
      if (currentMonth < 0) {
        currentMonth = 11;
        currentYear--;
      }
      renderCalendar(currentMonth, currentYear);
    });

    nextMonthBtn.addEventListener('click', () => {
      currentMonth++;
      if (currentMonth > 11) {
        currentMonth = 0;
        currentYear++;
      }
      renderCalendar(currentMonth, currentYear);
    });
  }

  // Time Slot Selection
  const timeSlotButtons = document.querySelectorAll('.time-slot-btn');
  timeSlotButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.classList.contains('disabled')) return;

      timeSlotButtons.forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');

      const timeVal = btn.dataset.time;
      const label = btn.dataset.label || btn.textContent.trim();

      if (timeInput) timeInput.value = timeVal;
      if (summaryTime) summaryTime.textContent = label;
    });
  });

  // Fetch booked slots for double booking protection visual feedback
  function fetchBookedSlots(dateStr) {
    const serviceIdEl = document.getElementById('service-id-hidden');
    if (!serviceIdEl) return;
    const serviceId = serviceIdEl.value;

    fetch(`/api/availability/?service_id=${serviceId}&date=${dateStr}`)
      .then(res => res.json())
      .then(data => {
        const booked = data.booked_slots || [];
        timeSlotButtons.forEach(btn => {
          const t = btn.dataset.time;
          if (booked.includes(t)) {
            btn.classList.add('disabled');
            btn.classList.remove('selected');
            btn.title = 'Already booked';
            if (timeInput && timeInput.value === t) {
              timeInput.value = '';
              if (summaryTime) summaryTime.textContent = 'Not selected';
            }
          } else {
            btn.classList.remove('disabled');
            btn.title = '';
          }
        });
      })
      .catch(() => {
        // Fallback gracefully
      });
  }

  // Address sync to summary
  if (addressInput && summaryAddress) {
    addressInput.addEventListener('input', () => {
      summaryAddress.textContent = addressInput.value.trim() ? `${addressInput.value.trim().substring(0, 24)}...` : 'Not entered yet';
    });
  }

  // Initial Calendar Render
  renderCalendar(currentMonth, currentYear);
});
