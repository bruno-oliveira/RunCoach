/**
 * share_renderer.js — Canvas rendering methods for ShareCard.
 *
 * Depends on share_card.js (window.ShareCard must already exist).
 * Attaches _render() and all _draw*() helpers onto the ShareCard object.
 */
(function () {
    'use strict';

    var SC = window.ShareCard;

    /* -------------------------------------------------------------- */
    /*  Render Pipeline                                                */
    /* -------------------------------------------------------------- */

    SC._render = function () {
        var fmt = this.FORMATS[this._currentFormat];
        var canvas = this._canvas;
        var dpr = 2; // HiDPI
        canvas.width = fmt.w * dpr;
        canvas.height = fmt.h * dpr;
        canvas.style.width = '100%';
        canvas.style.height = 'auto';
        canvas.style.maxHeight = '65vh';
        canvas.style.objectFit = 'contain';

        var ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);

        var run = this._currentRun;
        var w = fmt.w;
        var h = fmt.h;

        this._drawBackground(ctx, w, h);
        this._drawTopoLines(ctx, w, h);
        this._drawAccentSlash(ctx, w, h);

        if (this._currentFormat === 'story') {
            this._drawStoryLayout(ctx, run, w, h);
        } else {
            this._drawSquareLayout(ctx, run, w, h);
        }
    };

    /* -------------------------------------------------------------- */
    /*  Background                                                     */
    /* -------------------------------------------------------------- */

    SC._drawBackground = function (ctx, w, h) {
        var t = this._t();
        var grad = ctx.createLinearGradient(0, 0, w * 0.3, h);
        grad.addColorStop(0, t.bg[0]);
        grad.addColorStop(0.5, t.bg[1]);
        grad.addColorStop(1, t.bg[2]);
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, w, h);
    };

    /** Subtle topographic contour lines. */
    SC._drawTopoLines = function (ctx, w, h) {
        var t = this._t();
        ctx.save();
        ctx.globalAlpha = t.topoAlpha;
        ctx.strokeStyle = t.topoStroke;
        ctx.lineWidth = 1.2;

        var lines = 20;
        for (var i = 0; i < lines; i++) {
            ctx.beginPath();
            var yBase = (h / lines) * i;
            var phase = i * 0.8;
            for (var x = 0; x <= w; x += 3) {
                var y = yBase
                    + Math.sin(x * 0.006 + phase) * 35
                    + Math.sin(x * 0.002 + phase * 1.5) * 25
                    + Math.cos(x * 0.01 + i) * 10;
                if (x === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }
        ctx.restore();
    };

    /** Diagonal accent stripe for visual pop. */
    SC._drawAccentSlash = function (ctx, w, h) {
        var t = this._t();
        ctx.save();
        var grad = ctx.createLinearGradient(w * 0.6, 0, w, h * 0.4);
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
    };

    /* -------------------------------------------------------------- */
    /*  Square Layout (1080x1080)                                      */
    /* -------------------------------------------------------------- */

    SC._drawSquareLayout = function (ctx, run, w, h) {
        var t = this._t();
        var pad = 72;
        var y = pad;

        // Branding
        y = this._drawBranding(ctx, pad, y, w);
        y += 12;

        // Date + Workout Type
        y = this._drawDateRow(ctx, run, pad, y, w);
        y += 48;

        // Hero: distance
        var distStr = run.distance_km ? run.distance_km.toFixed(1) : '0.0';
        ctx.font = '800 140px ' + this.FONT_DISPLAY;
        ctx.fillStyle = t.textPrimary;
        ctx.textAlign = 'left';
        ctx.fillText(distStr, pad, y + 120);
        var distWidth = ctx.measureText(distStr).width;
        ctx.font = '500 36px ' + this.FONT_BODY;
        ctx.fillStyle = t.textSecondary;
        ctx.fillText('km', pad + distWidth + 12, y + 120);
        y += 150;

        // Duration + Pace row
        y = this._drawTimePaceRow(ctx, run, pad, y, w);

        // Quality Ring (right side)
        if (run.effort_quality_score || run.quality_label) {
            this._drawQualityRing(ctx, run, w - pad - 100, 280, 85);
        } else if (run.vdot) {
            this._drawVdotBadge(ctx, run.vdot, w - pad - 80, 290);
        }

        // Divider
        y += 40;
        this._drawDivider(ctx, pad, y, w - pad);
        y += 40;

        // Secondary stats
        y = this._drawSecondaryStats(ctx, run, pad, y, w);

        // VDOT (if quality ring was drawn, show VDOT below stats)
        if (run.vdot && (run.effort_quality_score || run.quality_label)) {
            y += 24;
            y = this._drawVdotRow(ctx, run.vdot, pad, y, w);
        }

        // Footer
        this._drawFooter(ctx, w, h, pad);
    };

    /* -------------------------------------------------------------- */
    /*  Story Layout (1080x1920)                                       */
    /* -------------------------------------------------------------- */

    SC._drawStoryLayout = function (ctx, run, w, h) {
        var t = this._t();
        var pad = 72;
        var y = 100;

        // Branding
        y = this._drawBranding(ctx, pad, y, w);
        y += 40;

        // Date + Workout Type
        y = this._drawDateRow(ctx, run, pad, y, w);
        y += 100;

        // Hero: distance (centered)
        var distStr = run.distance_km ? run.distance_km.toFixed(1) : '0.0';
        ctx.font = '800 200px ' + this.FONT_DISPLAY;
        ctx.fillStyle = t.textPrimary;
        ctx.textAlign = 'center';
        ctx.fillText(distStr, w / 2, y + 170);
        ctx.font = '500 48px ' + this.FONT_BODY;
        ctx.fillStyle = t.textSecondary;
        ctx.fillText('km', w / 2, y + 230);
        y += 280;

        // Duration + Pace (centered)
        var duration = this._formatDuration(run.duration_minutes);
        ctx.font = '600 64px ' + this.FONT_MONO;
        ctx.fillStyle = t.textPrimary;
        ctx.fillText(duration, w / 2, y);
        y += 56;

        var pace = run.avg_pace_min_km > 0 ? this._formatPace(run.avg_pace_min_km) + ' /km' : '';
        if (pace) {
            ctx.font = '500 36px ' + this.FONT_MONO;
            ctx.fillStyle = t.textSecondary;
            ctx.fillText(pace, w / 2, y);
        }
        y += 80;

        // Quality Ring (centered)
        if (run.effort_quality_score || run.quality_label) {
            this._drawQualityRing(ctx, run, w / 2, y + 100, 110);
            y += 280;
        } else if (run.vdot) {
            this._drawVdotBadge(ctx, run.vdot, w / 2, y + 30);
            y += 120;
        } else {
            y += 20;
        }

        // Divider
        this._drawDivider(ctx, pad, y, w - pad);
        y += 50;

        // Secondary stats (centered, vertical)
        y = this._drawStoryStats(ctx, run, pad, y, w);

        // VDOT row
        if (run.vdot && (run.effort_quality_score || run.quality_label)) {
            y += 30;
            ctx.textAlign = 'center';
            ctx.font = '600 28px ' + this.FONT_MONO;
            ctx.fillStyle = t.accent;
            ctx.fillText('VDOT ' + run.vdot.toFixed(1), w / 2, y);
        }

        // Footer
        this._drawFooter(ctx, w, h, pad);
    };

    /* -------------------------------------------------------------- */
    /*  Shared Drawing Helpers                                         */
    /* -------------------------------------------------------------- */

    SC._drawBranding = function (ctx, pad, y, w) {
        var t = this._t();
        ctx.font = '700 18px ' + this.FONT_DISPLAY;
        ctx.fillStyle = t.accent;
        ctx.textAlign = 'left';
        var brand = 'RUNCOACH';
        var bx = pad;
        for (var i = 0; i < brand.length; i++) {
            var ch = brand[i];
            ctx.fillText(ch, bx, y);
            bx += ctx.measureText(ch).width + 4;
        }
        return y + 12;
    };

    SC._drawDateRow = function (ctx, run, pad, y, w) {
        var t = this._t();
        var date = run.date
            ? new Date(run.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
            : '';
        var type = run.workout_type
            ? run.workout_type.charAt(0).toUpperCase() + run.workout_type.slice(1)
            : '';

        ctx.font = '500 22px ' + this.FONT_BODY;
        ctx.fillStyle = t.textSecondary;
        ctx.textAlign = 'left';

        var label = date;
        if (type) label += ' \u00B7 ' + type + ' Run';
        ctx.fillText(label, pad, y + 22);

        if (run.workout_type && this.WORKOUT_COLORS[run.workout_type]) {
            var dotX = pad + ctx.measureText(label).width + 16;
            ctx.beginPath();
            ctx.arc(dotX, y + 17, 5, 0, Math.PI * 2);
            ctx.fillStyle = this.WORKOUT_COLORS[run.workout_type];
            ctx.fill();
        }

        return y + 30;
    };

    SC._drawTimePaceRow = function (ctx, run, pad, y, w) {
        var t = this._t();
        var duration = this._formatDuration(run.duration_minutes);
        ctx.font = '600 48px ' + this.FONT_MONO;
        ctx.fillStyle = t.textPrimary;
        ctx.textAlign = 'left';
        ctx.fillText(duration, pad, y + 48);

        var pace = run.avg_pace_min_km > 0 ? this._formatPace(run.avg_pace_min_km) + ' /km' : '';
        if (pace) {
            var durWidth = ctx.measureText(duration).width;
            ctx.font = '500 28px ' + this.FONT_MONO;
            ctx.fillStyle = t.textSecondary;
            ctx.fillText(pace, pad + durWidth + 32, y + 48);
        }

        return y + 60;
    };

    /** Effort quality arc ring. */
    SC._drawQualityRing = function (ctx, run, cx, cy, radius) {
        var t = this._t();
        var score = run.effort_quality_score || 0;
        var label = run.quality_label || '';
        var color = this.QUALITY_COLORS[label] || t.accent;

        // Background ring
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.strokeStyle = t.ringBg;
        ctx.lineWidth = 10;
        ctx.stroke();

        // Score arc (from top, clockwise)
        var startAngle = -Math.PI / 2;
        var endAngle = startAngle + (Math.PI * 2 * Math.min(score, 100) / 100);
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
        ctx.font = '700 42px ' + this.FONT_DISPLAY;
        ctx.fillStyle = t.textPrimary;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(Math.round(score), cx, cy - 8);

        // Label
        if (label) {
            ctx.font = '600 16px ' + this.FONT_BODY;
            ctx.fillStyle = color;
            ctx.fillText(label, cx, cy + 28);
        }

        ctx.textBaseline = 'alphabetic';
    };

    SC._drawVdotBadge = function (ctx, vdot, cx, cy) {
        var t = this._t();
        ctx.textAlign = 'center';
        var bw = 120, bh = 52, br = 12;
        ctx.fillStyle = t.vdotBadgeBg;
        this._roundRect(ctx, cx - bw / 2, cy - bh / 2, bw, bh, br);
        ctx.fill();

        ctx.font = '600 14px ' + this.FONT_BODY;
        ctx.fillStyle = t.accent;
        ctx.fillText('VDOT', cx, cy - 6);
        ctx.font = '700 22px ' + this.FONT_MONO;
        ctx.fillText(vdot.toFixed(1), cx, cy + 18);
    };

    SC._drawVdotRow = function (ctx, vdot, pad, y, w) {
        var t = this._t();
        ctx.textAlign = 'left';
        ctx.font = '600 16px ' + this.FONT_BODY;
        ctx.fillStyle = t.accent;
        ctx.fillText('VDOT', pad, y);
        ctx.font = '700 24px ' + this.FONT_MONO;
        ctx.fillStyle = t.textPrimary;
        ctx.fillText(vdot.toFixed(1), pad + 60, y);
        return y + 10;
    };

    SC._drawDivider = function (ctx, x1, y, x2) {
        var t = this._t();
        ctx.beginPath();
        ctx.moveTo(x1, y);
        ctx.lineTo(x2, y);
        ctx.strokeStyle = t.divider;
        ctx.lineWidth = 1;
        ctx.stroke();
    };

    SC._drawSecondaryStats = function (ctx, run, pad, y, w) {
        var t = this._t();
        var stats = [];
        if (run.avg_heart_rate > 0)    stats.push({ icon: '\u2665', value: Math.round(run.avg_heart_rate), unit: 'bpm', color: '#EF4444' });
        if (run.elevation_gain_m > 0)  stats.push({ icon: '\u25B2', value: run.elevation_gain_m, unit: 'm', color: '#22C55E' });
        if (run.avg_cadence > 0)       stats.push({ icon: '\u26A1', value: Math.round(run.avg_cadence), unit: 'spm', color: '#EAB308' });
        if (run.perceived_effort > 0)  stats.push({ icon: '\uD83D\uDCAA', value: run.perceived_effort, unit: '/10', color: '#8B5CF6' });

        if (stats.length === 0) return y;

        var colW = (w - pad * 2) / stats.length;
        ctx.textAlign = 'center';

        stats.forEach(function (s, i) {
            var cx = pad + colW * i + colW / 2;

            ctx.font = '20px ' + SC.FONT_BODY;
            ctx.fillStyle = s.color;
            ctx.fillText(s.icon, cx, y);

            ctx.font = '700 32px ' + SC.FONT_MONO;
            ctx.fillStyle = t.textPrimary;
            ctx.fillText(String(s.value), cx, y + 40);

            ctx.font = '500 16px ' + SC.FONT_BODY;
            ctx.fillStyle = t.textMuted;
            ctx.fillText(s.unit, cx, y + 62);
        });

        return y + 80;
    };

    /** Vertical stat blocks for story layout. */
    SC._drawStoryStats = function (ctx, run, pad, y, w) {
        var t = this._t();
        var stats = [];
        if (run.avg_heart_rate > 0)    stats.push({ icon: '\u2665', value: Math.round(run.avg_heart_rate), unit: 'bpm', color: '#EF4444' });
        if (run.elevation_gain_m > 0)  stats.push({ icon: '\u25B2', value: run.elevation_gain_m, unit: 'm', color: '#22C55E' });
        if (run.avg_cadence > 0)       stats.push({ icon: '\u26A1', value: Math.round(run.avg_cadence), unit: 'spm', color: '#EAB308' });
        if (run.perceived_effort > 0)  stats.push({ icon: '\uD83D\uDCAA', value: run.perceived_effort, unit: '/10', color: '#8B5CF6' });

        if (stats.length === 0) return y;

        var colW = (w - pad * 2) / stats.length;
        ctx.textAlign = 'center';

        stats.forEach(function (s, i) {
            var cx = pad + colW * i + colW / 2;

            ctx.font = '24px ' + SC.FONT_BODY;
            ctx.fillStyle = s.color;
            ctx.fillText(s.icon, cx, y);

            ctx.font = '700 40px ' + SC.FONT_MONO;
            ctx.fillStyle = t.textPrimary;
            ctx.fillText(String(s.value), cx, y + 48);

            ctx.font = '500 18px ' + SC.FONT_BODY;
            ctx.fillStyle = t.textMuted;
            ctx.fillText(s.unit, cx, y + 72);
        });

        return y + 100;
    };

    SC._drawFooter = function (ctx, w, h, pad) {
        var t = this._t();
        var fy = h - pad + 10;

        this._drawDivider(ctx, pad, fy - 36, w - pad);

        ctx.textAlign = 'center';
        ctx.font = '700 16px ' + this.FONT_DISPLAY;
        ctx.fillStyle = t.textMuted;
        var brand = 'runcoach';
        var totalW = 0;
        for (var i = 0; i < brand.length; i++) totalW += ctx.measureText(brand[i]).width + 2.5;
        var bx = (w - totalW) / 2;
        for (var j = 0; j < brand.length; j++) {
            ctx.fillText(brand[j], bx, fy);
            bx += ctx.measureText(brand[j]).width + 2.5;
        }
    };

    /* -------------------------------------------------------------- */
    /*  Utility                                                        */
    /* -------------------------------------------------------------- */

    SC._formatPace = function (pace) {
        if (!pace || pace <= 0) return '--';
        var mins = Math.floor(pace);
        var secs = Math.round((pace - mins) * 60);
        return mins + ':' + (secs < 10 ? '0' : '') + secs;
    };

    SC._formatDuration = function (minutes) {
        if (!minutes || minutes <= 0) return '--:--';
        var h = Math.floor(minutes / 60);
        var m = Math.floor(minutes % 60);
        var s = Math.round((minutes % 1) * 60);
        if (h > 0) {
            return h + ':' + (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
        }
        return m + ':' + (s < 10 ? '0' : '') + s;
    };

    SC._roundRect = function (ctx, x, y, w, h, r) {
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
    };
})();
