/**
 * Custom plan builder (/plans/custom/new). The server owns every rule: it
 * says which sessions each cell may hold, how many, and why
 * (/api/custom-plans/options — the limits follow the goal, the plan length,
 * and the frequency the weekly base can carry), and the preview is the
 * generated plan itself (/api/custom-plans/preview). This file keeps the
 * runner's picks, in the order they made them, draws them, and posts them to
 * /generate-plan as the `custom_spec` field.
 */
(function () {
  'use strict';

  var form = document.getElementById('customPlanForm');
  if (!form) return;

  var grid = document.getElementById('cpGrid');
  var problemsBox = document.getElementById('cpProblems');
  var review = document.getElementById('cpReview');
  var previewBox = document.getElementById('cpPreview');
  var previewBtn = document.getElementById('cpPreviewBtn');
  var submitBtn = document.getElementById('cpSubmit');
  var statusLine = document.getElementById('cpStatus');
  var summary = document.getElementById('cpSummary');
  var blockerBox = document.getElementById('cpBlocker');
  var frequencyNote = document.getElementById('cpFrequencyNote');
  var timeline = document.getElementById('cpTimeline');
  var budget = document.getElementById('cpBudget');
  var isTrail = document.getElementById('cpIsTrail');
  var trailFields = form.querySelectorAll('.cp-trail');

  // A cell with this few sessions opens with its catalogue showing; a longer
  // one opens on the runner's picks, with the catalogue a tap away.
  var OPEN_UP_TO = 6;

  var TYPE_LABELS = {
    interval: 'Intervals',
    tempo: 'Tempo',
    hill: 'Hills',
    long: 'Long run'
  };
  var TYPE_ORDER = ['interval', 'tempo', 'hill', 'long'];

  // The colour a slot is drawn in: its sessions' type, or all three for the
  // single quality day that may hold any of them.
  var SLOT_TONES = {
    long: 'long',
    quality: 'quality',
    speed: 'interval',
    threshold: 'tempo'
  };

  // What a day without a named session is called in the preview (quality
  // days always carry the session's own name).
  var DAY_TYPES = {
    easy: 'Easy run',
    long: 'Long run'
  };

  var PROBLEMS = {
    empty_cell: 'Pick at least one session for this slot.',
    too_many_sessions: 'This slot has more sessions than its phase has training weeks to fit them.',
    duplicate_session: 'A session is picked twice in this slot.',
    ineligible_session: "One of these sessions doesn't fit this goal any more.",
    too_few_runs: 'Custom plans need at least 3 runs a week.'
  };

  // phase -> slot -> [ids in pick order]
  var picks = {};
  var cells = [];
  var blocked = false;
  var options = {};
  // Per-cell view state that survives a reload of the grid.
  var openCells = {};
  var filters = {};
  var views = [];
  var requestSeq = 0;

  // --- inputs --------------------------------------------------------------

  function checked(name) {
    var input = form.querySelector('input[name="' + name + '"]:checked');
    return input ? input.value : null;
  }

  function trail() {
    return checked('target_distance') === 'trail';
  }

  function goalKm() {
    return trail() ? parseFloat(form.trail_distance_km.value) : parseFloat(checked('target_distance'));
  }

  function runsAsked() {
    return parseInt(checked('max_runs_per_week'), 10) || 4;
  }

  function weeksAsked() {
    return parseInt(form.weeks.value, 10);
  }

  function currentKm() {
    return parseFloat(form.current_km.value);
  }

  function syncTrail() {
    var on = trail();
    isTrail.value = on ? 'on' : '';
    trailFields.forEach(function (box) {
      box.hidden = !on;
      box.querySelectorAll('input, select').forEach(function (input) {
        input.disabled = !on;
      });
    });
  }

  function optionsUrl() {
    var params = new URLSearchParams({
      target_distance: String(goalKm() || 0),
      max_runs_per_week: String(runsAsked()),
      is_trail: trail() ? 'true' : 'false'
    });
    var w = weeksAsked();
    if (w > 0) params.set('weeks', String(w));
    var km = currentKm();
    if (km > 0) params.set('current_km', String(km));
    if (trail()) {
      params.set('target_elevation_gain_m', form.target_elevation_gain_m.value || '0');
      params.set('training_terrain', form.training_terrain.value);
    }
    return '/api/custom-plans/options?' + params.toString();
  }

  // --- helpers -------------------------------------------------------------

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function key(cell) {
    return cell.phase + ':' + cell.slot;
  }

  function cellPicks(cell) {
    picks[cell.phase] = picks[cell.phase] || {};
    return picks[cell.phase][cell.slot] || (picks[cell.phase][cell.slot] = []);
  }

  function limitOf(cell) {
    return cell.limit || 5;
  }

  function plural(n, one, many) {
    return n === 1 ? one : n + ' ' + many;
  }

  function weekRange(span) {
    if (span.first_week === span.last_week) return 'Week ' + span.first_week;
    var range = span.first_week + '–' + span.last_week;
    return 'Weeks ' + range;
  }

  function reveal(node) {
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    node.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }

  function invalidatePreview() {
    review.hidden = true;
  }

  // --- the plan at a glance -------------------------------------------------

  function renderGlance(data) {
    var shape = data.shape || [];
    var weeks = weeksAsked();
    var runsPerWeek = data.runs_per_week;
    summary.textContent = weeks > 0 ? weeks + ' weeks · ' + runsPerWeek + ' runs a week' : '';

    blockerBox.textContent = '';
    blocked = !!data.blocker;
    if (data.blocker) {
      blockerBox.appendChild(el('p', 'cp-notice-title', data.blocker.message));
      if (data.blocker.suggestion) blockerBox.appendChild(el('p', null, data.blocker.suggestion));
    }
    blockerBox.hidden = !data.blocker;

    frequencyNote.textContent = '';
    if (data.runs_per_week < data.requested_runs_per_week) {
      var asked = data.requested_runs_per_week;
      var runs = data.runs_per_week;
      var km = currentKm();
      var note = 'At ' + km + ' km a week, ' + asked + ' runs would each be shorter than 2.5 km, so your plan runs ' + runs + ' days a week.';
      frequencyNote.appendChild(el('p', null, note));
      if (data.requested_runs_per_week >= 5 && data.runs_per_week <= 4) {
        frequencyNote.appendChild(el('p', null, 'That makes one quality day a week instead of two.'));
      }
    }
    frequencyNote.hidden = !frequencyNote.childNodes.length;

    renderTimeline(shape);
    renderBudget(shape);
  }

  // One block per week, grouped by phase: recovery weeks hollow, the taper
  // grey — the weeks the runner chooses for are the solid ones.
  function renderTimeline(shape) {
    timeline.textContent = '';
    timeline.hidden = !shape.length;
    shape.forEach(function (span) {
      var group = el('div', 'cp-tl-phase cp-phase--' + span.phase);
      group.style.flexGrow = String(span.weeks);
      var weeksRow = el('div', 'cp-tl-weeks');
      for (var w = span.first_week; w <= span.last_week; w++) {
        var recovery = span.recovery_weeks.indexOf(w) !== -1;
        var block = el('span', 'cp-tl-week' + (recovery ? ' cp-tl-week--recovery' : ''));
        block.title = recovery ? 'Week ' + w + ' · recovery' : 'Week ' + w;
        weeksRow.appendChild(block);
      }
      group.appendChild(weeksRow);
      group.appendChild(el('span', 'cp-tl-name', span.phase_label));
      group.appendChild(el('span', 'cp-tl-range', weekRange(span)));
      timeline.appendChild(group);
    });
    if (shape.some(function (s) { return s.recovery_weeks.length; })) {
      var legend = el('p', 'cp-tl-legend');
      legend.appendChild(el('span', 'cp-tl-week cp-tl-week--recovery'));
      legend.appendChild(document.createTextNode('Recovery week'));
      timeline.appendChild(legend);
    }
  }

  // How many sessions each slot takes in each phase: the answer to "how many
  // can I pick?" before the runner scrolls through a single card.
  function renderBudget(shape) {
    budget.textContent = '';
    if (!cells.length) return;
    var phases = [];
    cells.forEach(function (cell) {
      if (phases.indexOf(cell.phase) === -1) phases.push(cell.phase);
    });
    var labels = {};
    cells.forEach(function (cell) { labels[cell.phase] = cell.phase_label; });
    var slots = [];
    cells.forEach(function (cell) {
      if (slots.indexOf(cell.slot) === -1) slots.push(cell.slot);
    });
    var taper = shape.filter(function (s) { return s.phase === 'taper'; })[0];

    budget.appendChild(el('h3', 'cp-budget-title', 'Most sessions you can pick'));
    var table = el('table', 'cp-budget-table');
    var head = el('tr');
    head.appendChild(el('th', 'cp-budget-corner'));
    phases.forEach(function (phase) {
      head.appendChild(el('th', 'cp-phase--' + phase, labels[phase]));
    });
    if (taper) head.appendChild(el('th', 'cp-phase--taper', taper.phase_label));
    table.appendChild(head);

    slots.forEach(function (slot) {
      var row = el('tr');
      var sample = cells.filter(function (c) { return c.slot === slot; })[0];
      var th = el('th', 'cp-budget-slot cp-tone--' + SLOT_TONES[slot]);
      th.scope = 'row';
      th.appendChild(el('span', 'cp-dot'));
      th.appendChild(el('span', null, sample.slot_label));
      row.appendChild(th);
      phases.forEach(function (phase) {
        var cell = cells.filter(function (c) { return c.phase === phase && c.slot === slot; })[0];
        var td = el('td');
        if (!cell) {
          td.appendChild(el('span', 'cp-budget-none', '—'));
        } else {
          var jump = el('button', 'cp-budget-n cp-tone--' + SLOT_TONES[slot], String(limitOf(cell)));
          jump.type = 'button';
          jump.setAttribute('aria-label', cell.phase_label + ' · ' + cell.slot_label + ': ' + limitOf(cell));
          jump.addEventListener('click', function () { focusCell(cell); });
          td.appendChild(jump);
        }
        row.appendChild(td);
      });
      if (taper) row.appendChild(el('td', 'cp-budget-ours', 'Ours'));
      table.appendChild(row);
    });
    budget.appendChild(table);
    budget.appendChild(el('p', 'cp-budget-foot', 'One per training week, five at most. Base weeks build volume, so they only ask about the long run.'));
  }

  function focusCell(cell) {
    var view = views.filter(function (v) { return v.cell === cell; })[0];
    if (!view) return;
    setOpen(view, true);
    reveal(view.root);
  }

  // --- the session grid ----------------------------------------------------

  function renderGrid(data) {
    grid.textContent = '';
    views = [];
    var shapeByPhase = {};
    (data.shape || []).forEach(function (span) { shapeByPhase[span.phase] = span; });
    var phases = [];
    cells.forEach(function (cell) {
      if (phases.indexOf(cell.phase) === -1) phases.push(cell.phase);
    });
    phases.forEach(function (phase) {
      var phaseCells = cells.filter(function (c) { return c.phase === phase; });
      var section = el('section', 'cp-phase cp-phase--' + phase);
      var head = el('header', 'cp-phase-head');
      head.appendChild(el('h3', 'cp-phase-name', phaseCells[0].phase_label));
      var span = shapeByPhase[phase];
      if (span) {
        head.appendChild(el('span', 'cp-phase-range', weekRange(span)));
        var parts = [plural(span.training_weeks, '1 training week', 'training weeks')];
        if (span.recovery_weeks.length) {
          parts.push(plural(span.recovery_weeks.length, '1 recovery week', 'recovery weeks'));
        }
        head.appendChild(el('span', 'cp-phase-meta', parts.join(' · ')));
      }
      section.appendChild(head);
      phaseCells.forEach(function (cell) { section.appendChild(renderSlot(cell)); });
      grid.appendChild(section);
    });
  }

  function slotCaption(cell) {
    var limit = limitOf(cell);
    var tw = cell.training_weeks;
    if (limit === 1) return 'One pick fills this phase.';
    if (tw != null && tw > limit) return 'Pick up to ' + limit + ' — they rotate over ' + tw + ' training weeks.';
    if (tw != null) return 'Pick up to ' + limit + ' — one for each training week.';
    return 'Pick up to ' + limit + '.';
  }

  function renderSlot(cell) {
    var view = { cell: cell, cards: [] };
    var root = el('div', 'cp-slot cp-tone--' + SLOT_TONES[cell.slot]);
    root.dataset.phase = cell.phase;
    root.dataset.slot = cell.slot;
    view.root = root;

    var head = el('div', 'cp-slot-head');
    var title = el('h4', 'cp-slot-title');
    title.appendChild(el('span', 'cp-dot'));
    title.appendChild(el('span', null, cell.slot_label));
    head.appendChild(title);
    var meter = el('div', 'cp-meter');
    view.dots = el('span', 'cp-meter-dots');
    view.dots.setAttribute('aria-hidden', 'true');
    view.count = el('span', 'cp-meter-count');
    meter.appendChild(view.dots);
    meter.appendChild(view.count);
    head.appendChild(meter);
    root.appendChild(head);
    root.appendChild(el('p', 'cp-slot-caption', slotCaption(cell)));

    view.rotation = el('ol', 'cp-rotation');
    root.appendChild(view.rotation);

    view.toggle = el('button', 'cp-browse');
    view.toggle.type = 'button';
    view.toggle.addEventListener('click', function () { setOpen(view, !view.open); });
    root.appendChild(view.toggle);

    view.catalogue = el('div', 'cp-catalogue');
    var types = {};
    cell.options.forEach(function (o) { types[o.type] = (types[o.type] || 0) + 1; });
    var present = TYPE_ORDER.filter(function (t) { return types[t]; });
    if (present.length > 1) {
      var bar = el('div', 'cp-filters');
      bar.setAttribute('role', 'group');
      bar.setAttribute('aria-label', 'Filter sessions');
      [null].concat(present).forEach(function (type) {
        var chip = el('button', 'cp-filter' + (type ? ' cp-tone--' + type : ''));
        chip.type = 'button';
        if (type) chip.appendChild(el('span', 'cp-dot'));
        chip.appendChild(el('span', null, type ? TYPE_LABELS[type] : 'All types'));
        chip.appendChild(el('span', 'cp-filter-n', String(type ? types[type] : cell.options.length)));
        chip.dataset.type = type || '';
        chip.addEventListener('click', function () {
          filters[key(cell)] = type;
          applyFilter(view);
        });
        bar.appendChild(chip);
      });
      view.filterBar = bar;
      view.catalogue.appendChild(bar);
    }
    view.fullNote = el('p', 'cp-full-note', 'This slot is full. Remove a pick to swap in another.');
    view.catalogue.appendChild(view.fullNote);

    var list = el('div', 'cp-options');
    cell.options.forEach(function (option) {
      options[option.id] = option;
      list.appendChild(renderOption(view, option));
    });
    view.catalogue.appendChild(list);
    root.appendChild(view.catalogue);

    views.push(view);
    var remembered = openCells[key(cell)];
    view.open = remembered != null
      ? remembered
      : cell.options.length <= OPEN_UP_TO || !cellPicks(cell).length;
    refreshSlot(view);
    applyFilter(view);
    return root;
  }

  function renderOption(view, option) {
    var label = el('label', 'cp-option cp-tone--' + option.type);
    var input = document.createElement('input');
    input.type = 'checkbox';
    input.value = option.id;
    label.appendChild(input);

    var top = el('span', 'cp-option-top');
    var tag = el('span', 'cp-tag');
    tag.appendChild(el('span', 'cp-dot'));
    tag.appendChild(el('span', null, TYPE_LABELS[option.type] || option.type));
    top.appendChild(tag);
    var badge = el('span', 'cp-option-badge');
    badge.setAttribute('aria-hidden', 'true');
    top.appendChild(badge);
    label.appendChild(top);

    label.appendChild(el('span', 'cp-option-name', option.name));
    if (option.structure) label.appendChild(el('span', 'cp-option-structure', option.structure));
    if (option.rationale) label.appendChild(el('span', 'cp-option-why', option.rationale));

    input.addEventListener('change', function () {
      var chosen = cellPicks(view.cell);
      var at = chosen.indexOf(option.id);
      if (input.checked && at === -1) {
        if (chosen.length >= limitOf(view.cell)) {
          input.checked = false;
          nudge(view.fullNote);
          return;
        }
        chosen.push(option.id);
      } else if (!input.checked && at !== -1) {
        chosen.splice(at, 1);
      }
      changed(view);
    });
    view.cards.push({ option: option, label: label, input: input, badge: badge });
    return label;
  }

  function nudge(node) {
    node.classList.remove('cp-nudge');
    // Restart the animation on a repeat tap.
    void node.offsetWidth;
    node.classList.add('cp-nudge');
  }

  function setOpen(view, open) {
    view.open = open;
    openCells[key(view.cell)] = open;
    refreshSlot(view);
  }

  function applyFilter(view) {
    var type = filters[key(view.cell)] || null;
    if (view.filterBar) {
      view.filterBar.querySelectorAll('.cp-filter').forEach(function (chip) {
        var on = (chip.dataset.type || null) === type;
        chip.classList.toggle('cp-filter--on', on);
        chip.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    }
    view.cards.forEach(function (card) {
      card.label.hidden = !!type && card.option.type !== type;
    });
  }

  function changed(view) {
    view.root.classList.remove('cp-slot--problem');
    refreshSlot(view);
    invalidatePreview();
    updateStatus();
  }

  // Draw a slot from the picks: the ordered rotation, the meter, and the
  // cards' picked / locked state. In place, so focus stays where it was.
  function refreshSlot(view) {
    var cell = view.cell;
    var chosen = cellPicks(cell);
    var limit = limitOf(cell);
    var full = chosen.length >= limit;

    view.dots.textContent = '';
    for (var i = 0; i < limit; i++) {
      view.dots.appendChild(el('span', 'cp-meter-dot' + (i < chosen.length ? ' cp-meter-dot--on' : '')));
    }
    view.count.textContent = chosen.length + ' of ' + limit;

    view.rotation.textContent = '';
    if (!chosen.length) {
      view.rotation.appendChild(el('li', 'cp-rotation-empty', 'Nothing picked yet. Choose at least one session below.'));
    }
    chosen.forEach(function (id, index) {
      var option = options[id] || { id: id, name: id, type: 'long' };
      var item = el('li', 'cp-pick cp-tone--' + option.type);
      item.appendChild(el('span', 'cp-pick-n', String(index + 1)));
      var text = el('span', 'cp-pick-text');
      text.appendChild(el('span', 'cp-pick-name', option.name));
      if (option.structure) text.appendChild(el('span', 'cp-pick-structure', option.structure));
      item.appendChild(text);
      var tools = el('span', 'cp-pick-tools');
      if (index > 0) {
        var up = el('button', 'cp-icon-btn', '↑');
        up.type = 'button';
        up.title = 'Move earlier';
        up.setAttribute('aria-label', 'Move earlier');
        up.addEventListener('click', function () {
          chosen.splice(index, 1);
          chosen.splice(index - 1, 0, id);
          changed(view);
        });
        tools.appendChild(up);
      }
      var remove = el('button', 'cp-icon-btn', '×');
      remove.type = 'button';
      remove.title = 'Remove';
      remove.setAttribute('aria-label', 'Remove');
      remove.addEventListener('click', function () {
        chosen.splice(chosen.indexOf(id), 1);
        changed(view);
      });
      tools.appendChild(remove);
      item.appendChild(tools);
      view.rotation.appendChild(item);
    });

    view.cards.forEach(function (card) {
      var turn = chosen.indexOf(card.option.id);
      card.input.checked = turn !== -1;
      card.label.classList.toggle('cp-option--picked', turn !== -1);
      card.label.classList.toggle('cp-option--locked', full && turn === -1);
      card.badge.textContent = turn === -1 ? '' : String(turn + 1);
    });

    view.root.classList.toggle('cp-slot--full', full);
    view.catalogue.hidden = !view.open;
    view.toggle.setAttribute('aria-expanded', view.open ? 'true' : 'false');
    var total = cell.options.length;
    view.toggle.textContent = view.open ? 'Hide sessions' : 'Browse ' + total + ' sessions';
  }

  function updateStatus() {
    statusLine.classList.remove('cp-dock-status--ready', 'cp-dock-status--todo');
    if (!cells.length) {
      statusLine.textContent = '';
      return;
    }
    var empty = cells.filter(function (cell) { return !cellPicks(cell).length; }).length;
    previewBtn.disabled = blocked;
    submitBtn.disabled = blocked;
    if (blocked) {
      statusLine.textContent = 'Adjust your goal above to build this plan.';
      statusLine.classList.add('cp-dock-status--todo');
    } else if (empty) {
      statusLine.textContent = empty === 1 ? '1 slot needs a session' : empty + ' slots need a session';
      statusLine.classList.add('cp-dock-status--todo');
    } else {
      statusLine.textContent = 'Every slot is set';
      statusLine.classList.add('cp-dock-status--ready');
    }
  }

  // --- loading -------------------------------------------------------------

  // Where a pick may come from when the grid changes shape: the same cell,
  // or — across a change of frequency — the quality cells it splits into or
  // merges from, so a runner's choices survive 4 runs becoming 5.
  function carriedPicks(cell) {
    var previous = picks[cell.phase] || {};
    if (previous[cell.slot]) return previous[cell.slot];
    if (cell.slot === 'quality') return (previous.speed || []).concat(previous.threshold || []);
    if (cell.slot === 'speed' || cell.slot === 'threshold') return previous.quality || [];
    return [];
  }

  function loadOptions() {
    if (!(goalKm() > 0)) return;
    var seq = ++requestSeq;
    grid.setAttribute('aria-busy', 'true');
    fetch(optionsUrl(), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (data) {
        if (seq !== requestSeq) return;
        var defaults = (data.defaults && data.defaults.menus) || {};
        var next = {};
        // Keep a pick across a change of goal or frequency while it is
        // still offered; otherwise fall back to the server's default.
        data.cells.forEach(function (cell) {
          var offered = cell.options.map(function (o) { return o.id; });
          var old = carriedPicks(cell).filter(function (id, i, all) {
            return offered.indexOf(id) !== -1 && all.indexOf(id) === i;
          });
          next[cell.phase] = next[cell.phase] || {};
          // A shorter plan can lower a cell's limit: keep the earliest picks.
          next[cell.phase][cell.slot] = (old.length ? old : ((defaults[cell.phase] || {})[cell.slot] || []).slice())
            .slice(0, limitOf(cell));
        });
        picks = next;
        cells = data.cells;
        renderGlance(data);
        renderGrid(data);
        invalidatePreview();
        problemsBox.hidden = true;
        updateStatus();
      })
      .catch(function () {
        if (seq !== requestSeq) return;
        grid.textContent = '';
        grid.appendChild(el('p', 'cp-loading', "We couldn't load the sessions. Check the goal above and try again."));
      })
      .finally(function () {
        if (seq === requestSeq) grid.removeAttribute('aria-busy');
      });
  }

  var typingTimer = null;
  function loadSoon() {
    clearTimeout(typingTimer);
    typingTimer = setTimeout(loadOptions, 450);
  }

  // --- preview and submit --------------------------------------------------

  function strengthChoice() {
    var count = checked('cp_strength_count');
    var kind = checked('cp_strength_template');
    return {
      sessions_per_week: count != null ? parseInt(count, 10) : 2,
      template: kind || 'auto'
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
    problemsBox.appendChild(el('p', 'cp-notice-title', message));
    grid.querySelectorAll('.cp-slot--problem').forEach(function (c) { c.classList.remove('cp-slot--problem'); });
    var seen = {};
    (problems || []).forEach(function (p) {
      if (p.phase && p.slot) {
        var view = views.filter(function (v) { return v.cell.phase === p.phase && v.cell.slot === p.slot; })[0];
        if (view) {
          view.root.classList.add('cp-slot--problem');
          setOpen(view, true);
        }
      }
      if (PROBLEMS[p.key] && !seen[p.key]) {
        seen[p.key] = true;
        problemsBox.appendChild(el('p', 'cp-problem', PROBLEMS[p.key]));
      }
    });
    problemsBox.hidden = false;
    var first = grid.querySelector('.cp-slot--problem');
    reveal(first || problemsBox);
  }

  function requestBody() {
    var body = {
      current_km: currentKm(),
      target_distance: goalKm(),
      weeks: weeksAsked(),
      max_runs_per_week: runsAsked(),
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

  function dayTone(type) {
    return ['easy', 'long', 'tempo', 'interval', 'hill', 'race', 'recovery'].indexOf(type) !== -1 ? type : 'easy';
  }

  function renderPreview(data) {
    previewBox.textContent = '';
    var peak = data.peak_km || 1;
    var list = el('ol', 'cp-weeks');
    data.weeks.forEach(function (week) {
      var row = el('li', 'cp-wk cp-phase--' + week.phase + (week.is_recovery ? ' cp-wk--recovery' : ''));
      var head = el('div', 'cp-wk-head');
      head.appendChild(el('span', 'cp-wk-n', String(week.week)));
      var label = el('span', 'cp-wk-phase', week.phase_label);
      head.appendChild(label);
      if (week.is_recovery) head.appendChild(el('span', 'cp-wk-tag', 'Recovery'));
      var volume = el('span', 'cp-wk-volume');
      var bar = el('span', 'cp-wk-bar');
      var fill = el('span', 'cp-wk-fill');
      fill.style.width = Math.max(4, Math.round(((week.total_km || 0) / peak) * 100)) + '%';
      bar.appendChild(fill);
      volume.appendChild(bar);
      volume.appendChild(el('span', 'cp-wk-km', (week.total_km || 0) + ' km'));
      head.appendChild(volume);
      row.appendChild(head);

      var sessions = el('div', 'cp-wk-sessions');
      week.days.forEach(function (day) {
        if (!day.name && day.type === 'easy' && !day.strength) return;
        var chip = el('span', 'cp-chip cp-tone--' + dayTone(day.type) + (day.name ? ' cp-chip--named' : ''));
        chip.appendChild(el('span', 'cp-dot'));
        chip.appendChild(el('span', 'cp-chip-name', day.name || DAY_TYPES[day.type] || day.type));
        chip.appendChild(el('span', 'cp-chip-km', day.distance + ' km'));
        if (day.deferral_code) {
          chip.classList.add('cp-chip--deferred');
          chip.title = 'Your choices need more room than this day has, so it keeps our session.';
        }
        sessions.appendChild(chip);
        if (day.strength) {
          // The name alone in its own text node, so it translates.
          var strength = el('span', 'cp-chip cp-chip--strength cp-tone--strength');
          strength.appendChild(el('span', 'cp-dot'));
          strength.appendChild(el('span', 'cp-chip-name', day.strength));
          sessions.appendChild(strength);
        }
      });
      row.appendChild(sessions);
      list.appendChild(row);
    });
    previewBox.appendChild(list);
    review.hidden = false;
    reveal(review);
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
        previewBtn.disabled = blocked;
        previewBtn.removeAttribute('aria-busy');
        previewBtn.textContent = idle;
      });
  }

  // --- wiring --------------------------------------------------------------

  form.querySelectorAll('input[name="target_distance"]').forEach(function (input) {
    input.addEventListener('change', function () { syncTrail(); loadOptions(); });
  });
  form.querySelectorAll('input[name="max_runs_per_week"]').forEach(function (input) {
    input.addEventListener('change', loadOptions);
  });
  ['current_km', 'weeks', 'trail_distance_km', 'target_elevation_gain_m'].forEach(function (name) {
    form[name].addEventListener('input', loadSoon);
    form[name].addEventListener('change', function () {
      clearTimeout(typingTimer);
      loadOptions();
    });
  });
  form.training_terrain.addEventListener('change', loadOptions);
  form.querySelectorAll('input[name^="cp_strength"]').forEach(function (input) {
    input.addEventListener('change', invalidatePreview);
  });
  previewBtn.addEventListener('click', runPreview);

  form.addEventListener('submit', function (e) {
    if (!cells.length || blocked) {
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
