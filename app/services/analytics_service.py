"""Service for generating Strava analytics and charts."""

import base64
import io
import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple
from collections import defaultdict
import uuid

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for analyzing Strava data and generating charts."""

    HR_ZONES = {
        "Zone 1 (Easy)": (60, 70),
        "Zone 2 (Endurance)": (70, 80),
        "Zone 3 (Aerobic)": (80, 85),
        "Zone 4 (Anaerobic)": (85, 90),
        "Zone 5 (VO2 Max)": (90, 100),
    }

    @staticmethod
    def generate_analytics(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate comprehensive analytics from activity data.

        Args:
            activities: List of activity dictionaries

        Returns:
            Dictionary containing all analytics and chart data
        """
        run_activities = [
            a for a in activities
            if a.get("activity_type") == "Run" and a.get("date") and a.get("distance_km", 0) > 0
        ]

        if not run_activities:
            return {"error": "No running activities found"}

        sorted_activities = sorted(run_activities, key=lambda x: x["date"])

        analytics = {
            "pace_trends": AnalyticsService._analyze_pace_trends(sorted_activities),
            "distance_trends": AnalyticsService._analyze_distance_trends(sorted_activities),
            "hr_zones": AnalyticsService._analyze_hr_zones(sorted_activities),
            "hr_evolution": AnalyticsService._analyze_hr_evolution(sorted_activities),
            "weekly_volume": AnalyticsService._analyze_weekly_volume(sorted_activities),
            "summary": AnalyticsService._calculate_overall_summary(sorted_activities),
        }

        return analytics

    @staticmethod
    def _analyze_pace_trends(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze pace trends over time."""
        paces = []
        dates = []

        for activity in activities:
            distance = activity.get("distance_km", 0)
            moving_time = activity.get("moving_time_seconds", 0)
            if distance > 0 and moving_time > 0:
                pace_seconds_per_km = moving_time / distance
                pace_min_per_km = pace_seconds_per_km / 60
                paces.append(pace_min_per_km)
                dates.append(datetime.fromisoformat(activity["date"]))

        if not paces:
            return {"chart": base64.b64encode(b"").decode(), "avg_pace_min_km": 0}

        fig, ax = plt.subplots(figsize=(12, 6), dpi=100)
        ax.plot(dates, paces, marker="o", markersize=4, linewidth=1.5, color="#667eea", alpha=0.7)

        z = np.polyfit(range(len(dates)), paces, 1)
        p = np.poly1d(z)
        ax.plot(dates, p(range(len(dates))), "--", color="#f09", linewidth=2, label="Trend Line")

        ax.set_xlabel("Date", fontsize=12, fontweight="bold")
        ax.set_ylabel("Pace (min/km)", fontsize=12, fontweight="bold")
        ax.set_title("Pace Trends Over Time", fontsize=14, fontweight="bold", pad=20)
        ax.grid(True, alpha=0.3)
        ax.legend()
        plt.xticks(rotation=45)
        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format="png", bbox_inches="tight", facecolor="white")
        plt.close()
        img_buffer.seek(0)

        trend_slope = z[0] * 7
        trend_desc = f"{trend_slope:+.1f} min/km per week"

        return {
            "chart": base64.b64encode(img_buffer.getvalue()).decode(),
            "avg_pace_min_km": sum(paces) / len(paces),
            "avg_pace_formatted": AnalyticsService._format_pace(sum(paces) / len(paces)),
            "trend_description": trend_desc,
            "pace_improving": trend_slope < 0,
        }

    @staticmethod
    def _analyze_distance_trends(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze distance trends over time."""
        distances = []
        dates = []

        for activity in activities:
            distances.append(activity.get("distance_km", 0))
            dates.append(datetime.fromisoformat(activity["date"]))

        if not distances:
            return {"chart": base64.b64encode(b"").decode()}

        fig, ax = plt.subplots(figsize=(12, 6), dpi=100)
        ax.bar(dates, distances, color="#667eea", alpha=0.6)

        rolling_avg_days = 7
        for i in range(rolling_avg_days - 1, len(distances)):
            window = distances[max(0, i - rolling_avg_days + 1) : i + 1]
            avg = sum(window) / len(window)
            ax.axhline(y=avg, color="#f09", linestyle="--", alpha=0.3)

        ax.set_xlabel("Date", fontsize=12, fontweight="bold")
        ax.set_ylabel("Distance (km)", fontsize=12, fontweight="bold")
        ax.set_title("Distance Trends Over Time", fontsize=14, fontweight="bold", pad=20)
        ax.grid(True, alpha=0.3, axis="y")
        plt.xticks(rotation=45)
        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format="png", bbox_inches="tight", facecolor="white")
        plt.close()
        img_buffer.seek(0)

        return {
            "chart": base64.b64encode(img_buffer.getvalue()).decode(),
            "avg_distance_km": sum(distances) / len(distances),
            "max_distance_km": max(distances),
            "longest_runs": sorted(activities, key=lambda x: x["distance_km"], reverse=True)[:5],
        }

    @staticmethod
    def _analyze_hr_zones(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze heart rate zones distribution."""
        hr_data = [a for a in activities if a.get("avg_heart_rate")]

        if not hr_data:
            return {"chart": base64.b64encode(b"").decode(), "distribution": {}}

        zone_counts = defaultdict(int)
        max_hr_estimate = max(a.get("max_heart_rate", 180) for a in hr_data)

        for activity in hr_data:
            avg_hr = activity.get("avg_heart_rate", 0)
            max_hr = activity.get("max_heart_rate") or max_hr_estimate
            relative_intensity = (avg_hr / max_hr) * 100 if max_hr > 0 else 0

            for zone, (lower, upper) in AnalyticsService.HR_ZONES.items():
                if lower <= relative_intensity <= upper:
                    zone_counts[zone] += 1
                    break

        zones = list(AnalyticsService.HR_ZONES.keys())
        counts = [zone_counts[z] for z in zones]
        colors = ["#81c784", "#4fc3f7", "#ba68c8", "#f06292", "#ff8a65"]

        fig, ax = plt.subplots(figsize=(10, 6), dpi=100)
        bars = ax.barh(zones, counts, color=colors)
        ax.set_xlabel("Number of Activities", fontsize=12, fontweight="bold")
        ax.set_title("Heart Rate Zone Distribution", fontsize=14, fontweight="bold", pad=20)
        ax.grid(True, alpha=0.3, axis="x")

        for bar, count in zip(bars, counts):
            ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                   f"{count}", va="center", fontsize=10)

        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format="png", bbox_inches="tight", facecolor="white")
        plt.close()
        img_buffer.seek(0)

        distribution = {zone: count for zone, count in zone_counts.items()}

        return {
            "chart": base64.b64encode(img_buffer.getvalue()).decode(),
            "distribution": distribution,
            "dominant_zone": max(distribution.items(), key=lambda x: x[1])[0] if distribution else None,
            "avg_heart_rate": sum(a["avg_heart_rate"] for a in hr_data) / len(hr_data),
        }

    @staticmethod
    def _analyze_hr_evolution(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze heart rate evolution over time."""
        hr_data = [(a["date"], a["avg_heart_rate"]) for a in activities 
                   if a.get("avg_heart_rate") and a.get("date")]

        if len(hr_data) < 3:
            return {"chart": base64.b64encode(b"").decode(), "trend": "insufficient_data"}

        hr_data.sort(key=lambda x: x[0])
        dates = [datetime.fromisoformat(d[0]) for d in hr_data]
        heart_rates = [d[1] for d in hr_data]

        rolling_window = 8
        rolling_avg = [
            sum(heart_rates[max(0, i - rolling_window + 1) : i + 1]) / 
            min(rolling_window, i + 1)
            for i in range(len(heart_rates))
        ]

        fig, ax = plt.subplots(figsize=(12, 6), dpi=100)
        ax.scatter(dates, heart_rates, alpha=0.4, color="#667eea", label="Sessions")
        ax.plot(dates, rolling_avg, color="#f09", linewidth=2, label="Rolling Average (8 runs)")

        z = np.polyfit(range(len(dates)), rolling_avg, 1)
        p = np.poly1d(z)
        ax.plot(dates, p(range(len(dates))), "--", color="#333",
               linewidth=1.5, alpha=0.5, label="Trend")

        ax.set_xlabel("Date", fontsize=12, fontweight="bold")
        ax.set_ylabel("Average Heart Rate (bpm)", fontsize=12, fontweight="bold")
        ax.set_title("Heart Rate Evolution", fontsize=14, fontweight="bold", pad=20)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format="png", bbox_inches="tight", facecolor="white")
        plt.close()
        img_buffer.seek(0)

        trend_slope = z[0] * 7
        trend_desc = f"{trend_slope:+.1f} bpm per week"
        trend_type = "improving" if trend_slope < 0 else "declining"

        return {
            "chart": base64.b64encode(img_buffer.getvalue()).decode(),
            "trend_description": trend_desc,
            "overall_trend": trend_type,
            "avg_heart_rate": sum(heart_rates) / len(heart_rates),
            "starting_hr": rolling_avg[0],
            "current_hr": rolling_avg[-1],
        }

    @staticmethod
    def _analyze_weekly_volume(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze weekly volume breakdown by year."""
        weekly_data = defaultdict(lambda: defaultdict(float))
        year_weeks = defaultdict(set)

        for activity in activities:
            date = datetime.fromisoformat(activity["date"])
            year = date.year
            week = date.isocalendar()[1]
            distance = activity.get("distance_km", 0)

            weekly_data[year][week] += distance
            year_weeks[year].add(week)

        years = sorted(weekly_data.keys())

        fig, axes = plt.subplots(len(years), 1, figsize=(14, 4 * len(years)), dpi=100)
        if len(years) == 1:
            axes = [axes]

        yearly_stats = {}

        for idx, year in enumerate(years):
            weeks = sorted(weekly_data[year].keys())
            distances = [weekly_data[year][w] for w in weeks]

            bars = axes[idx].bar(weeks, distances, color="#667eea", alpha=0.7)
            axes[idx].set_xlabel(f"Week Number ({year})", fontsize=11, fontweight="bold")
            axes[idx].set_ylabel("Distance (km)", fontsize=11, fontweight="bold")
            axes[idx].set_title(f"Weekly Running Volume - {year}", fontsize=12, fontweight="bold")
            axes[idx].grid(True, alpha=0.3, axis="y")
            axes[idx].set_xticks(range(1, max(weeks) + 2, 5))

            highlight_bars = [d for d in distances if d > sum(distances) / len(distances)]
            highlight_bars.sort(reverse=True)

            axes[idx].axhline(y=sum(distances) / len(distances), 
                            color="#f09", linestyle="--", alpha=0.5, label="Average")

            total_dist = sum(distances)
            max_dist = max(distances)
            year_avg = total_dist / len(distances)

            yearly_stats[year] = {
                "total_distance_km": round(total_dist, 1),
                "weekly_average_km": round(year_avg, 1),
                "max_weekly_km": round(max_dist, 1),
                "num_weeks_with_runs": len(distances),
            }

        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format="png", bbox_inches="tight", facecolor="white")
        plt.close()
        img_buffer.seek(0)

        return {
            "chart": base64.b64encode(img_buffer.getvalue()).decode(),
            "yearly_breakdown": yearly_stats,
        }

    @staticmethod
    def _calculate_overall_summary(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate overall summary statistics."""
        total_distance = sum(a.get("distance_km", 0) for a in activities)
        total_time = sum(a.get("moving_time_seconds", 0) for a in activities)

        dates = [datetime.fromisoformat(a["date"]) for a in activities if a.get("date")]
        date_span = max(dates) - min(dates) if len(dates) >= 2 else None

        paces = []
        for activity in activities:
            distance = activity.get("distance_km", 0)
            time = activity.get("moving_time_seconds", 0)
            if distance > 0 and time > 0:
                paces.append((time / distance) / 60)

        avg_pace = sum(paces) / len(paces) if paces else 0

        hr_rates = [a.get("avg_heart_rate") for a in activities if a.get("avg_heart_rate")]
        avg_hr = sum(hr_rates) / len(hr_rates) if hr_rates else 0

        months = defaultdict(int)
        for activity in activities:
            date = datetime.fromisoformat(activity["date"])
            months[f"{date.year}-{date.month:02d}"] += 1

        most_active_month = max(months.items(), key=lambda x: x[1]) if months else None

        return {
            "total_runs": len(activities),
            "total_distance_km": round(total_distance, 1),
            "total_time_hours": round(total_time / 3600, 1),
            "date_range_days": date_span.days if date_span else 0,
            "avg_pace_min_km": round(avg_pace, 2),
            "avg_pace_formatted": AnalyticsService._format_pace(avg_pace),
            "avg_heart_rate": round(avg_hr, 1),
            "avg_distance_per_run_km": round(total_distance / len(activities), 1) if activities else 0,
            "most_active_month": most_active_month[0] if most_active_month else None,
        }

    @staticmethod
    def _format_pace(pace_min_km: float) -> str:
        """Format pace as mm:ss."""
        minutes = int(pace_min_km)
        seconds = int((pace_min_km - minutes) * 60)
        return f"{minutes}:{seconds:02d}"

    @staticmethod
    def compare_analytics(analytics_list: List[Dict[str, Any]], names: List[str]) -> Dict[str, Any]:
        """
        Compare multiple analytics sets side-by-side.

        Args:
            analytics_list: List of analytics dictionaries
            names: Names for each analytics set

        Returns:
            Dictionary with comparison charts
        """
        if len(analytics_list) != len(names) or len(analytics_list) < 2:
            return {"error": "Invalid comparison request"}

        fig, axes = plt.subplots(2, 2, figsize=(16, 12), dpi=100)
        fig.suptitle("Side-by-Side Analytics Comparison", fontsize=16, fontweight="bold", y=0.995)

        colors = ["#667eea", "#f09", "#4caf50", "#ff9800", "#9c27b0"]

        for idx, (analytics, name) in enumerate(zip(analytics_list, names)):
            color = colors[idx % len(colors)]

            if idx < len(analytics_list):
                if "pace_trends" in analytics and analytics["pace_trends"].get("avg_pace_min_km"):
                    axes[0, 0].bar(idx, analytics["pace_trends"]["avg_pace_min_km"], 
                                  color=color, alpha=0.7, label=name)
                if "distance_trends" in analytics and analytics["distance_trends"].get("avg_distance_km"):
                    axes[0, 1].bar(idx, analytics["distance_trends"]["avg_distance_km"], 
                                  color=color, alpha=0.7, label=name)

        axes[0, 0].set_title("Average Pace Comparison", fontweight="bold")
        axes[0, 0].set_ylabel("Pace (min/km)")
        axes[0, 0].set_xticks(range(len(names)))
        axes[0, 0].set_xticklabels(names, rotation=15, ha="right")
        axes[0, 0].legend()

        axes[0, 1].set_title("Average Distance per Run Comparison", fontweight="bold")
        axes[0, 1].set_ylabel("Distance (km)")
        axes[0, 1].set_xticks(range(len(names)))
        axes[0, 1].set_xticklabels(names, rotation=15, ha="right")
        axes[0, 1].legend()

        summary_comparison = []
        for analytics, name in zip(analytics_list, names):
            if "summary" in analytics:
                summary = analytics["summary"]
                summary_comparison.append({
                    "name": name,
                    "total_distance_km": summary.get("total_distance_km", 0),
                    "total_runs": summary.get("total_runs", 0),
                    "avg_pace_formatted": summary.get("avg_pace_formatted", ""),
                    "avg_heart_rate": summary.get("avg_heart_rate", 0),
                })

        axes[1, 0].axis("off")
        table_data = [
            [f"{s['name']}", f"{s['total_distance_km']} km", str(s['total_runs']), 
             s['avg_pace_formatted'], f"{s['avg_heart_rate']:.0f}"]
            for s in summary_comparison
        ]
        table = axes[1, 0].table(cellText=table_data,
                                colLabels=["Name", "Total Distance", "Total Runs", "Avg Pace", "Avg HR"],
                                cellLoc="center",
                                loc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2)
        axes[1, 0].set_title("Summary Statistics Comparison", fontweight="bold")

        axes[1, 1].axis("off")

        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format="png", bbox_inches="tight", facecolor="white")
        plt.close()
        img_buffer.seek(0)

        return {
            "comparison_chart": base64.b64encode(img_buffer.getvalue()).decode(),
            "summary_comparison": {
                name: analytics.get("summary", {}) 
                for name, analytics in zip(names, analytics_list)
            },
        }