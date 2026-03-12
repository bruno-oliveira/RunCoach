/**
 * Training Plan Page JavaScript
 * Extracted from plan.html
 * 
 * Global functions are exposed via window for HTML onclick handlers.
 * Initialization code runs after DOMContentLoaded.
 */

console.log('[plan.js] loaded');

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

// Run logging functionality
window.logRun = function(workoutId) {
    // For now, just open the modal - you'd need to pass more data from the template
    const modal = document.getElementById('logRunModal');
    if (modal && modal.style) {
        currentWorkoutId = workoutId;
        modal.style.display = 'block';
    }
};

window.openLogModal = function(workoutId, workoutType, distance, dayName, weekNum) {
    currentWorkoutId = workoutId;
    const modalTitle = document.getElementById('modal-title');
    const workoutTypeSelect = document.getElementById('workout_type');
    const distanceInput = document.getElementById('distance_km');
    const modal = document.getElementById('logRunModal');
    
    if (modalTitle) modalTitle.textContent = `Log Run - Week ${weekNum} ${dayName} (${workoutType})`;
    if (workoutTypeSelect) workoutTypeSelect.value = workoutType;
    if (distanceInput) distanceInput.value = distance;
    
    if (modal) {
        modal.style.display = 'flex';
        modal.style.alignItems = 'flex-start';
        modal.style.justifyContent = 'center';
        
        // Set focus on first input for better mobile UX
        const firstInput = modal.querySelector('input');
        if (firstInput) {
            setTimeout(() => firstInput.focus(), 100);
        }
    }
};

