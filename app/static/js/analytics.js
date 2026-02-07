const Analytics = {
    uploads: [],
    selectedUploads: new Set(),

    init() {
        this.bindEvents();
        this.loadUploads();
    },

    bindEvents() {
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const uploadBtn = document.getElementById('uploadBtn');
        const nameInput = document.getElementById('analyticsName');

        uploadArea.addEventListener('click', (e) => {
            if (e.target !== fileInput) {
                fileInput.click();
            }
        });
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file && file.name.endsWith('.csv')) {
                this.handleFile(file);
            }
        });

        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                uploadBtn.disabled = false;
            }
        });

        uploadBtn.addEventListener('click', () => {
            const file = fileInput.files[0];
            const name = nameInput.value.trim();
            if (file) {
                this.handleFile(file, name || undefined);
            }
        });

        document.getElementById('compareBtn').addEventListener('click', () => {
            this.compareSelected();
        });

        document.getElementById('backToList').addEventListener('click', () => {
            this.showUploads();
        });

        document.getElementById('backFromComparison').addEventListener('click', () => {
            this.showUploads();
        });
    },

    async handleFile(file, name = null) {
        name = name || file.name.replace('.csv', '');
        const formData = new FormData();
        formData.append('file', file);
        formData.append('name', name);

        const uploadBtn = document.getElementById('uploadBtn');
        uploadBtn.textContent = 'Uploading...';
        uploadBtn.disabled = true;

        try {
            const response = await fetch(`/api/analytics/upload?name=${encodeURIComponent(name)}`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }

            await this.loadUploads();
            document.getElementById('analyticsName').value = '';
            document.getElementById('fileInput').value = '';
            uploadBtn.textContent = 'Upload CSV';
            uploadBtn.disabled = true;

        } catch (error) {
            alert(`Upload failed: ${error.message}`);
            uploadBtn.textContent = 'Upload CSV';
            uploadBtn.disabled = false;
        }
    },

    async loadUploads() {
        try {
            const response = await fetch('/api/analytics');
            if (response.status === 401) {
                alert('You must be logged in to view analytics. Please sign in.');
                window.location.href = '/';
                return;
            }
            const data = await response.json();
            this.uploads = data.uploads || [];
            this.renderUploads();
        } catch (error) {
            console.error('Failed to load uploads:', error);
        }
    },

    renderUploads() {
        const uploadsSection = document.getElementById('uploadsSection');
        const analyticsList = document.getElementById('analyticsList');

        if (this.uploads.length === 0) {
            uploadsSection.style.display = 'none';
            return;
        }

        uploadsSection.style.display = 'block';
        analyticsList.innerHTML = this.uploads.map(upload => `
            <div class="analytics-card ${this.selectedUploads.has(upload.id) ? 'selected' : ''}" 
                 data-id="${upload.id}">
                <h3>${upload.name}</h3>
                <div class="date">📅 ${new Date(upload.upload_date).toLocaleDateString()}</div>
                <div class="stats">
                    <span class="stat">🏃 ${upload.total_activities} activities</span>
                    ${upload.summary?.total_distance_km ? `<span class="stat">📍 ${upload.summary.total_distance_km.toFixed(1)} km</span>` : ''}
                </div>
                <div class="actions">
                    <button class="action-btn view-btn" onclick="Analytics.viewAnalytics('${upload.id}')">View</button>
                    <button class="action-btn delete-btn" onclick="Analytics.deleteAnalytics('${upload.id}')">Delete</button>
                </div>
            </div>
        `).join('');

        this.attachCardListeners();
        this.updateCompareButton();
    },

    attachCardListeners() {
        document.querySelectorAll('.analytics-card').forEach(card => {
            card.addEventListener('click', (e) => {
                if (!e.target.classList.contains('view-btn') && !e.target.classList.contains('delete-btn')) {
                    const id = card.dataset.id;
                    if (this.selectedUploads.has(id)) {
                        this.selectedUploads.delete(id);
                    } else {
                        if (this.selectedUploads.size < 5) {
                            this.selectedUploads.add(id);
                        }
                    }
                    this.renderUploads();
                }
            });
        });
    },

    updateCompareButton() {
        const compareBtn = document.getElementById('compareBtn');
        const count = this.selectedUploads.size;
        compareBtn.disabled = count < 2 || count > 5;
        compareBtn.textContent = count >= 2 
            ? `Compare Selected (${count})` 
            : 'Compare Selected (2-5)';
    },

    async viewAnalytics(id) {
        const uploadsSection = document.getElementById('uploadsSection');
        const chartsSection = document.getElementById('chartsSection');
        
        chartsSection.querySelector('.loading')?.style.display === 'block' ||
        (chartsSection.innerHTML = '<div class="loading"><div class="spinner"></div>Loading analytics...</div>');
        chartsSection.style.display = 'block';
        uploadsSection.style.display = 'none';

        try {
            const response = await fetch(`/api/analytics/${id}`);
            const data = await response.json();

            document.getElementById('chartsTitle').textContent = data.name;
            document.getElementById('chartsSubtitle').textContent = `${data.total_activities} activities • Uploaded ${new Date(data.upload_date).toLocaleDateString()}`;

            this.renderCharts(data);
        } catch (error) {
            console.error('Failed to load analytics:', error);
            this.showUploads();
        }
    },

    renderCharts(data) {
        const container = document.getElementById('chartsContainer');
        const analytics = data.analytics;

        if (analytics.error) {
            container.innerHTML = `<div class="empty-state">${analytics.error}</div>`;
            return;
        }

        container.innerHTML = '';

        if (analytics.pace_trends?.chart) {
            container.innerHTML += `
                <div class="chart-section">
                    <h3>🏃 Pace Trends</h3>
                    <img class="chart" src="data:image/png;base64,${analytics.pace_trends.chart}" alt="Pace Trends">
                    <div class="summary">
                        <div class="summary-line">
                            <span>Average Pace:</span>
                            <span class="summary-value">${analytics.pace_trends.avg_pace_formatted}</span>
                        </div>
                        <div class="summary-line">
                            <span>Trend:</span>
                            <span class="summary-value">${analytics.pace_trends.trend_description}</span>
                        </div>
                    </div>
                </div>
            `;
        }

        if (analytics.distance_trends?.chart) {
            container.innerHTML += `
                <div class="chart-section">
                    <h3>📍 Distance Trends</h3>
                    <img class="chart" src="data:image/png;base64,${analytics.distance_trends.chart}" alt="Distance Trends">
                    <div class="summary">
                        <div class="summary-line">
                            <span>Average Distance per Run:</span>
                            <span class="summary-value">${analytics.distance_trends.avg_distance_km.toFixed(2)} km</span>
                        </div>
                        <div class="summary-line">
                            <span>Longest Run:</span>
                            <span class="summary-value">${analytics.distance_trends.max_distance_km.toFixed(2)} km</span>
                        </div>
                    </div>
                </div>
            `;
        }

        if (analytics.hr_zones?.chart) {
            container.innerHTML += `
                <div class="chart-section">
                    <h3>❤️ Heart Rate Zones</h3>
                    <img class="chart" src="data:image/png;base64,${analytics.hr_zones.chart}" alt="HR Zones">
                    <div class="summary">
                        <div class="summary-line">
                            <span>Average Heart Rate:</span>
                            <span class="summary-value">${analytics.hr_zones.avg_heart_rate.toFixed(0)} bpm</span>
                        </div>
                        <div class="summary-line">
                            <span>Dominant Zone:</span>
                            <span class="summary-value">${analytics.hr_zones.dominant_zone || 'N/A'}</span>
                        </div>
                    </div>
                </div>
            `;
        }

        if (analytics.hr_evolution?.chart) {
            container.innerHTML += `
                <div class="chart-section">
                    <h3>📈 Heart Rate Evolution</h3>
                    <img class="chart" src="data:image/png;base64,${analytics.hr_evolution.chart}" alt="HR Evolution">
                    <div class="summary">
                        <div class="summary-line">
                            <span>Trend:</span>
                            <span class="summary-value">${analytics.hr_evolution.overall_trend === 'improving' ? '🟢 Improving' : '🔴 Declining'}</span>
                        </div>
                        <div class="summary-line">
                            <span>${analytics.hr_evolution.trend_description}</span>
                        </div>
                    </div>
                </div>
            `;
        }

        if (analytics.weekly_volume?.chart) {
            container.innerHTML += `
                <div class="chart-section">
                    <h3>📅 Weekly Volume</h3>
                    <img class="chart" src="data:image/png;base64,${analytics.weekly_volume.chart}" alt="Weekly Volume">
                </div>
            `;
        }
    },

    async compareSelected() {
        const ids = Array.from(this.selectedUploads);
        if (ids.length < 2) return;

        const comparisonSection = document.getElementById('comparisonSection');
        const uploadsSection = document.getElementById('uploadsSection');

        comparisonSection.innerHTML = '<div class="loading"><div class="spinner"></div>Generating comparison...</div>';
        comparisonSection.style.display = 'block';
        uploadsSection.style.display = 'none';

        try {
            const response = await fetch(`/api/analytics/compare?${ids.map(id => `analytics_ids=${id}`).join('&')}`);
            const data = await response.json();

            comparisonSection.innerHTML = `
                <h2 class="section-title">Side-by-Side Comparison</h2>
                <button style="padding: 0.5rem 1rem; background: #666; color: white; border: none; border-radius: 6px; cursor: pointer; margin-bottom: 1rem;" id="backFromComparison">← Back to Uploads</button>
                <div class="chart-section">
                    <h3>Comparison Overview</h3>
                    <img id="comparisonChart" class="chart" src="data:image/png;base64,${data.comparison.comparison_chart}" alt="Comparison Chart">
                </div>
            `;

            document.getElementById('backFromComparison').addEventListener('click', () => {
                this.showUploads();
            });

        } catch (error) {
            console.error('Comparison failed:', error);
            this.showUploads();
        }
    },

    async deleteAnalytics(id) {
        if (!confirm('Are you sure you want to delete this analytics upload?')) return;

        try {
            await fetch(`/api/analytics/${id}`, { method: 'DELETE' });
            this.selectedUploads.delete(id);
            await this.loadUploads();
        } catch (error) {
            alert('Failed to delete analytics');
        }
    },

    showUploads() {
        document.getElementById('uploadsSection').style.display = 'none';
        document.getElementById('chartsSection').style.display = 'none';
        document.getElementById('comparisonSection').style.display = 'none';
        document.getElementById('uploadsSection').style.display = 'block';
    }
};

document.addEventListener('DOMContentLoaded', () => {
    Analytics.init();
});