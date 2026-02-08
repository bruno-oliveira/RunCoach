const Analytics = {
    uploads: [],
    selectedUploads: new Set(),
    storedAnalytics: [],

    init() {
        console.log('[Analytics] Initializing...');
        this.bindEvents();

        // Only load data if the analytics content exists (user is logged in)
        if (document.getElementById('uploadTab')) {
            this.loadUploads();
            this.loadStoredAnalytics();
        }
    },

    bindEvents() {
        console.log('[Analytics] bindEvents called');
        this.bindTabEvents();

        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const uploadBtn = document.getElementById('uploadBtn');
        const nameInput = document.getElementById('analyticsName');

        // Only bind upload events if elements exist (user is logged in)
        if (uploadArea && fileInput && uploadBtn && nameInput) {
            uploadArea.addEventListener('click', () => {
                console.log('[Analytics] Upload area clicked');
                fileInput.click();
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
                    const dataTransfer = new DataTransfer();
                    dataTransfer.items.add(file);
                    fileInput.files = dataTransfer.files;
                    uploadBtn.disabled = false;
                    uploadBtn.textContent = `Upload "${file.name}"`;
                    uploadArea.querySelector('p').innerHTML = `<strong>Selected:</strong> ${file.name}`;
                }
            });

            fileInput.addEventListener('change', (e) => {
                const file = e.target.files[0];
                console.log('[Analytics] File selected:', file?.name);
                if (file) {
                    uploadBtn.disabled = false;
                    uploadBtn.textContent = `Upload "${file.name}"`;
                    uploadArea.querySelector('p').innerHTML = `<strong>Selected:</strong> ${file.name}`;
                }
            });

            uploadBtn.addEventListener('click', () => {
                const file = fileInput.files[0];
                const name = nameInput.value.trim();
                console.log('[Analytics] Upload button clicked, file:', file?.name);
                if (file) {
                    this.uploadFile(file, name || undefined);
                }
            });
        }

        // Only bind if elements exist
        const compareBtn = document.getElementById('compareBtn');
        if (compareBtn) {
            compareBtn.addEventListener('click', () => {
                this.compareSelected();
            });
        }

        const backToListBtn = document.getElementById('backToList');
        if (backToListBtn) {
            backToListBtn.addEventListener('click', () => {
                this.showUploads();
            });
        }

        const backFromComparisonBtn = document.getElementById('backFromComparison');
        if (backFromComparisonBtn) {
            backFromComparisonBtn.addEventListener('click', () => {
                this.showUploads();
            });
        }
    },

    bindTabEvents() {
        const tabs = document.querySelectorAll('.tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                const tabId = tab.dataset.tab;
                document.querySelectorAll('.tab-content').forEach(content => {
                    content.classList.remove('active');
                });
                document.getElementById(tabId + 'Tab').classList.add('active');

                if (tabId === 'stored') {
                    this.loadStoredAnalytics();
                } else {
                    this.loadUploads();
                }
            });
        });
    },

        async uploadFile(file, name = null) {
        console.log('[Analytics] uploadFile called with file:', file?.name, 'name:', name);
        name = name || file.name.replace('.csv', '');
        const formData = new FormData();
        formData.append('file', file);

        const uploadBtn = document.getElementById('uploadBtn');
        const uploadArea = document.getElementById('uploadArea');
        uploadBtn.textContent = 'Uploading...';
        uploadBtn.disabled = true;

        try {
            const response = await fetch(`/api/analytics/upload?name=${encodeURIComponent(name)}`, {
                method: 'POST',
                body: formData
            });

            const contentType = response.headers.get('content-type');
            let errorText = 'Upload failed';
            
            if (!response.ok) {
                if (contentType && contentType.includes('application/json')) {
                    try {
                        const error = await response.json();
                        errorText = error.detail || error.message || 'Upload failed';
                    } catch (e) {
                        errorText = 'Upload failed - server returned an error';
                    }
                } else {
                    const text = await response.text();
                    errorText = text || 'Upload failed - server error';
                }
                throw new Error(errorText);
            }

            const uploadData = await response.json();
            console.log('[Analytics] Upload successful:', uploadData);
            document.getElementById('analyticsName').value = '';
            document.getElementById('fileInput').value = '';
            uploadBtn.textContent = 'Upload CSV';
            uploadBtn.disabled = true;
            uploadArea.querySelector('p').innerHTML = '<strong>Drag & drop</strong> your Strava activities.csv file here, or <strong>click to browse</strong>';

            this.showUploadSuccess(uploadData);

        } catch (error) {
            console.error('[Analytics] Upload failed:', error);
            alert(`Upload failed: ${error.message}`);
            uploadBtn.textContent = 'Upload CSV';
            uploadBtn.disabled = false;
            uploadArea.querySelector('p').innerHTML = '<strong>Drag & drop</strong> your Strava activities.csv file here, or <strong>click to browse</strong>';
        }
    },

    showUploadSuccess(uploadData) {
        this.uploads.unshift({
            id: uploadData.id,
            name: uploadData.name,
            upload_date: uploadData.upload_date,
            total_activities: uploadData.total_activities,
            summary: uploadData.summary
        });
        this.renderUploads();

        const uploadsSection = document.getElementById('uploadsSection');
        uploadsSection.scrollIntoView({ behavior: 'smooth' });

        const successMessage = document.createElement('div');
        successMessage.className = 'upload-success-message';
        successMessage.style.cssText = 'background: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center;';
        successMessage.innerHTML = `
            <span><strong>✓ Upload successful!</strong> "${uploadData.name}" has been added to your uploads.</span>
            <div style="display: flex; gap: 0.5rem;">
                <button class="action-btn view-btn" onclick="Analytics.viewAnalytics('${uploadData.id}')">View Analytics</button>
                <button class="action-btn" style="background: #6c757d; color: white;" onclick="this.parentElement.parentElement.remove()">Dismiss</button>
            </div>
        `;
        uploadsSection.insertBefore(successMessage, uploadsSection.querySelector('.comparison-controls') || uploadsSection.firstChild);

        setTimeout(() => {
            if (successMessage.parentElement) {
                successMessage.style.opacity = '0';
                successMessage.style.transition = 'opacity 0.3s';
                setTimeout(() => successMessage.remove(), 300);
            }
        }, 10000);
    },

    async loadStoredAnalytics() {
        try {
            const response = await fetch('/api/analytics');

            if (response.status === 401) {
                alert('You must be logged in to view analytics. Please sign in.');
                window.location.href = '/';
                return;
            }

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error (${response.status}): ${errorText}`);
            }

            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                const text = await response.text();
                throw new Error('Server returned non-JSON response');
            }

            let data;
            try {
                data = await response.json();
            } catch (e) {
                throw new Error(`Failed to parse JSON response: ${e.message}`);
            }

            this.storedAnalytics = data.uploads || [];
            this.renderStoredAnalytics();

        } catch (error) {
            console.error('Failed to load stored analytics:', error);
            const storedSubtitle = document.getElementById('storedSubtitle');
            if (storedSubtitle) {
                storedSubtitle.textContent = `Error: ${error.message}`;
            }
        }
    },

    renderStoredAnalytics() {
        const storedAnalyticsList = document.getElementById('storedAnalyticsList');
        const storedSubtitle = document.getElementById('storedSubtitle');

        if (!storedAnalyticsList || !storedSubtitle) {
            console.error('storedAnalyticsList or storedSubtitle element not found');
            return;
        }

        if (this.storedAnalytics.length === 0) {
            storedSubtitle.textContent = 'No analytics uploaded yet. Go to Upload & Compare to add your first analytics.';
            storedAnalyticsList.innerHTML = '<div class="empty-state">No analytics stored yet</div>';
            return;
        }

        storedSubtitle.textContent = `${this.storedAnalytics.length} analytics upload${this.storedAnalytics.length !== 1 ? 's' : ''} saved`;
        storedAnalyticsList.innerHTML = this.storedAnalytics.map(upload => `
            <div class="analytics-card" data-id="${upload.id}">
                <h3>${upload.name}</h3>
                <div class="date">📅 ${new Date(upload.upload_date).toLocaleDateString()}</div>
                <div class="stats">
                    <span class="stat">🏃 ${upload.total_activities} activities</span>
                    ${upload.summary?.total_distance_km ? `<span class="stat">📍 ${upload.summary.total_distance_km.toFixed(1)} km</span>` : ''}
                </div>
                <div class="actions">
                    <button class="action-btn view-btn" onclick="Analytics.viewStoredAnalytics('${upload.id}')">View Charts</button>
                    <button class="action-btn delete-btn" onclick="Analytics.deleteAnalytics('${upload.id}')">Delete</button>
                </div>
            </div>
        `).join('');
    },

    async viewStoredAnalytics(id) {
        // Navigate to dedicated analytics detail page
        window.location.href = `/analytics/${id}`;
    },

    async loadUploads() {
        try {
            const response = await fetch('/api/analytics');

            if (response.status === 401) {
                alert('You must be logged in to view analytics. Please sign in.');
                window.location.href = '/';
                return;
            }

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error (${response.status}): ${errorText}`);
            }

            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                const text = await response.text();
                throw new Error('Server returned non-JSON response');
            }

            let data;
            try {
                data = await response.json();
            } catch (e) {
                throw new Error(`Failed to parse JSON response: ${e.message}`);
            }

            this.uploads = data.uploads || [];
            this.renderUploads();

        } catch (error) {
            console.error('Failed to load uploads:', error);
            const uploadsSection = document.getElementById('uploadsSection');
            if (uploadsSection) {
                uploadsSection.innerHTML = `
                    <div style="padding: 2rem;">
                        <h2 style="color: #dc3545;">Error Loading Uploads</h2>
                        <p style="color: #666;">${error.message}</p>
                        <button onclick="window.location.reload()" style="padding: 0.5rem 1rem; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer;">
                            Refresh Page
                        </button>
                    </div>
                `;
            } else {
                console.error('uploadsSection element not found');
            }
        }
    },

    renderUploads() {
        const uploadsSection = document.getElementById('uploadsSection');
        const analyticsList = document.getElementById('analyticsList');

        if (!uploadsSection || !analyticsList) {
            console.error('uploadsSection or analyticsList element not found');
            return;
        }

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
                    <button class="action-btn view-btn" onclick="Analytics.viewAnalytics('${upload.id}')">View Charts</button>
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
        if (!compareBtn) return;

        const count = this.selectedUploads.size;
        compareBtn.disabled = count < 2 || count > 5;
        compareBtn.textContent = count >= 2
            ? `Compare Selected (${count})`
            : 'Compare Selected (2-5)';
    },

    async viewAnalytics(id) {
        // Navigate to dedicated analytics detail page
        window.location.href = `/analytics/${id}`;
    },





    async compareSelected() {
        const ids = Array.from(this.selectedUploads);
        if (ids.length < 2) return;

        const comparisonSection = document.getElementById('comparisonSection');
        const uploadsSection = document.getElementById('uploadsSection');

        if (!comparisonSection) {
            console.error('comparisonSection element not found');
            return;
        }

        comparisonSection.innerHTML = '<div class="loading"><div class="spinner"></div>Generating comparison...</div>';
        comparisonSection.style.display = 'block';
        if (uploadsSection) uploadsSection.style.display = 'none';

        try {
            const response = await fetch(`/api/analytics/compare?${ids.map(id => `analytics_ids=${id}`).join('&')}`);

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error (${response.status}): ${errorText}`);
            }

            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                const text = await response.text();
                throw new Error('Server returned non-JSON response');
            }

            let data;
            try {
                data = await response.json();
            } catch (e) {
                throw new Error(`Failed to parse JSON response: ${e.message}`);
            }

            comparisonSection.innerHTML = `
                <h2 class="section-title">Side-by-Side Comparison</h2>
                <button style="padding: 0.5rem 1rem; background: #666; color: white; border: none; border-radius: 6px; cursor: pointer; margin-bottom: 1rem;" id="backFromComparison">← Back to Uploads</button>
                <div class="chart-section">
                    <h3>Comparison Overview</h3>
                    <img id="comparisonChart" class="chart" src="data:image/png;base64,${data.comparison.comparison_chart}" alt="Comparison Chart">
                </div>
            `;

            const backBtn = document.getElementById('backFromComparison');
            if (backBtn) {
                backBtn.addEventListener('click', () => {
                    this.showUploads();
                });
            }

        } catch (error) {
            console.error('Comparison failed:', error);
            comparisonSection.innerHTML = `
                <div style="padding: 2rem;">
                    <h2 style="color: #dc3545;">Comparison Failed</h2>
                    <p style="color: #666;">${error.message}</p>
                    <button onclick="Analytics.showUploads()" style="padding: 0.5rem 1rem; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer;">
                        ← Back to Uploads
                    </button>
                </div>
            `;
        }
    },

    async deleteAnalytics(id) {
        if (!confirm('Are you sure you want to delete this analytics upload?')) return;

        try {
            const response = await fetch(`/api/analytics/${id}`, { method: 'DELETE' });

            if (!response.ok && response.status !== 204) {
                const errorText = await response.text();
                throw new Error(`Server error (${response.status}): ${errorText}`);
            }

            this.selectedUploads.delete(id);
            await this.loadUploads();
        } catch (error) {
            console.error('Failed to delete analytics:', error);
            alert(`Failed to delete analytics: ${error.message}`);
        }
    },

    showUploads() {
        const uploadsSection = document.getElementById('uploadsSection');
        const chartsSection = document.getElementById('chartsSection');
        const comparisonSection = document.getElementById('comparisonSection');

        if (chartsSection) chartsSection.style.display = 'none';
        if (comparisonSection) comparisonSection.style.display = 'none';
        if (uploadsSection) uploadsSection.style.display = 'block';
    }
};

// Make Analytics globally accessible for inline event handlers
window.Analytics = Analytics;

document.addEventListener('DOMContentLoaded', () => {
    Analytics.init();
});