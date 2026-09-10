/**
 * Servora Global JavaScript
 * Handles responsive mobile navigation drawer, alert dismissals, and general interactions.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Mobile drawer toggle
  const mobileBtn = document.querySelector('.mobile-menu-btn');
  const mobileDrawer = document.querySelector('.mobile-drawer');
  const overlay = document.querySelector('.mobile-overlay');

  if (mobileBtn && mobileDrawer && overlay) {
    const toggleMenu = () => {
      mobileDrawer.classList.toggle('open');
      overlay.classList.toggle('active');
      document.body.classList.toggle('menu-open');
    };

    mobileBtn.addEventListener('click', toggleMenu);
    overlay.addEventListener('click', toggleMenu);
  }

  // Auto-dismiss Django flash alerts after 5 seconds
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(alert => {
    setTimeout(() => {
      alert.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-10px)';
      setTimeout(() => alert.remove(), 500);
    }, 5000);
  });
});
