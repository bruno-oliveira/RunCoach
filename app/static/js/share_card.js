/**
 * ShareCard — Canvas-based run share card generator for social media.
 *
 * Creates branded, downloadable images from run data.
 * Supports Instagram Post (1080x1080) and Story (1080x1920).
 * Three visual themes: Midnight (dark), Dawn (light), Dusk (deep).
 */
const ShareCard = {

    /* ------------------------------------------------------------------ */
    /*  Config                                                             */
    /* ------------------------------------------------------------------ */
    FORMATS: {
        square: { w: 1080, h: 1080, label: 'Post' },
        story:  { w: 1080, h: 1920, label: 'Story' },
    },

    THEMES: {
        midnight: {
            label: 'Midnight',
            bg:            ['#0F172A', '#162044', '#1E3A5F'],
            accent:        '#FF6246',
            accentSlash:   'rgba(255, 98, 70, 0.06)',
            textPrimary:   '#FFFFFF',
            textSecondary: '#94A3B8',
            textMuted:     '#475569',
            ringBg:        'rgba(255,255,255,0.08)',
            divider:       'rgba(255,255,255,0.08)',
            topoStroke:    '#FFFFFF',
            topoAlpha:     0.04,
            vdotBadgeBg:   'rgba(255, 98, 70, 0.12)',
        },
        dawn: {
            label: 'Dawn',
            bg:            ['#FAFAF7', '#F3F0E8', '#EBE6DC'],
            accent:        '#1D4ED8',
            accentSlash:   'rgba(29, 78, 216, 0.04)',
            textPrimary:   '#1C1917',
            textSecondary: '#6B6560',
            textMuted:     '#A09A93',
            ringBg:        'rgba(28, 25, 23, 0.06)',
            divider:       'rgba(28, 25, 23, 0.10)',
            topoStroke:    '#1D4ED8',
            topoAlpha:     0.05,
            vdotBadgeBg:   'rgba(29, 78, 216, 0.08)',
        },
        dusk: {
            label: 'Dusk',
            bg:            ['#0A0A12', '#140E20', '#1C1230'],
            accent:        '#C084FC',
            accentSlash:   'rgba(192, 132, 252, 0.05)',
            textPrimary:   '#F1F0FB',
            textSecondary: '#8B83A8',
            textMuted:     '#5B5475',
            ringBg:        'rgba(241,240,251,0.07)',
            divider:       'rgba(241,240,251,0.07)',
            topoStroke:    '#C084FC',
            topoAlpha:     0.035,
            vdotBadgeBg:   'rgba(192, 132, 252, 0.12)',
        },
    },

    QUALITY_COLORS: {
        'Nailed it': '#22C55E',
        'On track':  '#3B82F6',
        'Too easy':  '#EAB308',
        'Too hard':  '#EF4444',
        'Easy':      '#22C55E',
        'Moderate':  '#3B82F6',
        'Hard':      '#F97316',
        'Max':       '#EF4444',
    },

    WORKOUT_COLORS: {
        easy:     '#22C55E',
        recovery: '#22C55E',
        tempo:    '#F97316',
        interval: '#EF4444',
        long:     '#3B82F6',
        hill:     '#8B5CF6',
        race:     '#EC4899',
    },

    // Fonts (from design system, loaded via Google Fonts on the page)
    FONT_DISPLAY: '"Bricolage Grotesque", Georgia, serif',
    FONT_BODY:    '"DM Sans", sans-serif',
    FONT_MONO:    '"JetBrains Mono", monospace',

    // Current state
    _modal: null,
    _canvas: null,
    _currentRun: null,
    _currentFormat: 'square',
    _currentTheme: 'midnight',

    /** Shortcut to the active theme palette. */
    _t() { return this.THEMES[this._currentTheme]; },

    /* ------------------------------------------------------------------ */
    /*  Public API                                                         */
    /* ------------------------------------------------------------------ */

    /** Open the share modal for a given run object. */
    async open(runData) {
        this._currentRun = runData;
        this._currentFormat = 'square';
        this._ensureModal();
        this._modal.classList.add('share-modal--open');
        document.body.style.overflow = 'hidden';
        await document.fonts.ready;
        this._render();
    },

    close() {
        if (this._modal) {
            this._modal.classList.remove('share-modal--open');
            document.body.style.overflow = '';
        }
    },

    /* ------------------------------------------------------------------ */
    /*  Modal DOM                                                          */
    /* ------------------------------------------------------------------ */
    _ensureModal() {
        if (this._modal) return;

        const themeButtons = Object.entries(this.THEMES).map(([key, t]) => {
            const active = key === this._currentTheme ? ' share-theme-btn--active' : '';
            const swatch = t.bg[0];
            return `<button class="share-theme-btn${active}" data-theme="${key}">
                <span class="share-theme-swatch" style="background:${swatch}"></span>
                ${t.label}
            </button>`;
        }).join('');

        const modal = document.createElement('div');
        modal.className = 'share-modal';
        modal.innerHTML = `
            <div class="share-modal-backdrop"></div>
            <div class="share-modal-panel">
                <div class="share-modal-header">
                    <h3 class="share-modal-title">Share Your Run</h3>
                    <button class="share-modal-close" aria-label="Close">&times;</button>
                </div>
                <div class="share-modal-controls">
                    <div class="share-modal-formats">
                        <button class="share-format-btn share-format-btn--active" data-fmt="square">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="12" height="12" rx="1.5"/></svg>
                            Post
                        </button>
                        <button class="share-format-btn" data-fmt="story">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="1" width="8" height="14" rx="1.5"/></svg>
                            Story
                        </button>
                    </div>
                    <div class="share-modal-themes">${themeButtons}</div>
                </div>
                <div class="share-modal-preview">
                    <canvas id="shareCardCanvas"></canvas>
                </div>
                <div class="share-modal-actions">
                    <button class="share-action-btn share-action-btn--primary" id="shareDownloadBtn">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                        Save Image
                    </button>
                    <button class="share-action-btn" id="shareCopyBtn">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                        Copy
                    </button>
                    <button class="share-action-btn" id="shareNativeBtn" style="display:none">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
                        Share
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        this._modal = modal;
        this._canvas = modal.querySelector('#shareCardCanvas');

        // Bind events
        modal.querySelector('.share-modal-backdrop').addEventListener('click', () => this.close());
        modal.querySelector('.share-modal-close').addEventListener('click', () => this.close());

        // Format buttons
        modal.querySelectorAll('.share-format-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                modal.querySelectorAll('.share-format-btn').forEach(b => b.classList.remove('share-format-btn--active'));
                btn.classList.add('share-format-btn--active');
                this._currentFormat = btn.dataset.fmt;
                this._render();
            });
        });

        // Theme buttons
        modal.querySelectorAll('.share-theme-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                modal.querySelectorAll('.share-theme-btn').forEach(b => b.classList.remove('share-theme-btn--active'));
                btn.classList.add('share-theme-btn--active');
                this._currentTheme = btn.dataset.theme;
                this._render();
            });
        });

        modal.querySelector('#shareDownloadBtn').addEventListener('click', () => this._download());
        modal.querySelector('#shareCopyBtn').addEventListener('click', () => this._copyToClipboard());

        // Web Share API (mobile)
        if (navigator.canShare) {
            modal.querySelector('#shareNativeBtn').style.display = '';
            modal.querySelector('#shareNativeBtn').addEventListener('click', () => this._nativeShare());
        }

        // Esc key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.close();
        });
    },

    /* ------------------------------------------------------------------ */
    /*  Render Pipeline                                                    */
    /* ------------------------------------------------------------------ */
    _render() {
        const fmt = this.FORMATS[this._currentFormat];
        const canvas = this._canvas;
        const dpr = 2; // HiDPI
        canvas.width = fmt.w * dpr;
        canvas.height = fmt.h * dpr;
        canvas.style.width = '100%';
        canvas.style.height = 'auto';
        canvas.style.maxHeight = '65vh';
        canvas.style.objectFit = 'contain';

        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);

        const run = this._currentRun;
        const w = fmt.w;
        const h = fmt.h;

        this._drawBackground(ctx, w, h);
        this._drawTopoLines(ctx, w, h);
        this._drawAccentSlash(ctx, w, h);

        if (this._currentFormat === 'story') {
            this._drawStoryLayout(ctx, run, w, h);
        } else {
            this._drawSquareLayout(ctx, run, w, h);
        }
    },

    /* ------------------------------------------------------------------ */
    /*  Background                                                         */
    /* ------------------------------------------------------------------ */
    _drawBackground(ctx, w, h) {
        const t = this._t();
        const grad = ctx.createLinearGradient(0, 0, w * 0.3, h);
        grad.addColorStop(0, t.bg[0]);
        grad.addColorStop(0.5, t.bg[1]);
        grad.addColorStop(1, t.bg[2]);
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, w, h);
    },

    /** Subtle topographic contour lines — RunCoach's unique visual signature. */
    _drawTopoLines(ctx, w, h) {
        const t = this._t();
        ctx.save();
        ctx.globalAlpha = t.topoAlpha;
        ctx.strokeStyle = t.topoStroke;
        ctx.lineWidth = 1.2;

        const lines = 20;
        for (let i = 0; i < lines; i++) {
            ctx.beginPath();
            const yBase = (h / lines) * i;
            const phase = i * 0.8;
            for (let x = 0; x <= w; x += 3) {
                const y = yBase
                    + Math.sin(x * 0.006 + phase) * 35
                    + Math.sin(x * 0.002 + phase * 1.5) * 25
                    + Math.cos(x * 0.01 + i) * 10;
                if (x === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }
        ctx.restore();
    },

    /** Diagonal accent stripe for visual pop. */
    _drawAccentSlash(ctx, w, h) {
        const t = this._t();
        ctx.save();
        const grad = ctx.createLinearGradient(w * 0.6, 0, w, h * 0.4);
        grad.addColorStop(0, 'rgba(0,0,0,0)');
        grad.addColorStop(0.5, t.accentSlash);
        grad.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(w * 0.55, 0);
        ctx.lineTo(w, 0);
        ctx.lineTo(w, h * 0.6);
        ctx.lineTo(w * 0.35, h);
        ctx.lineTo(0, h);
        ctx.lineTo(0, h * 0.5);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
    },

    /* ------------------------------------------------------------------ */
    /*  Square Layout (1080x1080)                                          */
    /* ------------------------------------------------------------------ */
    _drawSquareLayout(ctx, run, w, h) {
        const t = this._t();
        const pad = 72;
        let y = pad;

        // ── Branding ──
        y = this._drawBranding(ctx, pad, y, w);
        y += 12;

        // ── Date + Workout Type ──
        y = this._drawDateRow(ctx, run, pad, y, w);
        y += 36;

        // ── Hero: distance ──
        const distStr = run.distance_km ? run.distance_km.toFixed(1) : '0.0';
        ctx.font = `800 140px ${this.FONT_DISPLAY}`;
        ctx.fillStyle = t.textPrimary;
        ctx.textAlign = 'left';
        ctx.fillText(distStr, pad, y + 120);
        // "km" unit
        const distWidth = ctx.measureText(distStr).width;
        ctx.font = `500 36px ${this.FONT_BODY}`;
        ctx.fillStyle = t.textSecondary;
        ctx.fillText('km', pad + distWidth + 12, y + 120);
        y += 150;

        // ── Duration + Pace row ──
        y = this._drawTimePaceRow(ctx, run, pad, y, w);

        // ── Quality Ring (right side) ──
        if (run.effort_quality_score || run.quality_label) {
            this._drawQualityRing(ctx, run, w - pad - 100, 295, 85);
        } else if (run.vdot) {
            this._drawVdotBadge(ctx, run.vdot, w - pad - 80, 290);
        }

        // ── Divider ──
        y += 40;
        this._drawDivider(ctx, pad, y, w - pad);
        y += 40;

        // ── Secondary stats ──
        y = this._drawSecondaryStats(ctx, run, pad, y, w);

        // ── VDOT (if quality ring was drawn, show VDOT below stats) ──
        if (run.vdot && (run.effort_quality_score || run.quality_label)) {
            y += 24;
            y = this._drawVdotRow(ctx, run.vdot, pad, y, w);
        }

        // ── Footer ──
        this._drawFooter(ctx, w, h, pad);
    },

    /* ------------------------------------------------------------------ */
    /*  Story Layout (1080x1920)                                           */
    /* ------------------------------------------------------------------ */
    _drawStoryLayout(ctx, run, w, h) {
        const t = this._t();
        const pad = 72;
        let y = 100;

        // ── Branding ──
        y = this._drawBranding(ctx, pad, y, w);
        y += 40;

        // ── Date + Workout Type ──
        y = this._drawDateRow(ctx, run, pad, y, w);
        y += 80;

        // ── Hero: distance (centered) ──
        const distStr = run.distance_km ? run.distance_km.toFixed(1) : '0.0';
        ctx.font = `800 200px ${this.FONT_DISPLAY}`;
        ctx.fillStyle = t.textPrimary;
        ctx.textAlign = 'center';
        ctx.fillText(distStr, w / 2, y + 170);
        ctx.font = `500 48px ${this.FONT_BODY}`;
        ctx.fillStyle = t.textSecondary;
        ctx.fillText('km', w / 2, y + 230);
        y += 280;

        // ── Duration + Pace (centered) ──
        const duration = this._formatDuration(run.duration_minutes);
        ctx.font = `600 64px ${this.FONT_MONO}`;
        ctx.fillStyle = t.textPrimary;
        ctx.fillText(duration, w / 2, y);
        y += 56;

        const pace = run.avg_pace_min_km > 0 ? this._formatPace(run.avg_pace_min_km) + ' /km' : '';
        if (pace) {
            ctx.font = `500 36px ${this.FONT_MONO}`;
            ctx.fillStyle = t.textSecondary;
            ctx.fillText(pace, w / 2, y);
        }
        y += 80;

        // ── Quality Ring (centered) ──
        if (run.effort_quality_score || run.quality_label) {
            this._drawQualityRing(ctx, run, w / 2, y + 100, 110);
            y += 280;
        } else if (run.vdot) {
            this._drawVdotBadge(ctx, run.vdot, w / 2, y + 30);
            y += 120;
        } else {
            y += 20;
        }

        // ── Divider ──
        this._drawDivider(ctx, pad, y, w - pad);
        y += 50;

        // ── Secondary stats (centered, vertical) ──
        y = this._drawStoryStats(ctx, run, pad, y, w);

        // ── VDOT row ──
        if (run.vdot && (run.effort_quality_score || run.quality_label)) {
            y += 30;
            ctx.textAlign = 'center';
            ctx.font = `600 28px ${this.FONT_MONO}`;
            ctx.fillStyle = t.accent;
            ctx.fillText(`VDOT ${run.vdot.toFixed(1)}`, w / 2, y);
        }

        // ── Footer ──
        this._drawFooter(ctx, w, h, pad);
    },

    /* ------------------------------------------------------------------ */
    /*  Shared Drawing Helpers                                             */
    /* ------------------------------------------------------------------ */
    _drawBranding(ctx, pad, y, w) {
        const t = this._t();
        ctx.font = `700 18px ${this.FONT_DISPLAY}`;
        ctx.fillStyle = t.accent;
        ctx.textAlign = 'left';
        // Manual letter spacing for canvas
        const brand = 'RUNCOACH';
        let bx = pad;
        for (const ch of brand) {
            ctx.fillText(ch, bx, y);
            bx += ctx.measureText(ch).width + 4;
        }
        return y + 12;
    },

    _drawDateRow(ctx, run, pad, y, w) {
        const t = this._t();
        const type = run.workout_type
            ? run.workout_type.charAt(0).toUpperCase() + run.workout_type.slice(1)
            : '';

        // Date — larger, primary weight
        const dateStr = run.date
            ? new Date(run.date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
            : '';

        ctx.textAlign = 'left';
        ctx.font = `600 26px ${this.FONT_BODY}`;
        ctx.fillStyle = t.textSecondary;
        ctx.fillText(dateStr, pad, y + 26);

        // Workout type pill
        if (type) {
            const pillColor = this.WORKOUT_COLORS[run.workout_type] || t.accent;
            const pillText = type + ' Run';
            ctx.font = `600 18px ${this.FONT_BODY}`;
            const tw = ctx.measureText(pillText).width;
            const px = pad + ctx.measureText(dateStr).width + 20;
            // Pill background
            const pillH = 28, pillR = 14;
            ctx.fillStyle = pillColor + '22'; // 13% opacity
            this._roundRect(ctx, px - 10, y + 8, tw + 20, pillH, pillR);
            ctx.fill();
            // Pill text
            ctx.fillStyle = pillColor;
            ctx.fillText(pillText, px, y + 27);
        }

        return y + 40;
    },

    _drawTimePaceRow(ctx, run, pad, y, w) {
        const t = this._t();
        const duration = this._formatDuration(run.duration_minutes);
        ctx.font = `600 48px ${this.FONT_MONO}`;
        ctx.fillStyle = t.textPrimary;
        ctx.textAlign = 'left';
        ctx.fillText(duration, pad, y + 48);

        const pace = run.avg_pace_min_km > 0 ? this._formatPace(run.avg_pace_min_km) + ' /km' : '';
        if (pace) {
            const durWidth = ctx.measureText(duration).width;
            ctx.font = `500 28px ${this.FONT_MONO}`;
            ctx.fillStyle = t.textSecondary;
            ctx.fillText(pace, pad + durWidth + 32, y + 48);
        }

        return y + 60;
    },

    /** Effort quality arc ring. */
    _drawQualityRing(ctx, run, cx, cy, radius) {
        const t = this._t();
        const score = run.effort_quality_score || 0;
        const label = run.quality_label || '';
        const color = this.QUALITY_COLORS[label] || t.accent;

        // Background ring
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.strokeStyle = t.ringBg;
        ctx.lineWidth = 10;
        ctx.stroke();

        // Score arc (from top, clockwise)
        const startAngle = -Math.PI / 2;
        const endAngle = startAngle + (Math.PI * 2 * Math.min(score, 100) / 100);
        ctx.beginPath();
        ctx.arc(cx, cy, radius, startAngle, endAngle);
        ctx.strokeStyle = color;
        ctx.lineWidth = 10;
        ctx.lineCap = 'round';
        ctx.stroke();

        // Glow effect
        ctx.save();
        ctx.shadowColor = color;
        ctx.shadowBlur = 20;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, startAngle, endAngle);
        ctx.strokeStyle = color;
        ctx.lineWidth = 4;
        ctx.stroke();
        ctx.restore();

        // Score number
        ctx.font = `700 42px ${this.FONT_DISPLAY}`;
        ctx.fillStyle = t.textPrimary;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(Math.round(score), cx, cy - 8);

        // Label
        if (label) {
            ctx.font = `600 16px ${this.FONT_BODY}`;
            ctx.fillStyle = color;
            ctx.fillText(label, cx, cy + 28);
        }

        ctx.textBaseline = 'alphabetic';
    },

    _drawVdotBadge(ctx, vdot, cx, cy) {
        const t = this._t();
        ctx.textAlign = 'center';
        const bw = 120, bh = 52, br = 12;
        ctx.fillStyle = t.vdotBadgeBg;
        this._roundRect(ctx, cx - bw / 2, cy - bh / 2, bw, bh, br);
        ctx.fill();

        ctx.font = `600 14px ${this.FONT_BODY}`;
        ctx.fillStyle = t.accent;
        ctx.fillText('VDOT', cx, cy - 6);
        ctx.font = `700 22px ${this.FONT_MONO}`;
        ctx.fillText(vdot.toFixed(1), cx, cy + 18);
    },

    _drawVdotRow(ctx, vdot, pad, y, w) {
        const t = this._t();
        ctx.textAlign = 'left';
        ctx.font = `600 16px ${this.FONT_BODY}`;
        ctx.fillStyle = t.accent;
        ctx.fillText('VDOT', pad, y);
        ctx.font = `700 24px ${this.FONT_MONO}`;
        ctx.fillStyle = t.textPrimary;
        ctx.fillText(vdot.toFixed(1), pad + 60, y);
        return y + 10;
    },

    _drawDivider(ctx, x1, y, x2) {
        const t = this._t();
        ctx.beginPath();
        ctx.moveTo(x1, y);
        ctx.lineTo(x2, y);
        ctx.strokeStyle = t.divider;
        ctx.lineWidth = 1;
        ctx.stroke();
    },

    _drawSecondaryStats(ctx, run, pad, y, w) {
        const t = this._t();
        const stats = [];
        if (run.avg_heart_rate > 0)    stats.push({ icon: '\u2665', value: Math.round(run.avg_heart_rate), unit: 'bpm', color: '#EF4444' });
        if (run.elevation_gain_m > 0)  stats.push({ icon: '\u25B2', value: run.elevation_gain_m, unit: 'm', color: '#22C55E' });
        if (run.avg_cadence > 0)       stats.push({ icon: '\u26A1', value: Math.round(run.avg_cadence), unit: 'spm', color: '#EAB308' });
        if (run.perceived_effort > 0)  stats.push({ icon: '\u{1F4AA}', value: run.perceived_effort, unit: '/10', color: '#8B5CF6' });

        if (stats.length === 0) return y;

        const colW = (w - pad * 2) / stats.length;
        ctx.textAlign = 'center';

        stats.forEach((s, i) => {
            const cx = pad + colW * i + colW / 2;

            ctx.font = `20px ${this.FONT_BODY}`;
            ctx.fillStyle = s.color;
            ctx.fillText(s.icon, cx, y);

            ctx.font = `700 32px ${this.FONT_MONO}`;
            ctx.fillStyle = t.textPrimary;
            ctx.fillText(String(s.value), cx, y + 40);

            ctx.font = `500 16px ${this.FONT_BODY}`;
            ctx.fillStyle = t.textMuted;
            ctx.fillText(s.unit, cx, y + 62);
        });

        return y + 80;
    },

    /** Vertical stat blocks for story layout. */
    _drawStoryStats(ctx, run, pad, y, w) {
        const t = this._t();
        const stats = [];
        if (run.avg_heart_rate > 0)    stats.push({ icon: '\u2665', value: Math.round(run.avg_heart_rate), unit: 'bpm', color: '#EF4444' });
        if (run.elevation_gain_m > 0)  stats.push({ icon: '\u25B2', value: run.elevation_gain_m, unit: 'm', color: '#22C55E' });
        if (run.avg_cadence > 0)       stats.push({ icon: '\u26A1', value: Math.round(run.avg_cadence), unit: 'spm', color: '#EAB308' });
        if (run.perceived_effort > 0)  stats.push({ icon: '\u{1F4AA}', value: run.perceived_effort, unit: '/10', color: '#8B5CF6' });

        if (stats.length === 0) return y;

        const colW = (w - pad * 2) / stats.length;
        ctx.textAlign = 'center';

        stats.forEach((s, i) => {
            const cx = pad + colW * i + colW / 2;

            ctx.font = `24px ${this.FONT_BODY}`;
            ctx.fillStyle = s.color;
            ctx.fillText(s.icon, cx, y);

            ctx.font = `700 40px ${this.FONT_MONO}`;
            ctx.fillStyle = t.textPrimary;
            ctx.fillText(String(s.value), cx, y + 48);

            ctx.font = `500 18px ${this.FONT_BODY}`;
            ctx.fillStyle = t.textMuted;
            ctx.fillText(s.unit, cx, y + 72);
        });

        return y + 100;
    },

    _drawFooter(ctx, w, h, pad) {
        const t = this._t();
        const fy = h - pad + 10;

        this._drawDivider(ctx, pad, fy - 36, w - pad);

        ctx.textAlign = 'center';
        ctx.font = `700 16px ${this.FONT_DISPLAY}`;
        ctx.fillStyle = t.textMuted;
        const brand = 'runcoach';
        let totalW = 0;
        for (const ch of brand) totalW += ctx.measureText(ch).width + 2.5;
        let bx = (w - totalW) / 2;
        for (const ch of brand) {
            ctx.fillText(ch, bx, fy);
            bx += ctx.measureText(ch).width + 2.5;
        }
    },

    /* ------------------------------------------------------------------ */
    /*  Utility                                                            */
    /* ------------------------------------------------------------------ */
    _formatPace(pace) {
        if (!pace || pace <= 0) return '--';
        const mins = Math.floor(pace);
        const secs = Math.round((pace - mins) * 60);
        return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
    },

    _formatDuration(minutes) {
        if (!minutes || minutes <= 0) return '--:--';
        const h = Math.floor(minutes / 60);
        const m = Math.floor(minutes % 60);
        const s = Math.round((minutes % 1) * 60);
        if (h > 0) {
            return `${h}:${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
        }
        return `${m}:${s < 10 ? '0' : ''}${s}`;
    },

    _roundRect(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    },

    /* ------------------------------------------------------------------ */
    /*  Export                                                              */
    /* ------------------------------------------------------------------ */
    _toBlob() {
        return new Promise(resolve => this._canvas.toBlob(resolve, 'image/png'));
    },

    async _download() {
        const blob = await this._toBlob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        const run = this._currentRun;
        const datePart = run.date ? new Date(run.date).toISOString().slice(0, 10) : 'run';
        const distPart = run.distance_km ? run.distance_km.toFixed(1) : '';
        a.href = url;
        a.download = `runcoach-${datePart}-${distPart}km.png`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        this._flashButton('shareDownloadBtn', 'Saved!');
    },

    async _copyToClipboard() {
        try {
            const blob = await this._toBlob();
            await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
            this._flashButton('shareCopyBtn', 'Copied!');
        } catch {
            this._download();
        }
    },

    async _nativeShare() {
        try {
            const blob = await this._toBlob();
            const run = this._currentRun;
            const dist = run.distance_km ? run.distance_km.toFixed(1) : '';
            const file = new File([blob], `runcoach-${dist}km.png`, { type: 'image/png' });
            await navigator.share({
                title: `${dist} km run`,
                files: [file],
            });
        } catch (err) {
            if (err.name !== 'AbortError') {
                this._download();
            }
        }
    },

    _flashButton(id, text) {
        const btn = document.getElementById(id);
        if (!btn) return;
        const orig = btn.innerHTML;
        btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> ${text}`;
        btn.classList.add('share-action-btn--success');
        setTimeout(() => {
            btn.innerHTML = orig;
            btn.classList.remove('share-action-btn--success');
        }, 2000);
    },
};

// Make accessible globally
window.ShareCard = ShareCard;
