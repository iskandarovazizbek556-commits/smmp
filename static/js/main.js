// Sidebar mobile toggle
document.addEventListener('DOMContentLoaded', () => {
  // Auto-close alerts
  document.querySelectorAll('.alert').forEach(a => {
    setTimeout(() => a.style.opacity = '0', 4000);
    setTimeout(() => a.remove(), 4300);
  });

  // Refresh balance from server
  if (document.getElementById('balance-display')) {
    fetch('/api/price?service_id=0&quantity=0')
      .catch(() => {});
  }

  // Mobile sidebar close on outside click
  document.addEventListener('click', (e) => {
    const sidebar = document.getElementById('sidebar');
    if (sidebar && window.innerWidth <= 900 &&
        !sidebar.contains(e.target) &&
        !e.target.classList.contains('sidebar-toggle')) {
      sidebar.classList.remove('open');
    }
  });
});

// Confirm dialogs
function confirmDelete(msg) {
  return confirm(msg || "O'chirishni tasdiqlaysizmi?");
}

// Copy to clipboard
function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = '✓ Nusxalandi';
    setTimeout(() => btn.innerHTML = orig, 2000);
  });
}
