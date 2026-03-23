import math
import random
from typing import List, Dict, Any, Optional

from app.core.strength_plan import (
    derive_experience_level,
    generate_strength_session as _build_strength_session,
    get_phase_focus_rotation,
)

TRAINING_TIP_DATABASE = {
    "foundation": [
        "Establish a consistent training schedule - same time daily builds habit",
        "Start with conservative mileage increases (10% rule maximum)",
        "Focus on building your aerobic base before adding intensity",
        "Create a dedicated training space at home for pre/post-run routines",
        "Set up your gear night before to eliminate morning barriers"
    ],
    "routine": [
        "Develop pre-run warm-up routine: 5min walk + dynamic stretches",
        "Establish post-run recovery routine: stretching + nutrition timing",
        "Create a sleep schedule targeting 7-9 hours consistently",
        "Build hydration habits throughout day, not just during runs",
        "Set weekly training goals that are process-oriented (consistency over speed)"
    ],
    "equipment": [
        "Get fitted for proper running shoes at specialty running store",
        "Test different socks to prevent blisters during longer runs",
        "Consider GPS watch for tracking pace and distance accurately",
        "Invest in quality running clothes that prevent chafing",
        "Create a fueling belt or system for long run nutrition"
    ],
    "form": [
        "Focus on quick cadence (180+ steps per minute) for efficiency",
        "Keep shoulders relaxed and arms swinging forward, not across body",
        "Maintain upright posture - imagine a string pulling you upward",
        "Land mid-foot rather than heel striking for better shock absorption",
        "Practice running form drills 2x per week: high knees, butt kicks, bounding"
    ],
    "consistency": [
        "Never miss two consecutive training days - consistency trumps perfection",
        "Have backup plans for bad weather: treadmill, indoor alternatives",
        "Track your training in a log or app to monitor progress and stay motivated",
        "Find a training partner or group for accountability on tough days",
        "Celebrate showing up even when motivation is low"
    ],
    "recovery": [
        "Take ice baths after particularly hard workouts to reduce inflammation",
        "Use foam rolling 3-4 times per week, focusing on legs and hips",
        "Schedule active recovery days: gentle walking, swimming, or cycling",
        "Prioritize sleep - it's when your muscles repair and strengthen",
        "Consider massage therapy or self-massage tools for deep tissue work"
    ],
    "endurance": [
        "Practice negative splitting runs: second half faster than first",
        "Include progression runs: start easy, finish at threshold pace",
        "Build mental toughness by pushing through discomfort in final miles",
        "Test different fueling strategies during runs over 90 minutes",
        "Practice running on tired legs with back-to-back training days"
    ],
    "mental": [
        "Develop race mantras for different parts of race",
        "Practice visualization techniques: see yourself succeeding",
        "Create contingency plans for bad race moments (cramps, bad weather)",
        "Break long runs into smaller, manageable segments mentally",
        "Practice positive self-talk during challenging training sessions"
    ],
    "nutrition": [
        "Time your pre-run meals: 2-3 hours before for larger meals",
        "Practice race day breakfast during training weeks",
        "Experiment with different types of fuel during long runs",
        "Focus on post-run nutrition within 30 minutes: 3:1 carb:protein ratio",
        "Stay hydrated throughout day, not just around training"
    ],
    "pace": [
        "Learn your different paces: easy, tempo, interval, race pace",
        "Practice perceived effort vs. actual pace to develop internal awareness",
        "Use breathing patterns to gauge intensity: conversational for easy",
        "Test race pace in shorter segments during long runs",
        "Practice pace judgment by running without looking at your watch"
    ],
    "strength": [
        "Include core work 3x per week: planks, side planks, dead bugs",
        "Add single-leg exercises: Bulgarian split squats, single-leg deadlifts",
        "Incorporate plyometric exercises: box jumps, bounding, jump squats",
        "Focus on hip strengthening: clamshells, side-lying leg raises",
        "Practice running-specific strength: hill repeats, stair climbing"
    ],
    "injury_prevention": [
        "Listen to your body - distinguish between discomfort and pain",
        "Address minor aches immediately before they become major issues",
        "Include mobility work: hip flexor stretches, ankle mobility",
        "Vary running surfaces to reduce repetitive stress on joints",
        "Schedule regular rest days to allow for tissue repair"
    ],
    "race_simulation": [
        "Practice race day outfit during long runs including shoes and socks",
        "Simulate race start times in your training (early morning practice)",
        "Test your complete fueling strategy during long training runs",
        "Practice running expected race terrain: hills, flats, trails",
        "Do a dress rehearsal run at race pace for shorter distances"
    ],
    "strategy": [
        "Develop pacing strategy: conservative start, strong middle, fast finish",
        "Plan your nutrition timing: when to take gels, water, electrolytes",
        "Create mental checkpoints for different race distances",
        "Have backup plans for weather conditions: heat, rain, wind",
        "Practice race day decision making in training scenarios"
    ],
    "gear": [
        "Test all race day gear in training multiple times",
        "Break in new shoes gradually - never wear new shoes on race day",
        "Practice with your fueling system: belt, handheld, bottles",
        "Test anti-chafe products: Body Glide, Vaseline, specialized balms",
        "Choose socks based on distance - thicker for longer races"
    ],
    "confidence": [
        "Review your training log to see how far you've come",
        "Practice finishing strong in training runs to build race confidence",
        "Remind yourself of tough workouts you've completed successfully",
        "Visualize crossing the finish line at your goal time",
        "Trust your training - you've put in the work"
    ],
    "taper_preparation": [
        "Start reducing mileage while maintaining some intensity",
        "Focus on quality over quantity in remaining workouts",
        "Use extra time for sleep, nutrition, and mental preparation",
        "Avoid trying new things during taper period",
        "Stay busy with light activities to distract from pre-race nerves"
    ],
    "mental_training": [
        "Practice race day meditation or breathing exercises",
        "Develop pre-race routine to calm nerves and focus mind",
        "Write down your race goals and review them daily",
        "Practice dealing with pre-race anxiety: visualization, positive talk",
        "Prepare mentally for different race scenarios and outcomes"
    ],
    "final_preparations": [
        "Lay out race day gear night before race",
        "Plan your race morning timeline: wake up, breakfast, travel",
        "Check weather forecast and prepare appropriate clothing",
        "Charge your GPS watch and any electronic devices",
        "Prepare post-race recovery items: change of clothes, food"
    ],
    "logistics": [
        "Map out your route to race start and timing",
        "Plan parking or transportation to race venue",
        "Know race course: hills, aid stations, finish line location",
        "Prepare race day nutrition and pack it night before",
        "Have backup plans for transportation and gear issues"
    ],
    "race_day": [
        "Arrive at race venue early to avoid stress and allow warm-up",
        "Stick to your pre-race nutrition routine exactly as practiced",
        "Trust your training and don't get caught up in pre-race excitement",
        "Execute your pacing plan regardless of what others are doing",
        "Enjoy experience and celebrate your accomplishment"
    ],
    "taper": [
        "Embrace reduced mileage - your body is getting stronger",
        "Fight the urge to add extra training during taper",
        "Use extra mental energy for visualization and race planning",
        "Focus on hydration and nutrition more than ever",
        "Get extra sleep - every hour counts during taper"
    ],
    "visualization": [
        "Visualize entire race from start to finish successfully",
        "Imagine yourself handling tough moments with strength",
        "Picture crossing the finish line with your goal time",
        "See yourself executing your race strategy perfectly",
        "Visualize feeling strong and confident throughout race"
    ],
    "recovery_focus": [
        "Prioritize sleep above all else during final week",
        "Focus on anti-inflammatory foods: berries, leafy greens, omega-3s",
        "Stay hydrated but don't overdo it",
        "Keep moving with light activity to prevent stiffness",
        "Prepare mentally for post-race recovery period"
    ],
    "sharpening": [
        "Include short, sharp workouts to maintain fitness without fatigue",
        "Practice race pace efforts to stay familiar with goal speed",
        "Keep some intensity but reduce overall volume significantly",
        "Focus on running form and efficiency in final workouts",
        "Stay loose and mobile with stretching and light drills"
    ],
    "final_workouts": [
        "Make your last quality workout count but don't overdo it",
        "Practice race pace one final time to build confidence",
        "Keep workouts short but purposeful in final days",
        "Focus on feeling good and strong rather than pushing limits",
        "End each workout feeling like you could do more"
    ],
    "race_ready": [
        "Trust your taper - you're more fit than you feel",
        "Resist urge to test your fitness one last time",
        "Focus on feeling fresh and energized rather than tired",
        "Believe in your training and all the work you've done",
        "You're ready - now it's time to execute"
    ],
    "peak_performance": [
        "Execute your race strategy without hesitation",
        "Stay present and focused on each mile of race",
        "Draw strength from your training when things get tough",
        "Push through discomfort knowing you've prepared for it",
        "Leave everything on course - no regrets"
    ],
    "race_execution": [
        "Start conservatively - it's better to finish strong",
        "Stick to your nutrition plan regardless of how you feel",
        "Focus on form when fatigue sets in during later miles",
        "Use your mental training techniques when facing challenges",
        "Break race into smaller segments mentally"
    ],
    "post_race": [
        "Celebrate your accomplishment regardless of outcome",
        "Focus on proper recovery: nutrition, hydration, rest",
        "Reflect on what went well and what you learned",
        "Plan your return to training with adequate recovery time",
        "Thank supporters, volunteers, and fellow racers"
    ],
    "advanced_strategy": [
        "Practice surging and changing pace during training runs",
        "Learn to run tangents efficiently on road courses",
        "Master downhill running technique to save energy",
        "Practice drafting and positioning in crowded races",
        "Develop race-specific pacing for different course profiles"
    ],
    "course_specific": [
        "Study race course elevation profile and plan accordingly",
        "Practice running on similar terrain if possible",
        "Identify key points on course for mental checkpoints",
        "Plan your effort based on course challenges and features",
        "Know where tough sections are and prepare mentally"
    ],
    "conditions": [
        "Practice running in expected weather conditions",
        "Adjust your race strategy for heat, humidity, or cold",
        "Have gear options ready for different weather scenarios",
        "Practice hydration and fueling for specific conditions",
        "Mentally prepare for less-than-ideal race weather"
    ],
    "marathon_focus": [
        "Practice marathon pace during long runs to build familiarity",
        "Test your complete fueling strategy multiple times",
        "Include very long runs (20+ miles) to build mental confidence",
        "Practice running on tired legs in final miles of long runs",
        "Master art of patience in early marathon miles"
    ],
    "fueling_master": [
        "Create detailed fueling timeline for race day",
        "Practice with exact race day fuels during training",
        "Know where aid stations are and plan your fueling around them",
        "Practice taking nutrition while running at race pace",
        "Have backup fuel options in case of stomach issues"
    ],
    "mental_toughness": [
        "Practice embracing discomfort during training runs",
        "Develop strategies for pushing through marathon wall",
        "Build confidence by completing challenging workouts",
        "Practice positive self-talk during difficult training sessions",
        "Prepare mentally for unique challenges of 26.2 miles"
    ]
}

