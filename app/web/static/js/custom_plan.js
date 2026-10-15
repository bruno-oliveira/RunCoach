/**
 * Custom plan builder (/plans/custom/new). The server owns every rule: it
 * says which sessions each cell may hold (/api/custom-plans/options), and the
 * preview is the generated plan itself (/api/custom-plans/preview). This file
 * only keeps the runner's picks, in the order they made them, and posts them
 * to /generate-plan as the `custom_spec` field.
 */
(function () {
  'use strict';

  var form = document.getElementById('customPlanForm');
  if (!form) return;

  var MAX_PER_CELL = 5;
  var grid = document.getElementById('cpGrid');
  var problemsBox = document.getElementById('cpProblems');
  var previewBox = document.getElementById('cpPreview');
  var previewBtn = document.getElementById('cpPreviewBtn');
  var distance = document.getElementById('cpDistance');
  var runs = document.getElementById('cpRuns');
  var weeks = document.getElementById('cpWeeks');
  var isTrail = document.getElementById('cpIsTrail');
  var trailFields = form.querySelectorAll('.cp-trail');

  // What a day without a named session is called in the preview (quality
  // days always carry the session's own name).
  var DAY_TYPES = {
    easy: 'Easy run',
    long: 'Long run'
  };

  // phase -> slot -> [ids in pick order]
  var picks = {};
  var cells = [];
  var optionNames = {};

  var PROBLEMS = {
    empty_cell: 'Pick at least one session for this slot.',
    too_many_sessions: 'This slot has more sessions than its phase has training weeks to fit them.',
    duplicate_session: 'A session is picked twice in this slot.',
    ineligible_session: "One of these sessions doesn't fit this goal any more.",
    too_few_runs: 'Custom plans need at least 3 runs a week.'
  };

  function trail() {
    return distance.value === 'trail';
  }

  function goalKm() {
    return trail() ? parseFloat(form.trail_distance_km.value) : parseFloat(distance.value);
  }

  function syncTrail() {
    var on = trail();
    isTrail.value = on ? 'on' : '';
    trailFields.forEach(function (el) {
      el.hidden = !on;
      el.querySelectorAll('input, select').forEach(function (input) {
        input.disabled = !on;
      });
    });
  }

  function optionsUrl() {
    var params = new URLSearchParams({
      target_distance: String(goalKm() || 0),
      max_runs_per_week: runs.value,
      is_trail: trail() ? 'true' : 'false'
    });
    var w = parseInt(weeks.value, 10);
    if (w > 0) params.set('weeks', String(w));
    if (trail()) {
      params.set('target_elevation_gain_m', form.target_elevation_gain_m.value || '0');
      params.set('training_terrain', form.training_terrain.value);
    }
    return '/api/custom-plans/options?' + params.toString();
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function cellPicks(cell) {
    picks[cell.phase] = picks[cell.phase] || {};
    return picks[cell.phase][cell.slot] || (picks[cell.phase][cell.slot] = []);
  }

  function limitOf(cell) {
    return cell.limit || MAX_PER_CELL;
  }

  function renderCell(cell) {
    var box = el('fieldset', 'cp-cell');
    box.dataset.phase = cell.phase;
    box.dataset.slot = cell.slot;
    var legend = el('legend', 'cp-cell-title');
    legend.appendChild(el('span', 'cp-cell-phase', cell.phase_label));
    legend.appendChild(document.createTextNode(' · '));
    legend.appendChild(el('span', null, cell.slot_label));
    // "2 / 4": picked so far, and how many this phase has weeks for.
    var count = el('span', 'cp-cell-count');
    legend.appendChild(count);
    box.appendChild(legend);

    var chosen = cellPicks(cell);
    var limit = limitOf(cell);
    var list = el('div', 'cp-options');
    cell.options.forEach(function (option) {
      optionNames[option.id] = option.name;
      var label = el('label', 'cp-option cp-intensity--' + option.intensity);
      var input = document.createElement('input');
      input.type = 'checkbox';
      input.value = option.id;
      input.checked = chosen.indexOf(option.id) !== -1;
      var body = el('span', 'cp-option-body');
      var order = el('span', 'cp-option-order');
      body.appendChild(order);
      body.appendChild(el('span', 'cp-option-name', option.name));
      body.appendChild(el('span', 'cp-option-structure', option.structure));
      body.appendChild(el('span', 'cp-option-why', option.rationale));
      label.appendChild(input);
      label.appendChild(body);
      input.addEventListener('change', function () {
        var at = chosen.indexOf(option.id);
        if (input.checked && at === -1) {
          if (chosen.length >= limit) {
            input.checked = false;
            return;
          }
          chosen.push(option.id);
        } else if (!input.checked && at !== -1) {
          chosen.splice(at, 1);
        }
        markOrder(list, chosen, limit, count);
        previewBox.hidden = true;
      });
      list.appendChild(label);
    });
    box.appendChild(list);
    markOrder(list, chosen, limit, count);
    return box;
  }

  // The rotation follows pick order, so each picked card shows its turn.
  // A full cell dims the cards it can no longer take.
  function markOrder(list, chosen, limit, count) {
    var full = chosen.length >= limit;
    list.querySelectorAll('.cp-option').forEach(function (label) {
      var id = label.querySelector('input').value;
      var turn = chosen.indexOf(id);
      label.classList.toggle('cp-option--picked', turn !== -1);
      label.classList.toggle('cp-option--locked', full && turn === -1);
      label.querySelector('.cp-option-order').textContent = turn === -1 ? '' : String(turn + 1);
    });
    count.textContent = chosen.length + ' / ' + limit;
  }

  function loadOptions() {
    if (!(goalKm() > 0)) return;
    fetch(optionsUrl(), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (data) {
        cells = data.cells;
        var defaults = (data.defaults && data.defaults.menus) || {};
        var next = {};
        // Keep a pick across a change of goal or frequency while it is
        // still offered; otherwise fall back to the server's default.
        cells.forEach(function (cell) {
          var offered = cell.options.map(function (o) { return o.id; });
          var old = ((picks[cell.phase] || {})[cell.slot] || []).filter(function (id) {
            return offered.indexOf(id) !== -1;
          });
          next[cell.phase] = next[cell.phase] || {};
          // A shorter plan can lower a cell's limit: keep the earliest picks.
          next[cell.phase][cell.slot] = (old.length ? old : ((defaults[cell.phase] || {})[cell.slot] || []).slice())
            .slice(0, limitOf(cell));
        });
        picks = next;
        grid.textContent = '';
        cells.forEach(function (cell) { grid.appendChild(renderCell(cell)); });
        previewBox.hidden = true;
        problemsBox.hidden = true;
      })
      .catch(function () {
        grid.textContent = '';
        grid.appendChild(el('p', 'cp-loading', "We couldn't load the sessions. Check the goal above and try again."));
      });
  }

  function strengthChoice() {
    var count = form.querySelector('input[name="cp_strength_count"]:checked');
    var kind = form.querySelector('input[name="cp_strength_template"]:checked');
    return {
      sessions_per_week: count ? parseInt(count.value, 10) : 2,
      template: kind ? kind.value : 'auto'
    };
  }

  function spec() {
    var menus = {};
    cells.forEach(function (cell) {
      menus[cell.phase] = menus[cell.phase] || {};
      menus[cell.phase][cell.slot] = cellPicks(cell).slice();
    });
    return { version: 1, menus: menus, strength: strengthChoice() };
  }

  function showProblems(message, problems) {
    problemsBox.textContent = '';
    problemsBox.appendChild(el('p', null, message));
    grid.querySelectorAll('.cp-cell--problem').forEach(function (c) { c.classList.remove('cp-cell--problem'); });
    (problems || []).forEach(function (p) {
      if (p.phase && p.slot) {
        var cell = grid.querySelector('.cp-cell[data-phase="' + p.phase + '"][data-slot="' + p.slot + '"]');
        if (cell) cell.classList.add('cp-cell--problem');
      }
      if (PROBLEMS[p.key]) problemsBox.appendChild(el('p', 'cp-problem', PROBLEMS[p.key]));
    });
    problemsBox.hidden = false;
    reveal(problemsBox);
  }

  function requestBody() {
    var body = {
      current_km: parseFloat(form.current_km.value),
      target_distance: goalKm(),
      weeks: parseInt(form.weeks.value, 10),
      max_runs_per_week: parseInt(runs.value, 10),
      is_trail: trail(),
      custom_spec: spec()
    };
    if (trail()) {
      body.target_elevation_gain_m = parseFloat(form.target_elevation_gain_m.value || '0');
      body.training_terrain = form.training_terrain.value;
    }
    if (form.recent_race_distance_km.value && form.recent_race_time.value) {
      body.recent_race_distance_km = parseFloat(form.recent_race_distance_km.value);
      body.recent_race_time = form.recent_race_time.value;
    }
    return body;
  }

  function renderPreview(data) {
    previewBox.textContent = '';
    var table = el('table', 'cp-weeks');
    var head = el('tr');
    ['Week', 'Phase', 'km', 'Sessions'].forEach(function (h) { head.appendChild(el('th', null, h)); });
    table.appendChild(head);
    data.weeks.forEach(function (week) {
      var row = el('tr', week.is_recovery ? 'cp-week--recovery' : null);
      row.appendChild(el('td', null, String(week.week)));
      row.appendChild(el('td', null, week.is_recovery ? week.phase_label + ' · recovery' : week.phase_label));
      row.appendChild(el('td', 'cp-num', String(week.total_km)));
      var sessions = el('td', 'cp-week-sessions');
      week.days.forEach(function (day) {
        if (!day.name && day.type === 'easy' && !day.strength) return;
        var chip = el('span', 'cp-chip cp-chip--' + day.type);
        chip.textContent = (day.name || DAY_TYPES[day.type] || day.type) + ' · ' + day.distance + ' km';
        if (day.deferral_code) chip.title = 'Your choices need more room than this day has, so it keeps our session.';
        sessions.appendChild(chip);
        if (day.strength) {
          // The name alone in its own text node, so it translates.
          var strength = el('span', 'cp-chip cp-chip--strength', '+ ');
          strength.appendChild(document.createTextNode(day.strength));
          sessions.appendChild(strength);
        }
      });
      row.appendChild(sessions);
      table.appendChild(row);
    });
    previewBox.appendChild(table);
    previewBox.hidden = false;
    reveal(previewBox);
  }

  // The preview and the problems render at the foot of a long page, out of
  // sight of a runner who has just picked their sessions: bring them in.
  function reveal(node) {
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    node.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }

  function runPreview() {
    problemsBox.hidden = true;
    previewBtn.disabled = true;
    previewBtn.setAttribute('aria-busy', 'true');
    var idle = previewBtn.textContent;
    previewBtn.textContent = 'Building preview…';
    fetch('/api/custom-plans/preview', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody())
    })
      .then(function (r) {
        // A rate limit or a server error may not answer JSON.
        return r.json()
          .catch(function () { return {}; })
          .then(function (data) { return { ok: r.ok, status: r.status, data: data }; });
      })
      .then(function (res) {
        if (res.ok) renderPreview(res.data);
        else if (res.status === 429) showProblems('Too many previews in a row. Wait a minute and try again.');
        else showProblems(res.data.message || 'Check your choices and try again.', res.data.problems);
      })
      .catch(function () {
        showProblems("We couldn't build the preview. Try again in a moment.");
      })
      .finally(function () {
        previewBtn.disabled = false;
        previewBtn.removeAttribute('aria-busy');
        previewBtn.textContent = idle;
      });
  }

  distance.addEventListener('change', function () { syncTrail(); loadOptions(); });
  runs.addEventListener('change', loadOptions);
  weeks.addEventListener('change', loadOptions);
  ['trail_distance_km', 'target_elevation_gain_m', 'training_terrain'].forEach(function (name) {
    form[name].addEventListener('change', loadOptions);
  });
  previewBtn.addEventListener('click', runPreview);

  form.addEventListener('submit', function (e) {
    if (!cells.length) {
      e.preventDefault();
      return;
    }
    var empty = cells.filter(function (cell) { return !cellPicks(cell).length; });
    if (empty.length) {
      e.preventDefault();
      showProblems('Pick at least one session for every slot.', empty.map(function (c) {
        return { key: 'empty_cell', phase: c.phase, slot: c.slot };
      }));
      return;
    }
    document.getElementById('cpSpec').value = JSON.stringify(spec());
  });

  syncTrail();
  loadOptions();
})();
