/*
 * UI interaction scripts for InsightZen.
 *
 * This module enhances the user interface with the following features:
 *   - Persistent sidebar collapse: the collapsed state is saved in
 *     ``localStorage`` so that user preferences are remembered across
 *     sessions.
 *   - Collection performance chart: renders a stacked bar chart using
 *     Chart.js, fetching data from a data endpoint defined in the
 *     ``data-url`` attribute of the canvas element.  The chart updates
 *     periodically and whenever filter inputs change.
 *
 * Note: this script requires Chart.js to be loaded on pages that
 * include a ``canvas#performance-chart`` element.  Chart.js is
 * delivered via a CDN in the base template.
 */

document.addEventListener('DOMContentLoaded', function () {
  // Sidebar collapse persistence
  const body = document.body;
  const menuToggle = document.getElementById('menu-toggle');
  if (menuToggle) {
    const STORAGE_KEY = 'sidebarCollapsed';
    const mobileQuery = window.matchMedia('(max-width: 992px)');

    const updateAriaExpanded = () => {
      const expanded = !body.classList.contains('sidebar-collapsed');
      menuToggle.setAttribute('aria-expanded', expanded.toString());
      menuToggle.setAttribute('aria-controls', 'sidebar');
    };

    const applyInitialSidebarState = () => {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === 'true') {
        body.classList.add('sidebar-collapsed');
      } else if (stored === 'false') {
        body.classList.remove('sidebar-collapsed');
      } else if (mobileQuery.matches) {
        body.classList.add('sidebar-collapsed');
      } else {
        body.classList.remove('sidebar-collapsed');
      }
      updateAriaExpanded();
    };

    applyInitialSidebarState();

    menuToggle.addEventListener('click', function () {
      body.classList.toggle('sidebar-collapsed');
      const isCollapsed = body.classList.contains('sidebar-collapsed');
      localStorage.setItem(STORAGE_KEY, isCollapsed ? 'true' : 'false');
      updateAriaExpanded();
    });

    const handleViewportChange = (event) => {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === null) {
        if (event.matches) {
          body.classList.add('sidebar-collapsed');
        } else {
          body.classList.remove('sidebar-collapsed');
        }
      }
      updateAriaExpanded();
    };

    if (typeof mobileQuery.addEventListener === 'function') {
      mobileQuery.addEventListener('change', handleViewportChange);
    } else if (typeof mobileQuery.addListener === 'function') {
      mobileQuery.addListener(handleViewportChange);
    }
  }
  // Only allow one sidebar group (details element) open at a time
  const detailEls = document.querySelectorAll('.sidebar nav details');
  detailEls.forEach((det) => {
    det.addEventListener('toggle', function () {
      if (det.open) {
        detailEls.forEach((other) => {
          if (other !== det) {
            other.open = false;
          }
        });
      }
    });
  });

  const passwordToggleButtons = document.querySelectorAll('[data-password-toggle]');
  const updatePasswordToggleState = (button, input, showIcon, hideIcon) => {
    const isVisible = input.type === 'text';
    button.setAttribute('aria-pressed', isVisible.toString());
    if (showIcon) {
      showIcon.hidden = isVisible;
    }
    if (hideIcon) {
      hideIcon.hidden = !isVisible;
    }
  };

  passwordToggleButtons.forEach((button) => {
    const field = button.closest('.password-field');
    if (!field) {
      return;
    }
    const input = field.querySelector('input');
    if (!input) {
      return;
    }
    const showIcon = button.querySelector('[data-password-toggle-show]');
    const hideIcon = button.querySelector('[data-password-toggle-hide]');

    button.addEventListener('click', () => {
      const shouldShow = input.type === 'password';
      try {
        input.type = shouldShow ? 'text' : 'password';
      } catch (error) {
        return;
      }
      updatePasswordToggleState(button, input, showIcon, hideIcon);
    });

    updatePasswordToggleState(button, input, showIcon, hideIcon);
  });
});
