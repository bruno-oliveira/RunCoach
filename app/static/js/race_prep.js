/**
 * Race Prep - Frontend logic for GPX upload, analysis, and blueprint generation.
 */

(function () {
    "use strict";

    let elevationChart = null;
    let blueprintChart = null;
    let analysisData = null;
    let blueprintSessionId = null;
    let originalTrackpoints = null;

    const uploadZone = document.getElementById("uploadZone");
    const gpxFileInput = document.getElementById("gpxFileInput");
    const browseBtn = document.getElementById("browseBtn");
    const uploadLoading = document.getElementById("uploadLoading");
    const uploadError = document.getElementById("uploadError");
    const analysisCard = document.getElementById("analysisCard");
    const blueprintCard = document.getElementById("blueprintCard");
    const adjustTimeBtn = document.getElementById("adjustTimeBtn");
    const generateBlueprintBtn = document.getElementById("generateBlueprintBtn");
    const timeAdjustRow = document.getElementById("timeAdjustRow");
    const targetTimeInput = document.getElementById("targetTimeInput");
    const applyTimeBtn = document.getElementById("applyTimeBtn");
    const downloadGpxBtn = document.getElementById("downloadGpxBtn");

    if (!uploadZone) return;

    function formatDuration(seconds) {
        if (!seconds || seconds <= 0) return "--";
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (h > 0) {
            return h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
        }
        return m + ":" + String(s).padStart(2, "0");
    }

    function parseTimeString(timeStr) {
        const parts = timeStr.trim().split(":").map(Number);
        if (parts.some(isNaN)) return null;
        if (parts.length === 3) {
            return parts[0] * 3600 + parts[1] * 60 + parts[2];
        }
        if (parts.length === 2) {
            return parts[0] * 60 + parts[1];
        }
        return null;
    }

    function showToast(message, type) {
        type = type || "info";
        var existing = document.querySelector(".race-prep-toast");
        if (existing) existing.remove();

        var toast = document.createElement("div");
        toast.className = "race-prep-toast race-prep-toast--" + type;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(function () {
            if (toast.parentNode) toast.remove();
        }, 4000);
    }

    function getFeasibilityColor(label) {
        var map = {
            "Realistic": "green",
            "Challenging": "yellow",
            "Aggressive": "red",
            "Conservative": "blue",
        };
        return map[label] || "gray";
    }

    function renderElevationChart(profile) {
        if (elevationChart) {
            elevationChart.destroy();
            elevationChart = null;
        }

        var canvas = document.getElementById("elevationChart");
        if (!canvas) return;

        var ctx = canvas.getContext("2d");
        var labels = profile.map(function (s) {
            return s.start_km + "-" + s.end_km + "km";
        });
        var elevations = profile.map(function (s) {
            return s.avg_elevation;
        });
        var grades = profile.map(function (s) {
            return s.grade_pct;
        });

        elevationChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [
                    {
                        label: "Elevation (m)",
                        data: elevations,
                        backgroundColor: "rgba(59, 130, 246, 0.6)",
                        borderColor: "rgba(59, 130, 246, 1)",
                        borderWidth: 1,
                        yAxisID: "y",
                        order: 2,
                    },
                    {
                        label: "Grade (%)",
                        data: grades,
                        type: "line",
                        borderColor: "rgba(239, 68, 68, 0.8)",
                        backgroundColor: "rgba(239, 68, 68, 0.1)",
                        borderWidth: 2,
                        pointRadius: 2,
                        tension: 0.3,
                        yAxisID: "y1",
                        order: 1,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "top",
                        labels: { font: { size: 11 } },
                    },
                },
                scales: {
                    x: {
                        ticks: { font: { size: 10 }, maxRotation: 45 },
                        grid: { display: false },
                    },
                    y: {
                        position: "left",
                        title: { display: true, text: "Elevation (m)", font: { size: 11 } },
                        ticks: { font: { size: 10 } },
                    },
                    y1: {
                        position: "right",
                        title: { display: true, text: "Grade (%)", font: { size: 11 } },
                        ticks: { font: { size: 10 } },
                        grid: { drawOnChartArea: false },
                    },
                },
            },
        });
    }

    function renderBlueprintChart(segments) {
        if (blueprintChart) {
            blueprintChart.destroy();
            blueprintChart = null;
        }

        var canvas = document.getElementById("blueprintChart");
        if (!canvas) return;

        var ctx = canvas.getContext("2d");
        var labels = segments.map(function (s) {
            return s.start_km + "-" + s.end_km + "km";
        });
        var paces = segments.map(function (s) {
            return s.target_pace_min_km;
        });
        var elevations = segments.map(function (s) {
            return s.avg_elevation;
        });

        blueprintChart = new Chart(ctx, {
            type: "line",
            data: {
                labels: labels,
                datasets: [
                    {
                        label: "Target Pace (min/km)",
                        data: paces,
                        borderColor: "rgba(16, 185, 129, 1)",
                        backgroundColor: "rgba(16, 185, 129, 0.1)",
                        borderWidth: 2,
                        pointRadius: 3,
                        pointBackgroundColor: "rgba(16, 185, 129, 1)",
                        tension: 0.2,
                        yAxisID: "y",
                        order: 1,
                    },
                    {
                        label: "Elevation (m)",
                        data: elevations,
                        type: "bar",
                        backgroundColor: "rgba(107, 114, 128, 0.3)",
                        borderColor: "rgba(107, 114, 128, 0.5)",
                        borderWidth: 1,
                        yAxisID: "y1",
                        order: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "top",
                        labels: { font: { size: 11 } },
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                if (context.dataset.label.indexOf("Pace") !== -1) {
                                    var mins = Math.floor(context.parsed.y);
                                    var secs = Math.round((context.parsed.y - mins) * 60);
                                    return context.dataset.label + ": " + mins + ":" + String(secs).padStart(2, "0") + "/km";
                                }
                                return context.dataset.label + ": " + context.parsed.y + "m";
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: { font: { size: 10 }, maxRotation: 45 },
                        grid: { display: false },
                    },
                    y: {
                        position: "left",
                        title: { display: true, text: "Pace (min/km)", font: { size: 11 } },
                        ticks: {
                            font: { size: 10 },
                            callback: function (value) {
                                var mins = Math.floor(value);
                                var secs = Math.round((value - mins) * 60);
                                return mins + ":" + String(secs).padStart(2, "0");
                            },
                        },
                    },
                    y1: {
                        position: "right",
                        title: { display: true, text: "Elevation (m)", font: { size: 11 } },
                        ticks: { font: { size: 10 } },
                        grid: { drawOnChartArea: false },
                    },
                },
            },
        });
    }

    function renderBlueprintTable(segments) {
        var tbody = document.getElementById("blueprintTableBody");
        if (!tbody) return;
        tbody.innerHTML = "";

        segments.forEach(function (seg) {
            var tr = document.createElement("tr");

            var gradeClass = "grade-flat";
            if (seg.grade_pct > 0.5) gradeClass = "grade-uphill";
            else if (seg.grade_pct < -0.5) gradeClass = "grade-downhill";

            var gradeStr = seg.grade_pct > 0 ? "+" + seg.grade_pct.toFixed(1) + "%" : seg.grade_pct.toFixed(1) + "%";

            tr.innerHTML =
                "<td>" + seg.start_km + "-" + seg.end_km + "</td>" +
                "<td class='" + gradeClass + "'>" + gradeStr + "</td>" +
                "<td>" + seg.elevation_m + "m</td>" +
                "<td>" + seg.target_pace_str + "</td>" +
                "<td>" + formatDuration(seg.target_time_seconds) + "</td>" +
                "<td>" + formatDuration(seg.cumulative_time_seconds) + "</td>";

            tbody.appendChild(tr);
        });
    }

    async function handleFile(file) {
        if (!file) return;

        if (!file.name.toLowerCase().endsWith(".gpx")) {
            uploadError.textContent = "Please select a .gpx file";
            uploadError.style.display = "block";
            return;
        }

        uploadError.style.display = "none";
        uploadZone.style.display = "none";
        uploadLoading.style.display = "block";

        var formData = new FormData();
        formData.append("file", file);

        try {
            var response = await fetch("/api/race-prep/analyze", {
                method: "POST",
                body: formData,
            });

            if (!response.ok) {
                var errData = await response.json().catch(function () {
                    return null;
                });
                throw new Error((errData && errData.detail) || "Failed to analyze GPX file");
            }

            analysisData = await response.json();
            originalTrackpoints = analysisData.trackpoints || [];
            renderAnalysis(analysisData);
            showToast("Route analyzed successfully!", "success");
        } catch (err) {
            uploadError.textContent = err.message;
            uploadError.style.display = "block";
            showToast("Analysis failed: " + err.message, "error");
        } finally {
            uploadLoading.style.display = "none";
            uploadZone.style.display = "block";
        }
    }

    function renderAnalysis(data) {
        document.getElementById("statDistance").textContent = data.distance_km.toFixed(2) + " km";
        document.getElementById("statElevation").textContent = Math.round(data.total_elevation_gain) + " m";
        document.getElementById("statMaxElev").textContent = Math.round(data.max_elevation) + " m";

        document.getElementById("flatTime").textContent = formatDuration(data.flat_estimate_seconds);
        document.getElementById("elevationPenalty").textContent =
            (data.elevation_penalty_seconds > 0 ? "+" : "") + formatDuration(Math.abs(data.elevation_penalty_seconds));
        document.getElementById("adjustedTime").textContent = formatDuration(data.elevation_adjusted_seconds);

        var badge = document.getElementById("feasibilityBadge");
        var color = getFeasibilityColor(data.feasibility.label);
        badge.textContent = data.feasibility.label;
        badge.className = "feasibility-badge feasibility-badge--" + color;

        var profile = (data.elevation_profile || []).map(function (seg, idx) {
            return {
                segment_number: idx + 1,
                start_km: seg.start_km,
                end_km: seg.end_km,
                avg_elevation: seg.avg_elevation,
                grade_pct: seg.grade_pct,
            };
        });

        renderElevationChart(profile);

        analysisCard.style.display = "block";
        analysisCard.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    async function generateBlueprint() {
        if (!analysisData) return;

        var targetTime = analysisData.elevation_adjusted_seconds;
        var customTime = parseTimeString(targetTimeInput.value);
        if (customTime && customTime > 0) {
            targetTime = customTime;
        }

        generateBlueprintBtn.disabled = true;
        generateBlueprintBtn.textContent = "Generating...";

        try {
            var profile = (analysisData.elevation_profile || []).map(function (seg) {
                return {
                    start_km: seg.start_km,
                    end_km: seg.end_km,
                    avg_elevation: seg.avg_elevation,
                    grade_pct: seg.grade_pct,
                };
            });

            var response = await fetch("/api/race-prep/blueprint", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    target_time_seconds: targetTime,
                    distance_km: analysisData.distance_km,
                    elevation_profile: profile,
                }),
            });

            if (!response.ok) {
                var errData = await response.json().catch(function () {
                    return null;
                });
                throw new Error((errData && errData.detail) || "Failed to generate blueprint");
            }

            var blueprint = await response.json();
            blueprintSessionId = blueprint.session_id || null;

            if (blueprintSessionId && originalTrackpoints) {
                await fetch("/api/race-prep/blueprint/" + blueprintSessionId + "/attach-route", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(originalTrackpoints),
                });
            }

            document.getElementById("blueprintTargetTime").textContent = blueprint.target_time_str;
            renderBlueprintChart(blueprint.segments);
            renderBlueprintTable(blueprint.segments);

            blueprintCard.style.display = "block";
            showToast("Blueprint generated! Download your GPX below.", "success");

            blueprintCard.scrollIntoView({ behavior: "smooth", block: "start" });
        } catch (err) {
            showToast("Blueprint failed: " + err.message, "error");
        } finally {
            generateBlueprintBtn.disabled = false;
            generateBlueprintBtn.textContent = "Generate Blueprint";
        }
    }

    async function downloadGpx() {
        if (!blueprintSessionId) {
            showToast("No blueprint session available. Please regenerate.", "error");
            return;
        }

        try {
            var response = await fetch("/api/race-prep/download-gpx/" + blueprintSessionId);
            if (!response.ok) {
                var errData = await response.json().catch(function () {
                    return null;
                });
                throw new Error((errData && errData.detail) || "Download failed");
            }

            var blob = await response.blob();
            var url = URL.createObjectURL(blob);
            var a = document.createElement("a");
            a.href = url;
            a.download = "race_plan.gpx";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            showToast("GPX downloaded! Import it into Garmin Connect.", "success");
        } catch (err) {
            showToast("Download failed: " + err.message, "error");
        }
    }

    uploadZone.addEventListener("click", function () {
        gpxFileInput.click();
    });

    if (browseBtn) {
        browseBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            gpxFileInput.click();
        });
    }

    gpxFileInput.addEventListener("change", function () {
        if (gpxFileInput.files.length > 0) {
            handleFile(gpxFileInput.files[0]);
        }
    });

    uploadZone.addEventListener("dragover", function (e) {
        e.preventDefault();
        uploadZone.classList.add("drag-over");
    });

    uploadZone.addEventListener("dragleave", function () {
        uploadZone.classList.remove("drag-over");
    });

    uploadZone.addEventListener("drop", function (e) {
        e.preventDefault();
        uploadZone.classList.remove("drag-over");
        if (e.dataTransfer.files.length > 0) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    if (adjustTimeBtn) {
        adjustTimeBtn.addEventListener("click", function () {
            timeAdjustRow.style.display = timeAdjustRow.style.display === "none" ? "flex" : "none";
        });
    }

    if (applyTimeBtn) {
        applyTimeBtn.addEventListener("click", function () {
            var parsed = parseTimeString(targetTimeInput.value);
            if (parsed && parsed > 0) {
                showToast("Target time set to " + formatDuration(parsed), "info");
                timeAdjustRow.style.display = "none";
            } else {
                showToast("Invalid time format. Use HH:MM:SS or MM:SS", "error");
            }
        });
    }

    if (generateBlueprintBtn) {
        generateBlueprintBtn.addEventListener("click", generateBlueprint);
    }

    if (downloadGpxBtn) {
        downloadGpxBtn.addEventListener("click", downloadGpx);
    }
})();
