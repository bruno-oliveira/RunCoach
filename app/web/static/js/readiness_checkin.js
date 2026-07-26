/**
 * readiness_checkin.js — the 15-second morning check-in card.
 *
 * The capture side of "the plan that adapts to how you feel". A runner taps how
 * they slept, their energy, and how heavy their legs feel; we POST it, show the
 * readiness verdict, and refresh the Coach's Note so today's guidance reflects
 * the morning. One check-in per calendar day (the API upserts).
 *
 * Self-contained (window.ReadinessCheckIn); reuses no framework. Lives inside
 * #readinessCheckinCard — on the Coach "Today" tab, and folded into the Today
 * card at the head of the plan. Host pages can set `ReadinessCheckIn.onSaved`
 * to react to a fresh check-in (the plan page re-reads the advisory under
 * today's session, which is the whole reason the capture moved there).
 */
(function () {
    const CARD_ID = 'readinessCheckinCard';

    // 1–5 scales. `invert:true` means a high value is *worse* (soreness, stress)
    // — the scoring on the server inverts them; here we only label the ends.
    const SCALES = [
        { key: 'sleep_quality', label: 'Sleep quality', low: 'Poor', high: 'Great' },
        { key: 'energy', label: 'Energy', low: 'Drained', high: 'Buzzing' },
        { key: 'soreness', label: 'Legs', low: 'Fresh', high: 'Wrecked', invert: true },
        { key: 'stress', label: 'Stress', low: 'Calm', high: 'Frazzled', invert: true },
    ];

    const SLEEP_HOURS = [
        { label: '<5h', value: 4 },
        { label: '5h', value: 5 },
        { label: '6h', value: 6 },
        { label: '7h', value: 7 },
        { label: '8h', value: 8 },
        { label: '9h+', value: 9 },
    ];

    const BAND_CLASS = {
        primed: 'rc-band--primed',
        good: 'rc-band--good',
        ok: 'rc-band--ok',
        run_down: 'rc-band--low',
        depleted: 'rc-band--low',
    };

    const RC = {
        planId: null,
        // Optional host hook: called with the saved check-in after a successful
        // POST. Set by whichever page embeds the card; null on pages that
        // don't need to react.
        onSaved: null,
        _values: {},

        _esc(s) {
            return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
                { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
            ));
        },

        _card() { return document.getElementById(CARD_ID); },

        async load(planId) {
            const card = this._card();
            if (!card) return;
            this.planId = planId;
            this._values = {};

            if (!planId) { card.style.display = 'none'; card.innerHTML = ''; return; }

            card.style.display = '';
            card.innerHTML = this._skeleton();

            let data = null;
            try {
                const res = await fetch('/api/readiness/today', { credentials: 'same-origin' });
                if (res.ok) data = await res.json();
            } catch (e) { /* fall through to the empty form */ }

            if (data && data.logged && data.checkin) {
                this._renderLogged(data.checkin);
            } else {
                this._renderForm();
            }
        },

        _skeleton() {
            return '<div class="rc-skeleton"><div class="rc-shimmer"></div>' +
                '<div class="rc-shimmer rc-shimmer--short"></div></div>';
        },

        /* ---------- capture form ---------- */
        _renderForm(prefill) {
            const card = this._card();
            this._values = Object.assign({}, prefill || {});

            const hoursChips = SLEEP_HOURS.map((h) => (
                `<button type="button" class="rc-chip" data-hours="${h.value}"` +
                `${this._values.sleep_hours === h.value ? ' aria-pressed="true"' : ''}>` +
                `${this._esc(h.label)}</button>`
            )).join('');

            const scaleRows = SCALES.map((s) => {
                const dots = [1, 2, 3, 4, 5].map((n) => (
                    `<button type="button" class="rc-dot" data-scale="${s.key}" data-val="${n}"` +
                    `${this._values[s.key] === n ? ' aria-pressed="true"' : ''}` +
                    ` aria-label="${this._esc(s.label)} ${n} of 5">${n}</button>`
                )).join('');
                return (
                    '<div class="rc-scale">' +
                    `<div class="rc-scale-label">${this._esc(s.label)}</div>` +
                    `<div class="rc-scale-dots" role="group" aria-label="${this._esc(s.label)}">${dots}</div>` +
                    `<div class="rc-scale-ends"><span>${this._esc(s.low)}</span><span>${this._esc(s.high)}</span></div>` +
                    '</div>'
                );
            }).join('');

            card.innerHTML =
                '<div class="rc-head">' +
                '<span class="rc-eyebrow">Morning check-in</span>' +
                '<h3 class="rc-title">How do you feel this morning?</h3>' +
                '<p class="rc-sub">A few taps lets your coach adapt today to how you actually feel — not just what you ran.</p>' +
                '</div>' +
                '<div class="rc-sleep">' +
                '<div class="rc-scale-label">Hours slept</div>' +
                `<div class="rc-chips" role="group" aria-label="Hours slept">${hoursChips}</div>` +
                '</div>' +
                `<div class="rc-scales">${scaleRows}</div>` +
                '<div class="rc-actions">' +
                '<button type="button" class="rc-submit" id="rcSubmit" disabled>Log check-in</button>' +
                '<span class="rc-error" id="rcError" role="alert"></span>' +
                '</div>';

            this._bindForm();
            this._syncSubmit();
        },

        _bindForm() {
            const card = this._card();
            card.querySelectorAll('[data-hours]').forEach((btn) => {
                btn.onclick = () => {
                    const v = Number(btn.getAttribute('data-hours'));
                    const already = this._values.sleep_hours === v;
                    card.querySelectorAll('[data-hours]').forEach((b) => b.removeAttribute('aria-pressed'));
                    if (already) { delete this._values.sleep_hours; }
                    else { this._values.sleep_hours = v; btn.setAttribute('aria-pressed', 'true'); }
                    this._syncSubmit();
                };
            });
            card.querySelectorAll('[data-scale]').forEach((btn) => {
                btn.onclick = () => {
                    const key = btn.getAttribute('data-scale');
                    const v = Number(btn.getAttribute('data-val'));
                    const already = this._values[key] === v;
                    card.querySelectorAll(`[data-scale="${key}"]`).forEach((b) => b.removeAttribute('aria-pressed'));
                    if (already) { delete this._values[key]; }
                    else { this._values[key] = v; btn.setAttribute('aria-pressed', 'true'); }
                    this._syncSubmit();
                };
            });
            const submit = document.getElementById('rcSubmit');
            if (submit) submit.onclick = () => this._submit();
        },

        _syncSubmit() {
            const submit = document.getElementById('rcSubmit');
            if (submit) submit.disabled = Object.keys(this._values).length === 0;
        },

        async _submit() {
            const submit = document.getElementById('rcSubmit');
            const err = document.getElementById('rcError');
            if (err) err.textContent = '';
            if (submit) { submit.disabled = true; submit.textContent = 'Saving…'; }

            try {
                const res = await fetch('/api/readiness', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this._values),
                });
                if (!res.ok) throw new Error('save failed');
                const checkin = await res.json();
                this._renderLogged(checkin, true);
                this._refreshCoachNote();
                if (typeof this.onSaved === 'function') {
                    try { this.onSaved(checkin); } catch (e) { console.error('[checkin] onSaved', e); }
                }
            } catch (e) {
                if (err) err.textContent = 'Could not save your check-in. Try again.';
                if (submit) { submit.disabled = false; submit.textContent = 'Log check-in'; }
            }
        },

        /* ---------- logged verdict ---------- */
        _renderLogged(checkin, justSaved) {
            const card = this._card();
            const score = checkin.score != null ? Math.round(checkin.score) : '—';
            const bandClass = BAND_CLASS[checkin.band] || 'rc-band--ok';
            const drivers = (checkin.drivers || []);
            const hint = this._verdictHint(checkin);

            card.innerHTML =
                `<div class="rc-logged ${bandClass}">` +
                '<div class="rc-logged-main">' +
                `<div class="rc-ring"><span class="rc-ring-score">${score}</span><span class="rc-ring-max">/100</span></div>` +
                '<div class="rc-logged-copy">' +
                '<span class="rc-eyebrow">Today\'s readiness</span>' +
                `<h3 class="rc-logged-label">${this._esc(checkin.label || '')}</h3>` +
                `<p class="rc-logged-hint">${this._esc(hint)}</p>` +
                '</div>' +
                '</div>' +
                (drivers.length
                    ? `<div class="rc-drivers">${drivers.map((d) => `<span class="rc-driver">${this._esc(d)}</span>`).join('')}</div>`
                    : '') +
                '<button type="button" class="rc-edit" id="rcEdit">Update check-in</button>' +
                (justSaved ? '<span class="rc-saved" role="status">Saved ✓</span>' : '') +
                '</div>';

            const edit = document.getElementById('rcEdit');
            if (edit) edit.onclick = () => this._renderForm({
                sleep_hours: checkin.sleep_hours,
                sleep_quality: checkin.sleep_quality,
                energy: checkin.energy,
                soreness: checkin.soreness,
                stress: checkin.stress,
            });
        },

        /* One line under the verdict. Two constraints, both learned by putting
           this card next to today's session in the Today card: it must not
           claim the plan already moved (nothing changes without the runner
           going through Adjust my plan), and it must not point "below" — the
           session sits above the card on the plan page and below it on the
           Coach hub. */
        _verdictHint(checkin) {
            switch (checkin.band) {
                case 'primed':
                    return "You're fresh — a great morning to commit fully to today's session.";
                case 'good':
                    return 'Solid readiness. Run today as planned.';
                case 'ok':
                    return 'A little flat — keep an honest eye on effort today.';
                case 'run_down':
                case 'depleted':
                    return "Rough morning — ease today's session back, or move it with Adjust my plan.";
                default:
                    return 'Logged. Your coach will factor this into today.';
            }
        },

        /* Force the Coach's Note to re-fetch so it reflects the new check-in. */
        _refreshCoachNote() {
            const AD = window.AnalyticsDashboard;
            if (AD && typeof AD._loadCoachNote === 'function' && this.planId) {
                AD.coachNoteLoadedPlanId = undefined;
                AD._loadCoachNote(this.planId);
            }
        },
    };

    window.ReadinessCheckIn = RC;
})();
