"""Pre-encoded triathlon training plans for Sprint, Olympic, and Half Ironman distances.

Data sourced from:
  IRONMAN/13-training-plan-sprint.md
  IRONMAN/12-training-plan-olympic.md
  IRONMAN/10-training-plan-70-3.md
"""


class TriathlonPlanGenerator:
    """Returns pre-defined week-by-week triathlon training plans."""

    DISTANCES = {
        "sprint": {
            "label": "Sprint Triathlon",
            "swim": "750m",
            "bike": "20km",
            "run": "5km",
            "weeks": 8,
        },
        "olympic": {
            "label": "Olympic Triathlon",
            "swim": "1.5km",
            "bike": "40km",
            "run": "10km",
            "weeks": 16,
        },
        "half_ironman": {
            "label": "Half Ironman (70.3)",
            "swim": "1.9km",
            "bike": "90km",
            "run": "21.1km",
            "weeks": 20,
        },
    }

    # ---------------------------------------------------------------------------
    # Sprint plan  (8 weeks)   source: 13-training-plan-sprint.md
    # ---------------------------------------------------------------------------

    _SPRINT_PLAN = [
        {
            "week": 1, "phase": "base", "is_recovery": False,
            "swim_volume": "2,100m", "bike_volume": "2 hrs", "run_volume": "1.25 hrs", "total_hours": "3.5",
            "key_sessions": [
                {"type": "swim", "name": "Base Swim", "description": "600m: WU 200m easy, MS 300m continuous, CD 100m"},
                {"type": "bike", "name": "Foundation Ride", "description": "50 min easy-moderate. Last 5 min: brick run off bike"},
                {"type": "run", "name": "Easy Run", "description": "30 min easy steady pace"},
                {"type": "brick", "name": "Intro Brick", "description": "Bike 50 min → Run 5 min immediately off bike to feel the transition"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Base phase week 1: build comfort across all three disciplines. Walk breaks on the run are fine.",
        },
        {
            "week": 2, "phase": "base", "is_recovery": False,
            "swim_volume": "2,400m", "bike_volume": "2.3 hrs", "run_volume": "1.5 hrs", "total_hours": "4",
            "key_sessions": [
                {"type": "swim", "name": "Drill & Intervals", "description": "700m: WU 200m, 4×25 drill, MS 4×75 moderate RI 20 sec, CD 100m"},
                {"type": "bike", "name": "Moderate Ride", "description": "60 min moderate endurance, practice pacing"},
                {"type": "run", "name": "Steady Run + Pickups", "description": "35 min easy including some hills; end with 3×30 sec accelerations"},
                {"type": "brick", "name": "Bike-Run Brick", "description": "Bike 60 min → Run 8 min easy off the bike"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Build consistency. The brick on Sunday prepares your legs for the run-after-bike sensation.",
        },
        {
            "week": 3, "phase": "base", "is_recovery": False,
            "swim_volume": "2,700m", "bike_volume": "2.75 hrs", "run_volume": "1.75 hrs", "total_hours": "5",
            "key_sessions": [
                {"type": "swim", "name": "Interval Swim", "description": "800m: WU 200m, 6×25 drill, MS 4×100 moderate RI 20 sec, CD 100m"},
                {"type": "bike", "name": "Endurance Ride + Nutrition", "description": "75 min endurance — practice race-day nutrition strategy"},
                {"type": "run", "name": "Tempo Run", "description": "35 min: WU 10 min, MS 15 min moderate, CD 10 min with 4×30 sec pickups"},
                {"type": "brick", "name": "Brick Workout", "description": "Bike 75 min → Run 10 min moderate off bike, practice pacing"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Highest volume week of the base phase. Focus on nutrition during the longer bike ride.",
        },
        {
            "week": 4, "phase": "base", "is_recovery": True,
            "swim_volume": "2,100m", "bike_volume": "1.75 hrs", "run_volume": "1.25 hrs", "total_hours": "3.5",
            "key_sessions": [
                {"type": "swim", "name": "Easy Drill Swim", "description": "600m easy, focus on form and breathing"},
                {"type": "bike", "name": "Recovery Spin", "description": "30–35 min easy spin, keep effort low"},
                {"type": "run", "name": "Easy Run + Strides", "description": "30 min easy with strides at the end"},
                {"type": "brick", "name": "Recovery Brick", "description": "Bike 40 min moderate → Run 12 min moderate"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Recovery week: reduce volume by ~30%. Let your body absorb the training from weeks 1–3.",
        },
        {
            "week": 5, "phase": "build", "is_recovery": False,
            "swim_volume": "3,000m", "bike_volume": "3.25 hrs", "run_volume": "2 hrs", "total_hours": "5.5",
            "key_sessions": [
                {"type": "swim", "name": "Tempo Swim", "description": "900m: WU 200m, MS 4×150 steady RI 20 sec, CD 150m"},
                {"type": "bike", "name": "Long Ride + Nutrition", "description": "90 min ride; practice race nutrition strategy throughout"},
                {"type": "run", "name": "Tempo Run", "description": "35 min: WU 10 min, MS 15 min tempo, CD 10 min"},
                {"type": "brick", "name": "Race-Pace Brick", "description": "Bike 90 min → Run 15 min moderate off bike"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Build phase begins: increase intensity alongside volume. Tempo work sharpens race fitness.",
        },
        {
            "week": 6, "phase": "build", "is_recovery": False,
            "swim_volume": "3,300m", "bike_volume": "3.5 hrs", "run_volume": "2.25 hrs", "total_hours": "6",
            "key_sessions": [
                {"type": "swim", "name": "Race-Pace Swim", "description": "1000m: WU 200m, MS 6×100 moderate + 4×25 fast, CD 150m"},
                {"type": "bike", "name": "Intensity Ride", "description": "60 min: WU, MS 10 min tempo / 15 moderate / 10 tempo, CD"},
                {"type": "run", "name": "Strong Tempo Run", "description": "40 min: WU 10 min, MS 20 min tempo, CD 10 min"},
                {"type": "brick", "name": "Race-Effort Brick", "description": "Bike 105 min (incl. 20 min race effort) → Run 20 min (10 easy / 10 race pace)"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Peak build week. Race-effort work in the brick teaches your legs to run fast off the bike.",
        },
        {
            "week": 7, "phase": "build", "is_recovery": False,
            "swim_volume": "3,400m", "bike_volume": "3.75 hrs", "run_volume": "2.25 hrs", "total_hours": "6.5",
            "key_sessions": [
                {"type": "swim", "name": "Confidence Swim", "description": "1100m: WU 200m, MS 750m race pace, CD 150m"},
                {"type": "bike", "name": "Hard Interval Ride", "description": "65 min with 40 min moderate including intervals"},
                {"type": "run", "name": "Steady State Run", "description": "45 min: WU 10 min, MS 25 min steady-state, CD 10 min"},
                {"type": "brick", "name": "Race Simulation", "description": "Bike 75 min (25 min at race effort) → Run 25 min (15 min at race effort)"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Final big training week. The race simulation on Sunday tells you exactly what to expect on race day.",
        },
        {
            "week": 8, "phase": "taper", "is_recovery": True,
            "swim_volume": "1,500m", "bike_volume": "1.25 hrs", "run_volume": "1 hr", "total_hours": "3",
            "key_sessions": [
                {"type": "swim", "name": "Shakeout Swim", "description": "800m: WU 200m, MS pace work + fast efforts, CD 150m"},
                {"type": "bike", "name": "Easy Spin + Check", "description": "45 min: WU, 20 min easy-moderate, CD. Check bike is race-ready"},
                {"type": "run", "name": "Easy Activation Run", "description": "30 min easy with 4×30 sec pickups to stay sharp"},
                {"type": "swim", "name": "Pre-Race Swim", "description": "700m: WU 200m, MS 400m moderate, CD 150m"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["rest"], "sunday": ["race"],
            },
            "coaching_note": "Race week! Cut volume by ~50%. Trust your training. Stay hydrated and sleep well. Race day is Sunday.",
        },
    ]

    # ---------------------------------------------------------------------------
    # Olympic plan  (16 weeks)   source: 12-training-plan-olympic.md
    # ---------------------------------------------------------------------------

    _OLYMPIC_PLAN = [
        # --- Base Phase: Weeks 1–6 ---
        {
            "week": 1, "phase": "base", "is_recovery": False,
            "swim_volume": "4,600m", "bike_volume": "3 hrs", "run_volume": "1.75 hrs", "total_hours": "5.5",
            "key_sessions": [
                {"type": "swim", "name": "Base Swim", "description": "1500m: WU 300m easy, 6×25 drill, MS 800m moderate, CD 300m"},
                {"type": "bike", "name": "Endurance Ride", "description": "75 min: WU 10 min, MS 55 min moderate, CD 10 min"},
                {"type": "run", "name": "Easy Run", "description": "45 min easy steady pace"},
                {"type": "bike", "name": "Foundation Bike", "description": "60 min: WU 10 min, MS 40 min moderate, CD 10 min"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["bike"],
            },
            "coaching_note": "Base phase: build aerobic foundation across all disciplines with consistent moderate effort.",
        },
        {
            "week": 2, "phase": "base", "is_recovery": False,
            "swim_volume": "4,900m", "bike_volume": "3.5 hrs", "run_volume": "2 hrs", "total_hours": "6.5",
            "key_sessions": [
                {"type": "swim", "name": "Interval Swim", "description": "1600m: WU 300m, 6×25 drill, MS 3×300 moderate RI 30 sec, CD 300m"},
                {"type": "bike", "name": "Long Ride + Nutrition", "description": "90 min moderate endurance; practice race-day nutrition"},
                {"type": "run", "name": "Tempo Run", "description": "40 min: WU 10 min, MS 10 min tempo, CD 10 min + 5×30 sec strides"},
                {"type": "brick", "name": "Intro Brick", "description": "Bike 90 min → Run 10 min easy off the bike"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "First brick of the plan — get familiar with running on tired bike legs.",
        },
        {
            "week": 3, "phase": "base", "is_recovery": False,
            "swim_volume": "5,200m", "bike_volume": "4 hrs", "run_volume": "2.25 hrs", "total_hours": "7.5",
            "key_sessions": [
                {"type": "swim", "name": "Descending Swim", "description": "1700m: WU 300m, 8×25 drill, MS 4×300 moderate RI 30 sec, CD 300m"},
                {"type": "bike", "name": "Endurance Ride", "description": "105 min: endurance pace, practice race nutrition"},
                {"type": "run", "name": "Tempo Run", "description": "45 min: WU 10 min, MS 15 min tempo, CD 10 min + 6×30 sec pickups"},
                {"type": "brick", "name": "Brick Workout", "description": "Bike 105 min → Run 15 min moderate off bike"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Highest volume base week. Take nutrition seriously on the long bike.",
        },
        {
            "week": 4, "phase": "base", "is_recovery": True,
            "swim_volume": "3,900m", "bike_volume": "2.2 hrs", "run_volume": "1.75 hrs", "total_hours": "5",
            "key_sessions": [
                {"type": "swim", "name": "Easy Drill Focus", "description": "1200m easy with drill focus — prioritise stroke technique"},
                {"type": "bike", "name": "Recovery Spin", "description": "45 min easy spin"},
                {"type": "run", "name": "Easy Run + Strides", "description": "40 min easy with strides at the end"},
                {"type": "brick", "name": "Moderate Brick", "description": "Bike 50 min moderate → Run 15 min moderate"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Recovery week: drop volume by ~35%. Focus on recovery so you can attack the build phase.",
        },
        {
            "week": 5, "phase": "base", "is_recovery": False,
            "swim_volume": "5,500m", "bike_volume": "4.5 hrs", "run_volume": "2.5 hrs", "total_hours": "8",
            "key_sessions": [
                {"type": "swim", "name": "Race Pace Swim", "description": "1800m: WU 300m, MS 1000m moderate + 4×100 fast RI 30 sec, CD 300m"},
                {"type": "bike", "name": "Threshold Intervals", "description": "75 min: WU, MS 4×5 min threshold RI 3 min, CD"},
                {"type": "run", "name": "Tempo Run", "description": "45 min: WU 10 min, MS 20 min tempo, CD 10 min + 8×20 sec pickups"},
                {"type": "brick", "name": "Race-Effort Brick", "description": "Bike 120 min (20 min at race effort) → Run 20 min (10 easy / 10 moderate)"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Threshold work begins. These harder efforts raise your lactate threshold for race day.",
        },
        {
            "week": 6, "phase": "base", "is_recovery": False,
            "swim_volume": "5,800m", "bike_volume": "5 hrs", "run_volume": "2.75 hrs", "total_hours": "9",
            "key_sessions": [
                {"type": "swim", "name": "Continuous Race Swim", "description": "1900m: WU 300m, MS 1200m moderate + 6×50 fast RI 20 sec, CD 300m. Includes 1500m continuous at race effort"},
                {"type": "bike", "name": "Long Race-Effort Ride", "description": "135 min: long ride with 30 min at race effort mid-ride"},
                {"type": "run", "name": "Long Tempo Run", "description": "50 min: WU 10 min, MS 25 min tempo, CD 10 min"},
                {"type": "brick", "name": "Race Simulation Brick", "description": "Bike 135 min → Run 20 min (10 easy / 10 at race effort)"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "End of base phase — your highest base week. The body is adapting; race-effort segments build confidence.",
        },
        # --- Build Phase: Weeks 7–11 ---
        {
            "week": 7, "phase": "build", "is_recovery": False,
            "swim_volume": "6,100m", "bike_volume": "5.5 hrs", "run_volume": "3 hrs", "total_hours": "9.5",
            "key_sessions": [
                {"type": "swim", "name": "Long Interval Swim", "description": "2000m: WU 300m, MS 4×400 moderate + 4×75 fast RI 30 sec, CD 300m"},
                {"type": "bike", "name": "Threshold Ride", "description": "90 min: WU, MS 3×10 min threshold RI 4 min, CD"},
                {"type": "run", "name": "Long Run + Tempo", "description": "70 min: easy long run including 15 min tempo mid-run"},
                {"type": "brick", "name": "Race Simulation", "description": "Bike 150 min (45 min at race effort) → Run 25 min at race effort"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Build phase: intensity increases. Threshold intervals build your ability to sustain race pace.",
        },
        {
            "week": 8, "phase": "build", "is_recovery": False,
            "swim_volume": "6,100m", "bike_volume": "6 hrs", "run_volume": "3 hrs", "total_hours": "10",
            "key_sessions": [
                {"type": "swim", "name": "Time Trial Swim", "description": "2100m: WU 300m, MS 1500m time-trial pace, CD 300m"},
                {"type": "bike", "name": "Long Threshold Ride", "description": "90 min: WU, MS 4×8 min threshold RI 3 min, CD"},
                {"type": "run", "name": "Long Race-Effort Run", "description": "75 min: long run with 20 min at race effort"},
                {"type": "brick", "name": "Extended Brick", "description": "Bike 160 min (3×15 min race effort) → Run 25 min at race effort"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Your biggest training week. The extended brick on Sunday is the key workout — trust the process.",
        },
        {
            "week": 9, "phase": "build", "is_recovery": True,
            "swim_volume": "4,800m", "bike_volume": "3 hrs", "run_volume": "2.25 hrs", "total_hours": "6",
            "key_sessions": [
                {"type": "swim", "name": "Easy Recovery Swim", "description": "1500m easy with drill focus"},
                {"type": "bike", "name": "Easy Spin", "description": "60 min easy recovery spin"},
                {"type": "run", "name": "Easy Run + Strides", "description": "50 min easy with strides"},
                {"type": "brick", "name": "Moderate Brick", "description": "Bike 65 min moderate → Run 20 min moderate"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Recovery week: the body adapts during rest. Resist the urge to train harder.",
        },
        {
            "week": 10, "phase": "build", "is_recovery": False,
            "swim_volume": "6,200m", "bike_volume": "6.5 hrs", "run_volume": "3.5 hrs", "total_hours": "11",
            "key_sessions": [
                {"type": "swim", "name": "Race Pace Swim", "description": "2100m: WU 300m, MS 1650m at race pace, CD 300m"},
                {"type": "bike", "name": "Threshold Ride", "description": "95 min: WU, MS 5×6 min threshold RI 2 min, CD"},
                {"type": "run", "name": "Long Run + Race Effort", "description": "80 min: long run with 25 min at race effort"},
                {"type": "brick", "name": "Race Simulation Brick", "description": "Bike 165 min (50 min total race effort) → Run 30 min at race effort"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Peak volume week of the plan at 11 hours. Everything here is intentional preparation for race day.",
        },
        {
            "week": 11, "phase": "build", "is_recovery": False,
            "swim_volume": "5,900m", "bike_volume": "5 hrs", "run_volume": "3 hrs", "total_hours": "9",
            "key_sessions": [
                {"type": "swim", "name": "Race Pace Work", "description": "2000m: WU 300m, MS race pace work + speed pickups, CD 300m"},
                {"type": "bike", "name": "Threshold Ride", "description": "90 min: WU, MS 2×12 min threshold RI 4 min, CD"},
                {"type": "run", "name": "Moderate Long Run", "description": "75 min moderate effort with strong finish"},
                {"type": "brick", "name": "Final Race Simulation", "description": "Bike 2 hrs + Run 45 min at race effort"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Final big build week. The Sunday race simulation is your last dress rehearsal — execute it confidently.",
        },
        # --- Peak Phase: Week 12 ---
        {
            "week": 12, "phase": "peak", "is_recovery": False,
            "swim_volume": "5,500m", "bike_volume": "5 hrs", "run_volume": "2.75 hrs", "total_hours": "8.5",
            "key_sessions": [
                {"type": "swim", "name": "Confidence Swim", "description": "1800m: WU 300m, MS 1500m race pace, CD 300m"},
                {"type": "bike", "name": "Race Pace Ride", "description": "90 min: WU, MS includes 25 min at race pace, CD"},
                {"type": "run", "name": "Strong Tempo Run", "description": "55 min: WU 10 min, MS 35 min tempo, CD 10 min"},
                {"type": "brick", "name": "Peak Brick", "description": "Bike 120 min (45 min race effort) → Run 40 min (25 min race effort)"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Peak week: your sharpest, most race-specific training. Confidence is built here.",
        },
        # --- Taper Phase: Weeks 13–16 ---
        {
            "week": 13, "phase": "taper", "is_recovery": False,
            "swim_volume": "5,000m", "bike_volume": "4 hrs", "run_volume": "2.5 hrs", "total_hours": "7.5",
            "key_sessions": [
                {"type": "swim", "name": "Pace Work Swim", "description": "1700m: WU 300m, MS race pace work, CD 300m"},
                {"type": "bike", "name": "Moderate Ride", "description": "75 min: WU, MS 50 min moderate with some race effort, CD"},
                {"type": "run", "name": "Moderate Tempo", "description": "55 min: moderate effort with last 15 min strong"},
                {"type": "brick", "name": "Taper Brick", "description": "Bike 105 min (some race effort) → Run 20 min easy-moderate"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Taper begins: volume drops while you maintain race-specific intensity. Trust the process.",
        },
        {
            "week": 14, "phase": "taper", "is_recovery": False,
            "swim_volume": "4,400m", "bike_volume": "3 hrs", "run_volume": "2 hrs", "total_hours": "6",
            "key_sessions": [
                {"type": "swim", "name": "Race Segment Swim", "description": "1500m: WU 300m, MS race pace segments, CD 300m"},
                {"type": "bike", "name": "Moderate Ride + Race Efforts", "description": "60 min moderate with short race-pace efforts"},
                {"type": "run", "name": "Tempo Run", "description": "45 min: WU 10 min, MS 20 min tempo, CD 10 min"},
                {"type": "brick", "name": "Taper Brick", "description": "Bike 75 min moderate → Run 25 min moderate"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Legs are getting fresher. Maintain sharpness with short intense efforts within lower-volume sessions.",
        },
        {
            "week": 15, "phase": "taper", "is_recovery": False,
            "swim_volume": "3,700m", "bike_volume": "2 hrs", "run_volume": "1.25 hrs", "total_hours": "4",
            "key_sessions": [
                {"type": "swim", "name": "Short Pace Swim", "description": "1300m: WU 300m, MS pace work, CD 300m. Practice open-water sighting"},
                {"type": "bike", "name": "Easy Ride + Check", "description": "50 min easy-moderate. Check bike is race-ready"},
                {"type": "run", "name": "Easy Run + Strides", "description": "30 min easy with strides — stay sharp, don't tire"},
                {"type": "brick", "name": "Short Activation Brick", "description": "Bike 45 min easy → Run 15 min easy"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["run", "swim"], "sunday": ["brick"],
            },
            "coaching_note": "Deep taper: volume is very low. Focus on sleep, nutrition and mental preparation.",
        },
        {
            "week": 16, "phase": "taper", "is_recovery": True,
            "swim_volume": "2,000m", "bike_volume": "1.25 hrs", "run_volume": "1 hr", "total_hours": "3",
            "key_sessions": [
                {"type": "swim", "name": "Race-Week Swim", "description": "1000m: WU 300m, short pace pickups, CD 300m"},
                {"type": "bike", "name": "Easy Shake-Out Ride", "description": "40 min: WU, MS 15 min moderate, CD — bike check"},
                {"type": "run", "name": "Easy Activation Run", "description": "25 min easy with 4×30 sec pickups"},
                {"type": "swim", "name": "Pre-Race Swim", "description": "900m easy — open water swim if possible"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["swim", "run"], "wednesday": ["bike"],
                "thursday": ["swim", "run"], "friday": ["bike"], "saturday": ["rest"], "sunday": ["race"],
            },
            "coaching_note": "Race week! Minimal training, maximum rest. Everything is in place — now execute your race plan.",
        },
    ]

    # ---------------------------------------------------------------------------
    # Half Ironman (70.3) plan  (20 weeks)   source: 10-training-plan-70-3.md
    # Note: swim volumes converted from yards (1 yd ≈ 0.914 m)
    # ---------------------------------------------------------------------------

    _HALF_IRONMAN_PLAN = [
        # --- Base Phase: Weeks 1–8 ---
        {
            "week": 1, "phase": "base", "is_recovery": False,
            "swim_volume": "2,195m", "bike_volume": "2 hrs 45 min", "run_volume": "1 hr 45 min", "total_hours": "5.5",
            "key_sessions": [
                {"type": "bike", "name": "Power Intervals", "description": "45 min: WU, MS 4×20 sec sprint in high gear, CD"},
                {"type": "swim", "name": "Base Swim", "description": "1200 yd (1,097m): WU 300, 8×25 drill, MS 2×100 moderate, 8×25 kick, CD 300"},
                {"type": "run", "name": "Fartlek Run", "description": "30 min: WU 5 min, MS 6×30 sec VO2max, CD 5 min"},
                {"type": "run", "name": "Foundation Run", "description": "35–40 min easy aerobic — Sunday long run to build base"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["run"],
            },
            "coaching_note": "Base phase begins. The primary goal is developing aerobic capacity and injury resistance across all three disciplines.",
        },
        {
            "week": 2, "phase": "base", "is_recovery": False,
            "swim_volume": "3,840m", "bike_volume": "2 hrs", "run_volume": "1 hr 45 min", "total_hours": "5",
            "key_sessions": [
                {"type": "bike", "name": "Power Intervals", "description": "50 min: WU, MS 5×20 sec sprint in high gear, CD"},
                {"type": "swim", "name": "Fartlek + Sprint Swim", "description": "1300 yd (1,189m): WU 300, 8×25 drill, MS 4×100 build/descend, 4×25 kick, CD 300"},
                {"type": "brick", "name": "Brick Workout", "description": "Bike 45 min → Run 10 min moderate aerobic"},
                {"type": "swim", "name": "Long Base Swim", "description": "1600 yd (1,463m): WU 300, MS 1000 moderate, CD 300"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["brick"], "sunday": ["swim", "run"],
            },
            "coaching_note": "First brick workout. Weeks 2, 6 and so on include a Saturday bike-run brick.",
        },
        {
            "week": 3, "phase": "base", "is_recovery": False,
            "swim_volume": "4,025m", "bike_volume": "3 hrs 25 min", "run_volume": "2 hrs", "total_hours": "6.5",
            "key_sessions": [
                {"type": "bike", "name": "Power Intervals", "description": "50 min: WU, MS 5×20 sec sprint in high gear, CD"},
                {"type": "swim", "name": "Base Swim", "description": "1400 yd (1,280m): WU 300, 8×25 drill, MS 4×100 moderate, 8×25 kick, CD 300"},
                {"type": "run", "name": "Fartlek Run", "description": "35 min: WU 5 min, MS 8×30 sec VO2max, CD 5 min"},
                {"type": "bike", "name": "Long Foundation Bike", "description": "1 hr 15 min: WU, MS 55 min moderate, CD"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
            },
            "coaching_note": "Volume continues to build steadily. Three bikes and three swims this week — a full multi-sport load.",
        },
        {
            "week": 4, "phase": "base", "is_recovery": True,
            "swim_volume": "2,926m", "bike_volume": "1 hr 45 min", "run_volume": "1 hr 30 min", "total_hours": "4",
            "key_sessions": [
                {"type": "bike", "name": "Recovery Power Intervals", "description": "45 min: WU, MS 4×20 sec sprint, CD — keep effort easy"},
                {"type": "swim", "name": "Easy Base Swim", "description": "1000 yd (914m): WU 300, 8×25 drill, MS 2×100 moderate, CD 300"},
                {"type": "run", "name": "Easy Fartlek Run", "description": "30 min easy with 6×30 sec light pickups"},
                {"type": "brick", "name": "Recovery Brick", "description": "Bike 45 min → Run 10 min moderate — keep effort controlled"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "brick"],
            },
            "coaching_note": "Recovery week: every fourth week is reduced to allow your body to fully absorb the training.",
        },
        {
            "week": 5, "phase": "base", "is_recovery": False,
            "swim_volume": "3,705m", "bike_volume": "3 hrs 30 min", "run_volume": "2 hrs 10 min", "total_hours": "6.5",
            "key_sessions": [
                {"type": "bike", "name": "Short Hill Climbs", "description": "55 min: WU, MS 6×1 min hill climbs at speed, CD"},
                {"type": "swim", "name": "Base + Speed Swim", "description": "1450 yd (1,326m): WU 300, 8×25 drill, MS 3×100 + 6×25 speed, 8×25 kick, CD 300"},
                {"type": "run", "name": "Speed Intervals", "description": "39 min: WU 10 min, MS 8×30 sec with 2 min recovery, CD 9 min"},
                {"type": "bike", "name": "Long Foundation Bike", "description": "Two 90 min foundation rides — Saturday and Sunday"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["bike", "run"],
            },
            "coaching_note": "Hill climbing and speed work build power. Two long Saturday/Sunday bikes is a key load this week.",
        },
        {
            "week": 6, "phase": "base", "is_recovery": False,
            "swim_volume": "4,275m", "bike_volume": "2 hrs 25 min", "run_volume": "1 hr 25 min", "total_hours": "5",
            "key_sessions": [
                {"type": "bike", "name": "Hill Climbs", "description": "1 hr: WU, MS 7×1 min hill climbs at speed, CD"},
                {"type": "swim", "name": "Fartlek + Sprint Swim", "description": "1700 yd (1,555m): WU 300, 6×50 drill, MS 4×150 build/descend, 8×25 kick, CD 300"},
                {"type": "swim", "name": "Swim Time Trial", "description": "1400 yd (1,280m): WU 200, MS 1000 maximum effort, CD 200 — race simulation!"},
                {"type": "brick", "name": "Brick Workout", "description": "Bike 45 min → Run 15 min moderate"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["brick"], "sunday": ["swim", "run"],
            },
            "coaching_note": "Your first swim time trial this Sunday — swim 1000 yards at maximum effort to measure baseline fitness.",
        },
        {
            "week": 7, "phase": "base", "is_recovery": False,
            "swim_volume": "4,985m", "bike_volume": "3 hrs", "run_volume": "1 hr 40 min", "total_hours": "6.5",
            "key_sessions": [
                {"type": "bike", "name": "Short Climbs", "description": "1 hr 5 min: WU, MS 8×1 min hill climbs at speed, CD"},
                {"type": "swim", "name": "Base + Speed Swim", "description": "1700 yd (1,555m): WU 300, 8×25 drill, MS 5×100 + 8×25 speed, 8×25 kick, CD 300"},
                {"type": "run", "name": "Speed Intervals", "description": "42 min: WU 10 min, MS 10×30 sec VO2max with 2 min recovery, CD 10 min"},
                {"type": "bike", "name": "Long Foundation Bike", "description": "1 hr 45 min: WU, MS 1 hr 25 min moderate, CD — longest bike of base phase"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim"],
            },
            "coaching_note": "Final big base week. The 1h45 bike on Saturday is your longest ride so far — keep effort moderate.",
        },
        {
            "week": 8, "phase": "base", "is_recovery": True,
            "swim_volume": "4,070m", "bike_volume": "2 hrs 40 min", "run_volume": "1 hr 30 min", "total_hours": "5",
            "key_sessions": [
                {"type": "bike", "name": "Recovery Hill Climbs", "description": "55 min: WU, MS 6×1 min hill climbs, CD — reduced intensity"},
                {"type": "swim", "name": "Recovery Base Swim", "description": "1250 yd (1,143m): WU 300, 8×25 drill, MS 3×100 + 6×25 speed, CD 300"},
                {"type": "swim", "name": "Fartlek + Sprint Swim", "description": "1600 yd (1,463m): WU 300, 8×25 drill, MS 4×150 build, 8×25 kick, CD 300"},
                {"type": "brick", "name": "Recovery Brick", "description": "Bike 45 min → Run 15 min moderate"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "brick"],
            },
            "coaching_note": "Second recovery week. The base phase ends here. Rest up — the build phase brings harder work.",
        },
        # --- Build Phase: Weeks 9–14 ---
        {
            "week": 9, "phase": "build", "is_recovery": False,
            "swim_volume": "5,350m", "bike_volume": "3 hrs 15 min", "run_volume": "2 hrs 30 min", "total_hours": "7",
            "key_sessions": [
                {"type": "bike", "name": "Long Hill Climbs", "description": "1 hr: WU, MS 2×5 min hill climbs at VO2max, CD"},
                {"type": "swim", "name": "Base + VO2max Swim", "description": "1750 yd (1,600m): WU 300, 8×25 drill, MS 3×100 + 4×75 VO2max + 6×25 speed, 8×25 kick, CD 300"},
                {"type": "run", "name": "Lactate Intervals", "description": "32 min: WU 10 min, MS 12×30 sec VO2max with 30 sec recovery, CD 10 min"},
                {"type": "bike", "name": "Long Ride", "description": "2 hrs easy-moderate. Build phase long ride begins — stay aerobic"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
            },
            "coaching_note": "Build phase: lactate intervals in all three disciplines will maximize aerobic capacity and faster speeds.",
        },
        {
            "week": 10, "phase": "build", "is_recovery": False,
            "swim_volume": "5,510m", "bike_volume": "2 hrs 50 min", "run_volume": "1 hr 45 min", "total_hours": "6.5",
            "key_sessions": [
                {"type": "bike", "name": "Lactate Intervals", "description": "1 hr: WU, MS 2×3 min VO2max intervals on flat/rolling terrain, CD"},
                {"type": "swim", "name": "Base + VO2max Swim", "description": "1825 yd (1,669m): WU 300, 8×25 drill, MS 3×100 + 5×75 VO2max + 6×25 speed, 8×25 kick, CD 300"},
                {"type": "run", "name": "Lactate Intervals", "description": "34 min: WU 10 min, MS 14×30 sec VO2max, CD 10 min + strides"},
                {"type": "brick", "name": "Long Brick", "description": "Bike 1 hr → Run 20 min moderate"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["brick"], "sunday": ["swim", "run"],
            },
            "coaching_note": "Saturday brick week. Lactate intervals are demanding — take full recoveries between efforts.",
        },
        {
            "week": 11, "phase": "build", "is_recovery": False,
            "swim_volume": "5,530m", "bike_volume": "3 hrs 45 min", "run_volume": "2 hrs 50 min", "total_hours": "8",
            "key_sessions": [
                {"type": "bike", "name": "Long Hill Climbs", "description": "1 hr 5 min: WU, MS 3×5 min hill climbs at VO2max, CD"},
                {"type": "swim", "name": "Base + VO2max Swim", "description": "1900 yd (1,738m): WU 300, 8×25 drill, MS 3×100 + 6×75 VO2max + 6×25 speed, 8×25 kick, CD 300"},
                {"type": "swim", "name": "Swim Time Trial", "description": "2150 yd (1,966m): WU 250, MS 1650 maximum effort (1 mile), CD 250"},
                {"type": "run", "name": "Long Run", "description": "1 hr 5 min: WU 10 min, MS 45 min moderate, CD 10 min"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
            },
            "coaching_note": "Sunday swim time trial — 1650 yards at max effort measures your fitness before the final build weeks.",
        },
        {
            "week": 12, "phase": "build", "is_recovery": True,
            "swim_volume": "4,025m", "bike_volume": "2 hrs 35 min", "run_volume": "1 hr 45 min", "total_hours": "5.5",
            "key_sessions": [
                {"type": "bike", "name": "Lactate Intervals", "description": "1 hr: WU, MS 2×3 min VO2max, CD — recovery intensity"},
                {"type": "swim", "name": "Recovery Swim", "description": "1400 yd (1,280m): WU 300, 8×25 drill, MS 3×100 + 4×75 VO2max, CD 300"},
                {"type": "run", "name": "Lactate Intervals", "description": "32 min: WU 10 min, MS 12×30 sec VO2max, CD 10 min"},
                {"type": "swim", "name": "Optional Sprint Triathlon", "description": "Race day: Swim 800m, Bike 12 miles, Run 3 miles — or do a time trial on your own"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["race"],
            },
            "coaching_note": "Recovery week with an optional sprint triathlon tune-up. Even if you don't race, keep effort easy.",
        },
        {
            "week": 13, "phase": "build", "is_recovery": False,
            "swim_volume": "5,760m", "bike_volume": "4 hrs", "run_volume": "2 hrs 55 min", "total_hours": "8.5",
            "key_sessions": [
                {"type": "bike", "name": "Long Hill Climbs", "description": "1 hr 10 min: WU, MS 4×5 min hill climbs at VO2max, CD"},
                {"type": "swim", "name": "Base + VO2max Swim", "description": "1900 yd (1,738m): WU 300, 8×25 drill, MS 5×100 + 4×100 VO2max, 8×25 kick, CD 300"},
                {"type": "bike", "name": "Long Ride", "description": "2 hrs 30 min: WU, MS 2 hrs 10 min moderate, CD — your longest ride to date"},
                {"type": "run", "name": "Long Run", "description": "1 hr 10 min: WU 10 min, MS 50 min moderate, CD 10 min"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
            },
            "coaching_note": "Biggest build week yet — 2h30 long bike and 1h10 long run. These long efforts build race-day endurance.",
        },
        {
            "week": 14, "phase": "build", "is_recovery": False,
            "swim_volume": "5,945m", "bike_volume": "3 hrs 15 min", "run_volume": "2 hrs 50 min", "total_hours": "8",
            "key_sessions": [
                {"type": "bike", "name": "Lactate Intervals", "description": "1 hr 15 min: WU, MS 4×3 min VO2max on flat/rolling terrain, CD"},
                {"type": "swim", "name": "Base + VO2max Swim", "description": "2000 yd (1,829m): WU 300, 8×25 drill, MS 6×100 + 4×100 VO2max, 8×25 kick, CD 300"},
                {"type": "run", "name": "Long Lactate Run", "description": "40 min: WU 10 min, MS 20×30 sec VO2max with 30 sec recovery, CD 10 min"},
                {"type": "brick", "name": "Long Brick", "description": "Bike 1 hr 15 min → Run 30 min moderate"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "brick"],
            },
            "coaching_note": "Final build week. The long brick on Sunday is race-specific preparation — aim for even pacing.",
        },
        # --- Peak Phase: Weeks 15–18 ---
        {
            "week": 15, "phase": "peak", "is_recovery": False,
            "swim_volume": "6,125m", "bike_volume": "4 hrs 15 min", "run_volume": "3 hrs", "total_hours": "9",
            "key_sessions": [
                {"type": "bike", "name": "Tempo Bike", "description": "1 hr: WU 13 min, MS 2×12 min threshold with 10 min recovery, CD 13 min"},
                {"type": "swim", "name": "Base + VO2max Swim", "description": "2100 yd (1,920m): WU 300, 8×25 drill, MS 6×100 + 5×100 VO2max, 8×25 kick, CD 300"},
                {"type": "bike", "name": "Long Ride", "description": "2 hrs 45 min: WU, MS 2 hrs 25 min moderate, CD — your longest ride"},
                {"type": "run", "name": "Long Run", "description": "1 hr 20 min: WU 10 min, MS 1 hr moderate, CD 10 min — your longest run"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
            },
            "coaching_note": "Peak phase begins. Longest endurance work of the plan: 2h45 bike and 1h20 run. Stay aerobic.",
        },
        {
            "week": 16, "phase": "peak", "is_recovery": True,
            "swim_volume": "4,665m", "bike_volume": "2 hrs 20 min", "run_volume": "2 hrs 15 min", "total_hours": "6",
            "key_sessions": [
                {"type": "bike", "name": "Tempo Bike", "description": "55 min: WU 17 min, MS 22 min threshold, CD 16 min"},
                {"type": "swim", "name": "Recovery Swim", "description": "1600 yd (1,463m): WU 300, 8×25 drill, MS 4×100 + 4×100 VO2max, CD 300"},
                {"type": "run", "name": "Tempo Run", "description": "34 min: WU 10 min, MS 14 min threshold, CD 10 min"},
                {"type": "swim", "name": "Olympic-Distance Tune-Up", "description": "Optional: Swim 1.5km → Bike 40km → Run 10km — or a time trial"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["race"],
            },
            "coaching_note": "Recovery week with an optional Olympic-distance tune-up race. A great fitness check before the final push.",
        },
        {
            "week": 17, "phase": "peak", "is_recovery": False,
            "swim_volume": "6,125m", "bike_volume": "4 hrs 30 min", "run_volume": "3 hrs 10 min", "total_hours": "9.5",
            "key_sessions": [
                {"type": "bike", "name": "Tempo Bike", "description": "1 hr 5 min: WU 21 min, MS 24 min threshold, CD 20 min"},
                {"type": "swim", "name": "Base + VO2max Swim", "description": "2100 yd (1,920m): WU 300, 8×25 drill, MS 5×100 + 6×100 VO2max, 8×25 kick, CD 300"},
                {"type": "bike", "name": "Peak Long Ride", "description": "3 hrs: WU, MS 2 hrs 40 min moderate, CD — longest ride of the plan"},
                {"type": "run", "name": "Peak Long Run", "description": "1 hr 30 min: WU 10 min, MS 1 hr 10 min moderate, CD 10 min — your longest run"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
            },
            "coaching_note": "Your peak training week: 3 hr bike and 1h30 run. Peak volume at ~9.5 hrs total — you are ready.",
        },
        {
            "week": 18, "phase": "peak", "is_recovery": False,
            "swim_volume": "6,138m", "bike_volume": "3 hrs 45 min", "run_volume": "2 hrs 30 min", "total_hours": "8.5",
            "key_sessions": [
                {"type": "bike", "name": "Tempo Bike", "description": "1 hr 10 min: WU 22 min, MS 26 min threshold, CD 22 min"},
                {"type": "swim", "name": "Base + VO2max Swim", "description": "2100 yd (1,920m): WU 300, 8×25 drill, MS 5×100 + 6×100 VO2max, 8×25 kick, CD 300"},
                {"type": "swim", "name": "Swim Time Trial", "description": "2512 yd (2,297m): WU 200, MS 2112 yd (1.2 miles) maximum effort, CD 200 — final time trial!"},
                {"type": "brick", "name": "Long Race-Simulation Brick", "description": "Bike 1 hr 45 min → Run 45 min moderate — your final major brick workout"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["brick"], "sunday": ["swim", "run"],
            },
            "coaching_note": "Final peak week: 1.2-mile swim time trial and a 1h45+45min brick. Confidence-building before the taper.",
        },
        # --- Taper Phase: Weeks 19–20 ---
        {
            "week": 19, "phase": "taper", "is_recovery": False,
            "swim_volume": "5,670m", "bike_volume": "3 hrs 45 min", "run_volume": "2 hrs 50 min", "total_hours": "8.5",
            "key_sessions": [
                {"type": "bike", "name": "Tempo Bike", "description": "1 hr 15 min: WU 19 min, MS 2×14 min threshold with 10 min recovery, CD 18 min"},
                {"type": "swim", "name": "Base + VO2max Swim", "description": "2100 yd (1,920m): WU 300, MS 5×100 + 6×100 VO2max, CD 300"},
                {"type": "run", "name": "Tempo Run", "description": "40 min: WU 10 min, MS 20 min threshold, CD 10 min"},
                {"type": "run", "name": "Long Run", "description": "1 hr 5 min: WU 10 min, MS 45 min moderate, CD 10 min — taper long run"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
            },
            "coaching_note": "Taper begins Thursday. Volume will steadily decrease to ensure you arrive to the start line fresh.",
        },
        {
            "week": 20, "phase": "taper", "is_recovery": True,
            "swim_volume": "2,560m", "bike_volume": "1 hr 45 min", "run_volume": "1 hr", "total_hours": "4",
            "key_sessions": [
                {"type": "bike", "name": "Tempo Bike", "description": "1 hr: WU 13 min, MS 2×12 min threshold with 10 min recovery, CD 13 min"},
                {"type": "swim", "name": "Race-Week Swim", "description": "1700 yd (1,555m): WU 300, 8×25 drill, MS 3×100 + 6×100 VO2max, CD 300"},
                {"type": "run", "name": "Tempo Run", "description": "32 min: WU 10 min, MS 12 min threshold, CD 10 min"},
                {"type": "swim", "name": "Pre-Race Swim", "description": "1100 yd (1,006m): WU 300, MS 2×200 threshold, 4×25 speed, CD 300"},
            ],
            "weekly_schedule": {
                "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
                "thursday": ["bike"], "friday": ["swim"], "saturday": ["swim"], "sunday": ["race"],
            },
            "coaching_note": "Race week! Minimal training — trust your 20 weeks of preparation. Race day is Sunday: Swim 1.2mi → Bike 56mi → Run 13.1mi.",
        },
    ]

    def generate_plan(self, distance: str) -> list[dict]:
        """Return the pre-defined weekly plan for the given distance.

        Args:
            distance: One of 'sprint', 'olympic', 'half_ironman'

        Returns:
            List of weekly plan dicts.

        Raises:
            ValueError: If distance is not recognised.
        """
        if distance == "sprint":
            return list(self._SPRINT_PLAN)
        elif distance == "olympic":
            return list(self._OLYMPIC_PLAN)
        elif distance == "half_ironman":
            return list(self._HALF_IRONMAN_PLAN)
        else:
            raise ValueError(f"Unknown distance: {distance!r}. Choose from: sprint, olympic, half_ironman")

    def get_distance_info(self, distance: str) -> dict:
        """Return metadata for a distance."""
        if distance not in self.DISTANCES:
            raise ValueError(f"Unknown distance: {distance!r}")
        return self.DISTANCES[distance]
