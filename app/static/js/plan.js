/**
 * Training Plan Page JavaScript
 * Extracted from plan.html
 *
 * Global functions are exposed via window for HTML onclick handlers.
 * Initialization code runs after DOMContentLoaded.
 */

function escapeHtml(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

let currentWeek = 1;
let currentWorkoutId = null;

/**
 * Build fetch headers including Authorization only when a real token exists.
 * The app uses httponly cookies as the primary auth mechanism; localStorage
 * may not hold a token at all. Sending "Bearer null" breaks cookie fallback.
 */
function authHeaders(extra) {
    const headers = Object.assign({}, extra);
    const token = localStorage.getItem('access_token');
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
}

// Global functions called from HTML
window.adjustIntensity = function(intensity) {
    submitCustomization('intensity', intensity);
};

window.adjustDistance = function(change) {
    submitCustomization('distance', change);
};

window.applyAISuggestion = function(suggestion) {
    submitCustomization('ai_suggest', suggestion);
};

window.swapWorkout = function(swapInfo) {
    submitCustomization('workout_swap', swapInfo);
};

window.resetCustomization = function() {
    if (confirm('Are you sure you want to reset to the original plan? This will undo all customizations.')) {
        submitCustomization('reset', 'original');
    }
};

function submitCustomization(type, value) {
    // Show loading state
    const cards = document.querySelectorAll('.action-card');
    cards.forEach(card => {
        if (card && card.style) {
            card.style.opacity = '0.6';
            card.style.cursor = 'not-allowed';
        }
    });
    
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/customize-plan';
    
    // Add hidden fields - use APP_CTX data
    const fields = [
        { name: 'plan_id', value: window.APP_CTX.plan_id },
        { name: 'week_number', value: currentWeek },
        { name: 'adjustment_type', value: type },
        { name: 'adjustment_value', value: value }
    ];
    
    fields.forEach(field => {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = field.name;
        input.value = field.value;
        form.appendChild(input);
    });
    
    document.body.appendChild(form);
    form.submit();
}

window.updateCustomizationWeek = function() {
    const select = document.getElementById('weekSelect');
    if (!select) return;
    currentWeek = parseInt(select.value);
    
    // Update week display
    const display = document.getElementById('currentWeekDisplay');
    if (display) {
        display.textContent = currentWeek;
    }
    
    // Add visual feedback
    const section = document.querySelector('.customization-section');
    if (section) {
        section.style.animation = 'none';
        setTimeout(() => {
            section.style.animation = 'fadeIn 0.3s ease';
        }, 10);
    }
};

window.randomizeMeals = function() {
    // Show loading state
    const btn = document.querySelector('.randomize-meals-btn');
    if (!btn) {
        return;
    }
    
    const originalText = btn.innerHTML;
    btn.innerHTML = '🎲 Generating New Meals...';
    btn.disabled = true;
    if (btn.style) {
        btn.style.background = 'linear-gradient(135deg, #f39c12, #e67e22)';
        btn.style.transform = 'scale(0.95)';
    }
    
    // Add enhanced visual feedback to meal section
    const nutritionSection = document.querySelector('.nutrition-section');
    const mealCards = document.querySelectorAll('.meal-option-card');
    
    if (nutritionSection && nutritionSection.style) {
        nutritionSection.style.opacity = '0.7';
        nutritionSection.style.transition = 'opacity 0.3s ease';
        nutritionSection.style.transform = 'scale(0.98)';
        nutritionSection.style.transition = 'all 0.3s ease';
    }
    
    // Add loading animation to meal cards
    mealCards.forEach((card, index) => {
        setTimeout(() => {
            if (card && card.style) {
                card.style.opacity = '0.5';
                card.style.transform = 'scale(0.95)';
                card.style.transition = 'all 0.3s ease';
            }
        }, index * 50);
    });
    
    // Create and submit form
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/randomize-meals';
    
    const fields = [
        { name: 'plan_id', value: window.APP_CTX.plan_id }
    ];
    
    fields.forEach(field => {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = field.name;
        input.value = field.value;
        form.appendChild(input);
    });
    
    document.body.appendChild(form);
    
    // Small delay to show loading state
    setTimeout(() => {
        form.submit();
    }, 300);
};

function initScrollToTop() {
    const scrollButton = document.querySelector('.scroll-to-top');
    
    if (scrollButton) {
        window.addEventListener('scroll', function() {
            if (window.pageYOffset > 300) {
                scrollButton.classList.add('visible');
            } else {
                scrollButton.classList.remove('visible');
            }
        });
    }
}

window.scrollToTop = function() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
};

