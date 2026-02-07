/**
 * Training Plan Page JavaScript
 * Extracted from plan.html
 * 
 * Global functions are exposed via window for HTML onclick handlers.
 * Initialization code runs after DOMContentLoaded.
 */

let currentWeek = 1;
let currentWorkoutId = null;

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
        alert('Error: Required form fields not found');
        return;
    }
    
    const distance = parseFloat(distanceInput.value);
    const duration = parseFloat(durationInput.value);
    
    if (isNaN(distance) || distance <= 0) {
        alert('Please enter a valid distance');
        if (distanceInput) {
            distanceInput.focus();
            distanceInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
    }
    
    if (isNaN(duration) || duration <= 0) {
        alert('Please enter a valid duration');
        if (durationInput) {
            durationInput.focus();
            durationInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
    }
    
    if (!window.APP_CTX || !window.APP_CTX.training_plan_id) {
        alert('Error: Plan context not loaded. Please refresh the page.');
        return;
    }
    
    if (!currentWorkoutId) {
        alert('Error: Workout not selected. Please try again.');
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
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(formData)
        });
        
        if (response.ok) {
            closeLogModal();
            
            // Show success message with adaptation check option
            const adaptCheck = confirm('Run logged successfully! 🎉\n\nWould you like to check if your plan should be adapted based on your performance?');
            if (adaptCheck) {
                await checkForAdaptation();
            } else {
                location.reload();
            }
        } else {
            const error = await response.json();
            alert('Error logging run: ' + (error.detail || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error logging run:', error);
        alert('Error logging run: ' + error.message);
    } finally {
        // Reset button state
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Log Run';
            submitBtn.style.opacity = '1';
        }
    }
};

// Plan adaptation functionality
window.checkForAdaptation = async function() {
    try {
        const response = await fetch(`/api/plan/${window.APP_CTX.plan_id}/performance`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            
            if (data.should_adapt) {
                const msg = `Your performance suggests adapting your plan:\n\n${data.adaptation_reason}\n\nWould you like to adapt future weeks automatically?`;
                if (confirm(msg)) {
                    await adaptPlan();
                }
            } else {
                alert(`Your plan is working well!\n\n${data.adaptation_reason}\n\nKeep up the great work! 🎉`);
            }
        } else {
            alert('Unable to check adaptation. Please make sure you are logged in.');
        }
    } catch (error) {
        alert('Error checking adaptation: ' + error.message);
    }
};

window.adaptPlan = async function() {
    try {
        // Get current week (simple approximation - you might want to track this better)
        const currentWeek = Math.floor((new Date() - new Date(window.APP_CTX.created_at)) / (7 * 24 * 60 * 60 * 1000)) + 1;

        const response = await fetch(`/api/plan/${window.APP_CTX.plan_id}/adapt?current_week=${currentWeek}`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });

        if (response.ok) {
            const result = await response.json();

            if (result.adapted) {
                let msg = `Plan adapted successfully! 🎉\n\n${result.reason}\n\nChanges made:\n`;
                result.changes.forEach(change => {
                    msg += `\nWeek ${change.week}: ${change.workouts_adjusted.length} workouts adjusted (Total: ${change.new_total_km}km)`;
                });
                alert(msg);
                location.reload(); // Reload to show updated plan
            } else {
                alert(`No adaptation needed:\n${result.reason}`);
            }
        } else {
            alert('Error adapting plan. Please try again.');
        }
    } catch (error) {
        alert('Error adapting plan: ' + error.message);
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
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
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
            alert('Please sign in to save this plan to your account.');
            btn.innerHTML = originalText;
            btn.disabled = false;
        } else {
            const error = await response.json();
            alert('Error saving plan: ' + (error.detail || 'Unknown error'));
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    } catch (error) {
        alert('Error saving plan: ' + error.message);
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
