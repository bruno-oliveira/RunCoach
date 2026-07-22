/*
 * Home stats rail — pace + HR-zone evolution.
 *
 * Fetches /api/analytics/home-stats and renders two discreet cards into
 * #homeStats. Deliberately quiet: the takeaway sentence carries the meaning,
 * the little chart just backs it up. Renders nothing at all when there's no
 * data (a brand-new runner sees the clean hero, not an empty box), and shows a
 * one-line prompt per card that has too little to draw.
 */
(function () {
  "use strict";

  var panel = document.getElementById("homeStats");
  var layout = document.getElementById("statusLayout");
  if (!panel) return;

  // Intensity ramp, low -> high. Muted enough to sit quietly in the hero.
  var ZONE_COLORS = {
    1: "#6ba3d6",
    2: "#5cb87a",
    3: "#e6b84f",
    4: "#e08a4b",
    5: "#d9534f",
  };

  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement)
      .getPropertyValue(name)
      .trim();
    return v || fallback;
  }

  function formatPace(minPerKm) {
    var total = Math.round(minPerKm * 60);
    var m = Math.floor(total / 60);
    var s = total % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function emptyCard(title, reason) {
    var card = el("section", "home-stat-card home-stat-card--empty");
    var head = el("div", "home-stat-card-head");
    head.appendChild(el("span", "home-stat-card-title", title));
    card.appendChild(head);
    card.appendChild(el("p", "home-stat-empty", reason));
    return card;
  }

  function cardShell(title, basisText) {
    var card = el("section", "home-stat-card");
    var head = el("div", "home-stat-card-head");
    head.appendChild(el("span", "home-stat-card-title", title));
    if (basisText) head.appendChild(el("span", "home-stat-card-basis", basisText));
    card.appendChild(head);
    return card;
  }

  function chartHost(card) {
    var wrap = el("div", "home-stat-chart");
    var canvas = document.createElement("canvas");
    wrap.appendChild(canvas);
    card.appendChild(wrap);
    return canvas;
  }

  function renderPace(pace) {
    if (!pace || !pace.has_data) {
      return emptyCard(
        "Pace",
        (pace && pace.empty_reason) || "Log a few runs to see your pace trend."
      );
    }
    var basis = pace.effort_basis === "easy" ? "easy runs" : "all runs";
    var card = cardShell("Pace", basis);
    if (pace.trend && pace.trend.summary) {
      card.appendChild(el("p", "home-stat-takeaway", pace.trend.summary));
    }
    var canvas = chartHost(card);

    var accent = cssVar("--color-accent", "#4f7cff");
    var grid = cssVar("--color-border-subtle", "rgba(120,120,120,0.15)");
    var text = cssVar("--color-text-muted", "#8a8a8a");

    new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels: pace.points.map(function (p) {
          return p.label;
        }),
        datasets: [
          {
            data: pace.points.map(function (p) {
              return p.pace_min_km;
            }),
            borderColor: accent,
            backgroundColor: accent,
            borderWidth: 2,
            tension: 0.35,
            pointRadius: 3,
            pointBackgroundColor: accent,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return formatPace(ctx.parsed.y) + " /km";
              },
            },
          },
        },
        scales: {
          // Faster (lower min/km) reads as "up" — improvement climbs.
          y: {
            reverse: true,
            ticks: {
              color: text,
              font: { size: 10 },
              maxTicksLimit: 4,
              callback: function (v) {
                return formatPace(v);
              },
            },
            grid: { color: grid, drawBorder: false },
          },
          x: {
            ticks: { color: text, font: { size: 10 } },
            grid: { display: false, drawBorder: false },
          },
        },
      },
    });
    return card;
  }

  function renderHrZones(hr) {
    if (!hr || !hr.has_data) {
      return emptyCard(
        "Heart-rate zones",
        (hr && hr.empty_reason) ||
          "Connect your watch — heart-rate runs unlock your zone trend."
      );
    }
    var card = cardShell("Heart-rate zones", null);
    if (hr.takeaway) {
      card.appendChild(el("p", "home-stat-takeaway", hr.takeaway));
    }
    var canvas = chartHost(card);

    var text = cssVar("--color-text-muted", "#8a8a8a");
    var datasets = hr.series.map(function (s) {
      return {
        label: "Z" + s.zone,
        data: s.data,
        backgroundColor: ZONE_COLORS[s.zone] || "#999",
        borderWidth: 0,
        stack: "zones",
      };
    });

    new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: { labels: hr.labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: "bottom",
            labels: {
              color: text,
              boxWidth: 8,
              boxHeight: 8,
              font: { size: 9 },
              padding: 6,
            },
          },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var name = hr.series[ctx.datasetIndex].name;
                return name + ": " + Math.round(ctx.parsed.y) + "%";
              },
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            ticks: { color: text, font: { size: 10 } },
            grid: { display: false, drawBorder: false },
          },
          y: {
            stacked: true,
            min: 0,
            max: 100,
            display: false,
            grid: { display: false, drawBorder: false },
          },
        },
      },
    });
    return card;
  }

  function render(stats) {
    var pace = stats.pace_evolution || {};
    var hr = stats.hr_zone_evolution || {};
    // Nothing worth showing at all -> stay invisible, keep the hero clean.
    if (!pace.has_data && !hr.has_data) return;

    panel.appendChild(el("span", "home-stats-eyebrow", "Your trends"));
    panel.appendChild(renderPace(pace));
    panel.appendChild(renderHrZones(hr));

    panel.hidden = false;
    if (layout) layout.classList.add("has-stats");
  }

  function init() {
    if (typeof Chart === "undefined") return; // CDN blocked/offline — skip quietly.
    fetch("/api/analytics/home-stats", { credentials: "same-origin" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (stats) {
        if (stats) render(stats);
      })
      .catch(function () {
        /* A trends panel is a nice-to-have; never surface an error here. */
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
