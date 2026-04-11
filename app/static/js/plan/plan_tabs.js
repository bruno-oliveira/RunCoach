/**
 * plan_tabs.js — Tab switching, keyboard navigation, collapsible weeks.
 *
 * Depends on plan_core.js (reloadPlanPage).
 */
(function () {
    'use strict';

    /* -------------------------------------------------------------- */
    /*  Plan tab switching                                             */
    /* -------------------------------------------------------------- */

    window.switchPlanTab = function (tabName) {
        document.querySelectorAll('.plan-tab').forEach(function (t) {
            t.classList.remove('active');
            t.setAttribute('aria-selected', 'false');
            t.setAttribute('tabindex', '-1');
        });
        document.querySelectorAll('.plan-tab-panel').forEach(function (p) {
            p.classList.remove('active');
        });

        var tab = document.getElementById('tab-' + tabName);
        var panel = document.getElementById('panel-' + tabName);
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
                setTimeout(function () { loadGapAnalysis(); }, 100);
            }
        }
    };

    /* -------------------------------------------------------------- */
    /*  Tab keyboard navigation (ARIA tab pattern)                     */
    /* -------------------------------------------------------------- */

    function initTabKeyboardNav() {
        var tablist = document.querySelector('.plan-tabs[role="tablist"]');
        if (!tablist) return;

        tablist.addEventListener('keydown', function (e) {
            var tabs = Array.from(tablist.querySelectorAll('.plan-tab[role="tab"]'));
            var current = tabs.indexOf(document.activeElement);
            if (current < 0) return;

            var next = -1;
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

    /* -------------------------------------------------------------- */
    /*  Collapsible week cards                                         */
    /* -------------------------------------------------------------- */

    function initCollapsibleWeeks() {
        var cards = document.querySelectorAll('#panel-training .week-card');
        if (!cards.length) return;

        // If no pinned current week exists, expand the first card in the list
        if (!document.getElementById('pinned-current-week') && cards.length > 0) {
            cards[0].classList.add('week-expanded');
        }

        // Click headers to toggle — works on pinned card too
        document.querySelectorAll('.week-card .week-header').forEach(function (header) {
            header.addEventListener('click', function () {
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

    /* -------------------------------------------------------------- */
    /*  Expand / collapse all weeks                                    */
    /* -------------------------------------------------------------- */

    window.toggleAllWeeks = function () {
        var cards = document.querySelectorAll('#panel-training .week-card');
        var btn = document.getElementById('expand-all-btn');
        var expandedCount = document.querySelectorAll('#panel-training .week-card.week-expanded').length;
        var shouldExpand = expandedCount <= cards.length / 2;

        cards.forEach(function (card) {
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

    /* -------------------------------------------------------------- */
    /*  Expose init helpers for plan_core.js DOMContentLoaded          */
    /* -------------------------------------------------------------- */

    window._initTabKeyboardNav = initTabKeyboardNav;
    window._initCollapsibleWeeks = initCollapsibleWeeks;
})();
