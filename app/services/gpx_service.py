"""GPX parsing and generation service for Race Prep feature."""

import math
from datetime import datetime, timezone
from typing import Any

import gpxpy
import gpxpy.gpx


class GPXService:
    """Parse uploaded GPX files and generate planned GPX for Garmin watches."""

    @staticmethod
    def parse_gpx(file_content: bytes) -> dict[str, Any]:
        """Parse a GPX file and extract trackpoint data.

        Args:
            file_content: Raw bytes of the GPX file.

        Returns:
            Dict with trackpoints, distance_km, elevation_gain, and metadata.

        Raises:
            ValueError: If the GPX file is invalid or contains no track data.
        """
        try:
            gpx = gpxpy.parse(file_content.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Invalid GPX file: {exc}") from exc

        if not gpx.tracks:
            raise ValueError("GPX file contains no tracks")

        trackpoints = []
        total_elevation_gain = 0.0
        prev_elevation: float | None = None
        cumulative_distance = 0.0
        prev_point = None

        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    if prev_point is not None:
                        cumulative_distance += point.distance_2d(prev_point)

                    elevation = point.elevation
                    if elevation is None:
                        elevation = 0.0

                    if prev_elevation is not None and elevation > prev_elevation:
                        total_elevation_gain += elevation - prev_elevation

                    trackpoints.append({
                        "lat": point.latitude,
                        "lon": point.longitude,
                        "elevation": round(elevation, 1),
                        "distance_km": round(cumulative_distance / 1000.0, 3),
                        "time": point.time.isoformat() if point.time else None,
                    })

                    prev_elevation = elevation
                    prev_point = point

        if not trackpoints:
            raise ValueError("GPX file contains no trackpoints")

        distance_km = trackpoints[-1]["distance_km"]
        elevations = [tp["elevation"] for tp in trackpoints]

        return {
            "trackpoints": trackpoints,
            "distance_km": round(distance_km, 2),
            "elevation_gain": round(total_elevation_gain, 0),
            "max_elevation": round(max(elevations), 1),
            "min_elevation": round(min(elevations), 1),
            "point_count": len(trackpoints),
        }

    @staticmethod
    def build_elevation_profile(
        trackpoints: list[dict[str, Any]],
        segment_km: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Segment a race route into 1km chunks with elevation and grade data.

        Args:
            trackpoints: List of trackpoint dicts from parse_gpx.
            segment_km: Length of each segment in km (default 1.0).

        Returns:
            List of segment dicts with start_km, end_km, avg_elevation, grade_pct.
        """
        if not trackpoints:
            return []

        total_distance = trackpoints[-1]["distance_km"]
        segments = []
        segment_index = 0

        for seg_start in range(0, int(math.ceil(total_distance)), 1):
            seg_end = min(seg_start + segment_km, total_distance)
            if seg_start >= total_distance:
                break

            segment_points = [
                tp for tp in trackpoints
                if seg_start <= tp["distance_km"] < seg_end
            ]

            if not segment_points:
                continue

            elevations = [tp["elevation"] for tp in segment_points]
            avg_elevation = sum(elevations) / len(elevations)

            start_elev = segment_points[0]["elevation"]
            end_elev = segment_points[-1]["elevation"]
            distance_m = (seg_end - seg_start) * 1000.0
            grade_pct = ((end_elev - start_elev) / distance_m * 100.0) if distance_m > 0 else 0.0

            segments.append({
                "segment_number": segment_index + 1,
                "start_km": round(seg_start, 2),
                "end_km": round(seg_end, 2),
                "avg_elevation": round(avg_elevation, 1),
                "grade_pct": round(grade_pct, 2),
                "elevation_gain": round(max(0, end_elev - start_elev), 1),
                "elevation_loss": round(max(0, start_elev - end_elev), 1),
            })
            segment_index += 1

        return segments

    @staticmethod
    def generate_planned_gpx(
        original_trackpoints: list[dict[str, Any]],
        pace_plan: list[dict[str, Any]],
        target_time_seconds: int,
        race_name: str = "RunCoach Race Plan",
    ) -> bytes:
        """Generate a Garmin-compatible GPX file with pace targets as course points.

        Args:
            original_trackpoints: Original route trackpoints.
            pace_plan: List of segment dicts with pacing info.
            target_time_seconds: Total target race time.
            race_name: Name for the course.

        Returns:
            GPX file content as bytes.
        """
        gpx = gpxpy.gpx.GPX()
        gpx.name = race_name
        gpx.description = f"RunCoach pacing plan - target {target_time_seconds}s"

        track = gpxpy.gpx.GPXTrack()
        track.name = race_name
        gpx.tracks.append(track)

        segment = gpxpy.gpx.GPXTrackSegment()
        track.segments.append(segment)

        for tp in original_trackpoints:
            point = gpxpy.gpx.GPXTrackPoint(
                latitude=tp["lat"],
                longitude=tp["lon"],
                elevation=tp["elevation"],
                time=datetime.fromisoformat(tp["time"]) if tp.get("time") else datetime.now(timezone.utc),
            )
            segment.points.append(point)

        route = gpxpy.gpx.GPXRoute()
        route.name = "Pace Targets"
        gpx.routes.append(route)

        for seg in pace_plan:
            km_marker = seg["end_km"]
            matching_points = [
                tp for tp in original_trackpoints
                if abs(tp["distance_km"] - km_marker) < 0.05
            ]

            if matching_points:
                ref_point = matching_points[0]
            else:
                ref_point = original_trackpoints[-1]

            pace_str = seg.get("target_pace_str", "")
            rtept = gpxpy.gpx.GPXRoutePoint(
                latitude=ref_point["lat"],
                longitude=ref_point["lon"],
                elevation=ref_point["elevation"],
            )
            rtept.name = f"KM {km_marker:.1f}"
            rtept.description = f"Target: {pace_str}/km | Cum: {seg.get('cumulative_time_str', '')}"
            rtept.type = "Course Point"
            route.points.append(rtept)

        return gpx.to_xml().encode("utf-8")
