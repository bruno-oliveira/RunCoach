/**
 * Single run page (/run): build a one-off workout, send it to the watch,
 * delete it. The list is server-rendered, so every successful action reloads
 * rather than patching the DOM — one source of truth for what a card shows.
 */
(function () {
  'use strict';

  var form = document.getElementById('singleRunForm');
  if (!form) return;

  var amount = document.getElementById('singleAmount');
  var unit = document.getElementById('singleUnit');
  var dateInput = document.getElementById('singleDate');
  var sendWatch = document.getElementById('singleSendWatch');
  var submit = document.getElementById('singleSubmit');

  var WATCH_ERRORS = {
    not_connected: 'Saved. Connect your watch to send it.',
    auth: 'Saved, but Intervals.icu needs reconnecting before we can send it to your watch.',
    provider: "Saved, but we couldn't reach Intervals.icu. Try sending it again in a moment."
  };

  function t(key, fallback) {
    var i18n = window.RC_I18N;
    var text = i18n ? i18n.t(key) : key;
    return text === key ? fallback : text;
  }

  function checked(name) {
    return form.querySelector('input[name="' + name + '"]:checked');
  }

  // Distance bounds differ per type (a 3 km interval session isn't one), so
  // the input's range follows the selected type. Time has no fixed range: it
  // depends on the runner's paces, and the server says so if it doesn't fit.
  function syncAmount() {
    var byTime = checked('size_mode').value === 'time';
    var type = checked('run_type');
    if (byTime) {
      amount.min = 10;
      amount.max = 360;
      amount.step = 5;
      unit.textContent = t('single.unit_min', 'min');
      if (amount.dataset.mode !== 'time') amount.value = 40;
    } else {
      var min = parseFloat(type.dataset.minKm);
      var max = parseFloat(type.dataset.maxKm);
      amount.min = min;
      amount.max = max;
      amount.step = 0.5;
      unit.textContent = t('single.unit_km', 'km');
      var current = parseFloat(amount.value);
      // Back to the coach's pick, not a number of ours.
      if (amount.dataset.mode === 'time' || isNaN(current)) {
        current = parseFloat(amount.dataset.default) || 6;
      }
      amount.value = Math.min(max, Math.max(min, current));
    }
    amount.dataset.mode = byTime ? 'time' : 'distance';
    syncOverlap();
  }

  // "Your plan already has this run that day" — shown while the form still
  // describes a session the plan has on the chosen date (same kind, similar
  // size). Advisory only: two identical runs in a day is allowed, just rare.
  var overlaps = JSON.parse(form.dataset.planOverlaps || '[]');
  var similarShare = parseFloat(form.dataset.similarShare);
  var similarMinKm = parseFloat(form.dataset.similarMinKm);
  var overlapBox = document.getElementById('singleOverlap');
  var overlapWhat = document.getElementById('singleOverlapWhat');
  var overlapLink = document.getElementById('singleOverlapLink');

  function syncOverlap() {
    var type = checked('run_type').value;
    var byTime = checked('size_mode').value === 'time';
    var km = parseFloat(amount.value);
    var match = overlaps.find(function (planned) {
      if (planned.date !== dateInput.value || planned.run_type !== type) return false;
      // Sized by time, the distance isn't known until the server builds it;
      // the same kind of run on the same day is warning enough.
      if (byTime || isNaN(km)) return true;
      var tolerance = Math.max(similarMinKm, km * similarShare);
      return Math.abs(planned.distance_km - km) <= tolerance;
    });
    overlapBox.hidden = !match;
    if (!match) return;
    overlapWhat.textContent = match.distance_km.toFixed(1) + ' km ' +
      t('single.type_' + match.run_type, match.run_type).toLowerCase();
    overlapLink.href = match.url;
  }

  amount.addEventListener('input', syncOverlap);
  dateInput.addEventListener('change', syncOverlap);

  // Typed values bypass min/max (the form is novalidate so the server's
  // friendlier messages win), so pull a distance back into the type's range.
  amount.addEventListener('change', function () {
    var value = parseFloat(amount.value);
    if (amount.dataset.mode !== 'distance' || isNaN(value)) return;
    amount.value = Math.min(parseFloat(amount.max), Math.max(parseFloat(amount.min), value));
    syncOverlap();
  });

  form.querySelectorAll('input[name="run_type"], input[name="size_mode"]')
    .forEach(function (input) { input.addEventListener('change', syncAmount); });
  syncAmount();

  // A successful send used to be silent — the page just reloaded — which read
  // as "nothing happened". The confirmation has to survive that reload, so it
  // is parked in sessionStorage and shown by the next page load.
  var SENT_FLAG = 'rc_single_run_sent';

  function rememberSent() {
    try { window.sessionStorage.setItem(SENT_FLAG, '1'); } catch (e) { /* private mode */ }
  }

  try {
    if (window.sessionStorage.getItem(SENT_FLAG)) {
      window.sessionStorage.removeItem(SENT_FLAG);
      window.api.showSuccess(t('single.sent', 'Sent. It shows up when your watch next syncs with its app.'));
    }
  } catch (e) { /* private mode */ }

  function reportWatch(result) {
    if (result && result.watch_error) {
      window.api.showWarning(WATCH_ERRORS[result.watch_error] || WATCH_ERRORS.provider);
      return false;
    }
    return true;
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var value = parseFloat(amount.value);
    if (isNaN(value) || value <= 0) {
      amount.focus();
      return;
    }
    var payload = {
      run_type: checked('run_type').value,
      date: dateInput.value || null,
      send_to_watch: !!(sendWatch && sendWatch.checked)
    };
    if (checked('size_mode').value === 'time') payload.duration_minutes = value;
    else payload.distance_km = value;

    submit.disabled = true;
    window.api.post('/api/single-runs', payload)
      .then(function (result) {
        // Let a "saved, but not on your watch" toast be read before reloading.
        var sent = reportWatch(result);
        if (sent && payload.send_to_watch) rememberSent();
        var delay = sent ? 0 : 2500;
        setTimeout(function () { window.location.reload(); }, delay);
      })
      .catch(function () { submit.disabled = false; });  // api.js already toasted
  });

  document.querySelectorAll('[data-single-run-id]').forEach(function (card) {
    var id = card.dataset.singleRunId;

    card.querySelectorAll('[data-action]').forEach(function (button) {
      button.addEventListener('click', function () {
        button.disabled = true;
        var request = button.dataset.action === 'delete'
          ? window.api.del('/api/single-runs/' + id)
          : window.api.post('/api/single-runs/' + id + '/send-to-watch');
        request
          .then(function (result) {
            if (!reportWatch(result)) {
              button.disabled = false;
              return;
            }
            if (button.dataset.action === 'send') rememberSent();
            window.location.reload();
          })
          .catch(function () { button.disabled = false; });
      });
    });
  });
})();
