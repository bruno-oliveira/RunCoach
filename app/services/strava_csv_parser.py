"""Service for parsing Strava activities.csv files."""

import csv
import io
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class StravaCSVParser:
    """Parser for Strava activities.csv export files."""

    REQUIRED_COLUMNS = {
        "Activity ID",
        "Activity Date",
        "Activity Name",
        "Activity Type",
        "Distance",
        "Moving Time",
        "Elapsed Time",
    }

    OPTIONAL_COLUMNS = {
        "Average Speed",
        "Max Speed",
        "Average Heart Rate",
        "Max Heart Rate",
        "Elevation Gain",
        "Elevation Loss",
        "Calories",
    }

    COLUMN_ALIASES = {
        "Activity ID": ["Activity ID", "Activity Id", "id", "Id", "ID"],
        "Activity Date": ["Activity Date", "Date", "date", "activity_date"],
        "Activity Name": ["Activity Name", "Name", "name", "activity_name"],
        "Activity Type": ["Activity Type", "Type", "type", "activity_type"],
        "Distance": ["Distance", "distance", "dist"],
        "Moving Time": ["Moving Time", "Moving time", "Time", "time", "time_moving", "moving_time", "time moving"],
        "Elapsed Time": ["Elapsed Time", "Elapsed time", "Duration", "duration", "time_elapsed", "elapsed_time", "time elapsed"],
        "Average Speed": ["Average Speed", "Avg Speed", "average speed", "avg_speed", "speed"],
        "Max Speed": ["Max Speed", "Maximum Speed", "max speed", "maximum_speed", "max_speed"],
        "Average Heart Rate": ["Average Heart Rate", "Avg Heart Rate", "average heart rate", "Avg HR", "avg_hr"],
        "Max Heart Rate": ["Max Heart Rate", "Maximum Heart Rate", "max heart rate", "Max HR", "max_hr"],
        "Elevation Gain": ["Elevation Gain", "Elevation gain", "Elevation", "elevation", "elevation_gain"],
    }

    @staticmethod
    def parse_csv(csv_content: str) -> Dict[str, Any]:
        """
        Parse Strava activities.csv content.

        Args:
            csv_content: Raw CSV content as string

        Returns:
            Dictionary containing parsed activities and summary data
        """
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        all_columns = csv_reader.fieldnames or []

        logger.info(f"Parsing CSV with columns: {all_columns}")

        columns_lower = {col.lower(): col for col in all_columns}

        column_mapping = {}
        for required_col in StravaCSVParser.REQUIRED_COLUMNS:
            aliases = StravaCSVParser.COLUMN_ALIASES.get(required_col, [required_col])
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in columns_lower:
                    column_mapping[required_col] = columns_lower[alias_lower]
                    break

        missing_required = [
            col for col in StravaCSVParser.REQUIRED_COLUMNS
            if col not in column_mapping
        ]

        if missing_required:
            raise ValueError(
                f"CSV is missing required columns: {missing_required}. "
                f"Found columns: {all_columns}"
            )

        # Map all optional columns as well
        for optional_col in StravaCSVParser.OPTIONAL_COLUMNS:
            aliases = StravaCSVParser.COLUMN_ALIASES.get(optional_col, [optional_col])
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in columns_lower:
                    column_mapping[optional_col] = columns_lower[alias_lower]
                    break

        activities = []
        for row in csv_reader:
            try:
                mapped_row = {col: row.get(col_map) for col, col_map in column_mapping.items()}
                activity = StravaCSVParser._parse_activity(mapped_row)
                activities.append(activity)
            except Exception as e:
                logger.warning(f"Skipping invalid activity row: {e}")
                continue

        summary = StravaCSVParser._calculate_summary(activities)

        return {
            "activities": activities,
            "summary": summary,
            "total_activities": len(activities),
        }

    @staticmethod
    def _parse_activity(row: Dict[str, str]) -> Dict[str, Any]:
        """Parse a single activity row from CSV."""

        activity_id = (row.get("Activity ID") or row.get("Activity Id", "")).strip()
        date_str = (row.get("Activity Date") or "").strip()
        activity_type = (row.get("Activity Type") or "").strip()
        distance_str = (row.get("Distance") or "").strip()
        moving_time_str = (row.get("Moving Time") or "").strip()
        elapsed_time_str = (row.get("Elapsed Time") or "").strip()

        date = StravaCSVParser._parse_date(date_str)
        
        distance_km = 0
        if distance_str:
            try:
                distance_km = float(distance_str)
            except ValueError:
                pass

        moving_time_seconds = StravaCSVParser._parse_time(moving_time_str)
        elapsed_time_seconds = StravaCSVParser._parse_time(elapsed_time_str)

        avg_speed = 0
        if row.get("Average Speed"):
            try:
                avg_speed = float(row.get("Average Speed", "0").replace(",", ""))
            except ValueError:
                pass

        max_speed = 0
        if row.get("Max Speed"):
            try:
                max_speed = float(row.get("Max Speed", "0").replace(",", ""))
            except ValueError:
                pass

        avg_heart_rate = None
        hr_key = "Average Heart Rate"
        if row.get(hr_key):
            try:
                hr_value = float(row.get(hr_key, "0").replace(",", ""))
                if hr_value > 0:
                    avg_heart_rate = int(hr_value)
            except ValueError:
                pass

        max_heart_rate = None
        max_hr_key = "Max Heart Rate"
        if row.get(max_hr_key):
            try:
                max_hr_value = float(row.get(max_hr_key, "0").replace(",", ""))
                if max_hr_value > 0:
                    max_heart_rate = int(max_hr_value)
            except ValueError:
                pass

        elevation_gain = None
        if row.get("Elevation Gain"):
            try:
                gain_str = row.get("Elevation Gain", "0")
                if "ft" in gain_str.lower():
                    elevation_gain = float(gain_str.replace(",", "").replace("ft", "")) * 0.3048
                elif "m" in gain_str.lower():
                    elevation_gain = float(gain_str.replace(",", "").replace("m", ""))
                else:
                    elevation_gain = float(gain_str.replace(",", ""))
            except ValueError:
                pass

        calories = None
        if row.get("Calories"):
            try:
                calories_value = float(row.get("Calories", "0").replace(",", ""))
                if calories_value > 0:
                    calories = int(calories_value)
            except ValueError:
                pass

        return {
            "id": str(uuid.uuid4()),
            "activity_id": activity_id,
            "date": date.isoformat() if date else None,
            "activity_type": activity_type,
            "distance_km": distance_km,
            "moving_time_seconds": moving_time_seconds,
            "elapsed_time_seconds": elapsed_time_seconds,
            "avg_speed": avg_speed,
            "max_speed": max_speed,
            "avg_heart_rate": avg_heart_rate,
            "max_heart_rate": max_heart_rate,
            "elevation_gain_meters": elevation_gain,
            "calories": calories,
        }

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse Strava date format (e.g., 'Oct 20, 2024, 5:30:00 PM')."""
        if not date_str:
            return None

        month_map = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
        }

        try:
            parts = date_str.split(", ")
            date_part = parts[0].split(" ")
            month = month_map.get(date_part[0], 1)
            day = int(date_part[1])
            year = int(parts[1])

            time_part = parts[2].split(" ")
            time_parts = time_part[0].split(":")
            am_pm = time_part[1].upper()
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            second = int(time_parts[2])

            if am_pm == "PM" and hour != 12:
                hour += 12
            elif am_pm == "AM" and hour == 12:
                hour = 0

            return datetime(year, month, day, hour, minute, second)
        except Exception as e:
            logger.warning(f"Failed to parse date '{date_str}': {e}")
            return None

    @staticmethod
    def _parse_time(time_str: str) -> int:
        """Parse time duration format (e.g., '1:30:45' or '45:00')."""
        if not time_str:
            return 0
        try:
            parts = time_str.split(":")
            total_seconds = 0
            if len(parts) == 3:
                hours, minutes, seconds = map(int, parts)
                total_seconds = hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:
                minutes, seconds = map(int, parts)
                total_seconds = minutes * 60 + seconds
            else:
                total_seconds = int(parts[0])
            return total_seconds
        except Exception:
            return 0

    @staticmethod
    def _calculate_summary(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate summary statistics from parsed activities."""
        if not activities:
            return {}

        run_activities = [a for a in activities if a.get("activity_type") == "Run"]

        total_distance = sum(a.get("distance_km", 0) for a in run_activities)
        total_time = sum(a.get("moving_time_seconds", 0) for a in run_activities)

        dates = [a.get("date") for a in run_activities if a.get("date")]
        date_span_days = 0
        if dates:
            from datetime import datetime
            parsed_dates = [datetime.fromisoformat(d) for d in dates]
            date_span_days = (max(parsed_dates) - min(parsed_dates)).days

        avg_heart_rates = [a.get("avg_heart_rate") for a in run_activities if a.get("avg_heart_rate")]
        avg_heart_rate = sum(avg_heart_rates) / len(avg_heart_rates) if avg_heart_rates else 0

        return {
            "total_distance_km": round(total_distance, 2),
            "total_runs": len(run_activities),
            "total_hours": round(total_time / 3600, 1),
            "date_span_days": date_span_days,
            "avg_heart_rate": round(avg_heart_rate, 1),
            "activity_types": list({a.get("activity_type") for a in activities}),
        }