window.closeLogModal = function() {
    const modal = document.getElementById('logRunModal');
    const form = document.getElementById('logRunForm');
    if (modal) {
        modal.style.display = 'none';
    }
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
            closeLogModal();
            ApiClient.showSuccess('Run logged successfully!');
            setTimeout(() => location.reload(), 1500);
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

// Plan adaptation functionality — delegates to recalibrate for backward compat
window.checkForAdaptation = async function() {
    // Kept for backward compatibility; triggers recalibrate flow
    window.recalibratePlan();
};

window.adaptPlan = async function() {
    // Kept for backward compatibility; delegates to recalibrate
    window.recalibratePlan();
};

// Show an inline banner below the Strava card instead of a native alert
function showStravaAdaptMessage(message, isError) {
    const bannerId = 'strava-adapt-message';
    let banner = document.getElementById(bannerId);
    if (!banner) {
        banner = document.createElement('div');
        banner.id = bannerId;
        banner.style.cssText = [
            'margin-top:0.75rem',
            'padding:0.75rem 1rem',
            'border-radius:6px',
            'font-size:0.9rem',
            'line-height:1.4',
            'white-space:pre-wrap',
        ].join(';');
        const btn = document.getElementById('adapt-strava-btn');
        if (btn) {
            // Insert at the end of the strava card so it sits below the buttons
            const stravaCard = btn.closest('.plan-insights-strava') || btn.parentNode;
            stravaCard.appendChild(banner);
        }
    }
    banner.style.background = isError
        ? 'rgba(0,0,0,0.25)'
        : 'rgba(255,255,255,0.15)';
    banner.style.color = 'white';
    banner.style.border = isError
        ? '1px solid rgba(255,100,100,0.6)'
        : '1px solid rgba(255,255,255,0.4)';
    banner.textContent = message;
    banner.style.display = 'block';
}

// Adapt plan from Strava fitness data
window.adaptFromStrava = async function(planId) {
    console.log('adaptFromStrava called with planId:', planId);
    const btn = document.getElementById('adapt-strava-btn');
    const originalText = btn ? btn.textContent : '';

    // Ask for confirmation — this is a one-time action
    const confirmed = window.confirm(
        'This will adjust the distance of all remaining workouts based on your current Strava fitness.\n\n' +
        'This is a one-time calibration and cannot be undone.\n\n' +
        'Continue?'
    );
    if (!confirmed) return;

    // Clear any previous feedback banner
    const existingBanner = document.getElementById('strava-adapt-message');
    if (existingBanner) existingBanner.style.display = 'none';

    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Adapting...';
        btn.style.opacity = '0.7';
    }

    const restoreBtn = () => {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
            btn.style.opacity = '1';
        }
    };

    try {
        console.log('Making fetch request to:', `/api/plan/${planId}/adapt-from-strava`);
        const response = await fetch(`/api/plan/${planId}/adapt-from-strava`, {
            method: 'POST',
            headers: authHeaders(),
            credentials: 'same-origin'
        });
        console.log('Response status:', response.status);

        if (response.ok) {
            const result = await response.json();

            if (result.adapted) {
                let msg = `Plan adapted from Strava data!\n\n${result.reason}`;
                if (result.changes && result.changes.length > 0) {
                    msg += '\n\nChanges:';
                    result.changes.forEach(change => {
                        msg += `\n  Week ${change.week}: ${change.workouts_adjusted.length} workouts adjusted (Total: ${change.new_total_km} km)`;
                    });
                }
                showStravaAdaptMessage(msg, false);
                // Reload after a short delay so the user can see the banner
                setTimeout(() => location.reload(), 5800);
            } else {
                showStravaAdaptMessage(result.reason, false);
                restoreBtn();
            }
        } else {
            let errorMsg;
            if (response.status === 400) {
                errorMsg = 'Strava is not connected. Please connect Strava from the nav menu first.';
            } else if (response.status === 401) {
                errorMsg = 'Your session has expired. Please sign in again — your plan data is safe.';
                // Show a reload-to-sign-in link in the banner
                setTimeout(() => {
                    const banner = document.getElementById('strava-adapt-message');
                    if (banner) {
                        const link = document.createElement('a');
                        link.href = '/';
                        link.textContent = 'Go to home page to sign in';
                        link.style.cssText = 'display:block;margin-top:0.5rem;color:white;text-decoration:underline;';
                        banner.appendChild(link);
                    }
                }, 50);
            } else {
                errorMsg = `Error adapting plan (HTTP ${response.status}). Please try again.`;
            }
            showStravaAdaptMessage(errorMsg, true);
            restoreBtn();
        }
    } catch (error) {
        console.error('Error adapting from Strava:', error);
        showStravaAdaptMessage('Network error: ' + error.message, true);
        restoreBtn();
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

// Check if user is logged in and show appropriate save/view button
function initSaveButton() {
    const saveBtn = document.getElementById('save-plan-btn');
    const viewLink = document.getElementById('view-plans-link');

    if (!saveBtn || !viewLink) return;

    const token = localStorage.getItem('access_token');
    const userJson = localStorage.getItem('user');

    if (token && userJson) {
        try {
            const user = JSON.parse(userJson);
            const planUserId = window.APP_CTX.plan_user_id;

            // Show save button if logged in and plan doesn't belong to user
            if (user.id !== planUserId) {
                if (saveBtn.style) saveBtn.style.display = 'inline-flex';
            } else {
                // Plan already belongs to user, show view link
                if (viewLink.style) viewLink.style.display = 'inline-flex';
            }
        } catch (e) {
            console.error('Error checking plan ownership:', e);
        }
    }
    // If not logged in, neither button shows (default hidden state)
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
// Retroactive run mapping
// ------------------------------------------------------------------

window.previewMapRuns = async function() {
    const btn = document.getElementById('preview-map-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Loading...'; }

    try {
        const response = await fetch(`/api/plan/${window.APP_CTX.plan_id}/map-runs/preview`, {
            headers: authHeaders(),
            credentials: 'same-origin',
        });

        if (response.ok) {
            const result = await response.json();
            if (result.proposals && result.proposals.length > 0) {
                let msg = `Found ${result.proposals.length} run(s) to map:\n\n`;
                result.proposals.forEach(p => {
                    msg += `  Week ${p.week} Day ${p.day} (${p.workout_type}): `;
                    msg += `${p.actual_distance}km run on ${p.run_date}`;
                    msg += ` → planned ${p.planned_distance}km on ${p.workout_date}\n`;
                });
                msg += '\nClick "Map Runs" to apply.';
                ApiClient.showInfo(msg);
            } else {
                ApiClient.showInfo(result.message || 'No matching runs found.');
            }
        } else {
            const err = await response.json();
            ApiClient.showError(err.detail || 'Could not preview mappings.');
        }
    } catch (error) {
        ApiClient.showError('Error: ' + error.message);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Preview'; }
    }
};

window.mapRunsToPlan = async function() {
    const btn = document.getElementById('map-runs-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Mapping...'; }

    try {
        const response = await fetch(`/api/plan/${window.APP_CTX.plan_id}/map-runs`, {
            method: 'POST',
            headers: authHeaders(),
            credentials: 'same-origin',
        });

        if (response.ok) {
            const result = await response.json();
            if (result.mapped > 0) {
                ApiClient.showSuccess(`Mapped ${result.mapped} run(s) to your plan! Reloading...`);
                setTimeout(() => location.reload(), 1500);
            } else {
                ApiClient.showInfo(result.message || 'No runs could be mapped.');
                if (btn) { btn.disabled = false; btn.textContent = 'Map Runs'; }
            }
        } else {
            const err = await response.json();
            ApiClient.showError(err.detail || 'Could not map runs.');
            if (btn) { btn.disabled = false; btn.textContent = 'Map Runs'; }
        }
    } catch (error) {
        ApiClient.showError('Error: ' + error.message);
        if (btn) { btn.disabled = false; btn.textContent = 'Map Runs'; }
    }
};

// ------------------------------------------------------------------
// Plan recalibration
// ------------------------------------------------------------------

window.recalibratePlan = async function() {
    const confirmed = window.confirm(
        'This will adjust future week distances based on your adherence and effort data.\n\n' +
        'Past weeks will not be changed.\n\nContinue?'
    );
    if (!confirmed) return;

    const btn = document.getElementById('recalibrate-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Recalibrating...'; }

    try {
        const response = await fetch(`/api/plan/${window.APP_CTX.plan_id}/recalibrate`, {
            method: 'POST',
            headers: authHeaders(),
            credentials: 'same-origin',
        });

        if (response.ok) {
            const result = await response.json();
            if (result.recalibrated) {
                let msg = `Plan recalibrated!\n\n${result.reason}`;
                if (result.changes && result.changes.length > 0) {
                    msg += '\n\nChanges:';
                    result.changes.forEach(c => {
                        msg += `\n  Week ${c.week}: ${c.workouts_adjusted.length} workout(s) adjusted (Total: ${c.new_total_km} km)`;
                    });
                }
                ApiClient.showSuccess(msg);
                setTimeout(() => location.reload(), 2500);
            } else {
                ApiClient.showInfo(result.reason || 'No recalibration needed.');
                if (btn) { btn.disabled = false; btn.textContent = 'Recalibrate'; }
            }
        } else {
            const err = await response.json();
            ApiClient.showError(err.detail || 'Recalibration failed.');
            if (btn) { btn.disabled = false; btn.textContent = 'Recalibrate'; }
        }
    } catch (error) {
        ApiClient.showError('Error: ' + error.message);
        if (btn) { btn.disabled = false; btn.textContent = 'Recalibrate'; }
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
    });
    document.querySelectorAll('.plan-tab-panel').forEach(p => p.classList.remove('active'));

    const tab = document.getElementById('tab-' + tabName);
    const panel = document.getElementById('panel-' + tabName);
    if (tab) { tab.classList.add('active'); tab.setAttribute('aria-selected', 'true'); }
    if (panel) panel.classList.add('active');
};

window.toggleRecipe = function(mealName, button) {
    const recipeDetails = button.nextElementSibling;
    
    if (recipeDetails.style.display === 'none' || !recipeDetails.style.display) {
        recipeDetails.style.display = 'block';
        button.textContent = 'Hide';
        button.classList.add('active');
    } else {
        recipeDetails.style.display = 'none';
        button.textContent = 'Show';
        button.classList.remove('active');
    }
}

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

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    // Add CSS animation for customization
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn {
            from { opacity: 0.7; transform: translateY(5px); }
            to { opacity: 1; transform: translateY(0); }
        }
    `;
    document.head.appendChild(style);

    // Initialize customization week
    if (typeof updateCustomizationWeek === 'function') {
        updateCustomizationWeek();
    }

    // Initialize scroll to top
    initScrollToTop();

    // Initialize save button visibility
    initSaveButton();

    // Initialize Strava adapt button (backup listener; primary handler is onclick)
    const adaptStravaBtn = document.getElementById('adapt-strava-btn');
    if (adaptStravaBtn) {
        console.log('Strava adapt button found');
    } else {
        console.log('Strava adapt button NOT found');
    }

    // Close modal when clicking outside (works on mobile too)
    document.addEventListener('click', function(event) {
        const modal = document.getElementById('logRunModal');
        if (modal && event.target === modal) {
            closeLogModal();
        }
    });
    
    // Add touch event handling for mobile devices
    const logRunBtns = document.querySelectorAll('.log-run-btn');
    logRunBtns.forEach(btn => {
        // Remove existing event listeners to avoid duplicates
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        
        newBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const workoutId = this.getAttribute('onclick')?.match(/'([^']+)'/)?.[1];
            const workoutType = this.getAttribute('onclick')?.match(/,\s*'(\w+)'/)?.[1];
            const distance = this.getAttribute('onclick')?.match(/,\s*(\d+)/)?.[1];
            const dayName = this.getAttribute('onclick')?.match(/,\s*'(\w+)'/)?.[2];
            const weekNum = this.getAttribute('onclick')?.match(/,\s*(\d+)\)/)?.[1];
            
            if (workoutId && workoutType && distance && dayName && weekNum) {
                openLogModal(workoutId, workoutType, distance, dayName, weekNum);
            }
        }, { passive: false });
    });
    
    // Add touch event handling for modal close button
    const closeButtons = document.querySelectorAll('.close, [data-modal-close]');
    closeButtons.forEach(btn => {
        btn.addEventListener('touchend', function(e) {
            e.preventDefault();
            closeLogModal();
        }, { passive: false });
    });
});
