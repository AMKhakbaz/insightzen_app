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
    const collapsed = localStorage.getItem('sidebarCollapsed');
    if (collapsed === 'true') {
      body.classList.add('sidebar-collapsed');
    }
    menuToggle.addEventListener('click', function () {
      body.classList.toggle('sidebar-collapsed');
      const isCollapsed = body.classList.contains('sidebar-collapsed');
      localStorage.setItem('sidebarCollapsed', isCollapsed ? 'true' : 'false');
    });
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
});