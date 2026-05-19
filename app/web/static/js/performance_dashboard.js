(function() {
    const data = window.PROGRESS_DATA;
    if (!data || data.completed_count === 0) return;

    function formatPace(decimalPace) {
        if (!decimalPace || decimalPace <= 0) return '--';
        var m = Math.floor(decimalPace);
        var s = Math.round((decimalPace - m) * 60);
        if (s === 60) { m += 1; s = 0; }
        return m + ':' + (s < 10 ? '0' : '') + s;
    }

    const weekLabels = data.planned_weekly_km.map((_, i) => 'W' + (i + 1));

    // Weekly Mileage Bar Chart
    const mileageCtx = document.getElementById('weeklyMileageChart');
    if (mileageCtx) {
        new Chart(mileageCtx, {
            type: 'bar',
            data: {
                labels: weekLabels,
                datasets: [
                    {
                        label: 'Planned (km)',
                        data: data.planned_weekly_km,
                        backgroundColor: 'rgba(29, 78, 216, 0.25)',
                        borderColor: '#1D4ED8',
                        borderWidth: 1
                    },
                    {
                        label: 'Actual (km)',
                        data: data.actual_weekly_km,
                        backgroundColor: 'rgba(74, 222, 128, 0.5)',
                        borderColor: '#4ade80',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                aspectRatio: window.innerWidth < 768 ? 1.5 : 2,
                plugins: { legend: { position: 'top' }, title: { display: true, text: 'Weekly Mileage' } },
                scales: { y: { beginAtZero: true, title: { display: true, text: 'km' } } }
            }
        });
    }

    // Pace Trend Line Chart
    const paceCtx = document.getElementById('paceTrendChart');
    if (paceCtx && data.pace_by_week) {
        const paceWeeks = data.pace_by_week.map(p => p.week_label);
        const paceValues = data.pace_by_week.map(p => p.avg_pace);
        new Chart(paceCtx, {
            type: 'line',
            data: {
                labels: paceWeeks,
                datasets: [{
                    label: 'Avg Pace (min/km)',
                    data: paceValues,
                    borderColor: '#fb923c',
                    backgroundColor: 'rgba(251, 146, 60, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                aspectRatio: window.innerWidth < 768 ? 1.5 : 2,
                plugins: {
                    title: { display: true, text: 'Pace Trend' },
                    tooltip: {
                        callbacks: {
                            label: function(ctx) {
                                return 'Avg Pace: ' + formatPace(ctx.parsed.y) + '/km';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        reverse: true,
                        title: { display: true, text: 'min/km (lower is faster)' },
                        ticks: {
                            callback: function(value) {
                                return formatPace(value);
                            }
                        }
                    }
                }
            }
        });
    }

    // Completion Donut Chart
    const donutCtx = document.getElementById('completionDonutChart');
    if (donutCtx) {
        var missed = data.missed_count || 0;
        var remaining = Math.max(0, data.planned_count - data.completed_count - missed);
        var donutLabels = ['Completed'];
        var donutData = [data.completed_count];
        var donutColors = ['#4ade80'];
        if (missed > 0) {
            donutLabels.push('Missed');
            donutData.push(missed);
            donutColors.push('#f87171');
        }
        if (remaining > 0) {
            donutLabels.push('Remaining');
            donutData.push(remaining);
            donutColors.push('#e5e7eb');
        }
        new Chart(donutCtx, {
            type: 'doughnut',
            data: {
                labels: donutLabels,
                datasets: [{
                    data: donutData,
                    backgroundColor: donutColors
                }]
            },
            options: {
                responsive: true,
                aspectRatio: window.innerWidth < 768 ? 1 : 1.2,
                plugins: {
                    title: { display: true, text: 'Run Completion' },
                    legend: { position: 'bottom' }
                }
            }
        });
    }
})();
