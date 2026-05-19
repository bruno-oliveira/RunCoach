/**
 * plan_dragdrop.js — Drag-and-drop day swapping within a week.
 *
 * Depends on plan_core.js (authHeaders).
 */
(function () {
    'use strict';

    var dragSource = null;

    function initDragAndDrop() {
        var ctx = window.APP_CTX;
        // Only plan owners can reorder days
        if (!ctx || !ctx.current_user_id || ctx.current_user_id !== ctx.plan_user_id) return;

        document.querySelectorAll('.workout-item[data-day-num]').forEach(function (item) {
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
        document.querySelectorAll('.workout-item.drag-over').forEach(function (el) {
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
        var source = dragSource;
        var planId = window.APP_CTX.plan_id;
        var weekNum = parseInt(this.dataset.weekNum);
        var sourceDay = parseInt(source.dataset.dayNum);
        var targetDay = parseInt(this.dataset.dayNum);
        var target = this;

        try {
            var resp = await fetch(
                '/api/plan/' + planId + '/week/' + weekNum + '/swap-days',
                {
                    method: 'POST',
                    headers: window.authHeaders({ 'Content-Type': 'application/json' }),
                    credentials: 'same-origin',
                    body: JSON.stringify({ source_day: sourceDay, target_day: targetDay })
                }
            );

            if (!resp.ok) {
                var err = await resp.json().catch(function () { return {}; });
                ApiClient.showError(err.detail || 'Failed to swap workouts.');
                return;
            }

            swapWorkoutDomElements(source, target);
        } catch (err) {
            ApiClient.showError('Error: ' + err.message);
        }
    }

    function swapWorkoutDomElements(a, b) {
        var parent = a.parentNode;
        var aNext = a.nextSibling;
        var bNext = b.nextSibling;

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
        var aDayLabel = a.querySelector('.workout-day-label');
        var bDayLabel = b.querySelector('.workout-day-label');
        if (aDayLabel && bDayLabel) {
            var temp = aDayLabel.innerHTML;
            aDayLabel.innerHTML = bDayLabel.innerHTML;
            bDayLabel.innerHTML = temp;
        }

        // Swap data attributes so subsequent drags use correct values
        var aDay = a.getAttribute('data-day');
        var aDayNum = a.getAttribute('data-day-num');
        a.setAttribute('data-day', b.getAttribute('data-day'));
        a.setAttribute('data-day-num', b.getAttribute('data-day-num'));
        b.setAttribute('data-day', aDay);
        b.setAttribute('data-day-num', aDayNum);

        // Keep log-run-btn data-day-name in sync
        var aLogBtn = a.querySelector('.log-run-btn');
        var bLogBtn = b.querySelector('.log-run-btn');
        if (aLogBtn && bLogBtn) {
            var aDayName = aLogBtn.dataset.dayName;
            aLogBtn.dataset.dayName = bLogBtn.dataset.dayName;
            bLogBtn.dataset.dayName = aDayName;
        }
    }

    /* -------------------------------------------------------------- */
    /*  Expose init helper for plan_core.js DOMContentLoaded           */
    /* -------------------------------------------------------------- */

    window._initDragAndDrop = initDragAndDrop;
})();