class TrainingPlanGenerator:
    def __init__(self):
        self.workout_types = {
            'easy': {'intensity': 'low', 'description': 'Easy recovery run'},
            'tempo': {'intensity': 'medium', 'description': 'Tempo run at threshold pace'},
            'interval': {'intensity': 'high', 'description': 'High-intensity intervals'},
            'long': {'intensity': 'medium', 'description': 'Long distance run'},
            'hill': {'intensity': 'high', 'description': 'Hill repeats and strength training'},
            'rest': {'intensity': 'rest', 'description': 'Rest day'},
            'strength': {'intensity': 'low', 'description': 'Strength training'}
        }

    def _get_distance_category(self, target_distance: float) -> str:
        """Map target distance to a category key."""
        if target_distance <= 5:
            return '5K'
        elif target_distance <= 10:
            return '10K'
        elif target_distance <= 21.1:
            return 'Half'
        elif target_distance == 30.0:
            return 'Trail'
        else:
            return 'Marathon'

    def _calculate_phases(self, weeks: int, target_distance: float = 10.0) -> Dict[str, int]:
        """
        Calculate distance-aware phase distribution.

        Marathon/half marathon plans get longer builds and tapers.
        5K plans get more sharpening (peak) and shorter tapers.

        Args:
            weeks: Total training plan duration
            target_distance: Race distance in km (affects phase proportions)

        Returns:
            Dict with phase durations: {'base': int, 'build': int, 'peak': int, 'taper': int}
        """
        category = self._get_distance_category(target_distance)

        # Distance-specific ideal proportions: (base%, build%, peak%, taper_weeks)
        # Taper is prescribed as a fixed week count (not a %), then remaining weeks
        # are split among base/build/peak proportionally.
        phase_profiles = {
            '5K':       {'base_pct': 0.35, 'build_pct': 0.30, 'peak_pct': 0.20, 'taper': 1},
            '10K':      {'base_pct': 0.35, 'build_pct': 0.30, 'peak_pct': 0.15, 'taper': 1},
            'Half':     {'base_pct': 0.35, 'build_pct': 0.35, 'peak_pct': 0.10, 'taper': 2},
            'Trail':    {'base_pct': 0.35, 'build_pct': 0.35, 'peak_pct': 0.10, 'taper': 2},
            'Marathon': {'base_pct': 0.30, 'build_pct': 0.35, 'peak_pct': 0.05, 'taper': 3},
        }

        profile = phase_profiles[category]

        # Taper is prescribed by distance (marathon = 3 weeks, 5K = 1 week)
        taper = min(profile['taper'], max(1, weeks // 4))

        # Distribute remaining weeks among base/build/peak
        remaining = weeks - taper
        total_pct = profile['base_pct'] + profile['build_pct'] + profile['peak_pct']
        base = max(2, round(remaining * profile['base_pct'] / total_pct))
        build = max(2, round(remaining * profile['build_pct'] / total_pct))
        peak = max(1, remaining - base - build)

        # Safety: if rounding pushed us over, trim from the largest non-taper phase
        while base + build + peak + taper > weeks:
            if base >= build and base >= peak:
                base -= 1
            elif build >= peak:
                build -= 1
            else:
                peak -= 1

        # Safety: if rounding left us short, add to build
        while base + build + peak + taper < weeks:
            build += 1

        return {'base': base, 'build': build, 'peak': peak, 'taper': taper}

    def _get_long_run_ratio_range(self, phase: str, target_distance: float, weeks: int) -> tuple[float, float]:
        """
        Get the long run ratio range (min, max) for a phase.
        
        Args:
            phase: Training phase (base, build, peak, taper)
            target_distance: Race distance in km
            weeks: Total weeks in plan (for adjusting ratios in short plans)
        
        Returns:
            Tuple of (min_ratio, max_ratio)
        """
        category = self._get_distance_category(target_distance)

        ratio_ranges = {
            '5K': {
                'base': (0.25, 0.30),
                'build': (0.28, 0.32),
                'peak': (0.30, 0.35),
                'taper': (0.25, 0.30)
            },
            '10K': {
                'base': (0.28, 0.33),
                'build': (0.31, 0.36),
                'peak': (0.35, 0.40),
                'taper': (0.28, 0.33)
            },
            'Half': {
                'base': (0.30, 0.35),
                'build': (0.33, 0.38),
                'peak': (0.38, 0.43),
                'taper': (0.30, 0.35)
            },
            'Trail': {
                'base': (0.30, 0.35),
                'build': (0.35, 0.40),
                'peak': (0.40, 0.45),
                'taper': (0.35, 0.40)
            },
            'Marathon': {
                'base': (0.32, 0.38),
                'build': (0.35, 0.42),
                'peak': (0.40, 0.45),
                'taper': (0.32, 0.38)
            }
        }
        
        min_ratio, max_ratio = ratio_ranges[category][phase]
        
        if weeks <= 10:
            adjustment = 0.03
            min_ratio = max(0.25, min_ratio - adjustment)
            max_ratio = max(min_ratio + 0.02, max_ratio - adjustment)
        
        return (min_ratio, max_ratio)

    def _calculate_long_run_ratio(self, phase: str, week_number: int, phases: Dict[str, int],
                                target_distance: float, is_recovery_week: bool, total_weeks: int) -> float:
        """
        Calculate long run ratio with progression within phase.

        Args:
            phase: Current training phase
            week_number: Week number in plan (1-indexed)
            phases: Dictionary with phase durations
            target_distance: Race distance in km
            is_recovery_week: Whether this is a recovery week
            total_weeks: Total weeks in plan

        Returns:
            Long run ratio as a decimal (e.g., 0.35 for 35%)
        """
        min_ratio, max_ratio = self._get_long_run_ratio_range(phase, target_distance, total_weeks)

        if phase == 'base':
            week_in_phase = week_number - 1
            total_in_phase = phases['base']
        elif phase == 'build':
            week_in_phase = week_number - phases['base'] - 1
            total_in_phase = phases['build']
        elif phase == 'peak':
            week_in_phase = week_number - phases['base'] - phases['build'] - 1
            total_in_phase = phases['peak']
        else:
            week_in_phase = week_number - phases['base'] - phases['build'] - phases['peak'] - 1
            total_in_phase = phases['taper']

        if total_in_phase > 1:
            progression = week_in_phase / (total_in_phase - 1)
        else:
            progression = 0.0

        ratio = min_ratio + (max_ratio - min_ratio) * progression

        if is_recovery_week:
            recovery_reduction = random.uniform(0.08, 0.12)
            ratio = ratio * (1.0 - recovery_reduction)
            recovery_min = max(0.20, min_ratio - 0.05)
            ratio = max(recovery_min, ratio)
        else:
            ratio = max(0.25, ratio)

        return round(ratio, 3)

    def _get_workout_distribution(self, total_km: float, max_runs: int, phase: str = 'build',
                                is_recovery_week: bool = False, week_number: int = 1, phases: Dict[str, int] = None,
                                target_distance: float = 10.0) -> Dict[str, int]:
        """
        Calculate how many of each workout type per week.
        """
        is_backward_compatible_call = (phase == 'build' and not is_recovery_week and 
                                     week_number == 1 and phases is None and 
                                     target_distance == 10.0)
        
        if is_backward_compatible_call:
            return self._get_workout_distribution_simple(total_km, max_runs)
        
        long_runs = 1
        has_recovery = True
 
        if phase == 'base' or is_recovery_week:
            quality_workouts = 0
        elif phase == 'build':
            if phases:
                week_in_build = week_number - phases['base']
            else:
                week_in_build = week_number
            if week_in_build <= 2:
                quality_workouts = 1 if max_runs >= 4 else 0
            else:
                quality_workouts = 2 if max_runs >= 5 else 1
        elif phase == 'peak':
            quality_workouts = 2 if max_runs >= 5 else 1
        else:
            quality_workouts = 0
 
        # Recovery is an additional non-running day, does NOT count towards max_runs
        actual_run_slots = max_runs
        running_days = actual_run_slots - long_runs - quality_workouts
        easy_runs = max(0, running_days)
        rest_days = 7 - (max_runs + 1)

        if target_distance == 30.0 and quality_workouts > 0:
            if week_number % 4 in [1, 2]:
                distribution = {
                    'easy': easy_runs,
                    'long': long_runs,
                    'interval': 0,
                    'tempo': 0,
                    'hill': quality_workouts,
                    'rest': rest_days
                }
            else:
                distribution = {
                    'easy': easy_runs,
                    'long': long_runs,
                    'interval': quality_workouts,
                    'tempo': 0,
                    'hill': 0,
                    'rest': rest_days
                }
        else:
            distribution = {
                'easy': easy_runs,
                'long': long_runs,
                'interval': 1 if quality_workouts >= 1 else 0,
                'tempo': 1 if quality_workouts >= 2 else 0,
                'hill': 0,
                'rest': rest_days
            }

        return distribution



    def _schedule_workout_types(self, distribution: Dict[str, int], phase: str,
                               week_number: int, is_recovery_week: bool) -> List[Optional[str]]:
        """
        Assign workout types to specific days.
        Recovery is always on Day 2 and does NOT count towards max_runs.
        """
        workout_types = [None] * 7

        workout_types[1] = 'recovery'

        workout_types[5] = 'long'
        distribution['long'] -= 1

        if phase != 'base' and not is_recovery_week:
            quality_slots = [2, 3, 4]
            for day_idx in quality_slots:
                if workout_types[day_idx] is not None:
                    continue
                if distribution['hill'] > 0:
                    workout_types[day_idx] = 'hill'
                    distribution['hill'] -= 1
                elif distribution['interval'] > 0:
                    workout_types[day_idx] = 'interval'
                    distribution['interval'] -= 1
                elif distribution['tempo'] > 0:
                    workout_types[day_idx] = 'tempo'
                    distribution['tempo'] -= 1

        for day_idx in range(7):
            if workout_types[day_idx] is not None:
                continue
            if distribution['easy'] > 0:
                workout_types[day_idx] = 'easy'
                distribution['easy'] -= 1

        for day_idx in range(7):
            if workout_types[day_idx] is None:
                workout_types[day_idx] = 'rest'
                distribution['rest'] -= 1

        return workout_types
    
    def _get_workout_distribution_simple(self, total_km: float, max_runs: int) -> Dict[str, int]:
        """
        Simplified version of workout distribution for backward compatibility with tests.
        """
        long_runs = 1
        running_days = max_runs - long_runs

        if max_runs == 3:
            easy_runs = 1
            rest_days = 3
            quality_workouts = 1
        elif max_runs == 4:
            easy_runs = 2
            rest_days = 2
            quality_workouts = 1
        elif max_runs == 5:
            easy_runs = 2
            rest_days = 1
            quality_workouts = 2
        elif max_runs == 6:
            easy_runs = 3
            rest_days = 0
            quality_workouts = 2
        else:
            easy_runs = max(0, running_days - quality_workouts)
            rest_days = max_runs - long_runs - quality_workouts - easy_runs
            quality_workouts = max(1, running_days - easy_runs)

        return {
            'easy': easy_runs,
            'long': long_runs,
            'interval': quality_workouts if quality_workouts == 1 or (quality_workouts == 2 and max_runs == 4) else (1 if quality_workouts >= 1 else 0),
            'tempo': 1 if quality_workouts >= 2 and max_runs > 4 else 0,
            'hill': 0,
            'rest': rest_days
        }

    def _generate_daily_workouts(self, week_number: int, total_km: float, distribution: Dict[str, int],
                                target_distance: float, weeks: int, phase: str,
                                is_recovery_week: bool,
                                vdot: Optional[float] = None,
                                pace_zones: Optional[Dict] = None,
                                experience_level: str = "beginner",
                                week_in_phase: int = 0) -> List[Dict[str, Any]]:
        """
        Generate daily workouts with integrated strength/cross-training and rest day rules
        """
        long_run_distance = self._calculate_long_run_distance(total_km, target_distance, weeks, week_number, phase, is_recovery_week)
        remaining_km = total_km - long_run_distance

        quality_distances = self._calculate_quality_distances(total_km, phase,
                                                        distribution, is_recovery_week, long_run_distance, target_distance)

        workout_types = self._schedule_workout_types(distribution.copy(), phase, week_number, is_recovery_week)

        # Cap quality workouts: 85% of long run AND absolute physiological caps
        max_quality_pct = long_run_distance * 0.85
        quality_caps = {'tempo': 12.0, 'interval': 10.0, 'hill': 8.0}
        for key in quality_distances:
            cap = min(max_quality_pct, quality_caps.get(key, max_quality_pct))
            if quality_distances[key] > cap:
                quality_distances[key] = round(cap, 1)

        quality_total = sum(quality_distances.values())
        easy_total = remaining_km - quality_total

        easy_runs = sum(1 for wt in workout_types if wt == 'easy')

        # Cap individual easy runs at 95% of long run distance
        max_easy_distance = long_run_distance * 0.95
        total_max_easy = max_easy_distance * easy_runs
        # Accept the shortfall instead of redistributing to quality workouts
        actual_easy_total = min(easy_total, total_max_easy)

        easy_distances = [round(actual_easy_total / max(easy_runs, 1), 1) for _ in range(easy_runs)]
        
        # Cap individual easy runs to 95% of long run distance
        easy_distances = [round(min(d, max_easy_distance), 1) for d in easy_distances]

        easy_run_counter = 0
        strength_session_counter = 0

        # Track counters for quality workouts to get their distances
        quality_counters = {wt: 0 for wt in ['tempo', 'interval', 'hill']}

        workouts = []

        for day in range(7):
            workout_type = workout_types[day]

            if workout_type is None:
                continue

            day_number = day + 1

            # Get distance based on workout type
            if workout_type == 'easy':
                # Get easy distance from pre-calculated list
                if easy_run_counter < len(easy_distances):
                    easy_distance = easy_distances[easy_run_counter]
                else:
                    easy_distance = easy_distances[0]  # Fallback to first distance
                easy_run_counter += 1
            elif workout_type in ['tempo', 'interval', 'hill']:
                # Get quality workout distance
                if workout_type in quality_distances:
                    distance = quality_distances[workout_type]
                    easy_distance = distance
                    quality_counters[workout_type] += 1
                else:
                    easy_distance = 0
            else:
                easy_distance = 0

            # Generate workout based on type
            if workout_type == 'rest':
                workout = self._generate_rest_day(day_number)
            elif workout_type == 'recovery':
                workout = self._generate_recovery_day(day_number, phase)
            elif workout_type == 'long':
                workout = self._generate_long_run(day_number, long_run_distance, total_km, pace_zones=pace_zones)
            elif workout_type == 'easy':
                workout = self._generate_easy_run(day_number, easy_distance, total_km, pace_zones=pace_zones)
            elif workout_type == 'tempo':
                workout = self._generate_tempo_run(day_number, easy_distance, total_km,
                                                   vdot=vdot, pace_zones=pace_zones)
            elif workout_type == 'interval':
                workout = self._generate_interval_run(day_number, easy_distance, total_km,
                                                      vdot=vdot, pace_zones=pace_zones)
            elif workout_type == 'hill':
                workout = self._generate_hill_workout(day_number, easy_distance)

            # Overlay key workout description for quality sessions in build/peak
            if workout_type in ('interval', 'tempo', 'hill') and phase in ('build', 'peak'):
                from app.core.key_workout_library import KeyWorkoutLibrary
                key_wk = KeyWorkoutLibrary.get_for_phase(
                    target_distance, phase, week_in_phase, workout_type
                )
                if key_wk:
                    if pace_zones:
                        key_wk = KeyWorkoutLibrary.inject_vdot_paces(key_wk, pace_zones)
                    workout['description'] = key_wk['description']
                    workout['key_workout_id'] = key_wk['id']
                    workout['key_workout_name'] = key_wk['name']
                    workout['structure'] = key_wk['structure']
                    workout['key_workout_rationale'] = key_wk['rationale']

            if workout_type == 'easy':
                strength_session = self._generate_strength_session(
                    day_number, week_number, phase, workout_type,
                    session_index=strength_session_counter,
                    experience_level=experience_level,
                )
                if strength_session:
                    workout['strength_session'] = strength_session
                    strength_session_counter += 1

            # Add coaching rationale
            from app.core.coaching_notes_generator import generate_coaching_note
            workout['coaching_rationale'] = generate_coaching_note(
                workout_type, phase, week_number, target_distance, is_recovery_week
            )

            workouts.append(workout)
        
        return workouts

    def _calculate_quality_distances(self, total_km: float, phase: str,
                                    distribution: Dict[str, int], is_recovery_week: bool,
                                    long_run_distance: float = 0, target_distance: float = 10.0) -> Dict[str, float]:
        """
        Calculate distances for quality workouts based on phase distribution.
        """
        quality_distances = {}

        if is_recovery_week:
            return {'tempo': 0, 'interval': 0, 'hill': 0}

        phase_dist = self._get_phase_distribution(phase, target_distance)

        remaining_km = total_km - long_run_distance

        if distribution['tempo'] > 0:
            quality_distances['tempo'] = round(remaining_km * (phase_dist['tempo'] / (1 - phase_dist['long'])), 1)
        if distribution['interval'] > 0:
            quality_distances['interval'] = round(remaining_km * (phase_dist['interval'] / (1 - phase_dist['long'])), 1)
        if distribution['hill'] > 0:
            quality_distances['hill'] = round(remaining_km * (phase_dist['hill'] / (1 - phase_dist['long'])), 1)

        return quality_distances

    def _get_phase_distribution(self, phase: str, target_distance: float = 10.0) -> Dict[str, float]:
        """
        Get distance distribution percentages for each phase.

        Returns percentages that sum to 100% across all workout types.
        Long run percentages increase with race distance for proper endurance building.

        Args:
            phase: Current training phase (base, build, peak, taper)
            target_distance: Race distance in km (adjusts long run percentage)

        Returns:
            Dict with percentage breakdown of workout types
        """
        base_distributions = {
            '5K': {'long': 0.35, 'tempo': 0.0, 'interval': 0.0, 'hill': 0.0, 'easy': 0.65},
            '10K': {'long': 0.40, 'tempo': 0.0, 'interval': 0.0, 'hill': 0.0, 'easy': 0.60},
            'Half': {'long': 0.45, 'tempo': 0.0, 'interval': 0.0, 'hill': 0.0, 'easy': 0.55},
            'Trail': {'long': 0.45, 'tempo': 0.0, 'interval': 0.0, 'hill': 0.0, 'easy': 0.55},
            'Marathon': {'long': 0.45, 'tempo': 0.0, 'interval': 0.0, 'hill': 0.0, 'easy': 0.55}
        }

        build_distributions = {
            '5K': {'long': 0.35, 'tempo': 0.12, 'interval': 0.10, 'hill': 0.05, 'easy': 0.38},
            '10K': {'long': 0.40, 'tempo': 0.12, 'interval': 0.10, 'hill': 0.05, 'easy': 0.33},
            'Half': {'long': 0.45, 'tempo': 0.10, 'interval': 0.08, 'hill': 0.04, 'easy': 0.33},
            'Trail': {'long': 0.45, 'tempo': 0.10, 'interval': 0.08, 'hill': 0.04, 'easy': 0.33},
            'Marathon': {'long': 0.45, 'tempo': 0.10, 'interval': 0.08, 'hill': 0.04, 'easy': 0.33}
        }

        peak_distributions = {
            '5K': {'long': 0.33, 'tempo': 0.12, 'interval': 0.10, 'hill': 0.05, 'easy': 0.40},
            '10K': {'long': 0.38, 'tempo': 0.12, 'interval': 0.10, 'hill': 0.05, 'easy': 0.35},
            'Half': {'long': 0.43, 'tempo': 0.10, 'interval': 0.08, 'hill': 0.04, 'easy': 0.35},
            'Trail': {'long': 0.43, 'tempo': 0.10, 'interval': 0.08, 'hill': 0.04, 'easy': 0.35},
            'Marathon': {'long': 0.43, 'tempo': 0.10, 'interval': 0.08, 'hill': 0.04, 'easy': 0.35}
        }

        taper_distributions = {
            '5K': {'long': 0.30, 'tempo': 0.12, 'interval': 0.0, 'hill': 0.0, 'easy': 0.58},
            '10K': {'long': 0.35, 'tempo': 0.12, 'interval': 0.0, 'hill': 0.0, 'easy': 0.53},
            'Half': {'long': 0.40, 'tempo': 0.10, 'interval': 0.0, 'hill': 0.0, 'easy': 0.50},
            'Trail': {'long': 0.40, 'tempo': 0.10, 'interval': 0.0, 'hill': 0.0, 'easy': 0.50},
            'Marathon': {'long': 0.40, 'tempo': 0.10, 'interval': 0.0, 'hill': 0.0, 'easy': 0.50}
        }

        dist_key = self._get_distance_category(target_distance)
        distributions = {
            'base': base_distributions,
            'build': build_distributions,
            'peak': peak_distributions,
            'taper': taper_distributions,
        }
        return distributions.get(phase, taper_distributions)[dist_key]

    def _calculate_long_run_distance(self, total_km: float, target_distance: float,
                                  weeks: int = 12, week_number: int = 1, phase: str = 'build',
                                  is_recovery_week: bool = False) -> float:
        """
        Calculate long run distance with proper progression and phase-specific percentage.
        Long run percentage increases with race distance for appropriate endurance building.
        """
        phases = self._calculate_phases(weeks, target_distance)
        long_run_ratio = self._calculate_long_run_ratio(
            phase, week_number, phases, target_distance, is_recovery_week, weeks
        )

        long_run_base = total_km * long_run_ratio

        long_run_cap = {
            5.0: 8.0,
            10.0: 15.0,
            21.1: 20.0,
            30.0: 24.0,
            42.2: 32.0
        }.get(target_distance, target_distance * 0.77)

        long_run_base = min(long_run_base, long_run_cap)

        min_long_run = target_distance * 0.25

        if is_recovery_week:
            recovery_min = target_distance * 0.20
            min_long_run = recovery_min

        return round(max(min_long_run, long_run_base), 1)

    def _generate_rest_day(self, day: int) -> Dict[str, Any]:
        """
        Generate regular rest day (NOT recovery day after long run)

        Note: Swimming/cross-training only on recovery days, not regular rest days
        """
        rest_descriptions = [
            'Complete rest day for muscle repair and recovery',
            'Light stretching and mobility work (15-20 minutes)',
            'Active recovery with gentle walking (20-30 minutes)',
            'Rest day with foam rolling focus (15-20 minutes)'
        ]

        return {
            'day': day,
            'type': 'rest',
            'distance': 0,
            'intensity': 'rest',
            'description': rest_descriptions[day % len(rest_descriptions)]
        }

    def _generate_recovery_day(self, day: int, phase: str) -> Dict[str, Any]:
        """
        Generate active recovery day (swimming or walking).
        """
        recovery_descriptions = [
            'Active recovery: 30-45min swimming OR easy walking',
            'Active recovery: Light swimming for cardio without impact',
            'Active recovery: Easy walking to promote blood flow'
        ]

        return {
            'day': day,
            'type': 'recovery',
            'distance': 0,
            'intensity': 'very_low',
            'description': recovery_descriptions[day % len(recovery_descriptions)]
        }

    def _generate_strength_session(
        self,
        day: int,
        week_number: int,
        phase: str,
        workout_type: str,
        session_index: int = 0,
        experience_level: str = "beginner",
    ) -> Optional[Dict[str, Any]]:
        """Generate a periodized strength session to attach to an easy run.

        Args:
            day: Day number (1-7)
            week_number: Week number in plan
            phase: Training phase (base, build, peak, taper)
            workout_type: Must be 'easy' — other types return None
            session_index: 0-based counter of easy runs in this week,
                           used to cycle through the phase focus rotation
            experience_level: beginner / intermediate / advanced
        """
        if workout_type != 'easy':
            return None

        # Taper: only one session (the first easy run), reduced volume
        if phase == 'taper' and session_index > 0:
            return None

        rotation = get_phase_focus_rotation(phase)
        focus = rotation[session_index % len(rotation)]

        return _build_strength_session(focus, phase, experience_level, week_number)

    def _generate_long_run(self, day: int, distance: float, total_km: float,
                            pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
        """Generate long run workout"""
        if pace_zones:
            e_pace = pace_zones["E"]["pace_str"]
            m_pace = pace_zones["M"]["pace_str"]
            long_run_notes = [
                f'Long run at {e_pace} (E-pace). Focus on endurance and mental toughness.',
                f'Long run: first {round(distance*0.8, 1)}km at {e_pace}, final {round(distance*0.2, 1)}km at {m_pace} (M-pace).',
                f'Long run at {e_pace} (E-pace). Practice nutrition every 45-60 minutes.',
            ]
        else:
            long_run_notes = [
                f'Long run at conversational pace. Focus on endurance and mental toughness.',
                f'Long run with race pace finish: first {round(distance*0.8, 1)}km easy, final {round(distance*0.2, 1)}km at goal pace.',
                f'Long run on varied terrain if possible. Practice nutrition strategy every 45-60 minutes.'
            ]

        return {
            'day': day,
            'type': 'long',
            'distance': round(distance, 1),
            'intensity': 'medium',
            'description': long_run_notes[day % len(long_run_notes)]
        }

    def _generate_easy_run(self, day: int, distance: float, total_km: float,
                            pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
        """Generate easy run workout"""
        if pace_zones:
            e_pace = pace_zones["E"]["pace_str"]
            easy_variations = [
                f'Easy recovery run at {e_pace} (E-pace). Should feel conversational.',
                f'Easy run at {e_pace} with strides: 6×100m accelerations at the end.',
                f'Conversational pace at {e_pace}. Focus on relaxed form.',
            ]
        else:
            easy_variations = [
                f'Easy recovery run. Should be conversational pace.',
                f'Easy run with strides: main run easy, finish with 6x100m accelerations.',
                f'Conversational pace run. Focus on relaxed form and breathing.'
            ]

        return {
            'day': day,
            'type': 'easy',
            'distance': distance,
            'intensity': 'low',
            'description': easy_variations[day % len(easy_variations)]
        }
    
    def _generate_tempo_run(self, day: int, distance: float, total_km: float,
                            vdot: Optional[float] = None,
                            pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
        """Generate tempo run workout, with specific paces if VDOT is available."""
        if pace_zones:
            t_pace = pace_zones["T"]["pace_str"]
            m_pace = pace_zones["M"]["pace_str"]
            tempo_variations = [
                f'Tempo run: 2km warmup, {round(distance-2, 1)}km at {t_pace} (T-pace), 2km cooldown.',
                f'Cruise intervals: 3×{round((distance-2)/3, 1)}km at {t_pace} (T-pace) with 3min recovery.',
                f'Tempo run with surges: main tempo at {t_pace} (T-pace) with 4×30sec faster surges.',
            ]
        else:
            tempo_variations = [
                f'Tempo run: 2km warmup, {round(distance-2, 1)}km at threshold pace, 2km cooldown.',
                f'Cruise intervals: 3×{round((distance-2)/3, 1)}km at tempo pace with 3min recovery.',
                f'Tempo run with surges: Main tempo with 4×30sec faster surges.',
            ]

        from app.core.vdot_calculator import VDOTCalculator
        description = VDOTCalculator.inject_paces_into_description(
            tempo_variations[day % len(tempo_variations)], pace_zones or {}, "tempo"
        )

        return {
            'day': day,
            'type': 'tempo',
            'distance': round(distance, 1),
            'intensity': 'medium',
            'description': description,
        }
    
    def _generate_interval_run(self, day: int, distance: float, total_km: float,
                               vdot: Optional[float] = None,
                               pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
        """Generate interval run workout.

        Guardrail: 1000m+ intervals are gated behind 40km/week base.
        200m repeats are offered for 5K-focused runners with <30km base.
        VDOT pace zones are injected when available.
        """
        if pace_zones:
            i_pace = pace_zones["I"]["pace_str"]
            t_pace = pace_zones["T"]["pace_str"]
            m_pace = pace_zones["M"]["pace_str"]
            r_pace = pace_zones["R"]["pace_str"]
        else:
            i_pace = t_pace = m_pace = r_pace = None

        # ── Guardrail: gate long intervals behind sufficient base ──────
        if total_km >= 40:
            # Full suite including 1000m+ intervals
            if i_pace:
                interval_workouts = [
                    f'VO₂max intervals: 6×400m at {i_pace} (I-pace) with 400m recovery jog.',
                    f'Pyramid: 400m–800m–1200m–800m–400m at {i_pace} (I-pace) with equal recovery.',
                    f'Hill repeats: 8×45sec at {t_pace} (T-pace) effort with jog-down recovery.',
                    f'Yasso 800s: {max(4, round(distance / 0.8))}×800m at {m_pace} (M-pace).',
                    f'VO₂max intervals: 5×1000m at {i_pace} (I-pace) with 400m recovery jog.',
                ]
            else:
                interval_workouts = [
                    f'VO₂max intervals: 6×400m at 5K pace with 400m recovery jog.',
                    f'Pyramid intervals: 400m–800m–1200m–800m–400m with equal recovery.',
                    f'Hill repeats: 8×45sec at threshold effort with jog-down recovery.',
                    f'Yasso 800s: {max(4, round(distance / 0.8))}×800m at marathon goal pace.',
                    f'VO₂max intervals: 5×1000m at 5K pace with 400m recovery jog.',
                ]
        else:
            # Conservative: 400m–800m only; 200m repeats for low-base runners
            if i_pace:
                interval_workouts = [
                    f'Speed intervals: 10×400m at {i_pace} (I-pace) with 400m recovery jog.',
                    f'Cruise intervals: 6×800m at {t_pace} (T-pace) with 90sec rest.',
                    f'Speed work: 12×200m at {r_pace} (R-pace) with 200m recovery jog.',
                    f'Hill repeats: 8×30sec at hard effort with walk-down recovery.',
                ]
            else:
                interval_workouts = [
                    f'Speed intervals: 10×400m at 5K pace with 400m recovery jog.',
                    f'Cruise intervals: 6×800m at 10K pace with 90sec rest.',
                    f'Speed work: 12×200m at fast-but-controlled effort with 200m jog.',
                    f'Hill repeats: 8×30sec at hard effort with walk-down recovery.',
                ]

        from app.core.vdot_calculator import VDOTCalculator
        description = VDOTCalculator.inject_paces_into_description(
            interval_workouts[day % len(interval_workouts)], pace_zones or {}, "interval"
        )

        return {
            'day': day,
            'type': 'interval',
            'distance': round(distance, 1),
            'intensity': 'high',
            'description': description,
        }
    
    def _generate_hill_workout(self, day: int, distance: float = 0) -> Dict[str, Any]:
        """Generate hill workout"""
        hill_workouts = [
            f'Hill repeats: 10x30sec steep hill repeats with walk down recovery.',
            f'Long hill climbs: 5x2min moderate grade hills at threshold effort.',
            f'Hill bounding: 8x20sec explosive uphill bounds with full recovery.'
        ]
        
        return {
            'day': day,
            'type': 'hill',
            'distance': round(distance, 1) if distance > 0 else 0,
            'intensity': 'high',
            'description': hill_workouts[day % len(hill_workouts)]
        }
    def _generate_training_tips(self, week_number: int, target_distance: float) -> List[str]:
        """
        Generate diverse and week-specific training tips
        """
        tips = []

        # Create week-specific tip categories to ensure variety
        week_categories = {
            1: ["foundation", "routine", "equipment"],
            2: ["form", "consistency", "recovery"],
            3: ["endurance", "mental", "nutrition"],
            4: ["pace", "strength", "injury_prevention"],
            5: ["race_simulation", "strategy", "gear"],
            6: ["confidence", "taper_preparation", "mental_training"],
            7: ["final_preparations", "logistics", "race_day"],
            8: ["taper", "visualization", "recovery_focus"],
            9: ["sharpening", "final_workouts", "race_ready"],
            10: ["peak_performance", "race_execution", "post_race"],
            11: ["advanced_strategy", "course_specific", "conditions"],
            12: ["marathon_focus", "fueling_master", "mental_toughness"]
        }

        # Get categories for current week (cycle through if longer)
        current_week_categories = week_categories.get(
            week_number,
            week_categories[(week_number - 1) % 12 + 1]
        )

        # Generate tips based on week categories using module-level constant
        tip_database = TRAINING_TIP_DATABASE

        # Select tips from current week categories
        for category in current_week_categories:
                category_tips = tip_database[category]
                # Select 1-2 tips from each category, rotating based on week number
                num_tips = 1 if len(current_week_categories) > 2 else 2
                start_index = (week_number - 1) % len(category_tips)
                for i in range(num_tips):
                    tip_index = (start_index + i) % len(category_tips)
                    tips.append(category_tips[tip_index])
        
        # Add distance-specific tips that vary by week
        distance_tips = self._get_weekly_distance_tips(week_number, target_distance)
        tips.extend(distance_tips)
        
        # Add one motivational tip that rotates weekly
        motivational_tips = [
            f"Week {week_number}: Every mile in training pays dividends on race day",
            f"Week {week_number}: Trust the process - you're stronger than last week",
            f"Week {week_number}: Consistency is the secret weapon of successful runners",
            f"Week {week_number}: Embrace the challenge - that's where growth happens",
            f"Week {week_number}: Your future race self is thanking you for this work",
            f"Week {week_number}: One day at a time, one workout at a time",
            f"Week {week_number}: The pain of training is temporary, the pride is forever",
            f"Week {week_number}: You've already committed - now execute with confidence"
        ]
        
        motivational_index = (week_number - 1) % len(motivational_tips)
        tips.append(motivational_tips[motivational_index])
        
        return tips[:4]  # Return exactly 4 tips per week
    
    def _get_weekly_distance_tips(self, week_number: int, target_distance: float) -> List[str]:
        """Get distance-specific tips that vary by week"""
        
        if target_distance == 30:  # Trail running
            trail_tips = [
                "Practice power hiking steep sections - sometimes walking is faster",
                "Test your trail shoes on technical terrain before race day",
                "Practice running with trekking poles if allowed in your race",
                "Learn to read trail markings and navigate confidently",
                "Practice fueling with handheld bottles or hydration packs",
                "Include downhill running practice to build quad strength",
                "Test different sock combinations for wet trail conditions",
                "Practice running on varied surfaces: rocks, roots, mud, sand"
            ]
            return [trail_tips[(week_number - 1) % len(trail_tips)]]

        elif target_distance <= 5:
            speed_tips = [
                "Practice running at slightly faster than goal pace for short intervals",
                "Include strides (100m accelerations) after easy runs to improve leg turnover",
                "Focus on quick leg turnover and efficient running form",
                "Practice race starts with controlled acceleration",
                "Include some hill repeats to build power and speed",
                "Practice running the exact race distance at goal pace",
                "Focus on explosive power: box jumps, bounding exercises",
                "Practice mental preparation for short, intense effort"
            ]
            return [speed_tips[(week_number - 1) % len(speed_tips)]]
            
        elif target_distance <= 10:
            tempo_tips = [
                "Practice fast finishes on easy runs (last 1-2km at goal pace)",
                "Include tempo runs at goal race pace (3-5km total)",
                "Practice race pace nutrition: gel or sports drink at 5-6km mark",
                "Test your ability to hold pace through middle miles of race",
                "Practice race simulation: 2-3km at goal pace with proper warmup/cool",
                "Include progression runs building to race pace in final kilometers",
                "Practice mental focus for maintaining pace through 8km mark",
                "Test different pre-race meal timing for 10K distance"
            ]
            return [tempo_tips[(week_number - 1) % len(tempo_tips)]]
            
        elif target_distance <= 21.1:
            half_tips = [
                "Practice fueling during long runs (every 45-60 minutes)",
                "Include race-pace efforts in long runs (final 3-5km at goal pace)",
                "Practice running on tired legs (back-to-back long runs on weekend)",
                "Test your half marathon nutrition strategy multiple times",
                "Practice maintaining form through 15-18km when fatigue sets in",
                "Include race simulation runs of 15-16km at goal pace",
                "Test different shoes and socks for 21.1km distance comfort",
                "Practice mental strategies for dealing with fatigue around 18km mark"
            ]
            return [half_tips[(week_number - 1) % len(half_tips)]]
            
        else:  # Marathon
            marathon_tips = [
                "Practice comprehensive fueling strategy: gels, drinks, real food options",
                "Include very long runs (75-90% of race distance) with race simulation",
                "Practice running with race day gear and nutrition for 3+ hours",
                "Test mental strategies for dealing with fatigue around 30km mark",
                "Practice marathon pace during long runs to build muscle memory",
                "Test your complete race day nutrition plan multiple times",
                "Include back-to-back long runs to simulate marathon fatigue",
                "Practice running the wall - push through tough patches in training",
                "Test different pre-race carbo-loading strategies",
                "Practice mental preparation for 26.2 mile challenge"
            ]
            return [marathon_tips[(week_number - 1) % len(marathon_tips)]]

    def _validate_week_plan(self, workouts: List[Dict[str, Any]],
                           total_km: float, phase: str) -> tuple[bool, str]:
        """
        Validate week plan follows training principles

        Returns:
            (is_valid, error_message)

        Checks:
        - All workouts have 'description' field
        - Recovery day has label 'recovery' (not 'recovery_rest')
        - No easy run > 60% of long run distance
        - Total distance matches expected (±5% tolerance)
        """
        # Check description field exists
        for workout in workouts:
            if 'description' not in workout:
                return False, f"Missing description for {workout['type']} on day {workout['day']}"

        # Check recovery label
        for workout in workouts:
            if workout['type'] == 'recovery_rest':
                return False, f"Old label 'recovery_rest' on day {workout['day']}, should be 'recovery'"

        # Check easy runs are not longer than long runs (only flag if clearly too long)
        long_run_dist = max([w.get('distance', 0) for w in workouts if w['type'] == 'long'], default=0)
        if long_run_dist > 0:
            for workout in workouts:
                if workout['type'] == 'easy':
                    # Only flag if easy run is actually longer than long run (allow 5% margin for rounding)
                    if workout.get('distance', 0) > long_run_dist * 1.05:
                        return False, f"Easy run ({workout.get('distance')}km) > 105% of long run ({long_run_dist}km) on day {workout['day']}"

        # Check total distance (5% tolerance - actual should match target closely)
        actual_total = sum(w.get('distance', 0) for w in workouts)
        tolerance = total_km * 0.05
        if abs(actual_total - total_km) > tolerance:
            return False, f"Total distance mismatch: expected {total_km}km, got {actual_total}km"

        # Verify recovery days have 0 distance
        for workout in workouts:
            if workout['type'] == 'recovery' and workout.get('distance', 0) != 0:
                return False, f"Recovery day on day {workout['day']} has non-zero distance"

        return True, "Valid"
    
    def _get_phase(self, week_number: int, phases: Dict[str, int]) -> str:
        """
        Determine which phase a given week belongs to
        
        Returns: 'base', 'build', 'peak', or 'taper'
        """
        if week_number <= phases['base']:
            return 'base'
        elif week_number <= phases['base'] + phases['build']:
            return 'build'
        elif week_number <= phases['base'] + phases['build'] + phases['peak']:
            return 'peak'
        else:
            return 'taper'
    
    def _get_peak_mileage(self, target_distance: float, current_km: float, weeks: int,
                          vdot: Optional[float] = None) -> float:
        """
        Determine peak weekly mileage with length-based multipliers and optional VDOT adjustment.
        Higher VDOT runners can absorb slightly more volume (better aerobic fitness / recovery).
        """
        peak_multiplier = 1 + (1.5 * (weeks / 16))
        peak_multiplier = min(peak_multiplier, 2.6)

        ideal_peak = self._get_ideal_peak(target_distance, current_km, weeks)

        # VDOT adjustment: VDOT 30 = 0.95x, VDOT 50 = 1.0x, VDOT 65+ = 1.08x
        if vdot:
            vdot_factor = 0.95 + min(0.13, (vdot - 30) / 350)
            ideal_peak = ideal_peak * vdot_factor

        if current_km == 0:
            return ideal_peak

        peak = min(current_km * peak_multiplier, ideal_peak)

        return max(peak, current_km * 1.2)
    
    def _get_ideal_peak(self, target_distance: float, current_km: float, weeks: int) -> float:
        """
        Get ideal peak mileage based on race distance
        """
        if target_distance == 30:
            ideal_peak = 50
        elif target_distance <= 5:
            ideal_peak = max(25, current_km * 2.0)
        elif target_distance <= 10:
            ideal_peak = max(30, current_km * 2.2)
        elif target_distance <= 21.1:
            ideal_peak = max(40, current_km * 2.3)
        else:
            ideal_peak = max(50, current_km * 2.0)
        
        return ideal_peak
    
    def _is_recovery_week(self, week_number: int, phase: str, phases: Optional[Dict[str, int]] = None) -> bool:
        """
        Determine if a week is a recovery week.

        Every 4th week in base and build phases is a recovery week,
        but only if the phase is long enough (>=4 weeks) to justify it.
        No recovery weeks in peak or taper phases.
        """
        if phase in ['peak', 'taper']:
            return False
        if phases:
            phase_length = phases.get(phase, 0)
            if phase_length < 4:
                return False
        return week_number % 4 == 0
    
    def _calculate_weekly_progression(self, current_km: float, target_distance: float, weeks: int, max_runs: int = 4, vdot: Optional[float] = None) -> List[float]:
        """
        Calculate weekly mileage with phase-aware progression and 10% rule enforcement.

        Key safety invariant: no non-recovery week increases more than 10% over the
        previous non-recovery week's mileage.  Recovery weeks reduce by 25% but the
        "high-water mark" is tracked separately so the post-recovery ramp resumes
        from the pre-recovery level — never recalculating from the dip.

        Phases:
        - Base: Build to 70% of peak, recovery every 4th week
        - Build: Progress from 70% to 100% of peak, recovery every 4th week
        - Peak: Maintain near peak with slight variation
        - Taper: Distance-appropriate progressive reduction toward race week
        """
        phases = self._calculate_phases(weeks, target_distance)
        peak_km = self._get_peak_mileage(target_distance, current_km, weeks, vdot=vdot)
        weekly_progression: List[float] = []

        # high_water tracks the last non-recovery mileage (recovery dips don't reset it)
        high_water = current_km

        def _apply_10pct_cap(target: float, reference: float) -> float:
            """Enforce 10% rule: target can't exceed reference * 1.10."""
            return min(target, reference * 1.10)

        # ── Base phase: current → 70% of peak ─────────────────────────────
        base_end_target = peak_km * 0.70
        non_recovery_base = sum(1 for i in range(phases['base']) if not self._is_recovery_week(i + 1, 'base', phases))

        base_step = 0
        for week in range(phases['base']):
            week_number = week + 1
            if self._is_recovery_week(week_number, 'base', phases):
                week_km = high_water * 0.75
            else:
                if non_recovery_base > 0:
                    ideal = current_km + (base_end_target - current_km) * ((base_step + 1) / non_recovery_base)
                else:
                    ideal = current_km
                week_km = _apply_10pct_cap(ideal, high_water)
                week_km = max(week_km, high_water * 1.01)
                high_water = week_km
                base_step += 1

            weekly_progression.append(round(week_km, 1))

        # ── Build phase: 70% of peak → 100% of peak ──────────────────────
        build_start = max(high_water, base_end_target)
        non_recovery_build = sum(
            1 for i in range(phases['build'])
            if not self._is_recovery_week(phases['base'] + i + 1, 'build', phases)
        )

        build_step = 0
        for week in range(phases['build']):
            week_number = phases['base'] + week + 1
            should_recover = self._is_recovery_week(week_number, 'build', phases)

            if should_recover:
                week_km = high_water * 0.75
            else:
                if non_recovery_build > 0:
                    ideal = build_start + (peak_km - build_start) * ((build_step + 1) / non_recovery_build)
                else:
                    ideal = peak_km
                week_km = _apply_10pct_cap(ideal, high_water)
                week_km = max(week_km, high_water * 1.01)
                high_water = week_km
                build_step += 1

            weekly_progression.append(round(week_km, 1))

        # ── Peak phase: the highest mileage weeks ──────────────────────────
        # First peak week is capped at +10% over build high-water to prevent
        # abrupt jumps. Subsequent peak weeks are uncapped (summit by definition).
        for week in range(phases['peak']):
            week_km = peak_km * (0.97 + (week % 3) * 0.01)
            if week == 0 and phases['peak'] >= 2:
                week_km = min(week_km, high_water * 1.10)
            week_km = max(week_km, high_water)
            high_water = week_km
            weekly_progression.append(round(week_km, 1))

        # ── Taper phase: distance-appropriate reduction ───────────────────
        taper_weeks = phases['taper']
        for week in range(taper_weeks):
            if taper_weeks == 1:
                week_km = peak_km * 0.60
            elif taper_weeks == 2:
                week_km = peak_km * (0.80 if week == 0 else 0.60)
            elif taper_weeks == 3:
                week_km = peak_km * (0.85 if week == 0 else (0.70 if week == 1 else 0.55))
            else:
                taper_pcts = [0.90, 0.80, 0.65, 0.55]
                pct = taper_pcts[min(week, len(taper_pcts) - 1)]
                week_km = peak_km * pct

            weekly_progression.append(round(week_km, 1))
        
        return weekly_progression
    
    def _generate_weekly_plan(self, week_number: int, total_km: float, target_distance: float,
                            max_runs_per_week: int, weeks: int,
                            vdot: Optional[float] = None,
                            pace_zones: Optional[Dict] = None,
                            experience_level: str = "beginner") -> Dict[str, Any]:
        """
        Generate a single week's training plan.
        """
        phases = self._calculate_phases(weeks, target_distance)
        phase = self._get_phase(week_number, phases)
        is_recovery_week = self._is_recovery_week(week_number, phase, phases)

        # Calculate week_in_phase for key workout rotation
        if phase == 'base':
            week_in_phase = week_number - 1
        elif phase == 'build':
            week_in_phase = week_number - phases['base'] - 1
        elif phase == 'peak':
            week_in_phase = week_number - phases['base'] - phases['build'] - 1
        else:
            week_in_phase = week_number - phases['base'] - phases['build'] - phases['peak'] - 1

        distribution = self._get_workout_distribution(total_km, max_runs_per_week, phase,
                                                   is_recovery_week, week_number, phases, target_distance)

        workouts = self._generate_daily_workouts(
            week_number, total_km, distribution, target_distance, weeks, phase, is_recovery_week,
            vdot=vdot, pace_zones=pace_zones,
            experience_level=experience_level,
            week_in_phase=week_in_phase,
        )

        actual_total_km = round(sum(w.get('distance', 0) for w in workouts), 1)

        # Scale workouts down if actual exceeds target (preserves 10% progression cap)
        if actual_total_km > total_km * 1.03 and actual_total_km > 0:
            scale = total_km / actual_total_km
            for w in workouts:
                if w.get('distance', 0) > 0:
                    w['distance'] = round(w['distance'] * scale, 1)
            actual_total_km = round(sum(w.get('distance', 0) for w in workouts), 1)

        is_valid, validation_message = self._validate_week_plan(workouts, actual_total_km, phase)

        training_tips = self._generate_training_tips(week_number, target_distance)

        weekly_plan = {
            'week': week_number,
            'phase': phase,
            'is_recovery': is_recovery_week,
            'total_km': actual_total_km,
            'daily_workouts': workouts,
            'training_tips': training_tips,
            'validation': {'valid': is_valid, 'message': validation_message},
            'strength_training': [w['strength_session'] for w in workouts if w.get('strength_session')]
        }
        
        return weekly_plan
    
    def generate_plan(self, current_km: float, target_distance: float, weeks: int,
                      max_runs_per_week: int = 4, vdot: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Generate a comprehensive training plan with phase structure, conservative progression,
        mandatory rest days, and integrated strength/cross-training.

        Args:
            current_km:          Current weekly mileage in km
            target_distance:     Race distance in km
            weeks:               Training duration in weeks
            max_runs_per_week:   Maximum runs per week (3-6)
            vdot:                Optional VDOT score for personalised pace zones
        """
        from app.core.vdot_calculator import VDOTCalculator
        pace_zones = VDOTCalculator.get_pace_zones(vdot) if vdot else None

        experience_level = derive_experience_level(current_km)

        weekly_progression = self._calculate_weekly_progression(current_km, target_distance, weeks, max_runs_per_week, vdot=vdot)

        training_plan = []
        for week in range(1, weeks + 1):
            week_km = weekly_progression[week - 1]
            weekly_plan = self._generate_weekly_plan(
                week, week_km, target_distance, max_runs_per_week, weeks,
                vdot=vdot, pace_zones=pace_zones,
                experience_level=experience_level,
            )
            training_plan.append(weekly_plan)

        return training_plan
