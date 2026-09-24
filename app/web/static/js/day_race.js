/**
 * day_race.js — "This was a race" on a logged run (day_detail.html).
 *
 * Marks or unmarks the run as a race. Marking re-paces the plan in progress
 * from the result, so the note under the button says what moved.
 */
(function () {
  'use strict';

  function init() {
    var box = document.getElementById('dayRace');
    var btn = document.getElementById('dayRaceBtn');
    var note = document.getElementById('dayRaceNote');
    if (!box || !btn) return;

    btn.addEventListener('click', function () {
      var wasRace = box.getAttribute('data-is-race') === 'true';
      btn.disabled = true;
      note.textContent = wasRace ? 'Removing the race tag…' : 'Re-setting your paces from this race…';
      fetch('/api/runs/' + encodeURIComponent(box.getAttribute('data-run-id')) + '/race', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_race: !wasRace }),
      }).then(function (res) {
        if (!res.ok) throw new Error('http_' + res.status);
        return res.json();
      }).then(function (data) {
        box.setAttribute('data-is-race', data.is_race ? 'true' : 'false');
        btn.textContent = data.is_race ? 'Marked as a race · Undo' : 'This was a race';
        if (!data.is_race) {
          note.textContent = 'No longer counted as a race.';
        } else if (data.recalibration && data.recalibration.reason) {
          note.textContent = data.recalibration.reason;
        } else {
          note.textContent = 'Logged as a race. Your paces already match it, so nothing moved.';
        }
      }).catch(function () {
        note.textContent = 'Could not save that. Please try again.';
      }).finally(function () {
        btn.disabled = false;
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
