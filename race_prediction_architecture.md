# Race Prep Feature Architecture

## Overview

A new "Race Prep" page where users upload a race GPX file and receive an elevation-adjusted pacing blueprint with downloadable GPX for Garmin watches. The system auto-estimates finish time based on the user's recent running data (VDOT from RunLogs).

---

## User Flow

1. **Upload GPX** → Drag & drop or select race GPX file
2. **Auto-Analysis** → System instantly shows:
   - Route distance (from GPX)
   - Elevation profile
   - **Flat-ground estimate** (based on user's VDOT)
   - **Elevation-adjusted estimate** (accounts for hills)
   - Feasibility indicator (realistic / challenging / aggressive)
3. **Optional Override** → User can adjust target time if desired
4. **Generate Blueprint** → Segment-by-segment pacing plan
5. **Download** → Export planned GPX for Garmin

---

## UI Flow

```
┌─────────────────────────────────────────────┐
│  Upload Race GPX                            │
│  [Drag & drop or browse]                    │
└─────────────────────────────────────────────┘

         ↓ (auto-analyzes)

┌─────────────────────────────────────────────┐
│  Route Analysis                             │
│  Distance: 21.1 km                          │
│  Elevation: +350m                           │
│                                             │
│  Your VDOT: 42.3 (from 12 recent runs)      │
│  ─────────────────────────────────          │
│  Flat-ground estimate:    1:48:30           │
│  Elevation penalty:       +4:15             │
│  Elevation-adjusted:      1:52:45  🟢       │
│                                             │
│  [Adjust target time]  [Generate Blueprint] │
└─────────────────────────────────────────────┘

         ↓ (generate blueprint)

┌─────────────────────────────────────────────┐
│  Race Blueprint - 1:52:45                   │
│                                             │
│  [Elevation Profile Chart with Pace Overlay]│
│                                             │
│  Seg 1: 0-1km  ↑+2%  5:34/km  → 5:34       │
│  Seg 2: 1-2km  ↑+1%  5:28/km  → 11:02      │
│  Seg 3: 2-3km  ↓-1%  5:18/km  → 16:20      │
│  ...                                        │
│                                             │
│  [Download Planned GPX for Garmin]          │
└─────────────────────────────────────────────┘
```

---

## Architecture

### New Files

| File | Purpose |
|------|---------|
| `app/services/gpx_service.py` | GPX parsing and generation |
| `app/services/race_pacing_service.py` | Elevation-adjusted pacing strategy engine |
| `app/schemas/race_prep_schemas.py` | Request/response Pydantic models |
| `app/routers/race_prep.py` | API + page endpoints |
| `app/templates/race_prep.html` | Upload form + blueprint visualization |
| `app/static/js/race_prep.js` | Frontend logic, charts, GPX download |
| `app/static/css/race_prep.css` | Race prep page styling |

### Modified Files

| File | Change |
|------|--------|
| `requirements.txt` | Add `gpxpy>=1.6.0` |
| `app/routers/__init__.py` | Export race_prep router |
| `app/main.py` | Mount race_prep router |
| `app/templates/components/nav.html` | Add "Race Prep" nav link |

---

## Services

### GPXService (`app/services/gpx_service.py`)

```python
class GPXService:
    def parse_gpx(file_content: bytes) -> dict
        # Extract trackpoints: lat, lon, elevation, cumulative distance
        # Returns {"trackpoints": [...], "distance_km": float, "elevation_gain": float}

    def build_elevation_profile(trackpoints: list, segment_km: float = 1.0) -> list
        # Segment race into 1km chunks with avg elevation, grade %
        # Returns [{"start_km": 0, "end_km": 1, "avg_elevation": 120, "grade_pct": 2.1, ...}]

    def generate_planned_gpx(
        original_trackpoints: list,
        pace_plan: list[RaceSegment],
        target_time_seconds: int
    ) -> bytes
        # Create new GPX with pace targets as course points/extensions
        # Garmin-compatible format with <gpx:rte> course points
```

### RacePacingService (`app/services/race_pacing_service.py`)

```python
class RacePacingService:
    def get_user_vdot(user_id: str, db, days: int = 90) -> dict
        # Calculate median VDOT from recent RunLogs
        # Returns {"vdot": float, "run_count": int, "confidence": str}

    def predict_flat_time(vdot: float, distance_km: float) -> int
        # Seconds, from VDOTCalculator.predict_time_for_distance

    def predict_elevation_adjusted_time(
        vdot: float,
        distance_km: float,
        elevation_profile: list
    ) -> dict
        # Returns {"flat_time": X, "elevation_adjusted": Y, "elevation_penalty": Z}

    def generate_pace_blueprint(
        elevation_profile: list,
        target_time_seconds: int,
        user_vdot: float
    ) -> RaceBlueprint
        # Segment-by-segment pacing with elevation adjustments

    def validate_feasibility(
        target_time: int,
        flat_time: int,
        elevation_adjusted: int
    ) -> dict
        # Returns feasibility_label, message, color
```

---

## Schemas (`app/schemas/race_prep_schemas.py`)

```python
class GPXAnalysisResponse(BaseModel):
    distance_km: float
    total_elevation_gain: float
    max_elevation: float
    min_elevation: float
    flat_estimate_seconds: int        # Based on VDOT, no elevation
    elevation_adjusted_seconds: int  # Accounts for hills
    elevation_penalty_seconds: int   # The "hill cost"
    user_vdot: float
    vdot_confidence: str             # "high", "medium", "low"
    feasibility: dict                # {label, message, color}

class RacePrepRequest(BaseModel):
    target_time_seconds: Optional[int]  # If None, use auto-estimate
    distance_km: Optional[float]        # If None, use GPX distance

class RaceSegment(BaseModel):
    segment_number: int
    start_km: float
    end_km: float
    elevation_m: float
    grade_pct: float
    target_pace_min_km: float
    target_time_seconds: int
    cumulative_time_seconds: int

class RaceBlueprint(BaseModel):
    segments: list[RaceSegment]
    total_distance_km: float
    target_time_seconds: int
    estimated_time_seconds: int
    user_vdot: float
    feasibility: dict
```

---

## Router Endpoints (`app/routers/race_prep.py`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/race-prep` | Render upload page |
| `POST` | `/api/race-prep/analyze` | Upload GPX → Return analysis + auto-estimate |
| `POST` | `/api/race-prep/blueprint` | Generate pacing blueprint |
| `GET` | `/api/race-prep/download-gpx/{session_id}` | Download planned GPX |

---

## Pacing Algorithm

### Time Estimation

1. Calculate user's VDOT from recent runs (median of top-3 VDOTs, last 90 days)
2. Predict flat-ground time for race distance using VDOTCalculator
3. Analyze elevation profile → segment grades
4. Calculate elevation penalty per segment:
   - If grade > 0%: `penalty += grade * 12 sec/km`
   - If grade < 0%: `bonus -= grade * 5 sec/km` (max -15 sec/km)
5. `elevation_adjusted = flat_time + total_penalty - total_bonus`

### Blueprint Generation

For each 1km segment:
1. Calculate avg grade from elevation profile
2. Get base pace from user's VDOT for race distance
3. Adjust pace:
   - If grade > 0%: `pace += grade * 12 sec/km`
   - If grade < 0%: `pace -= grade * 5 sec/km` (max -15 sec/km)
4. Clamp pace within ±30 sec/km of base pace
5. Calculate segment time from adjusted pace
6. Track cumulative time

### Feasibility Validation

| Condition | Label | Color |
|-----------|-------|-------|
| target <= flat_time * 0.90 | Aggressive | Red |
| target <= flat_time * 0.95 | Challenging | Yellow |
| flat_time * 0.95 < target <= elevation_adjusted * 1.05 | Realistic | Green |
| target > elevation_adjusted * 1.05 | Conservative | Blue |

---

## Dependencies

- `gpxpy>=1.6.0` - Python GPX parser/generator (add to requirements.txt)
- `python-multipart>=0.0.20` - Already present (for file uploads)

---

## Garmin GPX Export Format

The generated GPX will include:
- Original route track from uploaded GPX
- Course points (`<gpx:rtept>`) at each kilometer marker
- Pace target embedded in `<gpx:description>` or `<gpx:extensions>`
- Compatible with Garmin Connect "Courses" feature for pace alerts

---

## Session Handling

Blueprints are stored in memory (dict) with UUID keys for download links. No database persistence needed since this is transient race-day planning data. Session cleanup handled via TTL or on-demand garbage collection.