window.openLogModal = function(workoutId, workoutType, distance, dayName, weekNum) {
    currentWorkoutId = workoutId;
    const modalTitle = document.getElementById('modal-title');
    const workoutTypeSelect = document.getElementById('workout_type');
    const distanceInput = document.getElementById('distance_km');

    if (modalTitle) modalTitle.textContent = `Log Run - Week ${weekNum} ${dayName} (${workoutType})`;
    if (workoutTypeSelect) workoutTypeSelect.value = workoutType;
    if (distanceInput) distanceInput.value = distance;

    ModalManager.openModal('logRunModal');
};

window.closeLogModal = function() {
    ModalManager.closeModal('logRunModal');
    const form = document.getElementById('logRunForm');
    if (form) {
        form.reset();
    }
    currentWorkoutId = null;
};

window.submitRunLog = async function(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    
    const submitBtn = document.querySelector('#logRunForm .submit-btn');
    
    // Validate required fields
    const distanceInput = document.getElementById('distance_km');
    const durationInput = document.getElementById('duration_minutes');
    
    if (!distanceInput || !durationInput) {
        ApiClient.showError('Required form fields not found.');
        return;
    }
    
    const distance = parseFloat(distanceInput.value);
    const duration = parseFloat(durationInput.value);
    
    if (isNaN(distance) || distance <= 0) {
        ApiClient.showWarning('Please enter a valid distance.');
        if (distanceInput) {
            distanceInput.focus();
            distanceInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
    }
    
    if (isNaN(duration) || duration <= 0) {
        ApiClient.showWarning('Please enter a valid duration.');
        if (durationInput) {
            durationInput.focus();
            durationInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
    }
    
    if (!window.APP_CTX || !window.APP_CTX.training_plan_id) {
        ApiClient.showError('Plan context not loaded. Please refresh the page.');
        return;
    }
    
    if (!currentWorkoutId) {
        ApiClient.showError('Workout not selected. Please try again.');
        return;
    }
    
    // Show loading state
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Logging...';
        submitBtn.style.opacity = '0.7';
    }
    
    const formData = {
        training_plan_id: window.APP_CTX.training_plan_id,
        daily_workout_id: currentWorkoutId,
        distance_km: distance,
        duration_minutes: duration,
        workout_type: document.getElementById('workout_type').value || 'easy',
        perceived_effort: parseInt(document.getElementById('perceived_effort').value) || null,
        avg_heart_rate: parseInt(document.getElementById('avg_heart_rate').value) || null,
        max_heart_rate: parseInt(document.getElementById('max_heart_rate').value) || null,
        avg_cadence: parseInt(document.getElementById('avg_cadence').value) || null,
        elevation_gain_m: parseInt(document.getElementById('elevation_gain_m').value) || null,
        notes: document.getElementById('notes').value || null,
        date: new Date().toISOString()
    };
    
    try {
        const response = await fetch('/api/runs', {
            method: 'POST',
            headers: authHeaders({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify(formData)
        });
        
        if (response.ok) {
            const data = await response.json();
            closeLogModal();

            // Show race comparison toast if this was a race with prediction data
            if (data.race_comparison) {
                showRaceComparisonToast(data);
                setTimeout(() => location.reload(), 8000);
            } else if (data.predictions) {
                // Show predictions toast if VDOT was calculated
                showRacePredictionsToast(data);
                setTimeout(() => location.reload(), 6000);
            } else {
                ApiClient.showSuccess('Run logged successfully!');
                setTimeout(() => location.reload(), 1500);
            }
        } else {
            const error = await response.json();
            ApiClient.showError('Error logging run: ' + (error.detail || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error logging run:', error);
        ApiClient.showError('Error logging run: ' + error.message);
    } finally {
        // Reset button state
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Log Run';
            submitBtn.style.opacity = '1';
        }
    }
};

window.showRacePredictionsToast = function(data) {
    const toastId = 'race-predictions-toast';
    let toast = document.getElementById(toastId);
    
    if (toast) {
        toast.remove();
    }
    
    toast = document.createElement('div');
    toast.id = toastId;
    toast.className = 'race-predictions-toast';
    
    const predictions = data.predictions || {};
    const distanceLabels = {
        '5K': '5K',
        '10K': '10K',
        'trail': 'Trail',
        'half_marathon': 'Half',
        'marathon': 'Full'
    };
    
    let predictionsHtml = '';
    for (const [key, pred] of Object.entries(predictions)) {
        const label = distanceLabels[key] || key;
        predictionsHtml += `<span class="toast-prediction"><strong>${escapeHtml(label)}:</strong> ${escapeHtml(pred.formatted)}</span>`;
    }

    toast.innerHTML = `
        <div class="toast-icon">🎯</div>
        <div class="toast-content">
            <div class="toast-title">Run logged! Based on your performance:</div>
            <div class="toast-predictions">${predictionsHtml}</div>
        </div>
        <div class="toast-actions">
            <button class="toast-btn toast-btn-secondary" onclick="dismissRaceToast()">Dismiss</button>
            <a href="/analytics" class="toast-btn toast-btn-primary">View</a>
        </div>
        <button class="toast-close" onclick="dismissRaceToast()">&times;</button>
    `;
    
    document.body.appendChild(toast);
    
    // Store in sessionStorage to prevent showing again in same session
    try {
        const dismissed = JSON.parse(sessionStorage.getItem('race_toast_dismissed') || '[]');
        const key = `race_${data.id || Date.now()}`;
        if (!dismissed.includes(key)) {
            sessionStorage.setItem('race_toast_dismissed', JSON.stringify([...dismissed, key]));
        }
    } catch (e) {}
    
    // Auto dismiss after 6 seconds
    setTimeout(() => {
        if (document.getElementById(toastId)) {
            dismissRaceToast();
        }
    }, 6000);
};

window.dismissRaceToast = function() {
    const toast = document.getElementById('race-predictions-toast');
    if (toast) {
        toast.classList.add('toast-fade-out');
        setTimeout(() => toast.remove(), 300);
    }
};

window.showRaceComparisonToast = function(data) {
    const toastId = 'race-predictions-toast';
    let toast = document.getElementById(toastId);
    if (toast) toast.remove();

    toast = document.createElement('div');
    toast.id = toastId;
    toast.className = 'race-predictions-toast race-comparison-toast';

    const comp = data.race_comparison;
    const isFaster = comp.faster_than_predicted;
    const icon = isFaster ? '🎉' : '🏁';
    const verdictClass = isFaster ? 'comparison-faster' : 'comparison-slower';
    const verdictText = isFaster
        ? `${escapeHtml(comp.delta_formatted)} faster than predicted!`
        : `${escapeHtml(comp.delta_formatted)} slower than predicted`;

    // Also show all-distance predictions if available
    let predictionsHtml = '';
    if (data.predictions) {
        const distanceLabels = { '5K': '5K', '10K': '10K', 'trail': 'Trail', 'half_marathon': 'Half', 'marathon': 'Full' };
        for (const [key, pred] of Object.entries(data.predictions)) {
            const label = distanceLabels[key] || key;
            predictionsHtml += `<span class="toast-prediction"><strong>${escapeHtml(label)}:</strong> ${escapeHtml(pred.formatted)}</span>`;
        }
    }

    toast.innerHTML = `
        <div class="toast-icon">${icon}</div>
        <div class="toast-content">
            <div class="toast-title">Race logged!</div>
            <div class="toast-comparison">
                <div class="toast-comparison-row">
                    <span class="toast-comparison-label">Predicted</span>
                    <span class="toast-comparison-value">${escapeHtml(comp.predicted_formatted)}</span>
                </div>
                <div class="toast-comparison-row">
                    <span class="toast-comparison-label">Actual</span>
                    <span class="toast-comparison-value toast-comparison-actual">${escapeHtml(comp.actual_formatted)}</span>
                </div>
                <div class="toast-comparison-verdict ${verdictClass}">${verdictText}</div>
            </div>
            ${predictionsHtml ? `<div class="toast-predictions">${predictionsHtml}</div>` : ''}
        </div>
        <div class="toast-actions">
            <button class="toast-btn toast-btn-secondary" onclick="dismissRaceToast()">Dismiss</button>
            <a href="/analytics" class="toast-btn toast-btn-primary">View Analytics</a>
        </div>
        <button class="toast-close" onclick="dismissRaceToast()">&times;</button>
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        if (document.getElementById(toastId)) {
            dismissRaceToast();
        }
    }, 8000);
};

window.unlinkRun = async function(runId) {
    if (!confirm('Remove this logged run?')) return;
    try {
        const response = await fetch(`/api/runs/${runId}`, {
            method: 'DELETE',
            headers: authHeaders(),
            credentials: 'same-origin'
        });
        if (response.ok) {
            ApiClient.showSuccess('Run removed.');
            setTimeout(() => location.reload(), 800);
        } else {
            ApiClient.showError('Could not remove run.');
        }
    } catch (err) {
        ApiClient.showError('Error: ' + err.message);
    }
};

// Save plan to user account
window.savePlanToAccount = async function() {
    const btn = document.getElementById('save-plan-btn');
    if (!btn) return;
    
    const originalText = btn.innerHTML;

    btn.innerHTML = '💾 Saving...';
    btn.disabled = true;

    try {
        const response = await fetch(`/api/plan/${window.APP_CTX.plan_id}/save`, {
            method: 'POST',
            headers: authHeaders(),
            credentials: 'same-origin'
        });

        if (response.ok) {
            btn.innerHTML = '✓ Saved!';
            if (btn.style) btn.style.background = '#48bb78';

            // Replace button with link to My Plans after short delay
            setTimeout(() => {
                btn.outerHTML = '<a href="/my-plans" class="btn btn-secondary">📋 View My Plans</a>';
            }, 1500);
        } else if (response.status === 401) {
            ApiClient.showWarning('Please sign in to save this plan to your account.');
            btn.innerHTML = originalText;
            btn.disabled = false;
        } else {
            const error = await response.json();
            ApiClient.showError('Error saving plan: ' + (error.detail || 'Unknown error'));
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    } catch (error) {
        ApiClient.showError('Error saving plan: ' + error.message);
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
};

// Check if user is logged in and show appropriate save/view button.
// Uses server-rendered APP_CTX (current_user_id, plan_user_id) so that
// the decision is based on the actual session, not stale localStorage.
function initSaveButton() {
    const saveBtn = document.getElementById('save-plan-btn');
    const viewLink = document.getElementById('view-plans-link');

    if (!saveBtn || !viewLink) return;

    const ctx = window.APP_CTX;
    if (!ctx) return;

    const currentUserId = ctx.current_user_id;
    const planUserId = ctx.plan_user_id;

    if (currentUserId) {
        if (currentUserId !== planUserId) {
            // Logged in, but plan belongs to someone else (or no one) — offer save
            if (saveBtn.style) saveBtn.style.display = 'inline-flex';
        } else {
            // Plan already belongs to the current user — show view link
            if (viewLink.style) viewLink.style.display = 'inline-flex';
        }
    }
    // If not logged in (currentUserId is null), neither button shows (default hidden state)
}

function showAdaptationBanner(reason) {
    const banner = document.getElementById('adaptation-banner');
    const reasonText = document.getElementById('adaptation-reason');

    if (reasonText) reasonText.textContent = reason || 'Based on your synced runs, we recommend adjusting your plan.';
    if (banner && banner.style) {
        banner.style.display = 'block';
        banner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function dismissAdaptationBanner() {
    const banner = document.getElementById('adaptation-banner');
    if (banner && banner.style) banner.style.display = 'none';
}

function viewAdaptationDetails() {
    const perfSection = document.querySelector('.plan-insights');
    if (perfSection) {
        perfSection.scrollIntoView({ behavior: 'smooth' });
    }
    dismissAdaptationBanner();
}

// ------------------------------------------------------------------
// Plan adjustment (unified — replaces map-runs + recalibrate)
// ------------------------------------------------------------------

window.adjustPlan = async function() {
    const confirmed = window.confirm(
        'This will adjust future week distances based on your recent running data.\n\n' +
        'Past weeks will not be changed.\n\nContinue?'
    );
    if (!confirmed) return;

    const btn = document.getElementById('adjust-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Adjusting...'; }

    try {
        const response = await fetch(`/api/plan/${window.APP_CTX.plan_id}/adjust`, {
            method: 'POST',
            headers: authHeaders(),
            credentials: 'same-origin',
        });

        if (response.ok) {
            const result = await response.json();
            if (result.adjusted) {
                let msg = `Plan adjusted!\n\n${result.reason}`;
                msg += `\n\n${result.weeks_changed} week(s) updated (x${result.multiplier}).`;
                if (result.raw_multiplier != null) {
                    msg += `\n\nSignals: volume=${result.volume_ratio}, effort=${result.effort_factor}, completion=${result.completion_rate} (${result.total_runs} runs)`;
                }
                ApiClient.showSuccess(msg);
                setTimeout(() => location.reload(), 2500);
            } else {
                ApiClient.showInfo(result.reason || 'No adjustment needed.');
                if (btn) { btn.disabled = false; btn.textContent = 'Adjust Plan'; }
            }
        } else {
            const err = await response.json();
            ApiClient.showError(err.detail || 'Adjustment failed.');
            if (btn) { btn.disabled = false; btn.textContent = 'Adjust Plan'; }
        }
    } catch (error) {
        ApiClient.showError('Error: ' + error.message);
        if (btn) { btn.disabled = false; btn.textContent = 'Adjust Plan'; }
    }
};

// Reset adjustment — restore original baseline distances
window.resetAdjustment = async function() {
    const confirmed = window.confirm(
        'This will reset all adjusted distances back to the original plan.\n\nContinue?'
    );
    if (!confirmed) return;

    const btn = document.getElementById('reset-adjust-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Resetting...'; }

    try {
        const response = await fetch(`/api/plan/${window.APP_CTX.plan_id}/reset-adjustment`, {
            method: 'POST',
            headers: authHeaders(),
            credentials: 'same-origin',
        });

        if (response.ok) {
            const result = await response.json();
            if (result.reset) {
                ApiClient.showSuccess('Plan restored to original distances.');
                setTimeout(() => location.reload(), 1500);
            } else {
                ApiClient.showInfo(result.reason || 'No adjustment to reset.');
                if (btn) { btn.disabled = false; btn.textContent = 'Reset to original'; }
            }
        } else {
            const err = await response.json();
            ApiClient.showError(err.detail || 'Reset failed.');
            if (btn) { btn.disabled = false; btn.textContent = 'Reset to original'; }
        }
    } catch (error) {
        ApiClient.showError('Error: ' + error.message);
        if (btn) { btn.disabled = false; btn.textContent = 'Reset to original'; }
    }
};

// Set plan start date
window.startPlan = async function() {
    const dateInput = document.getElementById('plan-start-date');
    if (!dateInput || !dateInput.value) {
        ApiClient.showWarning('Please select a start date.');
        return;
    }

    try {
        const response = await fetch(`/api/plan/${window.APP_CTX.plan_id}/start`, {
            method: 'POST',
            headers: authHeaders({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({ start_date: dateInput.value })
        });

        if (response.ok) {
            ApiClient.showSuccess('Plan started! Reloading...');
            setTimeout(() => location.reload(), 800);
        } else {
            const error = await response.json();
            ApiClient.showError('Error: ' + (error.detail || 'Could not set start date'));
        }
    } catch (error) {
        ApiClient.showError('Error setting start date: ' + error.message);
    }
};

// Plan tab switching
window.switchPlanTab = function(tabName) {
    document.querySelectorAll('.plan-tab').forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
        t.setAttribute('tabindex', '-1');
    });
    document.querySelectorAll('.plan-tab-panel').forEach(p => p.classList.remove('active'));

    const tab = document.getElementById('tab-' + tabName);
    const panel = document.getElementById('panel-' + tabName);
    if (tab) {
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        tab.setAttribute('tabindex', '0');
    }
    if (panel) panel.classList.add('active');

    // Lazy-load readiness data when tab is first opened
    if (tabName === 'readiness') {
        if (typeof loadReadiness === 'function') loadReadiness();
        if (typeof loadGapAnalysis === 'function') {
            // Small delay so readiness renders first
            setTimeout(function() { loadGapAnalysis(); }, 100);
        }
    }
};

// Tab keyboard navigation (ARIA tab pattern)
function initTabKeyboardNav() {
    const tablist = document.querySelector('.plan-tabs[role="tablist"]');
    if (!tablist) return;

    tablist.addEventListener('keydown', function(e) {
        const tabs = Array.from(tablist.querySelectorAll('.plan-tab[role="tab"]'));
        const current = tabs.indexOf(document.activeElement);
        if (current < 0) return;

        let next = -1;
        if (e.key === 'ArrowRight') {
            next = (current + 1) % tabs.length;
        } else if (e.key === 'ArrowLeft') {
            next = (current - 1 + tabs.length) % tabs.length;
        } else if (e.key === 'Home') {
            next = 0;
        } else if (e.key === 'End') {
            next = tabs.length - 1;
        }

        if (next >= 0) {
            e.preventDefault();
            tabs[next].focus();
            tabs[next].click();
        }
    });
}

window.toggleRecipe = function(button) {
    const targetId = button.getAttribute('data-target');
    const recipeDetails = targetId ? document.getElementById(targetId) : null;
    if (!recipeDetails) return;

    if (recipeDetails.style.display === 'none' || !recipeDetails.style.display) {
        recipeDetails.style.display = 'block';
        button.textContent = 'Hide';
        button.classList.add('active');
    } else {
        recipeDetails.style.display = 'none';
        button.textContent = 'Show';
        button.classList.remove('active');
    }
};

// Detect bfcache (back/forward cache) restores.
// When a browser restores a page from bfcache, no new server request is made,
// so the server-rendered "logged in" state can be stale. If the user's session
// has expired, any API call from the restored page will return 401.
// Reloading forces a fresh server render with the correct auth state.
window.addEventListener('pageshow', function(event) {
    if (event.persisted) {
        // Page was restored from bfcache — verify session is still alive.
        fetch('/api/auth/me', { credentials: 'same-origin' }).then(function(resp) {
            if (resp.status === 401) {
                // Session expired while page was cached — reload to get fresh state.
                window.location.reload();
            }
        }).catch(function() {
            // Network error — don't reload, let the user try normally.
        });
    }
});

// ------------------------------------------------------------------
// In-plan adaptive suggestions (Phase 3)
// ------------------------------------------------------------------

let suggestionsLoaded = false;

window.loadSuggestions = function() {
    if (suggestionsLoaded) return;
    var planId = window.APP_CTX && window.APP_CTX.plan_id;
    if (!planId) return;

    fetch('/api/plan/' + planId + '/suggestions', {
        headers: authHeaders(),
        credentials: 'same-origin'
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        suggestionsLoaded = true;
        if (!data.suggestions || data.suggestions.length === 0) return;
        renderSuggestionCards(data.suggestions);
    })
    .catch(function(err) {
        console.error('[suggestions]', err);
    });
};

function renderSuggestionCards(suggestions) {
    suggestions.forEach(function(weekSuggestion) {
        var weekNum = weekSuggestion.week;
        // Find the week card in the DOM
        var weekCard = document.querySelector('[data-week="' + weekNum + '"]');
        if (!weekCard) return;

        var container = document.createElement('div');
        container.className = 'suggestion-cards';

        weekSuggestion.suggestions.forEach(function(s) {
            var card = document.createElement('div');
            card.className = 'suggestion-card suggestion-card--' + s.type;

            var html = '<div class="suggestion-message">' + escapeHtml(s.message) + '</div>';

            if (s.action === 'accept') {
                html += '<div class="suggestion-actions">';
                html += '<button class="btn btn-small btn-primary" onclick="acceptSuggestion(\'' + weekNum + '\', \'' + s.type + '\', this)">Accept</button>';
                html += '<button class="btn btn-small btn-ghost" onclick="skipSuggestion(this)">Skip</button>';
                html += '</div>';
            } else if (s.action === 'reduce') {
                html += '<div class="suggestion-actions">';
                html += '<button class="btn btn-small btn-primary" onclick="reduceWeek(' + weekNum + ')">Reduce 30%</button>';
                html += '<button class="btn btn-small btn-ghost" onclick="skipSuggestion(this)">Skip</button>';
                html += '</div>';
            }

            card.innerHTML = html;
            container.appendChild(card);
        });

        // Insert after the week header
        var weekHeader = weekCard.querySelector('.week-header, .week-card-header');
        if (weekHeader) {
            weekHeader.after(container);
        } else {
            weekCard.prepend(container);
        }
    });
}

window.acceptSuggestion = function(weekNum, suggestionType, btn) {
    var planId = window.APP_CTX && window.APP_CTX.plan_id;
    if (!planId) return;

    var actionMap = {
        'exceeding': 'bump',
        'deficit': 'ease_deficit',
        'long_run': 'extend_long_run'
    };
    var action = actionMap[suggestionType];
    if (!action) return;

    if (btn) { btn.disabled = true; btn.textContent = 'Applying...'; }

    fetch('/api/plan/' + planId + '/week/' + weekNum + '/override', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        credentials: 'same-origin',
        body: JSON.stringify({ action: action })
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.ok) {
            ApiClient.showSuccess('Suggestion applied. Reloading...');
            setTimeout(function() { location.reload(); }, 1200);
        } else {
            ApiClient.showError(data.detail || 'Failed to apply suggestion.');
            if (btn) { btn.disabled = false; btn.textContent = 'Accept'; }
        }
    })
    .catch(function(err) {
        ApiClient.showError('Error: ' + err.message);
        if (btn) { btn.disabled = false; btn.textContent = 'Accept'; }
    });
};

window.reduceWeek = function(weekNum) {
    var planId = window.APP_CTX && window.APP_CTX.plan_id;
    if (!planId) return;

    fetch('/api/plan/' + planId + '/week/' + weekNum + '/override', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        credentials: 'same-origin',
        body: JSON.stringify({ action: 'reduce_30' })
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.ok) {
            ApiClient.showSuccess('Week reduced by 30%. Reloading...');
            setTimeout(function() { location.reload(); }, 1200);
        }
    })
    .catch(function(err) {
        ApiClient.showError('Error: ' + err.message);
    });
};

window.resetWeek = function(weekNum) {
    var planId = window.APP_CTX && window.APP_CTX.plan_id;
    if (!planId) return;

    fetch('/api/plan/' + planId + '/week/' + weekNum + '/override', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        credentials: 'same-origin',
        body: JSON.stringify({ action: 'reset_week' })
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.ok) {
            ApiClient.showSuccess('Week reset to original distances. Reloading...');
            setTimeout(function() { location.reload(); }, 1200);
        } else {
            ApiClient.showError(data.detail || 'Failed to reset week.');
        }
    })
    .catch(function(err) {
        ApiClient.showError('Error: ' + err.message);
    });
};

// ------------------------------------------------------------------
// Proactive adaptation alerts (Phase 4)
// ------------------------------------------------------------------

window.showRecalibrateModal = function() {
    var modal = document.getElementById('recalibrate-modal');
    if (modal) modal.style.display = 'flex';
};

window.dismissAdaptationAlert = function() {
    var planId = window.APP_CTX && window.APP_CTX.plan_id;
    if (!planId) return;

    fetch('/api/plan/' + planId + '/dismiss-alert', {
        method: 'POST',
        headers: authHeaders(),
        credentials: 'same-origin'
    })
    .then(function(res) { return res.json(); })
    .then(function() {
        var banner = document.getElementById('adaptation-alert-banner');
        if (banner) {
            banner.style.opacity = '0';
            banner.style.transition = 'opacity 0.3s ease';
            setTimeout(function() { banner.remove(); }, 300);
        }
    })
    .catch(function(err) {
        console.error('[alert] dismiss failed:', err);
    });
};

window.recalibratePlan = function(strategy) {
    var planId = window.APP_CTX && window.APP_CTX.plan_id;
    if (!planId) return;

    fetch('/api/plan/' + planId + '/recalibrate', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        credentials: 'same-origin',
        body: JSON.stringify({ strategy: strategy })
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        var modal = document.getElementById('recalibrate-modal');
        if (modal) modal.style.display = 'none';

        if (data.ok) {
            ApiClient.showSuccess(data.reason || 'Plan recalibrated.');
            setTimeout(function() { location.reload(); }, 1500);
        } else {
            ApiClient.showError(data.error || 'Recalibration failed.');
        }
    })
    .catch(function(err) {
        ApiClient.showError('Error: ' + err.message);
    });
};

function initAdaptationAlert() {
    var alertText = document.getElementById('adaptation-alert-text');
    var alertDetail = document.getElementById('recalibrate-alert-detail');
    if (!alertText) return;

    // Parse the alert from the server-rendered data
    try {
        var alertData = window.APP_CTX && window.APP_CTX.adaptation_alert;
        if (alertData) {
            alertText.textContent = alertData.message || 'Your plan needs attention.';
            if (alertDetail) alertDetail.textContent = alertData.message || '';
        }
    } catch (e) {
        alertText.textContent = 'Your plan may need adjustment.';
    }
}

window.skipSuggestion = function(btn) {
    var card = btn.closest('.suggestion-card');
    if (card) {
        card.style.opacity = '0';
        card.style.transition = 'opacity 0.3s ease';
        setTimeout(function() { card.remove(); }, 300);
    }
};

// ---- Collapsible week cards (all viewports) ----
function initCollapsibleWeeks() {
    var cards = document.querySelectorAll('#panel-training .week-card');
    if (!cards.length) return;

    // If no pinned current week exists, expand the first card in the list
    if (!document.getElementById('pinned-current-week') && cards.length > 0) {
        cards[0].classList.add('week-expanded');
    }

    // Click headers to toggle — works on pinned card too
    document.querySelectorAll('.week-card .week-header').forEach(function(header) {
        header.addEventListener('click', function() {
            var card = this.closest('.week-card');
            if (!card) return;
            card.classList.toggle('week-expanded');
            // Keep current-week class in sync for CSS
            if (card.classList.contains('current-week')) {
                if (!card.classList.contains('week-expanded')) {
                    card.classList.remove('current-week');
                    card.dataset.wasCurrent = '1';
                }
            } else if (card.dataset.wasCurrent === '1' && card.classList.contains('week-expanded')) {
                card.classList.add('current-week');
            }
        });
    });
}

// Expand / collapse all weeks (training tab list only)
window.toggleAllWeeks = function() {
    var cards = document.querySelectorAll('#panel-training .week-card');
    var btn = document.getElementById('expand-all-btn');
    var expandedCount = document.querySelectorAll('#panel-training .week-card.week-expanded').length;
    var shouldExpand = expandedCount <= cards.length / 2;

    cards.forEach(function(card) {
        if (shouldExpand) {
            card.classList.add('week-expanded');
        } else {
            card.classList.remove('week-expanded');
        }
    });

    if (btn) {
        btn.textContent = shouldExpand ? 'Collapse all' : 'Expand all';
    }
};

// ------------------------------------------------------------------
// Drag-and-drop day swapping
// ------------------------------------------------------------------

let dragSource = null;

function initDragAndDrop() {
    const ctx = window.APP_CTX;
    // Only plan owners can reorder days
    if (!ctx || !ctx.current_user_id || ctx.current_user_id !== ctx.plan_user_id) return;

    document.querySelectorAll('.workout-item[data-day-num]').forEach(item => {
        item.addEventListener('dragstart', handleDragStart);
        item.addEventListener('dragend', handleDragEnd);
        item.addEventListener('dragover', handleDragOver);
        item.addEventListener('dragleave', handleDragLeave);
        item.addEventListener('drop', handleDrop);
    });
}

function handleDragStart(e) {
    dragSource = this;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', ''); // required for Firefox
    this.classList.add('dragging');
}

function handleDragEnd() {
    this.classList.remove('dragging');
    dragSource = null;
    document.querySelectorAll('.workout-item.drag-over').forEach(el => {
        el.classList.remove('drag-over');
    });
}

function handleDragOver(e) {
    if (!dragSource || dragSource === this) return;
    if (dragSource.dataset.weekNum !== this.dataset.weekNum) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    this.classList.add('drag-over');
}

function handleDragLeave() {
    this.classList.remove('drag-over');
}

async function handleDrop(e) {
    e.preventDefault();
    this.classList.remove('drag-over');

    if (!dragSource || dragSource === this) return;
    if (dragSource.dataset.weekNum !== this.dataset.weekNum) {
        ApiClient.showWarning('Workouts can only be swapped within the same week.');
        return;
    }

    // Capture before await — dragend fires during fetch and nulls the global
    const source = dragSource;
    const planId = window.APP_CTX.plan_id;
    const weekNum = parseInt(this.dataset.weekNum);
    const sourceDay = parseInt(source.dataset.dayNum);
    const targetDay = parseInt(this.dataset.dayNum);
    const target = this;

    try {
        const resp = await fetch(
            `/api/plan/${planId}/week/${weekNum}/swap-days`,
            {
                method: 'POST',
                headers: authHeaders({ 'Content-Type': 'application/json' }),
                credentials: 'same-origin',
                body: JSON.stringify({ source_day: sourceDay, target_day: targetDay })
            }
        );

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            ApiClient.showError(err.detail || 'Failed to swap workouts.');
            return;
        }

        swapWorkoutDomElements(source, target);
    } catch (err) {
        ApiClient.showError('Error: ' + err.message);
    }
}

function swapWorkoutDomElements(a, b) {
    const parent = a.parentNode;
    const aNext = a.nextSibling;
    const bNext = b.nextSibling;

    // Swap DOM positions
    if (aNext === b) {
        parent.insertBefore(b, a);
    } else if (bNext === a) {
        parent.insertBefore(a, b);
    } else {
        if (bNext) {
            parent.insertBefore(a, bNext);
        } else {
            parent.appendChild(a);
        }
        if (aNext) {
            parent.insertBefore(b, aNext);
        } else {
            parent.appendChild(b);
        }
    }

    // Swap day labels so each card reflects its new calendar position
    const aDayLabel = a.querySelector('.workout-day-label');
    const bDayLabel = b.querySelector('.workout-day-label');
    if (aDayLabel && bDayLabel) {
        const temp = aDayLabel.innerHTML;
        aDayLabel.innerHTML = bDayLabel.innerHTML;
        bDayLabel.innerHTML = temp;
    }

    // Swap data attributes so subsequent drags use correct values
    const aDay = a.getAttribute('data-day');
    const aDayNum = a.getAttribute('data-day-num');
    a.setAttribute('data-day', b.getAttribute('data-day'));
    a.setAttribute('data-day-num', b.getAttribute('data-day-num'));
    b.setAttribute('data-day', aDay);
    b.setAttribute('data-day-num', aDayNum);

    // Keep log-run-btn data-day-name in sync
    const aLogBtn = a.querySelector('.log-run-btn');
    const bLogBtn = b.querySelector('.log-run-btn');
    if (aLogBtn && bLogBtn) {
        const aDayName = aLogBtn.dataset.dayName;
        aLogBtn.dataset.dayName = bLogBtn.dataset.dayName;
        bLogBtn.dataset.dayName = aDayName;
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize collapsible weeks for mobile
    initCollapsibleWeeks();
    // Initialize customization week
    if (typeof updateCustomizationWeek === 'function') {
        updateCustomizationWeek();
    }

    // Initialize scroll to top
    initScrollToTop();

    // Initialize save button visibility
    initSaveButton();

    // Initialize tab keyboard navigation
    initTabKeyboardNav();

    // Load inline suggestions for upcoming weeks
    if (window.APP_CTX && window.APP_CTX.plan_id && window.APP_CTX.current_user_id) {
        loadSuggestions();
    }

    // Initialize adaptation alert banner
    initAdaptationAlert();

    // Initialize drag-and-drop day swapping
    initDragAndDrop();

    // Log-run buttons — read data-* attributes (works on all devices including touch)
    document.querySelectorAll('.log-run-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();

            const workoutId = this.dataset.workoutId;
            const workoutType = this.dataset.workoutType;
            const distance = this.dataset.distance;
            const dayName = this.dataset.dayName;
            const weekNum = this.dataset.weekNum;

            if (workoutId && workoutType && distance && dayName && weekNum) {
                openLogModal(workoutId, workoutType, distance, dayName, weekNum);
            }
        });
    });

    // Share buttons on completed workout items
    document.querySelectorAll('.workout-share-corner .share-run-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            try {
                const run = JSON.parse(this.dataset.run);
                if (window.ShareCard) window.ShareCard.open(run);
            } catch (err) {
                console.warn('Failed to open share card:', err);
            }
        });
    });
});
