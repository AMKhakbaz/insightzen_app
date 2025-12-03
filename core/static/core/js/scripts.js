// Global scripts for InsightZen
// Handles sidebar toggle and Conjoint Analysis AJAX interactions.

document.addEventListener('DOMContentLoaded', function () {
  initNotificationCenter();
  initBreadcrumbs();
  // Conjoint analysis form submission
  const form = document.getElementById('conjoint-form');
  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      const fileInput = document.getElementById('conjoint-file');
      if (!fileInput || !fileInput.files.length) {
        alert('Please select a file.');
        return;
      }
      const analysisTypeSelect = document.getElementById('analysis-type');
      const analysisType = analysisTypeSelect ? analysisTypeSelect.value : 'cbc';
      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      formData.append('analysis_type', analysisType);
      const csrftoken = getCookie('csrftoken');
      fetch('/conjoint/analyze/', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData,
      })
        .then((resp) => resp.json())
        .then((data) => {
          const resultDiv = document.getElementById('conjoint-results');
          if (!resultDiv) return;
          resultDiv.innerHTML = '';
          if (data.error) {
            resultDiv.innerHTML = '<div class="alert alert-error">' + data.error + '</div>';
            return;
          }
          if (data.analysis === 'cbc' || data.analysis === 'full_profile') {
            // Build a dashboard grid for charts and tables. Cards appear in a logical order: bar chart, scatter plot (if any), part-worth table, and top profiles.
            const grid = document.createElement('div');
            grid.className = 'dashboard-grid';

            // Part‑worth bar chart card
            const barCard = document.createElement('div');
            barCard.className = 'dashboard-card';
            const barChartId = 'bar-chart-' + Date.now();
            barCard.innerHTML = '<h3>Part‑Worth Chart</h3>' + `<canvas id="${barChartId}" style="width:100%;height:200px;"></canvas>`;
            grid.appendChild(barCard);

            // Scatter chart card (optional)
            let scatterChartId = null;
            if (data.scatter_data && data.scatter_data.length > 0) {
              const scatterCard = document.createElement('div');
              scatterCard.className = 'dashboard-card';
              scatterChartId = 'scatter-' + Date.now();
              scatterCard.innerHTML = '<h3>Profile Scatter</h3>' + `<canvas id="${scatterChartId}" style="width:100%;height:220px;"></canvas>`;
              grid.appendChild(scatterCard);
            }

            // Part‑worth table card
            const pwCard = document.createElement('div');
            pwCard.className = 'dashboard-card';
            let pwHtml = '<h3>Part‑Worth Table</h3>';
            pwHtml += '<div class="table-responsive"><table class="table"><thead><tr><th>Level</th><th>Value</th></tr></thead><tbody>';
            data.partworth_table.forEach((row) => {
              pwHtml += `<tr><td>${row.level}</td><td>${row.value}</td></tr>`;
            });
            pwHtml += '</tbody></table></div>';
            pwCard.innerHTML = pwHtml;
            grid.appendChild(pwCard);

            // Top profiles table card
            const topCard = document.createElement('div');
            topCard.className = 'dashboard-card';
            let topHtml = '<h3>Top Profiles</h3>';
            if (data.top_profiles && data.top_profiles.length > 0) {
              topHtml += '<div class="table-responsive"><table class="table"><thead><tr>';
              Object.keys(data.top_profiles[0]).forEach((key) => {
                topHtml += `<th>${key}</th>`;
              });
              topHtml += '</tr></thead><tbody>';
              data.top_profiles.forEach((profile) => {
                topHtml += '<tr>';
                Object.values(profile).forEach((val) => {
                  topHtml += `<td>${val}</td>`;
                });
                topHtml += '</tr>';
              });
              topHtml += '</tbody></table></div>';
            }
            topCard.innerHTML = topHtml;
            grid.appendChild(topCard);

            resultDiv.appendChild(grid);
            // Render bar chart using Chart.js (top 10 by absolute utility)
            const sortedPW = data.partworth_table
              .slice()
              .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
            const pwLimit = Math.min(10, sortedPW.length);
            const topPW = sortedPW.slice(0, pwLimit);
            const labels = topPW.map((r) => r.level);
            const values = topPW.map((r) => r.value);
            const colors = values.map((v) => (v < 0 ? '#ff4955' : '#15b8d9'));
            const barCtx = document.getElementById(barChartId).getContext('2d');
            new Chart(barCtx, {
              type: 'bar',
              data: {
                labels: labels,
                datasets: [
                  {
                    label: 'Utility',
                    data: values,
                    backgroundColor: colors,
                  },
                ],
              },
              options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                  legend: { display: false },
                  tooltip: {
                    callbacks: {
                      label: function (context) {
                        return context.dataset.label + ': ' + context.parsed.x.toFixed(3);
                      },
                    },
                  },
                },
                scales: {
                  x: {
                    grid: { color: '#333' },
                    ticks: { color: '#e8e8e8' },
                  },
                  y: {
                    grid: { color: '#333' },
                    ticks: { color: '#e8e8e8' },
                    maxBarThickness: 14,
                    categoryPercentage: 0.65,
                    barPercentage: 0.65,
                  },
                },
              },
            });

            // Render scatter chart if available
            if (scatterChartId) {
              const scatterCtx = document.getElementById(scatterChartId).getContext('2d');
              // Determine min and max for probability or rating
              const valuesArr = data.scatter_data.map((p) => p.prob !== undefined ? p.prob : p.rating);
              const minVal = Math.min(...valuesArr);
              const maxVal = Math.max(...valuesArr);
              function interpolateColor(val) {
                // Normalize between 0 and 1
                const t = (val - minVal) / (maxVal - minVal || 1);
                // Interpolate between red (#ff4955) and blue (#15b8d9)
                const rStart = 0xff, gStart = 0x49, bStart = 0x55;
                const rEnd = 0x15, gEnd = 0xb8, bEnd = 0xd9;
                const r = Math.round(rStart + (rEnd - rStart) * t);
                const g = Math.round(gStart + (gEnd - gStart) * t);
                const b = Math.round(bStart + (bEnd - bStart) * t);
                return `rgb(${r}, ${g}, ${b})`;
              }
              const scatterPoints = data.scatter_data.map((p) => {
                const value = p.prob !== undefined ? p.prob : p.rating;
                return {
                  x: p.x,
                  y: p.y,
                  r: 4,
                  backgroundColor: interpolateColor(value),
                  _customVal: value,
                };
              });
              new Chart(scatterCtx, {
                type: 'scatter',
                data: {
                  datasets: [
                    {
                      label: '',
                      data: scatterPoints,
                      pointRadius: scatterPoints.map((pt) => pt.r),
                      backgroundColor: scatterPoints.map((pt) => pt.backgroundColor),
                      borderWidth: 0,
                    },
                  ],
                },
                options: {
                  responsive: true,
                  maintainAspectRatio: false,
                  animation: false,
                  plugins: {
                    legend: { display: false },
                    tooltip: {
                      callbacks: {
                        label: function (context) {
                          const point = context.raw;
                          const val = point._customVal;
                          const label = data.analysis === 'cbc' ? 'Prob: ' : 'Rating: ';
                          // Show one decimal percent for probability or one decimal for rating
                          if (data.analysis === 'cbc') {
                            return label + (val * 100).toFixed(1) + '%';
                          }
                          return label + val.toFixed(2);
                        },
                      },
                    },
                  },
                  scales: {
                    x: {
                      title: { display: true, text: 'PCA 1', color: '#e8e8e8' },
                      grid: { color: '#333' },
                      ticks: { color: '#e8e8e8' },
                    },
                    y: {
                      title: { display: true, text: 'PCA 2', color: '#e8e8e8' },
                      grid: { color: '#333' },
                      ticks: { color: '#e8e8e8' },
                    },
                  },
                },
              });
            }
          } else if (data.analysis === 'maxdiff') {
            // Build a dashboard grid with two columns. The first row holds two charts,
            // and the second row holds the table spanning both columns. This
            // layout makes better use of space and improves readability.
            const grid = document.createElement('div');
            grid.className = 'dashboard-grid';
            // Force two columns for maxdiff layout
            grid.style.gridTemplateColumns = '1fr 1fr';
            // Prepare data if results exist
            if (data.results && data.results.length > 0) {
              // Limit top items to 5 for readability
              const topItems = data.results.slice(0, 5);
              const labels = topItems.map((item) => item.Item);
              const scores = topItems.map((item) => Number(item.Score));
              const bestCounts = topItems.map((item) => Number(item['Best Count']));
              const worstCounts = topItems.map((item) => -Number(item['Worst Count']));
              // Score chart card
              const scoreCard = document.createElement('div');
              scoreCard.className = 'dashboard-card';
              const scoreChartId = 'md-score-' + Date.now();
              scoreCard.innerHTML = '<h3>Score Chart</h3>' + `<canvas id="${scoreChartId}" style="width:100%;height:220px;"></canvas>`;
              grid.appendChild(scoreCard);
              // Counts chart card
              const countsCard = document.createElement('div');
              countsCard.className = 'dashboard-card';
              const countsChartId = 'md-counts-' + Date.now();
              countsCard.innerHTML = '<h3>Best vs Worst Counts</h3>' + `<canvas id="${countsChartId}" style="width:100%;height:220px;"></canvas>`;
              grid.appendChild(countsCard);
              // Table card spanning both columns
              const tableCard = document.createElement('div');
              tableCard.className = 'dashboard-card';
              // Span across two columns on larger screens
              tableCard.style.gridColumn = 'span 2';
              let tblHtml = '<h3>MaxDiff Results</h3>';
              tblHtml += '<div class="table-responsive"><table class="table"><thead><tr>';
              Object.keys(data.results[0]).forEach((key) => {
                tblHtml += `<th>${key}</th>`;
              });
              tblHtml += '</tr></thead><tbody>';
              data.results.forEach((row) => {
                tblHtml += '<tr>';
                Object.values(row).forEach((val) => {
                  tblHtml += `<td>${val}</td>`;
                });
                tblHtml += '</tr>';
              });
              tblHtml += '</tbody></table></div>';
              tableCard.innerHTML = tblHtml;
              grid.appendChild(tableCard);
              // Append grid to resultDiv
              resultDiv.appendChild(grid);
              // Render Score bar chart
              const scoreCtx = document.getElementById(scoreChartId).getContext('2d');
              const scoreColors = scores.map((s) => (s >= 0 ? '#15b8d9' : '#ff4955'));
              new Chart(scoreCtx, {
                type: 'bar',
                data: {
                  labels: labels,
                  datasets: [
                    {
                      label: 'Score',
                      data: scores,
                      backgroundColor: scoreColors,
                    },
                  ],
                },
                options: {
                  indexAxis: 'y',
                  responsive: true,
                  maintainAspectRatio: false,
                  animation: false,
                  plugins: {
                    legend: { display: false },
                    tooltip: {
                      callbacks: {
                        label: function (context) {
                          return 'Score: ' + context.parsed.x.toFixed(3);
                        },
                      },
                    },
                  },
                  scales: {
                    x: {
                      grid: { color: '#333' },
                      ticks: { color: '#e8e8e8' },
                    },
                    y: {
                      grid: { color: '#333' },
                      ticks: { color: '#e8e8e8' },
                      maxBarThickness: 14,
                      categoryPercentage: 0.65,
                      barPercentage: 0.65,
                    },
                  },
                },
              });
              // Render Best vs Worst counts chart
              const countsCtx = document.getElementById(countsChartId).getContext('2d');
              new Chart(countsCtx, {
                type: 'bar',
                data: {
                  labels: labels,
                  datasets: [
                    {
                      label: 'Best Count',
                      data: bestCounts,
                      backgroundColor: '#15b8d9',
                    },
                    {
                      label: 'Worst Count',
                      data: worstCounts,
                      backgroundColor: '#ff4955',
                    },
                  ],
                },
                options: {
                  indexAxis: 'y',
                  responsive: true,
                  maintainAspectRatio: false,
                  animation: false,
                  plugins: {
                    legend: {
                      display: true,
                      labels: { color: '#e8e8e8' },
                    },
                    tooltip: {
                      callbacks: {
                        label: function (context) {
                          const label = context.dataset.label;
                          const val = context.parsed.x;
                          return label + ': ' + Math.abs(val);
                        },
                      },
                    },
                  },
                  scales: {
                    x: {
                      stacked: true,
                      grid: { color: '#333' },
                      ticks: { color: '#e8e8e8' },
                    },
                    y: {
                      stacked: true,
                      grid: { color: '#333' },
                      ticks: { color: '#e8e8e8' },
                      maxBarThickness: 14,
                      categoryPercentage: 0.65,
                      barPercentage: 0.65,
                    },
                  },
                },
              });
            } else {
              // If no results, display an empty table card
              const tableCard = document.createElement('div');
              tableCard.className = 'dashboard-card';
              tableCard.style.gridColumn = 'span 2';
              tableCard.innerHTML = '<h3>MaxDiff Results</h3><p>No results.</p>';
              grid.appendChild(tableCard);
              resultDiv.appendChild(grid);
            }
          }
        })
        .catch((err) => {
          console.error(err);
          const resultDiv = document.getElementById('conjoint-results');
          if (resultDiv) {
            resultDiv.innerHTML = '<div class="alert alert-error">Error processing request</div>';
          }
        });
    });
  }

  // Coding/Category analysis form submission
  const codingForm = document.getElementById('coding-form');
  if (codingForm) {
    codingForm.addEventListener('submit', function (e) {
      e.preventDefault();
      const fileInput = document.getElementById('coding-file');
      if (!fileInput || !fileInput.files.length) {
        alert('Please select a file.');
        return;
      }
      const analysisTypeSelect = document.getElementById('coding-type');
      const analysisType = analysisTypeSelect ? analysisTypeSelect.value : 'coding';
      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      formData.append('analysis_type', analysisType);
      const csrftoken = getCookie('csrftoken');
      fetch('/coding/analyze/', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData,
      })
        .then((resp) => resp.json())
        .then((data) => {
          const resultDiv = document.getElementById('coding-results');
          if (!resultDiv) return;
          resultDiv.innerHTML = '';
          if (data.error) {
            resultDiv.innerHTML = '<div class="alert alert-error">' + data.error + '</div>';
            return;
          }
          // Build display for coding or category results
          if (data.analysis === 'coding' || data.analysis === 'category') {
            const rows = data.rows || [];
            if (rows.length === 0) {
              resultDiv.innerHTML = '<p>No results.</p>';
              return;
            }
            rows.forEach((row) => {
              const card = document.createElement('div');
              card.className = 'result-batch';
              const header = document.createElement('h4');
              header.textContent = `${row.qid} — Rows ${row.batch_start}-${row.batch_end}`;
              const pre = document.createElement('pre');
              pre.textContent = row.content;
              pre.style.whiteSpace = 'pre-wrap';
              pre.style.background = '#1e1e1e';
              pre.style.padding = '0.5rem';
              pre.style.borderRadius = '0.5rem';
              pre.style.overflowX = 'auto';
              card.appendChild(header);
              card.appendChild(pre);
              resultDiv.appendChild(card);
            });
          }
        })
        .catch((err) => {
          console.error(err);
          const resultDiv = document.getElementById('coding-results');
          if (resultDiv) {
            resultDiv.innerHTML = '<div class="alert alert-error">Error processing request</div>';
          }
        });
    });
  }

  const qcEditButtons = document.querySelectorAll('[data-enketo-edit]');
  if (qcEditButtons.length) {
    qcEditButtons.forEach((button) => {
      button.addEventListener('click', function (event) {
        event.preventDefault();
        if (button.disabled) {
          return;
        }
        const submissionId = button.getAttribute('data-enketo-edit');
        const entryId = button.getAttribute('data-entry-id');
        if (!submissionId || !entryId) {
          return;
        }
        const statusEl = button.parentElement ? button.parentElement.querySelector('[data-status]') : null;
        const loadingText = button.dataset.loadingText || 'Requesting link…';
        const successText = button.dataset.successText || 'Edit form opened.';
        const errorText = button.dataset.errorText || 'Unable to fetch edit link.';
        if (statusEl) {
          statusEl.textContent = loadingText;
          statusEl.dataset.state = 'loading';
        }
        button.disabled = true;
        const pendingWindow = window.open('', '_blank');
        const csrftoken = getCookie('csrftoken');
        fetch(`/qc/edit/${entryId}/link/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken,
          },
          body: JSON.stringify({ submission_id: submissionId }),
        })
          .then((response) =>
            response
              .json()
              .catch(() => ({}))
              .then((data) => ({ status: response.status, data })),
          )
          .then(({ status, data }) => {
            if (status >= 200 && status < 300 && data.url) {
              if (pendingWindow) {
                pendingWindow.location.href = data.url;
                pendingWindow.focus();
              } else {
                window.open(data.url, '_blank', 'noopener');
              }
              if (statusEl) {
                statusEl.textContent = successText;
                statusEl.dataset.state = 'success';
              }
            } else {
              if (pendingWindow) {
                pendingWindow.close();
              }
              const message = data.error || errorText;
              if (statusEl) {
                statusEl.textContent = message;
                statusEl.dataset.state = 'error';
              }
            }
          })
          .catch(() => {
            if (pendingWindow) {
              pendingWindow.close();
            }
            if (statusEl) {
              statusEl.textContent = errorText;
              statusEl.dataset.state = 'error';
            }
          })
          .finally(() => {
            button.disabled = false;
          });
      });
    });
  }

  const messagingPanel = document.querySelector('[data-member-messaging]');
  if (messagingPanel) {
    const endpoint = messagingPanel.getAttribute('data-member-endpoint');
    const textarea = messagingPanel.querySelector('[data-member-message-input]');
    const sendButton = messagingPanel.querySelector('[data-member-send]');
    const clearButton = messagingPanel.querySelector('[data-member-clear]');
    const counterNode = messagingPanel.querySelector('[data-member-char-count]');
    const selectedCountNode = messagingPanel.querySelector('[data-member-selected-count]');
    const statusNode = messagingPanel.querySelector('[data-member-status]');
    const table = document.getElementById('membership-table');
    const masterCheckbox = document.querySelector('[data-member-select-all]');
    const lang = document.documentElement.lang === 'fa' ? 'fa' : 'en';
    const text = {
      en: {
        sending: 'Sending message…',
        success: (count) => `${count} notification${count === 1 ? '' : 's'} sent.`,
        partial: 'Some recipients were skipped because they lack access.',
        required: 'Enter a message before sending.',
        none: 'Select at least one member.',
        error: 'Unable to send the message. Please try again.',
      },
      fa: {
        sending: 'در حال ارسال پیام…',
        success: (count) => `${count} اعلان ارسال شد.`,
        partial: 'برخی کاربران به دلیل محدودیت دسترسی نادیده گرفته شدند.',
        required: 'لطفاً متن پیام را وارد کنید.',
        none: 'حداقل یک کاربر را انتخاب کنید.',
        error: 'امکان ارسال پیام وجود ندارد. دوباره تلاش کنید.',
      },
    };

    const state = {
      selected: new Set(),
      sending: false,
    };

    const setStatus = (message, variant) => {
      if (!statusNode) return;
      statusNode.textContent = message || '';
      statusNode.classList.remove('is-error', 'is-success');
      if (variant === 'error') {
        statusNode.classList.add('is-error');
      } else if (variant === 'success') {
        statusNode.classList.add('is-success');
      }
    };

    const clearStatus = () => setStatus('', null);

    const getCheckboxes = () => {
      if (!table) return [];
      return Array.from(table.querySelectorAll('[data-member-checkbox]'));
    };

    const syncCounter = () => {
      if (!textarea || !counterNode) return;
      const maxLen = 500;
      if (textarea.value.length > maxLen) {
        textarea.value = textarea.value.slice(0, maxLen);
      }
      counterNode.textContent = `${textarea.value.length} / ${maxLen}`;
    };

    const updateControls = () => {
      const hasSelection = state.selected.size > 0;
      const message = textarea ? textarea.value.trim() : '';
      if (selectedCountNode) {
        selectedCountNode.textContent = state.selected.size;
      }
      if (sendButton) {
        const disabled =
          !endpoint || !hasSelection || !message || message.length > 500 || state.sending;
        sendButton.disabled = disabled;
      }
      if (clearButton) {
        clearButton.disabled = !hasSelection || state.sending;
      }
    };

    const refreshMaster = () => {
      if (!masterCheckbox) return;
      const boxes = getCheckboxes();
      const total = boxes.length;
      if (!total) {
        masterCheckbox.checked = false;
        masterCheckbox.indeterminate = false;
        return;
      }
      const selected = state.selected.size;
      masterCheckbox.checked = selected > 0 && selected === total;
      masterCheckbox.indeterminate = selected > 0 && selected < total;
    };

    const toggleSelection = (checkbox, force) => {
      if (!checkbox) return;
      const value = parseInt(checkbox.value, 10);
      if (Number.isNaN(value)) {
        return;
      }
      const shouldCheck = typeof force === 'boolean' ? force : checkbox.checked;
      checkbox.checked = shouldCheck;
      if (shouldCheck) {
        state.selected.add(value);
      } else {
        state.selected.delete(value);
      }
    };

    const attachCheckboxHandlers = () => {
      getCheckboxes().forEach((checkbox) => {
        checkbox.addEventListener('change', (event) => {
          const target = event.currentTarget;
          if (!(target instanceof HTMLInputElement)) return;
          toggleSelection(target);
          refreshMaster();
          updateControls();
          clearStatus();
        });
      });
    };

    const clearSelection = () => {
      getCheckboxes().forEach((checkbox) => {
        toggleSelection(checkbox, false);
      });
      state.selected.clear();
      if (masterCheckbox) {
        masterCheckbox.checked = false;
        masterCheckbox.indeterminate = false;
      }
      updateControls();
    };

    const sendMessage = () => {
      if (!textarea || !sendButton || !endpoint) return;
      const message = textarea.value.trim();
      if (!state.selected.size) {
        setStatus(text[lang].none, 'error');
        return;
      }
      if (!message) {
        setStatus(text[lang].required, 'error');
        return;
      }
      const csrftoken = getCookie('csrftoken') || '';
      state.sending = true;
      updateControls();
      setStatus(text[lang].sending, null);
      fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrftoken,
        },
        body: JSON.stringify({
          message,
          user_ids: Array.from(state.selected),
        }),
      })
        .then((response) =>
          response
            .json()
            .then((data) => ({ ok: response.ok, data }))
            .catch(() => ({ ok: response.ok, data: {} }))
        )
        .then((result) => {
          const data = result.data || {};
          if (!result.ok || !data.ok) {
            setStatus(data.message || text[lang].error, 'error');
            return;
          }
          const count = Number(data.created || 0);
          let messageText = text[lang].success(count);
          if (Array.isArray(data.skipped) && data.skipped.length) {
            messageText = `${messageText} ${text[lang].partial}`;
          }
          setStatus(messageText, 'success');
          textarea.value = '';
          syncCounter();
          clearSelection();
        })
        .catch(() => {
          setStatus(text[lang].error, 'error');
        })
        .finally(() => {
          state.sending = false;
          updateControls();
        });
    };

    attachCheckboxHandlers();
    refreshMaster();
    syncCounter();
    updateControls();

    if (masterCheckbox) {
      masterCheckbox.addEventListener('change', () => {
        const shouldCheck = masterCheckbox.checked;
        getCheckboxes().forEach((checkbox) => {
          toggleSelection(checkbox, shouldCheck);
        });
        if (!shouldCheck) {
          masterCheckbox.indeterminate = false;
        }
        updateControls();
        clearStatus();
      });
    }

    if (clearButton) {
      clearButton.addEventListener('click', () => {
        clearSelection();
        clearStatus();
      });
    }

    if (textarea) {
      textarea.addEventListener('input', () => {
        syncCounter();
        updateControls();
        clearStatus();
      });
    }

    if (sendButton) {
      sendButton.addEventListener('click', sendMessage);
    }
  }

});

function initNotificationCenter() {
  const root = document.querySelector('[data-notification-root]');
  if (!root) return;

  const toggle = root.querySelector('[data-notification-toggle]');
  const panel = root.querySelector('[data-notification-panel]');
  if (!toggle || !panel) return;

  const list = root.querySelector('[data-notification-list]');
  const emptyState = root.querySelector('[data-notification-empty]');
  const countBadge = root.querySelector('[data-notification-count]');
  const statusEl = root.querySelector('[data-notification-status]');
  const markAllButton = root.querySelector('[data-notification-mark-all]');

  const lang = document.documentElement.lang === 'fa' ? 'fa' : 'en';
  const locale = lang === 'fa' ? 'fa-IR' : 'en-US';

  const text = {
    en: {
      loading: 'Loading notifications…',
      error: 'Unable to load notifications.',
      updated: 'Notifications updated.',
      markAll: 'Mark all as read',
      empty: "You're all caught up.",
      none: 'No unread notifications.',
      project: 'Project',
    },
    fa: {
      loading: 'در حال بارگذاری اعلان‌ها…',
      error: 'بارگذاری اعلان‌ها ممکن نیست.',
      updated: 'اعلان‌ها به‌روزرسانی شد.',
      markAll: 'علامت‌گذاری همه به‌عنوان خوانده‌شده',
      empty: 'اعلان خوانده‌نشده‌ای وجود ندارد.',
      none: 'اعلان خوانده‌نشده‌ای وجود ندارد.',
      project: 'پروژه',
    },
  };

  if (markAllButton) {
    markAllButton.textContent = text[lang].markAll;
  }
  if (emptyState) {
    emptyState.textContent = text[lang].empty;
  }

  let totalUnread = 0;
  let cachedItems = [];
  let isOpen = false;
  let isFetching = false;

  const updateBadge = (total) => {
    if (!countBadge) return;
    if (total > 0) {
      countBadge.hidden = false;
      countBadge.textContent = total > 99 ? '99+' : String(total);
    } else {
      countBadge.hidden = true;
    }
  };

  const setStatus = (message, tone = 'info') => {
    if (!statusEl) return;
    statusEl.textContent = message || '';
    statusEl.dataset.tone = tone;
  };

  const formatTimestamp = (isoString) => {
    if (!isoString) return '';
    try {
      const date = new Date(isoString);
      if (Number.isNaN(date.getTime())) {
        return '';
      }
      return date.toLocaleString(locale, {
        dateStyle: 'medium',
        timeStyle: 'short',
      });
    } catch (err) {
      return '';
    }
  };

  const renderList = (items) => {
    cachedItems = Array.isArray(items) ? items.slice() : [];
    if (list) {
      list.innerHTML = '';
    }
    if (!list) {
      return;
    }
    if (!cachedItems.length) {
      if (emptyState) {
        emptyState.hidden = false;
      }
      return;
    }
    if (emptyState) {
      emptyState.hidden = true;
    }

    cachedItems.forEach((item) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'notification-item';
      button.dataset.id = String(item.id);
      button.setAttribute('role', 'listitem');

      const message = document.createElement('div');
      message.className = 'notification-item__message';
      message.textContent = item.message || '';
      button.appendChild(message);

      const metaParts = [];
      if (item.project) {
        metaParts.push(`${text[lang].project}: ${item.project}`);
      }
      const when = formatTimestamp(item.createdAt);
      if (when) {
        metaParts.push(when);
      }
      if (metaParts.length) {
        const meta = document.createElement('div');
        meta.className = 'notification-item__meta';
        meta.textContent = metaParts.join(' • ');
        button.appendChild(meta);
      }

      list.appendChild(button);
    });
  };

  const fetchNotifications = (force = false) => {
    if (isFetching) return;
    if (!force && !isOpen) {
      return;
    }
    isFetching = true;
    setStatus(text[lang].loading);
    fetch('/api/notifications/unread/', { headers: { Accept: 'application/json' } })
      .then((response) => {
        if (!response.ok) {
          throw new Error('Failed to load');
        }
        return response.json();
      })
      .then((data) => {
        const notifications = Array.isArray(data.notifications) ? data.notifications : [];
        totalUnread = Number(data.count) || 0;
        renderList(notifications);
        updateBadge(totalUnread);
        setStatus(totalUnread ? '' : text[lang].none);
      })
      .catch(() => {
        setStatus(text[lang].error, 'error');
      })
      .finally(() => {
        isFetching = false;
      });
  };

  const postMark = (payload) => {
    return fetch('/api/notifications/mark-read/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken') || '',
      },
      body: JSON.stringify(payload),
    }).then((response) => {
      if (!response.ok) {
        throw new Error('failed');
      }
      return response.json();
    });
  };

  const closePanel = () => {
    if (!isOpen) return;
    isOpen = false;
    panel.setAttribute('hidden', '');
    toggle.setAttribute('aria-expanded', 'false');
    document.removeEventListener('click', handleOutside, true);
    document.removeEventListener('keydown', handleKeydown, true);
  };

  const openPanel = () => {
    if (isOpen) return;
    isOpen = true;
    panel.removeAttribute('hidden');
    toggle.setAttribute('aria-expanded', 'true');
    fetchNotifications(true);
    document.addEventListener('click', handleOutside, true);
    document.addEventListener('keydown', handleKeydown, true);
  };

  const handleOutside = (event) => {
    if (!root.contains(event.target)) {
      closePanel();
    }
  };

  const handleKeydown = (event) => {
    if (event.key === 'Escape') {
      closePanel();
    }
  };

  toggle.addEventListener('click', () => {
    if (isOpen) {
      closePanel();
    } else {
      openPanel();
    }
  });

  if (markAllButton) {
    markAllButton.addEventListener('click', () => {
      if (!totalUnread) {
        setStatus(text[lang].none);
        return;
      }
      markAllButton.disabled = true;
      setStatus(text[lang].loading);
      postMark({ all: true })
        .then((data) => {
          const updated = Number(data.updated) || totalUnread;
          totalUnread = Math.max(0, totalUnread - updated);
          cachedItems = [];
          renderList([]);
          updateBadge(totalUnread);
          setStatus(text[lang].updated);
        })
        .catch(() => {
          setStatus(text[lang].error, 'error');
        })
        .finally(() => {
          markAllButton.disabled = false;
        });
    });
  }

  if (list) {
    list.addEventListener('click', (event) => {
      const target = event.target.closest('.notification-item');
      if (!target) return;
      const id = Number(target.dataset.id);
      if (!id) return;
      target.disabled = true;
      postMark({ ids: [id] })
        .then((data) => {
          const removed = Number(data.updated) || 1;
          totalUnread = Math.max(0, totalUnread - removed);
          cachedItems = cachedItems.filter((item) => item.id !== id);
          renderList(cachedItems);
          updateBadge(totalUnread);
          setStatus(totalUnread ? text[lang].updated : text[lang].none);
        })
        .catch(() => {
          setStatus(text[lang].error, 'error');
          target.disabled = false;
        });
    });
  }

  // Prime the badge once the page loads.
  fetchNotifications(true);
}

function initBreadcrumbs() {
  const breadcrumbNavs = document.querySelectorAll('[data-breadcrumb]');
  breadcrumbNavs.forEach((nav) => {
    const items = nav.querySelectorAll('[data-breadcrumb-item]');
    if (!items.length) return;
    const current = items[items.length - 1];
    current.setAttribute('aria-current', 'page');
    if (nav.scrollWidth > nav.clientWidth) {
      nav.scrollLeft = nav.scrollWidth;
    }
  });
}

// Helper to get CSRF token from cookies
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === name + '=') {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}