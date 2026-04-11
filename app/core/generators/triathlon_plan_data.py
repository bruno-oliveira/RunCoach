"""Pre-encoded triathlon training plan data: Sprint and Olympic distances.

Data sourced from:
  IRONMAN/13-training-plan-sprint.md
  IRONMAN/12-training-plan-olympic.md

The Half Ironman plan is in triathlon_plan_data_70_3.py.
"""

from app.core.generators.triathlon_plan_data_70_3 import HALF_IRONMAN_PLAN  # noqa: F401

# ---------------------------------------------------------------------------
# Sprint plan  (8 weeks)   source: 13-training-plan-sprint.md
# ---------------------------------------------------------------------------

SPRINT_PLAN = [
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

OLYMPIC_PLAN = [
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
