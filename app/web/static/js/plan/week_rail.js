/* Week day rail: tapping a day scrolls to that workout inside the pinned
   current week and flashes it. Pure progressive enhancement — the rail is
   server-rendered and informative without JS. */
(function () {
    'use strict';

    function findWorkoutCard(weekNum, dayNum) {
        var pinned = document.getElementById('pinned-current-week');
        var scope = pinned || document;
        return scope.querySelector(
            '.workout-item[data-week-num="' + weekNum + '"][data-day-num="' + dayNum + '"]'
        );
    }

    function onRailTap(e) {
        var btn = e.target.closest('.week-rail-day');
        if (!btn) return;
        var card = findWorkoutCard(btn.dataset.railWeek, btn.dataset.railDay);
        if (!card) return;
        var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        card.scrollIntoView({
            behavior: reduced ? 'auto' : 'smooth',
            block: 'center'
        });
        card.classList.remove('rail-flash');
        // restart the animation if the same card is tapped twice
        void card.offsetWidth;
        card.classList.add('rail-flash');
    }

    document.addEventListener('DOMContentLoaded', function () {
        var rail = document.querySelector('.week-rail');
        if (rail) rail.addEventListener('click', onRailTap);
    });
})();
