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

        # Focus on essential analytics with minimal data: distance, heart rate, pace, number of runs
        analytics = {
            "distance_trends": AnalyticsService._analyze_distance_trends(sorted_activities),
            "hr_evolution": AnalyticsService._analyze_hr_evolution(sorted_activities),
            "pace_evolution": AnalyticsService._analyze_pace_evolution(sorted_activities),
            "weekly_volume": AnalyticsService._analyze_weekly_volume(sorted_activities),
            "summary": AnalyticsService._calculate_overall_summary(sorted_activities),
        }

        return analytics



    @staticmethod
    def _analyze_distance_trends(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze distance trends over time with improved styling."""
        distances = []
        dates = []

        for activity in activities:
            distances.append(activity.get("distance_km", 0))
            dates.append(datetime.fromisoformat(activity["date"]))

        if not distances:
            return {"chart": base64.b64encode(b"").decode()}

        # Create figure with improved styling
        fig, ax = plt.subplots(figsize=(14, 7), dpi=120)
        fig.patch.set_facecolor('#fafbfc')
        ax.set_facecolor('#ffffff')

        # Main bar chart with gradient-like colors
        bars = ax.bar(dates, distances, color="#667eea", alpha=0.75, edgecolor="#5568d3", linewidth=1.2)

        # Calculate and plot rolling average
        rolling_window = min(7, len(distances))
        if len(distances) >= rolling_window:
            rolling_avg = []
            rolling_dates = []
            for i in range(rolling_window - 1, len(distances)):
                window = distances[max(0, i - rolling_window + 1) : i + 1]
                avg = sum(window) / len(window)
                rolling_avg.append(avg)
                rolling_dates.append(dates[i])

            ax.plot(rolling_dates, rolling_avg, color="#FF6B6B", linewidth=2.5,
                   label=f'{rolling_window}-run Moving Average', marker='o', markersize=4, alpha=0.9)

        # Add trend line
        if len(distances) > 2:
            x_numeric = np.arange(len(dates))
            z = np.polyfit(x_numeric, distances, 1)
            p = np.poly1d(z)
            ax.plot(dates, p(x_numeric), "--", color="#4ECDC4", linewidth=2,
                   alpha=0.8, label="Overall Trend")

        # Styling improvements
        ax.set_xlabel("Date", fontsize=13, fontweight="600", color="#2c3e50")
        ax.set_ylabel("Distance (km)", fontsize=13, fontweight="600", color="#2c3e50")
        ax.set_title("Distance Trends Over Time", fontsize=16, fontweight="700",
                    pad=20, color="#2c3e50")

        # Modern grid styling
        ax.grid(True, alpha=0.2, linestyle='-', linewidth=0.8, color="#95a5a6", axis="y")
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#bdc3c7')
        ax.spines['bottom'].set_color('#bdc3c7')

        plt.xticks(rotation=45, ha='right', fontsize=10)
        plt.yticks(fontsize=10)
        ax.legend(loc='upper left', framealpha=0.95, fontsize=10)
        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format="png", bbox_inches="tight", facecolor='#fafbfc', dpi=120)
        plt.close()
        img_buffer.seek(0)

        return {
            "chart": base64.b64encode(img_buffer.getvalue()).decode(),
            "avg_distance_km": float(sum(distances) / len(distances)),
            "max_distance_km": float(max(distances)),
            "longest_runs": sorted(activities, key=lambda x: x["distance_km"], reverse=True)[:5],
        }



    @staticmethod
    def _analyze_hr_evolution(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze heart rate evolution over time with improved styling."""
        hr_data = [(a["date"], a["avg_heart_rate"]) for a in activities
                   if a.get("avg_heart_rate") and a.get("date")]

        if len(hr_data) < 3:
            return {"chart": base64.b64encode(b"").decode(), "trend": "insufficient_data"}

        hr_data.sort(key=lambda x: x[0])
        dates = [datetime.fromisoformat(d[0]) for d in hr_data]
        heart_rates = [d[1] for d in hr_data]

        rolling_window = min(8, len(heart_rates))
        rolling_avg = [
            sum(heart_rates[max(0, i - rolling_window + 1) : i + 1]) /
            min(rolling_window, i + 1)
            for i in range(len(heart_rates))
        ]

        # Create figure with improved styling
        fig, ax = plt.subplots(figsize=(14, 7), dpi=120)
        fig.patch.set_facecolor('#fafbfc')
        ax.set_facecolor('#ffffff')

        # Scatter plot for individual sessions
        ax.scatter(dates, heart_rates, alpha=0.35, color="#667eea", s=60,
                  edgecolors='#5568d3', linewidth=1, label="Individual Sessions")

        # Rolling average
        ax.plot(dates, rolling_avg, color="#FF6B6B", linewidth=3,
               label=f"Rolling Average ({rolling_window} runs)", marker='o', markersize=4)

        # Trend line
        z = np.polyfit(range(len(dates)), rolling_avg, 1)
        p = np.poly1d(z)
        ax.plot(dates, p(range(len(dates))), "--", color="#4ECDC4",
               linewidth=2.5, alpha=0.85, label="Trend Line")

        # Styling improvements
        ax.set_xlabel("Date", fontsize=13, fontweight="600", color="#2c3e50")
        ax.set_ylabel("Average Heart Rate (bpm)", fontsize=13, fontweight="600", color="#2c3e50")
        ax.set_title("Heart Rate Evolution", fontsize=16, fontweight="700",
                    pad=20, color="#2c3e50")

        # Modern grid and spines
        ax.grid(True, alpha=0.2, linestyle='-', linewidth=0.8, color="#95a5a6")
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#bdc3c7')
        ax.spines['bottom'].set_color('#bdc3c7')

        ax.legend(loc='upper left', framealpha=0.95, fontsize=10)
        plt.xticks(rotation=45, ha='right', fontsize=10)
        plt.yticks(fontsize=10)
        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format="png", bbox_inches="tight", facecolor='#fafbfc', dpi=120)
        plt.close()
        img_buffer.seek(0)

        trend_slope = z[0] * 7
        trend_desc = f"{trend_slope:+.1f} bpm per week"
        trend_type = "improving" if trend_slope < 0 else "declining"

        return {
            "chart": base64.b64encode(img_buffer.getvalue()).decode(),
            "trend_description": trend_desc,
            "overall_trend": trend_type,
            "avg_heart_rate": float(sum(heart_rates) / len(heart_rates)),
            "starting_hr": float(rolling_avg[0]),
            "current_hr": float(rolling_avg[-1]),
        }

    @staticmethod
    def _analyze_pace_evolution(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze pace evolution over time with trend lines."""
        pace_data = [(a["date"], a["pace_min_km"]) for a in activities
                     if a.get("pace_min_km") and a.get("date")]

        if len(pace_data) < 3:
            return {"chart": base64.b64encode(b"").decode(), "trend": "insufficient_data"}

        pace_data.sort(key=lambda x: x[0])
        dates = [datetime.fromisoformat(d[0]) for d in pace_data]
        paces = [d[1] for d in pace_data]

        rolling_window = min(8, len(paces))
        rolling_avg = [
            sum(paces[max(0, i - rolling_window + 1) : i + 1]) /
            min(rolling_window, i + 1)
            for i in range(len(paces))
        ]

        # Create figure with improved styling
        fig, ax = plt.subplots(figsize=(14, 7), dpi=120)
        fig.patch.set_facecolor('#fafbfc')
        ax.set_facecolor('#ffffff')

        # Scatter plot for individual sessions
        ax.scatter(dates, paces, alpha=0.35, color="#667eea", s=60,
                  edgecolors='#5568d3', linewidth=1, label="Individual Runs")

        # Rolling average
        ax.plot(dates, rolling_avg, color="#FF6B6B", linewidth=3,
               label=f"Rolling Average ({rolling_window} runs)", marker='o', markersize=4)

        # Trend line
        z = np.polyfit(range(len(dates)), rolling_avg, 1)
        p = np.poly1d(z)
        ax.plot(dates, p(range(len(dates))), "--", color="#4ECDC4",
               linewidth=2.5, alpha=0.85, label="Trend Line")

        # Styling improvements
        ax.set_xlabel("Date", fontsize=13, fontweight="600", color="#2c3e50")
        ax.set_ylabel("Pace (min/km)", fontsize=13, fontweight="600", color="#2c3e50")
        ax.set_title("Pace Evolution Over Time", fontsize=16, fontweight="700",
                    pad=20, color="#2c3e50")

        # Invert Y-axis (faster pace is lower number, should be at top)
        ax.invert_yaxis()

        # Format y-axis labels as min:sec
        def pace_formatter(x, pos):
            minutes = int(x)
            seconds = int((x - minutes) * 60)
            return f"{minutes}:{seconds:02d}"

        from matplotlib.ticker import FuncFormatter
        ax.yaxis.set_major_formatter(FuncFormatter(pace_formatter))

        # Modern grid and spines
        ax.grid(True, alpha=0.2, linestyle='-', linewidth=0.8, color="#95a5a6")
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#bdc3c7')
        ax.spines['bottom'].set_color('#bdc3c7')

        ax.legend(loc='upper right', framealpha=0.95, fontsize=10)
        plt.xticks(rotation=45, ha='right', fontsize=10)
        plt.yticks(fontsize=10)
        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format="png", bbox_inches="tight", facecolor='#fafbfc', dpi=120)
        plt.close()
        img_buffer.seek(0)

        # Calculate trend (negative slope means getting faster)
        trend_slope = z[0] * 7  # Change per week
        trend_type = "improving" if trend_slope < 0 else "declining"
        trend_desc = f"{abs(trend_slope):.1f} sec/km per week"

        avg_pace = sum(paces) / len(paces)

        return {
            "chart": base64.b64encode(img_buffer.getvalue()).decode(),
            "trend_description": trend_desc,
            "overall_trend": trend_type,
            "avg_pace": float(avg_pace),
            "starting_pace": float(rolling_avg[0]),
            "current_pace": float(rolling_avg[-1]),
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

        fig, axes = plt.subplots(len(years), 1, figsize=(14, 5 * len(years)), dpi=120)
        if len(years) == 1:
            axes = [axes]

        fig.patch.set_facecolor('#fafbfc')

        yearly_stats = {}

        for idx, year in enumerate(years):
            weeks = sorted(weekly_data[year].keys())
            distances = [weekly_data[year][w] for w in weeks]

            axes[idx].set_facecolor('#ffffff')

            # Bar chart with improved styling
            bars = axes[idx].bar(weeks, distances, color="#667eea", alpha=0.75,
                               edgecolor="#5568d3", linewidth=1.2)

            # Calculate average and highlight bars above average
            avg_dist = sum(distances) / len(distances)
            axes[idx].axhline(y=avg_dist, color="#FF6B6B", linestyle="--",
                            linewidth=2, alpha=0.8, label="Average")

            # Add trend line
            if len(distances) > 2:
                x_numeric = np.array(weeks)
                z = np.polyfit(x_numeric, distances, 1)
                p = np.poly1d(z)
                axes[idx].plot(weeks, p(x_numeric), "--", color="#4ECDC4",
                             linewidth=2, alpha=0.8, label="Trend")

            # Styling
            axes[idx].set_xlabel(f"Week Number ({year})", fontsize=12, fontweight="600", color="#2c3e50")
            axes[idx].set_ylabel("Distance (km)", fontsize=12, fontweight="600", color="#2c3e50")
            axes[idx].set_title(f"Weekly Running Volume - {year}", fontsize=14,
                              fontweight="700", pad=15, color="#2c3e50")

            # Modern grid and spines
            axes[idx].grid(True, alpha=0.2, linestyle='-', linewidth=0.8, color="#95a5a6", axis="y")
            axes[idx].spines['top'].set_visible(False)
            axes[idx].spines['right'].set_visible(False)
            axes[idx].spines['left'].set_color('#bdc3c7')
            axes[idx].spines['bottom'].set_color('#bdc3c7')

            axes[idx].set_xticks(range(1, max(weeks) + 2, 5))
            axes[idx].tick_params(labelsize=10)
            axes[idx].legend(loc='upper left', framealpha=0.95, fontsize=10)

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
        plt.savefig(img_buffer, format="png", bbox_inches="tight", facecolor='#fafbfc', dpi=120)
        plt.close()
        img_buffer.seek(0)

        # Calculate aggregate weekly statistics across all years
        all_weekly_avgs = [stats["weekly_average_km"] for stats in yearly_stats.values()]
        all_max_weekly = [stats["max_weekly_km"] for stats in yearly_stats.values()]

        return {
            "chart": base64.b64encode(img_buffer.getvalue()).decode(),
            "yearly_breakdown": yearly_stats,
            "avg_weekly_distance": sum(all_weekly_avgs) / len(all_weekly_avgs) if all_weekly_avgs else 0,
            "max_weekly_distance": max(all_max_weekly) if all_max_weekly else 0,
        }

    @staticmethod
    def _calculate_overall_summary(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate overall summary statistics from minimal data."""
        total_distance = sum(a.get("distance_km", 0) for a in activities)
        distances = [a.get("distance_km", 0) for a in activities if a.get("distance_km", 0) > 0]
        max_distance = max(distances) if distances else 0

        dates = [datetime.fromisoformat(a["date"]) for a in activities if a.get("date")]
        date_span = max(dates) - min(dates) if len(dates) >= 2 else None

        hr_rates = [a.get("avg_heart_rate") for a in activities if a.get("avg_heart_rate")]
        avg_hr = sum(hr_rates) / len(hr_rates) if hr_rates else 0

        months = defaultdict(int)
        for activity in activities:
            date = datetime.fromisoformat(activity["date"])
            months[f"{date.year}-{date.month:02d}"] += 1

        most_active_month = max(months.items(), key=lambda x: x[1]) if months else None

        avg_distance_per_run = float(round(total_distance / len(activities), 1)) if activities else 0

        return {
            # Original field names
            "total_runs": int(len(activities)),
            "total_distance_km": float(round(total_distance, 1)),
            "date_range_days": int(date_span.days) if date_span else 0,
            "avg_heart_rate": float(round(avg_hr, 1)) if avg_hr else 0,
            "avg_distance_per_run_km": avg_distance_per_run,
            "most_active_month": most_active_month[0] if most_active_month else None,
            # Add backward compatible field aliases for template
            "total_activities": int(len(activities)),
            "total_distance": float(round(total_distance, 1)),
            "avg_distance": avg_distance_per_run,
            "max_distance": float(round(max_distance, 1)),
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

        # Compare essential metrics only: distance and heart rate
        for idx, (analytics, name) in enumerate(zip(analytics_list, names)):
            color = colors[idx % len(colors)]

            if idx < len(analytics_list):
                if "distance_trends" in analytics and analytics["distance_trends"].get("avg_distance_km"):
                    axes[0, 0].bar(idx, analytics["distance_trends"]["avg_distance_km"], 
                                  color=color, alpha=0.7, label=name)
                if "summary" in analytics and analytics["summary"].get("avg_heart_rate"):
                    axes[0, 1].bar(idx, analytics["summary"]["avg_heart_rate"], 
                                  color=color, alpha=0.7, label=name)

        axes[0, 0].set_title("Average Distance per Run Comparison", fontweight="bold")
        axes[0, 0].set_ylabel("Distance (km)")
        axes[0, 0].set_xticks(range(len(names)))
        axes[0, 0].set_xticklabels(names, rotation=15, ha="right")
        axes[0, 0].legend()

        axes[0, 1].set_title("Average Heart Rate Comparison", fontweight="bold")
        axes[0, 1].set_ylabel("Heart Rate (bpm)")
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
                    "avg_heart_rate": summary.get("avg_heart_rate", 0),
                })

        axes[1, 0].axis("off")
        table_data = [
            [f"{s['name']}", f"{s['total_distance_km']} km", str(s['total_runs']), 
             f"{s['avg_heart_rate']:.0f}" if s['avg_heart_rate'] else "N/A"]
            for s in summary_comparison
        ]
        table = axes[1, 0].table(cellText=table_data,
                                colLabels=["Name", "Total Distance", "Total Runs", "Avg HR"],
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