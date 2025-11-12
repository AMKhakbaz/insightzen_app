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
  const codeCanvas = document.getElementById('code-chart');
  const hourlyCanvas = document.getElementById('hourly-chart');
  const topTable = document.getElementById('top5-table');
  const rawTable = document.getElementById('raw-records-table');
  const rawPageSizeSelect = document.getElementById('raw-page-size');
  const rawPageInfo = document.getElementById('raw-page-info');
  const rawPrevButton = document.getElementById('raw-page-prev');
  const rawNextButton = document.getElementById('raw-page-next');
  const rawResultsStatus = document.getElementById('raw-results-status');
  if (!barCanvas || !donutCanvas || !lineCanvas || !topTable) {
    return;
  }

  const ctxBar = barCanvas.getContext('2d');
  const ctxDonut = donutCanvas.getContext('2d');
  const ctxLine = lineCanvas.getContext('2d');
  const ctxCode = codeCanvas ? codeCanvas.getContext('2d') : null;
  const ctxHourly = hourlyCanvas ? hourlyCanvas.getContext('2d') : null;
  let barChart = null;
  let donutChart = null;
  let lineChart = null;
  let codeChart = null;
  let hourlyChart = null;
  let donutSegments = [];
  let topData = [];
  let topTableInstance = null;
  let needsTableRefresh = false;
  let rawTableInstance = null;
  let rawNeedsRefresh = false;
  let rawCurrentPage = 1;
  let rawTotalPages = 1;
  const locale = document.documentElement.lang || 'en';
  const isPersian = locale.startsWith('fa');
  const kpiTotal = document.getElementById('kpi-total-interviews');
  const kpiSuccess = document.getElementById('kpi-successful-interviews');
  const kpiRate = document.getElementById('kpi-success-rate');
  const kpiDuration = document.getElementById('kpi-average-duration');
  const kpiDurationSample = document.getElementById('kpi-duration-sample');
  const kpiPeakHour = document.getElementById('kpi-peak-hour');
  const statusLabels = {
    true: isPersian ? 'موفق' : 'Successful',
    false: isPersian ? 'ناموفق' : 'Unsuccessful',
  };

  topTable.addEventListener('interactive-table:init', (event) => {
    topTableInstance = event.detail.instance;
    if (needsTableRefresh) {
      topTableInstance.refresh();
      needsTableRefresh = false;
    }
  });

  if (rawTable) {
    rawTable.addEventListener('interactive-table:init', (event) => {
      rawTableInstance = event.detail.instance;
      if (rawNeedsRefresh) {
        rawTableInstance.refresh();
        rawNeedsRefresh = false;
      }
    });
  }

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

  function collectFilters() {
    const projectSelect = document.getElementById('project-select');
    const userSelect = document.getElementById('user-select');
    const startInput = document.getElementById('start-date');
    const endInput = document.getElementById('end-date');
    const selectedProjects = projectSelect
      ? Array.from(projectSelect.selectedOptions)
          .map((option) => option.value)
          .filter((value) => value)
      : [];
    const selectedUsers = userSelect
      ? Array.from(userSelect.selectedOptions)
          .map((option) => option.value)
          .filter((value) => value)
      : [];
    const start = startInput ? startInput.value : '';
    const end = endInput ? endInput.value : '';
    return {
      projects: selectedProjects,
      users: selectedUsers,
      start,
      end,
    };
  }

  function appendFilters(params, filters) {
    if (filters.projects.length) {
      params.append('projects', filters.projects.join(','));
    }
    if (filters.start) {
      params.append('start_date', filters.start);
    }
    if (filters.end) {
      params.append('end_date', filters.end);
    }
    if (filters.users.length) {
      params.append('users', filters.users.join(','));
    }
  }

  function formatNumber(value) {
    if (!Number.isFinite(value)) {
      return '';
    }
    const localeName = isPersian ? 'fa-IR' : undefined;
    return value.toLocaleString(localeName);
  }

  function formatDateTime(value) {
    if (!value) {
      return { display: '', sort: '' };
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return { display: value, sort: value };
    }
    const localeName = isPersian ? 'fa-IR' : undefined;
    const options = {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    };
    const display = date.toLocaleString(localeName || undefined, options);
    return { display, sort: date.toISOString() };
  }

  function formatDurationMinutes(value) {
    if (!Number.isFinite(value) || value <= 0) {
      return isPersian ? '—' : '—';
    }
    const totalSeconds = Math.round(value * 60);
    const seconds = totalSeconds % 60;
    const minutes = Math.floor(totalSeconds / 60) % 60;
    const hours = Math.floor(totalSeconds / 3600);
    if (hours > 0) {
      return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }

  function getHeatColor(ratio) {
    const clamped = Math.max(0, Math.min(1, ratio || 0));
    const hue = 210 - clamped * 150; // shift from blue to warm as intensity increases
    const saturation = 70;
    const lightness = 32 + (1 - clamped) * 18;
    return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
  }

  function buildHeatColours(values) {
    if (!Array.isArray(values) || values.length === 0) {
      return [];
    }
    const max = Math.max(...values.map((v) => (Number.isFinite(v) ? v : 0)));
    if (!max) {
      return values.map(() => getCssVar('--surface-raised', '#1e293b'));
    }
    return values.map((value) => getHeatColor(value / max));
  }

  function updateKpis(meta) {
    const safeMeta = meta || {};
    const total = Number.isFinite(safeMeta.total_interviews) ? safeMeta.total_interviews : 0;
    const success = Number.isFinite(safeMeta.successful_interviews) ? safeMeta.successful_interviews : 0;
    const rateValue = Number.isFinite(safeMeta.success_rate)
      ? safeMeta.success_rate
      : total
      ? (success / total) * 100
      : 0;
    if (kpiTotal) {
      kpiTotal.textContent = formatNumber(total);
    }
    if (kpiSuccess) {
      kpiSuccess.textContent = formatNumber(success);
    }
    if (kpiRate) {
      if (Number.isFinite(rateValue)) {
        const localeName = isPersian ? 'fa-IR' : undefined;
        kpiRate.textContent = `${rateValue.toLocaleString(localeName, {
          minimumFractionDigits: 1,
          maximumFractionDigits: 1,
        })}%`;
      } else {
        kpiRate.textContent = '—';
      }
    }

    const durationLabel = safeMeta.average_duration_label || formatDurationMinutes(safeMeta.average_duration_minutes);
    if (kpiDuration) {
      kpiDuration.textContent = durationLabel || '—';
    }
    if (kpiDurationSample) {
      const sample = Number.isFinite(safeMeta.duration_sample_size) ? safeMeta.duration_sample_size : 0;
      if (sample > 0) {
        kpiDurationSample.textContent = isPersian
          ? `بر پایه ${formatNumber(sample)} رکورد`
          : `Based on ${formatNumber(sample)} records`;
      } else {
        kpiDurationSample.textContent = isPersian ? 'داده‌ای موجود نیست' : 'No duration data';
      }
    }
    if (kpiPeakHour) {
      const label = safeMeta.peak_hour_label || '';
      if (label) {
        kpiPeakHour.textContent = isPersian ? `اوج: ${label}` : `Peak: ${label}`;
      } else {
        kpiPeakHour.textContent = isPersian ? 'اوج مشخص نیست' : 'No peak hour';
      }
    }
  }

  function buildChartUrl() {
    const baseUrl = barCanvas.dataset.url;
    const params = new URLSearchParams();
    const filters = collectFilters();
    appendFilters(params, filters);
    return params.toString() ? `${baseUrl}?${params.toString()}` : baseUrl;
  }

  function buildRawUrl(pageOverride) {
    if (!rawTable || !rawTable.dataset || !rawTable.dataset.url) {
      return '';
    }
    const baseUrl = rawTable.dataset.url;
    const params = new URLSearchParams();
    const filters = collectFilters();
    appendFilters(params, filters);
    let pageSize = 30;
    if (rawPageSizeSelect) {
      const parsed = parseInt(rawPageSizeSelect.value, 10);
      if (!Number.isNaN(parsed) && [30, 50, 200].includes(parsed)) {
        pageSize = parsed;
      }
    }
    params.append('page_size', pageSize);
    const pageNumber = pageOverride && pageOverride > 0 ? pageOverride : rawCurrentPage || 1;
    params.append('page', pageNumber);
    return params.toString() ? `${baseUrl}?${params.toString()}` : baseUrl;
  }

  function setRawLoading() {
    if (rawPageInfo) {
      rawPageInfo.textContent = isPersian ? 'در حال بارگذاری…' : 'Loading…';
    }
    if (rawResultsStatus) {
      rawResultsStatus.textContent = '';
    }
    if (rawPrevButton) {
      rawPrevButton.disabled = true;
    }
    if (rawNextButton) {
      rawNextButton.disabled = true;
    }
  }

  function updateRawPagination(totalItems, page, pageSize, totalPages) {
    const safeTotalPages = Math.max(totalPages || 1, 1);
    rawTotalPages = safeTotalPages;
    rawCurrentPage = page;
    if (rawPageSizeSelect && String(pageSize) !== rawPageSizeSelect.value) {
      const option = Array.from(rawPageSizeSelect.options).find((opt) => opt.value === String(pageSize));
      if (option) {
        rawPageSizeSelect.value = option.value;
      }
    }
    if (rawPageInfo) {
      if (totalItems === 0) {
        rawPageInfo.textContent = isPersian ? 'هیچ رکوردی یافت نشد' : 'No records';
      } else {
        const pageLabel = isPersian
          ? `صفحه ${formatNumber(page)} از ${formatNumber(safeTotalPages)}`
          : `Page ${page} of ${safeTotalPages}`;
        rawPageInfo.textContent = pageLabel;
      }
    }
    if (rawResultsStatus) {
      if (totalItems === 0) {
        rawResultsStatus.textContent = isPersian ? 'هیچ مصاحبه‌ای برای نمایش وجود ندارد' : 'No interviews to display';
      } else {
        const startIndex = (page - 1) * pageSize + 1;
        const endIndex = Math.min(totalItems, startIndex + pageSize - 1);
        const startLabel = formatNumber(startIndex);
        const endLabel = formatNumber(endIndex);
        const totalLabel = formatNumber(totalItems);
        rawResultsStatus.textContent = isPersian
          ? `نمایش ${startLabel}–${endLabel} از ${totalLabel}`
          : `Showing ${startLabel}–${endLabel} of ${totalLabel}`;
      }
    }
    if (rawPrevButton) {
      rawPrevButton.disabled = totalItems === 0 || page <= 1;
    }
    if (rawNextButton) {
      rawNextButton.disabled = totalItems === 0 || page >= safeTotalPages;
    }
  }

  function renderRawRows(results) {
    if (!rawTable) {
      return;
    }
    const tbody = rawTable.querySelector('tbody');
    if (!tbody) {
      return;
    }
    tbody.innerHTML = '';
    if (!Array.isArray(results) || results.length === 0) {
      if (rawTableInstance) {
        rawTableInstance.refresh();
      } else {
        rawNeedsRefresh = true;
      }
      return;
    }
    results.forEach((item) => {
      const tr = document.createElement('tr');
      const projectCell = document.createElement('td');
      projectCell.textContent = item.project || '';
      tr.appendChild(projectCell);

      const userCell = document.createElement('td');
      userCell.textContent = item.user || '';
      tr.appendChild(userCell);

      const codeCell = document.createElement('td');
      if (item.code != null) {
        codeCell.textContent = String(item.code);
        codeCell.dataset.sortValue = String(item.code);
      } else {
        codeCell.textContent = '';
        delete codeCell.dataset.sortValue;
      }
      tr.appendChild(codeCell);

      const statusCell = document.createElement('td');
      const statusKey = item.status ? true : false;
      statusCell.textContent = statusLabels[statusKey];
      statusCell.dataset.sortValue = item.status ? '1' : '0';
      tr.appendChild(statusCell);

      const startCell = document.createElement('td');
      const startFormatted = formatDateTime(item.start_form);
      startCell.textContent = startFormatted.display;
      if (startFormatted.sort) {
        startCell.dataset.sortValue = startFormatted.sort;
      } else {
        delete startCell.dataset.sortValue;
      }
      tr.appendChild(startCell);

      const endCell = document.createElement('td');
      const endFormatted = formatDateTime(item.end_form);
      endCell.textContent = endFormatted.display;
      if (endFormatted.sort) {
        endCell.dataset.sortValue = endFormatted.sort;
      } else {
        delete endCell.dataset.sortValue;
      }
      tr.appendChild(endCell);

      const createdCell = document.createElement('td');
      const createdFormatted = formatDateTime(item.created_at);
      createdCell.textContent = createdFormatted.display;
      if (createdFormatted.sort) {
        createdCell.dataset.sortValue = createdFormatted.sort;
      } else {
        delete createdCell.dataset.sortValue;
      }
      tr.appendChild(createdCell);

      tbody.appendChild(tr);
    });
    if (rawTableInstance) {
      rawTableInstance.refresh();
    } else {
      rawNeedsRefresh = true;
    }
  }

  function fetchRawData(pageOverride) {
    if (!rawTable || !rawTable.dataset || !rawTable.dataset.url) {
      return;
    }
    setRawLoading();
    const url = buildRawUrl(pageOverride);
    if (!url) {
      renderRawRows([]);
      updateRawPagination(0, 1, 30, 1);
      return;
    }
    fetch(url)
      .then((resp) => resp.json())
      .then((data) => {
        const results = Array.isArray(data.results) ? data.results : [];
        const page = data.page || 1;
        const pageSize = data.page_size || (rawPageSizeSelect ? parseInt(rawPageSizeSelect.value, 10) || 30 : 30);
        const totalPages = data.total_pages || 1;
        const totalItems = data.total_items || 0;
        renderRawRows(results);
        updateRawPagination(totalItems, page, pageSize, totalPages);
      })
      .catch((error) => {
        console.error('Error loading raw interviews', error);
        if (rawPageInfo) {
          rawPageInfo.textContent = isPersian ? 'خطا در بارگیری داده‌ها' : 'Failed to load data';
        }
        if (rawResultsStatus) {
          rawResultsStatus.textContent = '';
        }
        if (rawPrevButton) {
          rawPrevButton.disabled = true;
        }
        if (rawNextButton) {
          rawNextButton.disabled = true;
        }
      });
  }


  function fetchChartsAndTop() {
    fetch(buildChartUrl())
      .then((resp) => resp.json())
      .then((data) => {
        updateKpis(data.meta);
        // Update bar chart
        const barData = data.bar || {};
        const labels = barData.labels || [];
        const totals = barData.totals || [];
        const successes = barData.successes || [];
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
        const donutData = data.donut || { labels: [], values: [], segments: [] };
        donutSegments = donutData.segments || [];
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
                tooltip: {
                  callbacks: {
                    label(context) {
                      const segment = donutSegments[context.dataIndex];
                      const label = segment ? segment.label : context.label;
                      return `${label}: ${context.formattedValue}`;
                    },
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
        // Update code breakdown chart
        if (ctxCode) {
          const codeItems = data.codes && Array.isArray(data.codes.items) ? data.codes.items : [];
          const codeValues = codeItems.map((item) => (Number.isFinite(item.count) ? item.count : Number(item.count) || 0));
          const codeLabels = codeItems.map((item) => {
            if (item.code === null || item.code === undefined || item.code === '') {
              return isPersian ? 'نامشخص' : 'Unknown';
            }
            const baseLabel = item.label || item.code;
            return isPersian ? `کد ${baseLabel}` : `Code ${baseLabel}`;
          });
          const codeColours = codeValues.length ? getPalette(codeValues.length) : [];
          if (codeChart) {
            codeChart.data.labels = codeLabels;
            codeChart.data.datasets[0].data = codeValues;
            codeChart.data.datasets[0].backgroundColor = codeColours.length ? codeColours : [];
            codeChart.data.datasets[0].borderColor = codeColours.length ? codeColours : [];
            codeChart.update();
          } else {
            codeChart = new Chart(ctxCode, {
              type: 'doughnut',
              data: {
                labels: codeLabels,
                datasets: [
                  {
                    data: codeValues,
                    backgroundColor: codeColours.length ? codeColours : [],
                    borderColor: codeColours.length ? codeColours : [],
                    borderWidth: 1,
                  },
                ],
              },
              options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '55%',
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
              },
            });
          }
        }
        // Update hourly distribution chart
        if (ctxHourly) {
          const hourly = data.hourly || { labels: [], totals: [], successes: [] };
          const totalsData = Array.isArray(hourly.totals) ? hourly.totals : [];
          const successData = Array.isArray(hourly.successes) ? hourly.successes : [];
          const heatColours = buildHeatColours(totalsData);
          if (hourlyChart) {
            hourlyChart.data.labels = Array.isArray(hourly.labels) ? hourly.labels : [];
            hourlyChart.data.datasets[0].data = totalsData;
            hourlyChart.data.datasets[0].backgroundColor = heatColours;
            hourlyChart.data.datasets[0].borderColor = heatColours;
            hourlyChart.data.datasets[1].data = successData;
            hourlyChart.update();
          } else {
            hourlyChart = new Chart(ctxHourly, {
              type: 'bar',
              data: {
                labels: Array.isArray(hourly.labels) ? hourly.labels : [],
                datasets: [
                  {
                    label: isPersian ? 'کل تماس‌ها' : 'Total Calls',
                    data: totalsData,
                    backgroundColor: heatColours,
                    borderColor: heatColours,
                    borderWidth: 1,
                    maxBarThickness: 28,
                  },
                  {
                    label: isPersian ? 'موفق' : 'Successful',
                    data: successData,
                    type: 'line',
                    borderColor: secondaryBorder,
                    backgroundColor: 'rgba(0,0,0,0)',
                    borderWidth: 2,
                    tension: 0.25,
                    pointRadius: 2,
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
                      maxRotation: 0,
                      minRotation: 0,
                      autoSkip: true,
                      maxTicksLimit: 12,
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
        topData = data.top && data.top.rows ? data.top.rows : [];
        renderTopTable();
      })
      .catch((err) => {
        console.error('Error loading performance data', err);
      });
  }

  function renderTopTable() {
    const tbody = topTable.querySelector('tbody');
    tbody.innerHTML = '';
    if (!topData.length) {
      if (topTableInstance) {
        topTableInstance.refresh();
      } else {
        needsTableRefresh = true;
      }
      return;
    }
    const sorted = topData.slice().sort((a, b) => b.total - a.total);
    sorted.forEach((row) => {
      const tr = document.createElement('tr');
      const projectCell = document.createElement('td');
      projectCell.textContent = row.project || '';
      const userCell = document.createElement('td');
      userCell.textContent = row.user;
      const totalCell = document.createElement('td');
      totalCell.textContent = row.total;
      totalCell.dataset.sortValue = row.total;
      const successCell = document.createElement('td');
      successCell.textContent = row.success;
      successCell.dataset.sortValue = row.success;
      const rateCell = document.createElement('td');
      rateCell.textContent = `${row.rate}%`;
      rateCell.dataset.sortValue = row.rate;
      tr.appendChild(projectCell);
      tr.appendChild(userCell);
      tr.appendChild(totalCell);
      tr.appendChild(successCell);
      tr.appendChild(rateCell);
      tbody.appendChild(tr);
    });
    if (topTableInstance) {
      topTableInstance.refresh();
    } else {
      needsTableRefresh = true;
    }
  }

  function refreshAll(resetRawPage = false) {
    fetchChartsAndTop();
    if (rawTable && rawTable.dataset && rawTable.dataset.url) {
      if (resetRawPage) {
        rawCurrentPage = 1;
      }
      fetchRawData(rawCurrentPage);
    }
  }

  // Fetch data initially and whenever filters change
  refreshAll(true);
  ['project-select', 'start-date', 'end-date', 'user-select'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', () => refreshAll(true));
    }
  });

  if (rawPageSizeSelect) {
    rawPageSizeSelect.addEventListener('change', () => {
      rawCurrentPage = 1;
      fetchRawData(rawCurrentPage);
    });
  }

  if (rawPrevButton) {
    rawPrevButton.addEventListener('click', () => {
      if (rawCurrentPage > 1) {
        rawCurrentPage -= 1;
        fetchRawData(rawCurrentPage);
      }
    });
  }

  if (rawNextButton) {
    rawNextButton.addEventListener('click', () => {
      if (rawCurrentPage < rawTotalPages) {
        rawCurrentPage += 1;
        fetchRawData(rawCurrentPage);
      }
    });
  }
});