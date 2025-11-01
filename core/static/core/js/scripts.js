// Global scripts for InsightZen
// Handles sidebar toggle and Conjoint Analysis AJAX interactions.

document.addEventListener('DOMContentLoaded', function () {
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
});

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