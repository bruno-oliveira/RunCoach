/**
 * Performance Training JavaScript
 * Handles pace calculator, time conversions, and form interactions
 */

document.addEventListener('DOMContentLoaded', function() {
    const distanceSelect = document.getElementById('target_distance');
    const currentTimeInput = document.getElementById('current_time');
    const goalTimeInput = document.getElementById('goal_time');
    const goalPaceDisplay = document.getElementById('goal-pace-display');
    const improvementDisplay = document.getElementById('improvement-display');

    // Time to pace conversion
    function timeToMinutes(timeStr) {
        const parts = timeStr.split(':');
        if (parts.length === 2) {
            // MM:SS format
            return parseInt(parts[0]) + parseInt(parts[1]) / 60;
        } else if (parts.length === 3) {
            // HH:MM:SS format
            return parseInt(parts[0]) * 60 + parseInt(parts[1]) + parseInt(parts[2]) / 60;
        }
        return 0;
    }

    function minutesToPace(minutes, seconds) {
        return `${minutes}:${seconds.toString().padStart(2, '0')}/km`;
    }

    function calculatePace(timeStr, distanceKm) {
        if (!timeStr || !distanceKm) return null;

        const totalMinutes = timeToMinutes(timeStr);
        if (totalMinutes === 0) return null;

        const paceMinPerKm = totalMinutes / distanceKm;
        const minutes = Math.floor(paceMinPerKm);
        const seconds = Math.round((paceMinPerKm - minutes) * 60);

        return {
            decimal: paceMinPerKm,
            formatted: minutesToPace(minutes, seconds)
        };
    }

    function updatePaceCalculator() {
        const distance = parseFloat(distanceSelect.value);
        const goalTime = goalTimeInput.value.trim();
        const currentTime = currentTimeInput.value.trim();

        if (!distance || !goalTime) {
            goalPaceDisplay.textContent = '--:--/km';
            improvementDisplay.textContent = '--%';
            return;
        }

        // Calculate goal pace
        const goalPace = calculatePace(goalTime, distance);
        if (goalPace) {
            goalPaceDisplay.textContent = goalPace.formatted;
        }

        // Calculate improvement if current time is provided
        if (currentTime && goalTime) {
            const currentPace = calculatePace(currentTime, distance);
            if (currentPace && goalPace) {
                const improvement = ((currentPace.decimal - goalPace.decimal) / currentPace.decimal) * 100;

                if (improvement > 0) {
                    improvementDisplay.textContent = `${improvement.toFixed(1)}%`;
                    improvementDisplay.style.color = improvement > 15 ? '#c62828' : '#2e7d32';

                    if (improvement > 15) {
                        improvementDisplay.title = 'Warning: >15% improvement may be unrealistic';
                    }
                } else if (improvement < 0) {
                    improvementDisplay.textContent = `${improvement.toFixed(1)}%`;
                    improvementDisplay.style.color = '#c62828';
                    improvementDisplay.title = 'Goal pace must be faster than current pace';
                } else {
                    improvementDisplay.textContent = '0%';
                    improvementDisplay.style.color = '#666';
                }
            }
        }
    }

    // Auto-calculate fitness when distance changes
    async function updateFitnessForDistance() {
        const distance = parseFloat(distanceSelect.value);
        if (!distance) return;

        try {
            const response = await fetch(`/api/performance/calculate-fitness?distance=${distance}`);
            const data = await response.json();

            if (data.has_sufficient_data) {
                // Update current time field with estimated time
                if (data.estimated_finish_time && !currentTimeInput.value) {
                    currentTimeInput.value = data.estimated_finish_time;
                }

                // Update hidden fields
                const currentPaceField = document.getElementById('current_pace');
                const currentWeeklyKmField = document.getElementById('current_weekly_km');

                if (currentPaceField) {
                    currentPaceField.value = data.avg_pace;
                }
                if (currentWeeklyKmField) {
                    currentWeeklyKmField.value = data.avg_weekly_km;
                }

                updatePaceCalculator();
            }
        } catch (error) {
            console.error('Error calculating fitness:', error);
        }
    }

    // Event listeners
    if (distanceSelect) {
        distanceSelect.addEventListener('change', function() {
            updatePaceCalculator();
            updateFitnessForDistance();
        });
    }

    if (goalTimeInput) {
        goalTimeInput.addEventListener('input', updatePaceCalculator);
    }

    if (currentTimeInput) {
        currentTimeInput.addEventListener('input', updatePaceCalculator);
    }

    // Time input validation and formatting
    function validateTimeInput(input) {
        input.addEventListener('blur', function() {
            const value = this.value.trim();
            if (!value) return;

            // Check if it matches MM:SS or HH:MM:SS format
            const pattern = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/;
            const match = value.match(pattern);

            if (!match) {
                this.setCustomValidity('Time must be in MM:SS or HH:MM:SS format');
                this.reportValidity();
                return;
            }

            // Validate ranges
            const hours = match[3] ? parseInt(match[1]) : 0;
            const minutes = match[3] ? parseInt(match[2]) : parseInt(match[1]);
            const seconds = match[3] ? parseInt(match[3]) : parseInt(match[2]);

            if (minutes >= 60 || seconds >= 60) {
                this.setCustomValidity('Invalid time values');
                this.reportValidity();
                return;
            }

            this.setCustomValidity('');
        });

        input.addEventListener('input', function() {
            this.setCustomValidity('');
        });
    }

    if (currentTimeInput) {
        validateTimeInput(currentTimeInput);
    }

    if (goalTimeInput) {
        validateTimeInput(goalTimeInput);
    }

    // Form submission validation
    const form = document.getElementById('performance-form');
    if (form) {
        form.addEventListener('submit', function(e) {
            const distance = parseFloat(distanceSelect.value);
            const goalTime = goalTimeInput.value.trim();
            const currentTime = currentTimeInput.value.trim();

            if (!distance || !goalTime) {
                e.preventDefault();
                alert('Please fill in all required fields');
                return;
            }

            // Validate improvement if both times are provided
            if (currentTime && goalTime) {
                const currentPace = calculatePace(currentTime, distance);
                const goalPace = calculatePace(goalTime, distance);

                if (currentPace && goalPace) {
                    if (goalPace.decimal >= currentPace.decimal) {
                        e.preventDefault();
                        alert('Goal pace must be faster than current pace for performance training');
                        return;
                    }

                    const improvement = ((currentPace.decimal - goalPace.decimal) / currentPace.decimal) * 100;
                    if (improvement > 15) {
                        const confirm = window.confirm(
                            `Your goal represents a ${improvement.toFixed(1)}% improvement, which may be unrealistic. ` +
                            'Performance plans work best with improvements under 15%. Continue anyway?'
                        );
                        if (!confirm) {
                            e.preventDefault();
                            return;
                        }
                    }
                }
            }
        });
    }

    // Initial calculation
    updatePaceCalculator();
});
