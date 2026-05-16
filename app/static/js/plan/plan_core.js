/**
 * plan_core.js — Core utilities and initialisation for the plan page.
 *
 * Must be loaded FIRST among the plan/* scripts.
 * Exposes helpers on `window` so other plan modules and HTML onclick
 * handlers can use them.
 */
(function () {
    'use strict';

    /* -------------------------------------------------------------- */
    /*  Utility helpers                                                */
    /* -------------------------------------------------------------- */

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    let currentWeek = 1;
    let currentWorkoutId = null;

    /**
     * Navigate to the canonical plan URL instead of a raw reload.
     * After a POST /generate-plan the browser URL may still be /generate-plan;
     * a plain reload on mobile sends GET to that URL -> 405.  This always
     * navigates to /plan/{id} which is a safe GET endpoint.
     */
    function reloadPlanPage() {
        const planId = window.APP_CTX && window.APP_CTX.plan_id;
        if (planId) {
            window.location.href = '/plan/' + planId;
        } else {
            window.location.reload();
        }
    }

    /**
     * Build fetch headers including Authorization only when a real token exists.
     * The app uses httponly cookies as the primary auth mechanism; localStorage
     * may not hold a token at all. Sending "Bearer null" breaks cookie fallback.
     */
    function authHeaders(extra) {
        return Object.assign({}, extra);
    }

    /* -------------------------------------------------------------- */
    /*  Customisation form helpers                                     */
    /* -------------------------------------------------------------- */

    function submitCustomization(type, value) {
        // Show loading state
        const cards = document.querySelectorAll('.action-card');
        cards.forEach(function (card) {
            if (card && card.style) {
                card.style.opacity = '0.6';
                card.style.cursor = 'not-allowed';
            }
        });

        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/customize-plan';

        var fields = [
            { name: 'plan_id', value: window.APP_CTX.plan_id },
            { name: 'week_number', value: currentWeek },
            { name: 'adjustment_type', value: type },
            { name: 'adjustment_value', value: value }
        ];

        fields.forEach(function (field) {
            var input = document.createElement('input');
            input.type = 'hidden';
            input.name = field.name;
            input.value = field.value;
            form.appendChild(input);
        });

        document.body.appendChild(form);
        form.submit();
    }

    window.adjustIntensity = function (intensity) {
        submitCustomization('intensity', intensity);
    };

    window.adjustDistance = function (change) {
        submitCustomization('distance', change);
    };

    window.applyAISuggestion = function (suggestion) {
        submitCustomization('ai_suggest', suggestion);
    };

    window.swapWorkout = function (swapInfo) {
        submitCustomization('workout_swap', swapInfo);
    };

    window.resetCustomization = function () {
        if (confirm('Are you sure you want to reset to the original plan? This will undo all customizations.')) {
            submitCustomization('reset', 'original');
        }
    };

    window.updateCustomizationWeek = function () {
        var select = document.getElementById('weekSelect');
        if (!select) return;
        currentWeek = parseInt(select.value);

        var display = document.getElementById('currentWeekDisplay');
        if (display) {
            display.textContent = currentWeek;
        }

        var section = document.querySelector('.customization-section');
        if (section) {
            section.style.animation = 'none';
            setTimeout(function () {
                section.style.animation = 'fadeIn 0.3s ease';
            }, 10);
        }
    };

    /* -------------------------------------------------------------- */
    /*  Meal randomisation                                             */
    /* -------------------------------------------------------------- */

    window.randomizeMeals = function () {
        var btn = document.querySelector('.randomize-meals-btn');
        if (!btn) return;

        var originalText = btn.innerHTML;
        btn.innerHTML = '\uD83C\uDFB2 Generating New Meals...';
        btn.disabled = true;
        if (btn.style) {
            btn.style.background = 'linear-gradient(135deg, #f39c12, #e67e22)';
            btn.style.transform = 'scale(0.95)';
        }

        var nutritionSection = document.querySelector('.nutrition-section');
        var mealCards = document.querySelectorAll('.meal-option-card');

        if (nutritionSection && nutritionSection.style) {
            nutritionSection.style.opacity = '0.7';
            nutritionSection.style.transition = 'opacity 0.3s ease';
            nutritionSection.style.transform = 'scale(0.98)';
            nutritionSection.style.transition = 'all 0.3s ease';
        }

        mealCards.forEach(function (card, index) {
            setTimeout(function () {
                if (card && card.style) {
                    card.style.opacity = '0.5';
                    card.style.transform = 'scale(0.95)';
                    card.style.transition = 'all 0.3s ease';
                }
            }, index * 50);
        });

        var form = document.createElement('form');
        form.method = 'POST';
        form.action = '/randomize-meals';

        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'plan_id';
        input.value = window.APP_CTX.plan_id;
        form.appendChild(input);

        document.body.appendChild(form);

        setTimeout(function () {
            form.submit();
        }, 300);
    };

    /* -------------------------------------------------------------- */
    /*  Scroll-to-top button                                           */
    /* -------------------------------------------------------------- */

    function initScrollToTop() {
        var scrollButton = document.querySelector('.scroll-to-top');
        if (scrollButton) {
            window.addEventListener('scroll', function () {
                if (window.pageYOffset > 300) {
                    scrollButton.classList.add('visible');
                } else {
                    scrollButton.classList.remove('visible');
                }
            });
        }
    }

    window.scrollToTop = function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    /* -------------------------------------------------------------- */
    /*  Run log modal                                                  */
    /* -------------------------------------------------------------- */

    window.openLogModal = function (workoutId, workoutType, distance, dayName, weekNum) {
        currentWorkoutId = workoutId;
        var modalTitle = document.getElementById('modal-title');
        var workoutTypeSelect = document.getElementById('workout_type');
        var distanceInput = document.getElementById('distance_km');

        if (modalTitle) modalTitle.textContent = 'Log Run - Week ' + weekNum + ' ' + dayName + ' (' + workoutType + ')';
        if (workoutTypeSelect) workoutTypeSelect.value = workoutType;
        if (distanceInput) distanceInput.value = distance;

        ModalManager.openModal('logRunModal');
    };

    window.closeLogModal = function () {
        ModalManager.closeModal('logRunModal');
        var form = document.getElementById('logRunForm');
        if (form) form.reset();
        currentWorkoutId = null;
    };

    window.submitRunLog = async function (event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }

        var submitBtn = document.querySelector('#logRunForm .submit-btn');

        var distanceInput = document.getElementById('distance_km');
        var durationInput = document.getElementById('duration_minutes');

        if (!distanceInput || !durationInput) {
            ApiClient.showError('Required form fields not found.');
            return;
        }

        var distance = parseFloat(distanceInput.value);
        var duration = parseFloat(durationInput.value);

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

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Logging...';
            submitBtn.style.opacity = '0.7';
        }

        var formData = {
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
            var response = await fetch('/api/runs', {
                method: 'POST',
                headers: authHeaders({ 'Content-Type': 'application/json' }),
                credentials: 'same-origin',
                body: JSON.stringify(formData)
            });

            if (response.ok) {
                var data = await response.json();
                closeLogModal();

                if (data.race_comparison) {
                    showRaceComparisonToast(data);
                    setTimeout(function () { reloadPlanPage(); }, 8000);
                } else if (data.predictions) {
                    showRacePredictionsToast(data);
                    setTimeout(function () { reloadPlanPage(); }, 6000);
                } else {
                    ApiClient.showSuccess('Run logged successfully!');
                    setTimeout(function () { reloadPlanPage(); }, 1500);
                }
            } else {
                var error = await response.json();
                ApiClient.showError('Error logging run: ' + (error.detail || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error logging run:', error);
            ApiClient.showError('Error logging run: ' + error.message);
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Log Run';
                submitBtn.style.opacity = '1';
            }
        }
    };

    /* -------------------------------------------------------------- */
    /*  Race prediction / comparison toasts                            */
    /* -------------------------------------------------------------- */

    window.showRacePredictionsToast = function (data) {
        var toastId = 'race-predictions-toast';
        var toast = document.getElementById(toastId);
        if (toast) toast.remove();

        toast = document.createElement('div');
        toast.id = toastId;
        toast.className = 'race-predictions-toast';

        var predictions = data.predictions || {};
        var distanceLabels = { '5K': '5K', '10K': '10K', 'trail': 'Trail', 'half_marathon': 'Half', 'marathon': 'Full' };

        var predictionsHtml = '';
        for (var key in predictions) {
            var pred = predictions[key];
            var label = distanceLabels[key] || key;
            predictionsHtml += '<span class="toast-prediction"><strong>' + escapeHtml(label) + ':</strong> ' + escapeHtml(pred.formatted) + '</span>';
        }

        toast.innerHTML =
            '<div class="toast-icon">\uD83C\uDFAF</div>' +
            '<div class="toast-content">' +
                '<div class="toast-title">Run logged! Based on your performance:</div>' +
                '<div class="toast-predictions">' + predictionsHtml + '</div>' +
            '</div>' +
            '<div class="toast-actions">' +
                '<button class="toast-btn toast-btn-secondary" onclick="dismissRaceToast()">Dismiss</button>' +
                '<a href="/analytics" class="toast-btn toast-btn-primary">View</a>' +
            '</div>' +
            '<button class="toast-close" onclick="dismissRaceToast()">&times;</button>';

        document.body.appendChild(toast);

        try {
            var dismissed = JSON.parse(sessionStorage.getItem('race_toast_dismissed') || '[]');
            var storeKey = 'race_' + (data.id || Date.now());
            if (!dismissed.includes(storeKey)) {
                sessionStorage.setItem('race_toast_dismissed', JSON.stringify(dismissed.concat([storeKey])));
            }
        } catch (e) { /* ignore */ }

        setTimeout(function () {
            if (document.getElementById(toastId)) dismissRaceToast();
        }, 6000);
    };

    window.dismissRaceToast = function () {
        var toast = document.getElementById('race-predictions-toast');
        if (toast) {
            toast.classList.add('toast-fade-out');
            setTimeout(function () { toast.remove(); }, 300);
        }
    };

    window.showRaceComparisonToast = function (data) {
        var toastId = 'race-predictions-toast';
        var toast = document.getElementById(toastId);
        if (toast) toast.remove();

        toast = document.createElement('div');
        toast.id = toastId;
        toast.className = 'race-predictions-toast race-comparison-toast';

        var comp = data.race_comparison;
        var isFaster = comp.faster_than_predicted;
        var icon = isFaster ? '\uD83C\uDF89' : '\uD83C\uDFC1';
        var verdictClass = isFaster ? 'comparison-faster' : 'comparison-slower';
        var verdictText = isFaster
            ? escapeHtml(comp.delta_formatted) + ' faster than predicted!'
            : escapeHtml(comp.delta_formatted) + ' slower than predicted';

        var predictionsHtml = '';
        if (data.predictions) {
            var distanceLabels = { '5K': '5K', '10K': '10K', 'trail': 'Trail', 'half_marathon': 'Half', 'marathon': 'Full' };
            for (var key in data.predictions) {
                var pred = data.predictions[key];
                var label = distanceLabels[key] || key;
                predictionsHtml += '<span class="toast-prediction"><strong>' + escapeHtml(label) + ':</strong> ' + escapeHtml(pred.formatted) + '</span>';
            }
        }

        toast.innerHTML =
            '<div class="toast-icon">' + icon + '</div>' +
            '<div class="toast-content">' +
                '<div class="toast-title">Race logged!</div>' +
                '<div class="toast-comparison">' +
                    '<div class="toast-comparison-row">' +
                        '<span class="toast-comparison-label">Predicted</span>' +
                        '<span class="toast-comparison-value">' + escapeHtml(comp.predicted_formatted) + '</span>' +
                    '</div>' +
                    '<div class="toast-comparison-row">' +
                        '<span class="toast-comparison-label">Actual</span>' +
                        '<span class="toast-comparison-value toast-comparison-actual">' + escapeHtml(comp.actual_formatted) + '</span>' +
                    '</div>' +
                    '<div class="toast-comparison-verdict ' + verdictClass + '">' + verdictText + '</div>' +
                '</div>' +
                (predictionsHtml ? '<div class="toast-predictions">' + predictionsHtml + '</div>' : '') +
            '</div>' +
            '<div class="toast-actions">' +
                '<button class="toast-btn toast-btn-secondary" onclick="dismissRaceToast()">Dismiss</button>' +
                '<a href="/analytics" class="toast-btn toast-btn-primary">View Analytics</a>' +
            '</div>' +
            '<button class="toast-close" onclick="dismissRaceToast()">&times;</button>';

        document.body.appendChild(toast);

        setTimeout(function () {
            if (document.getElementById(toastId)) dismissRaceToast();
        }, 8000);
    };

    /* -------------------------------------------------------------- */
    /*  Unlink run                                                     */
    /* -------------------------------------------------------------- */

    window.unlinkRun = async function (runId) {
        if (!confirm('Remove this logged run?')) return;
        try {
            var response = await fetch('/api/runs/' + runId, {
                method: 'DELETE',
                headers: authHeaders(),
                credentials: 'same-origin'
            });
            if (response.ok) {
                ApiClient.showSuccess('Run removed.');
                setTimeout(function () { reloadPlanPage(); }, 800);
            } else {
                ApiClient.showError('Could not remove run.');
            }
        } catch (err) {
            ApiClient.showError('Error: ' + err.message);
        }
    };

    /* -------------------------------------------------------------- */
    /*  Save plan to account                                           */
    /* -------------------------------------------------------------- */

    window.savePlanToAccount = async function () {
        var btn = document.getElementById('save-plan-btn');
        if (!btn) return;

        var originalText = btn.innerHTML;
        btn.innerHTML = '\uD83D\uDCBE Saving...';
        btn.disabled = true;

        try {
            var response = await fetch('/api/plan/' + window.APP_CTX.plan_id + '/save', {
                method: 'POST',
                headers: authHeaders(),
                credentials: 'same-origin'
            });

            if (response.ok) {
                btn.innerHTML = '\u2713 Saved!';
                if (btn.style) btn.style.background = '#48bb78';

                setTimeout(function () {
                    btn.outerHTML = '<a href="/my-plans" class="btn btn-secondary">\uD83D\uDCCB View My Plans</a>';
                }, 1500);
            } else if (response.status === 401) {
                ApiClient.showWarning('Please sign in to save this plan to your account.');
                btn.innerHTML = originalText;
                btn.disabled = false;
            } else {
                var error = await response.json();
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

    function initSaveButton() {
        var saveBtn = document.getElementById('save-plan-btn');
        var viewLink = document.getElementById('view-plans-link');
        if (!saveBtn || !viewLink) return;

        var ctx = window.APP_CTX;
        if (!ctx) return;

        var currentUserId = ctx.current_user_id;
        var planUserId = ctx.plan_user_id;

        if (currentUserId) {
            if (currentUserId !== planUserId) {
                if (saveBtn.style) saveBtn.style.display = 'inline-flex';
            } else {
                if (viewLink.style) viewLink.style.display = 'inline-flex';
            }
        }
    }

    /* -------------------------------------------------------------- */
    /*  Plan adjustment / reset                                        */
    /* -------------------------------------------------------------- */

    window.adjustPlan = async function () {
        var confirmed = window.confirm(
            'This will adjust future week distances based on your recent running data.\n\n' +
            'Past weeks will not be changed.\n\nContinue?'
        );
        if (!confirmed) return;

        var btn = document.getElementById('adjust-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Adjusting...'; }

        try {
            var response = await fetch('/api/plan/' + window.APP_CTX.plan_id + '/adjust', {
                method: 'POST',
                headers: authHeaders(),
                credentials: 'same-origin',
            });

            if (response.ok) {
                var result = await response.json();
                console.log('[adjustPlan] response', result);
                if (result.adjusted) {
                    var msg = result.reason;
                    if (result.overreach_detected) {
                        msg = '⚠️ Overreach detected — plan reduced to protect recovery.\n\n' + msg;
                    }
                    if (result.effort_trend && result.effort_trend !== 'stable' && result.effort_trend !== 'insufficient_data') {
                        msg += '\nEffort trend: ' + result.effort_trend + '.';
                    }
                    if (result.vdot_recalibration) {
                        msg += '\nVDOT updated: ' + result.vdot_recalibration.old_vdot + ' → ' + result.vdot_recalibration.new_vdot + ' (' + result.vdot_recalibration.direction + ')';
                    }
                    ApiClient.showSuccess(msg);
                    setTimeout(function () { reloadPlanPage(); }, 2500);
                } else {
                    var noopMsg = result.reason || 'No adjustment needed.';
                    if (ApiClient.showWarning) {
                        ApiClient.showWarning(noopMsg);
                    } else {
                        ApiClient.showInfo(noopMsg);
                    }
                    if (btn) { btn.disabled = false; btn.textContent = 'Adjust Plan'; }
                }
            } else {
                var err = await response.json();
                ApiClient.showError(err.detail || 'Adjustment failed.');
                if (btn) { btn.disabled = false; btn.textContent = 'Adjust Plan'; }
            }
        } catch (error) {
            ApiClient.showError('Error: ' + error.message);
            if (btn) { btn.disabled = false; btn.textContent = 'Adjust Plan'; }
        }
    };

    window.resetAdjustment = async function () {
        var confirmed = window.confirm(
            'This will reset all adjusted distances back to the original plan.\n\nContinue?'
        );
        if (!confirmed) return;

        var btn = document.getElementById('reset-adjust-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Resetting...'; }

        try {
            var response = await fetch('/api/plan/' + window.APP_CTX.plan_id + '/reset-adjustment', {
                method: 'POST',
                headers: authHeaders(),
                credentials: 'same-origin',
            });

            if (response.ok) {
                var result = await response.json();
                if (result.reset) {
                    ApiClient.showSuccess('Plan restored to original distances.');
                    setTimeout(function () { reloadPlanPage(); }, 1500);
                } else {
                    ApiClient.showInfo(result.reason || 'No adjustment to reset.');
                    if (btn) { btn.disabled = false; btn.textContent = 'Reset to original'; }
                }
            } else {
                var err = await response.json();
                ApiClient.showError(err.detail || 'Reset failed.');
                if (btn) { btn.disabled = false; btn.textContent = 'Reset to original'; }
            }
        } catch (error) {
            ApiClient.showError('Error: ' + error.message);
            if (btn) { btn.disabled = false; btn.textContent = 'Reset to original'; }
        }
    };

    /* -------------------------------------------------------------- */
    /*  Start plan (set start date)                                    */
    /* -------------------------------------------------------------- */

    window.startPlan = async function () {
        var dateInput = document.getElementById('plan-start-date');
        if (!dateInput || !dateInput.value) {
            ApiClient.showWarning('Please select a start date.');
            return;
        }

        try {
            var response = await fetch('/api/plan/' + window.APP_CTX.plan_id + '/start', {
                method: 'POST',
                headers: authHeaders({ 'Content-Type': 'application/json' }),
                credentials: 'same-origin',
                body: JSON.stringify({ start_date: dateInput.value })
            });

            if (response.ok) {
                ApiClient.showSuccess('Plan started! Reloading...');
                setTimeout(function () { reloadPlanPage(); }, 800);
            } else {
                var error = await response.json();
                ApiClient.showError('Error: ' + (error.detail || 'Could not set start date'));
            }
        } catch (error) {
            ApiClient.showError('Error setting start date: ' + error.message);
        }
    };

    /* -------------------------------------------------------------- */
    /*  Recipe toggle                                                  */
    /* -------------------------------------------------------------- */

    window.toggleRecipe = function (button) {
        var targetId = button.getAttribute('data-target');
        var recipeDetails = targetId ? document.getElementById(targetId) : null;
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

    /* -------------------------------------------------------------- */
    /*  bfcache detection                                              */
    /* -------------------------------------------------------------- */

    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            fetch('/api/auth/me', { credentials: 'same-origin' }).then(function (resp) {
                if (resp.status === 401) {
                    reloadPlanPage();
                }
            }).catch(function () { /* ignore */ });
        }
    });

    /* -------------------------------------------------------------- */
    /*  Expose shared helpers for other plan modules                   */
    /* -------------------------------------------------------------- */

    window.escapeHtml = escapeHtml;
    window.reloadPlanPage = reloadPlanPage;
    window.authHeaders = authHeaders;

    /**
     * Highlight tomorrow's hard workout after a low-readiness check-in.
     * Called from plan_readiness_daily.js on non-"ready" status.
     */
    window.highlightTomorrowSwap = function (status) {
        if (!status || status === 'ready') return;

        const today = new Date();
        const tomorrow = new Date(today);
        tomorrow.setDate(today.getDate() + 1);
        const tomorrowDayNum = tomorrow.getDay() === 0 ? 7 : tomorrow.getDay();

        // Only touch the pinned-current-week block (drives "this week's plan")
        const container = document.getElementById('pinned-current-week');
        if (!container) return;

        const items = container.querySelectorAll('.workout-item[data-day-num="' + tomorrowDayNum + '"]');
        items.forEach(function (item) {
            const type = (item.className.match(/\b(interval|tempo|hill|long|threshold)\b/) || [])[0];
            if (!type) return;
            item.classList.add('readiness-swap-hint');
            // Auto-remove the class after the animation plays so the badge
            // doesn't linger through the whole session.
            setTimeout(function () {
                item.classList.remove('readiness-swap-hint');
            }, 8000);
        });
    };

    /* -------------------------------------------------------------- */
    /*  DOMContentLoaded — master init                                 */
    /* -------------------------------------------------------------- */

    document.addEventListener('DOMContentLoaded', function () {
        // Collapsible weeks (defined in plan_tabs.js)
        if (typeof window._initCollapsibleWeeks === 'function') window._initCollapsibleWeeks();

        // Customisation week selector
        if (typeof window.updateCustomizationWeek === 'function') {
            window.updateCustomizationWeek();
        }

        // Scroll-to-top
        initScrollToTop();

        // Save button visibility
        initSaveButton();

        // Tab keyboard navigation (defined in plan_tabs.js)
        if (typeof window._initTabKeyboardNav === 'function') window._initTabKeyboardNav();

        // Inline suggestions for upcoming weeks (defined in plan_adaptation.js)
        if (window.APP_CTX && window.APP_CTX.plan_id && window.APP_CTX.current_user_id) {
            if (typeof window.loadSuggestions === 'function') window.loadSuggestions();
        } else {
            console.log('[suggestions] Not loading — plan_id:', window.APP_CTX && window.APP_CTX.plan_id, 'current_user_id:', window.APP_CTX && window.APP_CTX.current_user_id);
        }

        // Adaptation alert banner (defined in plan_adaptation.js)
        if (typeof window._initAdaptationAlert === 'function') window._initAdaptationAlert();

        // Pending recommendation banner (defined in plan_adaptation.js)
        if (typeof window._initPendingRecommendation === 'function') window._initPendingRecommendation();

        // Drag-and-drop (defined in plan_dragdrop.js)
        if (typeof window._initDragAndDrop === 'function') window._initDragAndDrop();

        // Log-run buttons
        document.querySelectorAll('.log-run-btn').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();

                var workoutId = this.dataset.workoutId;
                var workoutType = this.dataset.workoutType;
                var distance = this.dataset.distance;
                var dayName = this.dataset.dayName;
                var weekNum = this.dataset.weekNum;

                if (workoutId && workoutType && distance && dayName && weekNum) {
                    window.openLogModal(workoutId, workoutType, distance, dayName, weekNum);
                }
            });
        });

        // Share buttons on completed workout items
        document.querySelectorAll('.workout-share-corner .share-run-btn').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                try {
                    var run = JSON.parse(this.dataset.run);
                    if (window.ShareCard) window.ShareCard.open(run);
                } catch (err) {
                    console.warn('Failed to open share card:', err);
                }
            });
        });
    });
})();
