/*
 * charts.js
 *
 * This module powers the interactive collection performance dashboard.
 * It renders a stacked bar chart, a donut chart, a line chart and
 * populates a sortable top‑interviewers table.  Charts automatically
 * update whenever the user changes a filter (project, date range or
 * interviewers).  Colours and fonts are derived from CSS variables to
 * match the dark theme.  Sorting on the table headers toggles
 * ascending/descending order.
 */

document.addEventListener('DOMContentLoaded', function () {
  const barCanvas = document.getElementById('bar-chart');
  const donutCanvas = document.getElementById('donut-chart');
  const lineCanvas = document.getElementById('line-chart');
  const topTable = document.getElementById('top5-table');
  if (!barCanvas || !donutCanvas || !lineCanvas || !topTable) {
    return;
  }

  const ctxBar = barCanvas.getContext('2d');
  const ctxDonut = donutCanvas.getContext('2d');
  const ctxLine = lineCanvas.getContext('2d');
  let barChart = null;
  let donutChart = null;
  let lineChart = null;
  let topData = [];
  let sortKey = 'total';
  let sortAsc = false;

  // Generate a palette of colours for donut segments
  function getPalette(n) {
    const baseColours = [
      '#0099e5', '#33b679', '#eeb211', '#e55039', '#9c27b0', '#3f51b5', '#009688', '#8bc34a', '#ff9800', '#673ab7', '#ff5722', '#795548', '#607d8b'
    ];
    const colours = [];
    for (let i = 0; i < n; i++) {
      const c = baseColours[i % baseColours.length];
      colours.push(c);
    }
    return colours;
  }

  function getCssVar(name, fallback) {
    const val = getComputedStyle(document.documentElement).getPropertyValue(name);
    return val && val.trim() ? val.trim() : fallback;
  }

  function buildUrl() {
    const baseUrl = barCanvas.dataset.url;
    const params = new URLSearchParams();
    const project = document.getElementById('project-select').value;
    const start = document.getElementById('start-date').value;
    const end = document.getElementById('end-date').value;
    const userSelect = document.getElementById('user-select');
    const selectedUsers = Array.from(userSelect.selectedOptions).map((o) => o.value).join(',');
    if (project) params.append('project', project);
    if (start) params.append('start_date', start);
    if (end) params.append('end_date', end);
    if (selectedUsers) params.append('users', selectedUsers);
    return params.toString() ? `${baseUrl}?${params.toString()}` : baseUrl;
  }

  function fetchAndRender() {
    fetch(buildUrl())
      .then((resp) => resp.json())
      .then((data) => {
        // Update bar chart
        const labels = data.labels || [];
        const totals = data.totals || [];
        const successes = data.successes || [];
        const primary = getCssVar('--primary', 'rgba(88,166,255,0.6)');
        const primaryBorder = getCssVar('--primary-light', 'rgba(88,166,255,1)');
        const secondary = getCssVar('--secondary', 'rgba(139,92,246,0.6)');
        const secondaryBorder = getCssVar('--secondary-light', 'rgba(139,92,246,1)');
        if (barChart) {
          barChart.data.labels = labels;
          barChart.data.datasets[0].data = totals;
          barChart.data.datasets[1].data = successes;
          barChart.update();
        } else {
          barChart = new Chart(ctxBar, {
            type: 'bar',
            data: {
              labels: labels,
              datasets: [
                {
                  label: barCanvas.dataset.totalLabel || 'Total',
                  data: totals,
                  backgroundColor: primary,
                  borderColor: primaryBorder,
                  borderWidth: 1,
                },
                {
                  label: barCanvas.dataset.successLabel || 'Successful',
                  data: successes,
                  backgroundColor: secondary,
                  borderColor: secondaryBorder,
                  borderWidth: 1,
                },
              ],
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              scales: {
                x: {
                  stacked: true,
                  grid: {
                    color: getCssVar('--border-color', '#2a3551'),
                  },
                  ticks: {
                    color: getCssVar('--text-color', '#e2e8f0'),
                  },
                },
                y: {
                  stacked: true,
                  beginAtZero: true,
                  grid: {
                    color: getCssVar('--border-color', '#2a3551'),
                  },
                  ticks: {
                    color: getCssVar('--text-color', '#e2e8f0'),
                  },
                },
              },
              plugins: {
                legend: {
                  labels: {
                    color: getCssVar('--text-color', '#e2e8f0'),
                  },
                },
              },
              animation: {
                duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 500,
              },
            },
          });
        }
        // Update donut chart
        const donutData = data.donut || { labels: [], values: [] };
        const donutColours = getPalette(donutData.values.length);
        if (donutChart) {
          donutChart.data.labels = donutData.labels;
          donutChart.data.datasets[0].data = donutData.values;
          donutChart.data.datasets[0].backgroundColor = donutColours;
          donutChart.update();
        } else {
          donutChart = new Chart(ctxDonut, {
            type: 'doughnut',
            data: {
              labels: donutData.labels,
              datasets: [
                {
                  data: donutData.values,
                  backgroundColor: donutColours,
                  borderColor: donutColours.map((c) => c),
                  borderWidth: 1,
                },
              ],
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: {
                  position: 'bottom',
                  labels: {
                    color: getCssVar('--text-color', '#e2e8f0'),
                  },
                },
              },
              animation: {
                duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 500,
              },
              cutout: '60%',
            },
          });
        }
        // Update line chart (daily trend)
        const daily = data.daily || { labels: [], totals: [], successes: [] };
        if (lineChart) {
          lineChart.data.labels = daily.labels;
          lineChart.data.datasets[0].data = daily.totals;
          lineChart.data.datasets[1].data = daily.successes;
          lineChart.update();
        } else {
          lineChart = new Chart(ctxLine, {
            type: 'line',
            data: {
              labels: daily.labels,
              datasets: [
                {
                  label: barCanvas.dataset.totalLabel || 'Total',
                  data: daily.totals,
                  borderColor: primaryBorder,
                  backgroundColor: 'rgba(0,0,0,0)',
                  borderWidth: 2,
                  tension: 0.3,
                },
                {
                  label: barCanvas.dataset.successLabel || 'Successful',
                  data: daily.successes,
                  borderColor: secondaryBorder,
                  backgroundColor: 'rgba(0,0,0,0)',
                  borderWidth: 2,
                  tension: 0.3,
                },
              ],
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              scales: {
                x: {
                  grid: {
                    color: getCssVar('--border-color', '#2a3551'),
                  },
                  ticks: {
                    color: getCssVar('--text-color', '#e2e8f0'),
                  },
                },
                y: {
                  beginAtZero: true,
                  grid: {
                    color: getCssVar('--border-color', '#2a3551'),
                  },
                  ticks: {
                    color: getCssVar('--text-color', '#e2e8f0'),
                  },
                },
              },
              plugins: {
                legend: {
                  labels: {
                    color: getCssVar('--text-color', '#e2e8f0'),
                  },
                },
              },
              animation: {
                duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 500,
              },
            },
          });
        }
        // Update top data and render table
        topData = data.top5_all || [];
        renderTopTable();
      })
      .catch((err) => {
        console.error('Error loading performance data', err);
      });
  }

  function renderTopTable() {
    const tbody = topTable.querySelector('tbody');
    tbody.innerHTML = '';
    // Sort by current sortKey and sortAsc
    const sorted = topData.slice().sort((a, b) => {
      if (sortKey === 'rate') {
        const diff = a.rate - b.rate;
        return sortAsc ? diff : -diff;
      }
      if (sortKey === 'user') {
        const cmp = a.user.localeCompare(b.user);
        return sortAsc ? cmp : -cmp;
      }
      // numeric sorts for total and success
      const diff = a[sortKey] - b[sortKey];
      return sortAsc ? diff : -diff;
    });
    const topN = sorted.slice(0, 5);
    topN.forEach((row) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.user}</td>
        <td>${row.total}</td>
        <td>${row.success}</td>
        <td>${row.rate}%</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // Attach sort handlers to table headers
  topTable.querySelectorAll('th[data-sort-key]').forEach((th) => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', function () {
      const key = th.getAttribute('data-sort-key');
      if (sortKey === key) {
        sortAsc = !sortAsc;
      } else {
        sortKey = key;
        sortAsc = false;
      }
      renderTopTable();
    });
  });

  // Fetch data initially and whenever filters change
  fetchAndRender();
  ['project-select', 'start-date', 'end-date', 'user-select'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', fetchAndRender);
    }
  });
});