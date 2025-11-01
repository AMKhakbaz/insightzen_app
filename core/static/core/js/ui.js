/*
 * UI interaction scripts for InsightZen.
 *
 * Enhancements provided:
 *   - Responsive sidebar toggle with desktop collapse persistence and
 *     mobile overlay behaviour.  The collapsed state (desktop) is saved in
 *     ``localStorage`` so user preferences survive reloads.
 *   - Accordion-style sidebar navigation where only one group can be open
 *     at any time, mirroring KoboToolbox's navigation.
 */

document.addEventListener('DOMContentLoaded', () => {
  const body = document.body;
  const menuToggle = document.getElementById('menu-toggle');
  const sidebar = document.getElementById('sidebar');
  const collapsePreferenceKey = 'sidebarCollapsed';
  const desktopMediaQuery = window.matchMedia('(min-width: 961px)');

  const updateMenuToggleAria = () => {
    if (!menuToggle) {
      return;
    }
    const isDesktop = desktopMediaQuery.matches;
    if (isDesktop) {
      const expanded = !body.classList.contains('sidebar-collapsed');
      menuToggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    } else {
      const expanded = body.classList.contains('sidebar-open');
      menuToggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }
  };

  const applyCollapsedPreference = () => {
    const shouldCollapse = localStorage.getItem(collapsePreferenceKey) === 'true';
    if (desktopMediaQuery.matches) {
      body.classList.toggle('sidebar-collapsed', shouldCollapse);
      body.classList.remove('sidebar-open');
    } else {
      body.classList.remove('sidebar-collapsed');
      body.classList.remove('sidebar-open');
    }
    updateMenuToggleAria();
  };

  applyCollapsedPreference();
  desktopMediaQuery.addEventListener('change', applyCollapsedPreference);

  if (menuToggle) {
    menuToggle.setAttribute('aria-controls', 'sidebar');
    menuToggle.addEventListener('click', () => {
      if (desktopMediaQuery.matches) {
        const nowCollapsed = body.classList.toggle('sidebar-collapsed');
        localStorage.setItem(collapsePreferenceKey, nowCollapsed ? 'true' : 'false');
      } else {
        body.classList.toggle('sidebar-open');
      }
      updateMenuToggleAria();
    });
  }

  if (sidebar) {
    const navLinks = sidebar.querySelectorAll('nav a');
    navLinks.forEach((link) => {
      link.addEventListener('click', () => {
        if (!desktopMediaQuery.matches && body.classList.contains('sidebar-open')) {
          body.classList.remove('sidebar-open');
          updateMenuToggleAria();
        }
      });
    });
  }

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && body.classList.contains('sidebar-open')) {
      body.classList.remove('sidebar-open');
      updateMenuToggleAria();
    }
  });

  const detailEls = document.querySelectorAll('.sidebar nav details');
  detailEls.forEach((det) => {
    det.addEventListener('toggle', () => {
      if (det.open) {
        detailEls.forEach((other) => {
          if (other !== det) {
            other.open = false;
          }
        });
      }
    });
  });
});
