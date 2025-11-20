(function () {
    function formatNumber(value) {
        const numeric = Number(value || 0);
        return Number.isFinite(numeric) ? numeric.toLocaleString() : '0';
    }

    function updateElements(root, selector, value) {
        root.querySelectorAll(selector).forEach((el) => {
            el.textContent = value;
        });
    }

    function buildChart(root, chartRef, state) {
        const canvas = root.querySelector('[data-dashboard-chart]');
        if (!canvas || !window.Chart) {
            return chartRef;
        }

        const total = (state.chart.success_calls || 0) + (state.chart.failed_calls || 0);
        const success = state.chart.success_calls || 0;
        const failed = state.chart.failed_calls || 0;

        const data = {
            labels: [state.labels.success, state.labels.unsuccessful],
            datasets: [
                {
                    label: 'Calls',
                    data: [success, failed],
                    backgroundColor: ['#22c55e', '#ec4899'],
                    borderWidth: 0,
                },
            ],
        };

        const options = {
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom',
                    labels: {
                        color: '#cbd5e1',
                        usePointStyle: true,
                    },
                },
                tooltip: {
                    callbacks: {
                        label(context) {
                            const raw = context.raw || 0;
                            const pct = total ? ((raw / total) * 100).toFixed(1) : '0.0';
                            return `${context.label}: ${formatNumber(raw)} (${pct}%)`;
                        },
                    },
                },
            },
            cutout: '68%',
        };

        if (chartRef) {
            chartRef.data = data;
            chartRef.options = options;
            chartRef.update();
            return chartRef;
        }

        return new Chart(canvas.getContext('2d'), {
            type: 'doughnut',
            data,
            options,
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        const root = document.querySelector('[data-dashboard-root]');
        const dataScript = document.getElementById('dashboard-data');
        if (!root || !dataScript) {
            return;
        }

        let state = JSON.parse(dataScript.textContent);
        const endpoint = root.dataset.endpoint;
        const projectSelect = root.querySelector('[data-dashboard-project]');
        const topSummary = root.querySelector('[data-top-summary]');
        const selectedLabel = root.querySelector('[data-selected-label]');
        const successPercent = root.querySelector('[data-success-percent]');
        const failedPercent = root.querySelector('[data-failed-percent]');
        let chartRef = null;

        function render() {
            updateElements(root, '[data-total-calls]', formatNumber(state.summary.total_calls));
            updateElements(root, '[data-success-calls]', formatNumber(state.summary.success_calls));
            updateElements(root, '[data-failed-calls]', formatNumber(state.summary.failed_calls));
            updateElements(root, '[data-success-rate]', formatNumber(state.summary.success_rate));

            if (topSummary) {
                topSummary.textContent = state.top_summary;
            }
            if (selectedLabel) {
                selectedLabel.textContent = state.selected_label;
            }
            if (successPercent) {
                successPercent.textContent = `${state.chart.success_percentage}%`;
            }
            if (failedPercent) {
                failedPercent.textContent = `${state.chart.failed_percentage}%`;
            }

            chartRef = buildChart(root, chartRef, state);
        }

        async function fetchData(projectId) {
            if (!endpoint) return;
            const url = projectId ? `${endpoint}?project=${encodeURIComponent(projectId)}` : endpoint;
            try {
                const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                if (!response.ok) {
                    throw new Error(`Request failed with status ${response.status}`);
                }
                const data = await response.json();
                state = data;
                render();
            } catch (error) {
                console.error('Unable to load dashboard data', error);
            }
        }

        if (projectSelect) {
            projectSelect.addEventListener('change', (event) => {
                fetchData(event.target.value);
            });
        }

        render();
    });
})();
