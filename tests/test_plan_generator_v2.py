import pytest
from app.core.plan_generator import TrainingPlanGenerator

class TestPlanGeneratorV2:
    """Test improved plan generator with phases and rest day rules"""
    
    @pytest.fixture
    def generator(self):
        return TrainingPlanGenerator()
    
    def test_phase_calculation_8_weeks(self, generator):
        phases = generator._calculate_phases(8)
        assert phases['base'] == 3
        assert phases['build'] == 2
        assert phases['peak'] == 1
        assert phases['taper'] == 2
    
    def test_phase_calculation_17_weeks(self, generator):
        phases = generator._calculate_phases(17)
        assert phases['base'] == 8
        assert phases['build'] == 4
        assert phases['peak'] == 2
        assert phases['taper'] == 3
    
    def test_phase_calculation_10_weeks(self, generator):
        phases = generator._calculate_phases(10)
        assert phases['base'] == 4
        assert phases['build'] == 3
        assert phases['peak'] == 1
        assert phases['taper'] == 2
    
    def test_get_phase_base(self, generator):
        phases = {'base': 4, 'build': 3, 'peak': 1, 'taper': 2}
        assert generator._get_phase(1, phases) == 'base'
        assert generator._get_phase(4, phases) == 'base'
    
    def test_get_phase_build(self, generator):
        phases = {'base': 4, 'build': 3, 'peak': 1, 'taper': 2}
        assert generator._get_phase(5, phases) == 'build'
        assert generator._get_phase(7, phases) == 'build'
    
    def test_long_run_before_rest_day(self, generator):
        """Verify long run is always preceded by rest day"""
        plan = generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        for week in plan:
            workouts = week['daily_workouts']
            schedule = {w['day']: w['type'] for w in workouts}
            
            long_run_day = None
            for day, wtype in schedule.items():
                if wtype == 'long':
                    long_run_day = day
                    break
            
            assert schedule.get(long_run_day - 1) == 'rest', \
                f"Week {week['week']}: Long run on day {long_run_day} not preceded by rest"
    
    def test_long_run_after_recovery(self, generator):
        """Verify long run is followed by recovery rest"""
        plan = generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        for week in plan:
            workouts = week['daily_workouts']
            schedule = {w['day']: w['type'] for w in workouts}
            
            long_run_day = None
            for day, wtype in schedule.items():
                if wtype == 'long':
                    long_run_day = day
                    break
            
            assert schedule.get(long_run_day + 1) in ['rest', 'recovery'], \
                f"Week {week['week']}: Long run on day {long_run_day} not followed by rest/recovery"
    
    def test_no_quality_workouts_in_base(self, generator):
        """Base phase should have no quality workouts"""
        plan = generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        phases = generator._calculate_phases(12)
        
        for week in plan:
            if week['phase'] == 'base':
                workout_types = [w['type'] for w in week['daily_workouts']]
                assert 'interval' not in workout_types
                assert 'tempo' not in workout_types
                assert 'hill' not in workout_types
    
    def test_strength_on_easy_days_only(self, generator):
        """Strength training should only be on easy run days"""
        plan = generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        
        for week in plan:
            for workout in week['daily_workouts']:
                if 'strength_session' in workout and workout['strength_session']:
                    assert workout['type'] == 'easy', \
                        f"Strength session on {workout['type']} day (should be easy only)"
    
    def test_conservative_progression(self, generator):
        """Progressive build weeks within phases should have conservative increases"""
        plan = generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        
        volumes = [week['total_km'] for week in plan]
        phases = [week['phase'] for week in plan]
        
        for i in range(1, len(volumes)):
            # Only check consecutive weeks in same phase (not recovery jumps)
            if phases[i] != phases[i-1]:
                continue
            
            # Check if this is a recovery week (significant decrease)
            prev_change = (volumes[i-1] - volumes[i-2]) / volumes[i-2] if i > 1 else 0
            if prev_change < -0.20:  # Previous was recovery week
                continue
            
            curr_change = (volumes[i] - volumes[i-1]) / volumes[i-1]
            
            # Only check positive increases, allow slightly more (15%) for progressive ratio changes
            if curr_change > 0:
                assert curr_change <= 0.15, \
                    f"Week {i+1}: {curr_change:.1%} increase exceeds 15% rule"
    
    def test_swimming_in_base_build_only(self, generator):
        """Swimming should only be in base/build phases"""
        plan = generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        
        for week in plan:
            if week['phase'] in ['peak', 'taper']:
                for workout in week['daily_workouts']:
                    swimming = workout.get('optional_cross_training', {}).get('type')
                    assert swimming != 'swimming_cross_training', \
                        f"Week {week['week']}: Swimming in {week['phase']} phase"
    
    def test_peak_mileage_consistent_with_length(self, generator):
        """Peak mileage should scale with plan length"""
        plan_8_weeks = generator.generate_plan(current_km=10, target_distance=10, weeks=8)
        plan_12_weeks = generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        plan_17_weeks = generator.generate_plan(current_km=10, target_distance=10, weeks=17)
        
        peak_8 = max(w['total_km'] for w in plan_8_weeks)
        peak_12 = max(w['total_km'] for w in plan_12_weeks)
        peak_17 = max(w['total_km'] for w in plan_17_weeks)
        
        assert peak_17 > peak_12 > peak_8, \
            "Peak mileage should increase with longer plans"
    
    def test_phase_in_weekly_plan(self, generator):
        """Each weekly plan should include phase information"""
        plan = generator.generate_plan(current_km=10, target_distance=10, weeks=12)
        
        for week in plan:
            assert 'phase' in week
            assert week['phase'] in ['base', 'build', 'peak', 'taper']
    
    def test_plan_generates_successfully(self, generator):
        """Plan should generate without errors"""
        plan = generator.generate_plan(current_km=20, target_distance=10, weeks=8)
        
        assert len(plan) == 8
        for week in plan:
            assert 'week' in week
            assert 'phase' in week
            assert 'total_km' in week
            assert 'daily_workouts' in week
            assert 'training_tips' in week

    def test_actual_total_matches_target(self, generator):
        """Actual total distance should match target within 5%"""
        plan = generator.generate_plan(current_km=20, target_distance=10, weeks=12)

        for week in plan:
            target = week['total_km']
            actual = sum(w.get('distance', 0) for w in week['daily_workouts'])
            diff_pct = abs(actual - target) / target if target > 0 else 0
            assert diff_pct <= 0.05, f"Week {week['week']}: {diff_pct:.1%} difference exceeds 5%"

    def test_recovery_days_zero_distance(self, generator):
        """Recovery days should always have 0km distance"""
        plan = generator.generate_plan(current_km=20, target_distance=10, weeks=12)

        for week in plan:
            for workout in week['daily_workouts']:
                if workout['type'] == 'recovery':
                    assert workout.get('distance', 0) == 0, \
                        f"Week {week['week']} Day {workout['day']}: Recovery has distance"

    def test_phase_distance_distribution(self, generator):
        """Verify progressive long run ratios are used correctly with phase-appropriate ranges"""
        plan = generator.generate_plan(current_km=30, target_distance=21.1, weeks=16)

        for week in plan:
            phase = week['phase']
            min_ratio, max_ratio = generator._get_long_run_ratio_range(phase, 21.1, 16)

            long_run = next((w for w in week['daily_workouts'] if w['type'] == 'long'), None)
            if long_run:
                long_pct = long_run['distance'] / week['total_km']

                # Check ratio is within expected range (with extra tolerance for caps and recovery)
                if phase == 'taper':
                    tolerance = 0.20  # Higher tolerance for taper (volume reduction affects ratio)
                elif week['is_recovery']:
                    tolerance = 0.08
                elif phase in ['peak', 'build']:
                    tolerance = 0.12  # Higher tolerance for peak/build (caps may reduce ratio)
                else:
                    tolerance = 0.08

                # Allow ratios below minimum if capped (caps reduce actual ratio)
                assert long_pct <= max_ratio + tolerance, \
                    f"Week {week['week']} ({phase}): Long run {long_pct:.1%} exceeds maximum {max_ratio:.1%}"

                # For non-peak phases, also check minimum
                if phase not in ['peak']:
                    assert long_pct >= min_ratio - tolerance, \
                        f"Week {week['week']} ({phase}): Long run {long_pct:.1%} below minimum {min_ratio:.1%}"

    def test_recovery_week_ratio_reduction(self, generator):
        """Test that recovery weeks have reduced long run ratios (percentage-based reduction)"""
        plan = generator.generate_plan(current_km=25, target_distance=30, weeks=12)

        for week_idx in range(1, len(plan)):
            current_week = plan[week_idx]
            prev_week = plan[week_idx - 1]

            if current_week['is_recovery'] and not prev_week['is_recovery']:
                # Compare long run ratios
                prev_long = next((w for w in prev_week['daily_workouts'] if w['type'] == 'long'), None)
                curr_long = next((w for w in current_week['daily_workouts'] if w['type'] == 'long'), None)

                if prev_long and curr_long:
                    prev_ratio = prev_long['distance'] / prev_week['total_km']
                    curr_ratio = curr_long['distance'] / current_week['total_km']

                    # Recovery week should have lower ratio (approximately 8-12% reduction)
                    expected_reduction = 0.10
                    actual_reduction = (prev_ratio - curr_ratio) / prev_ratio

                    # Allow ±3% tolerance for other factors
                    assert 0.05 <= actual_reduction <= 0.15, \
                        f"Week {current_week['week']}: Recovery ratio reduction {actual_reduction:.1%} outside expected 8-12% range"

    def test_long_run_progression(self, generator):
        """Test that long run distances increase progressively through plan"""
        plan = generator.generate_plan(current_km=20, target_distance=21.1, weeks=12)

        # Track long runs by phase
        long_runs = []
        for week in plan:
            long_run = next((w for w in week['daily_workouts'] if w['type'] == 'long'), None)
            if long_run:
                long_runs.append({
                    'week': week['week'],
                    'phase': week['phase'],
                    'is_recovery': week['is_recovery'],
                    'distance': long_run['distance'],
                    'ratio': long_run['distance'] / week['total_km']
                })

        # Check progression within each phase (excluding recovery weeks)
        for phase in ['base', 'build', 'peak']:
            phase_runs = [lr for lr in long_runs if lr['phase'] == phase and not lr['is_recovery']]
            if len(phase_runs) > 1:
                for i in range(1, len(phase_runs)):
                    assert phase_runs[i]['distance'] >= phase_runs[i-1]['distance'] * 0.95, \
                        f"Long run decreased in {phase} phase from week {phase_runs[i-1]['week']} to {phase_runs[i]['week']}"
                    assert phase_runs[i]['ratio'] >= phase_runs[i-1]['ratio'] - 0.03, \
                        f"Long run ratio decreased significantly in {phase} phase"

