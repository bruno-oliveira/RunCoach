"""PDF plan content pages — title, summary, weekly plans, zones."""

from typing import Any, Dict, List

from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER

from app.models import TrainingPlan
from app.utils import format_pace as _shared_format_pace


class PlanPagesMixin:
    """Methods for rendering plan-related PDF pages."""

    def _add_title_page(self, story: List, training_plan: TrainingPlan, plan_data: List[Dict]):
        plan_type = getattr(training_plan, 'plan_type', 'distance')
        is_performance = plan_type == 'performance'
        is_fitness = plan_type == 'fitness'

        if is_performance:
            story.append(Paragraph("⚡ Performance Training Plan", self.title_style))
        elif is_fitness:
            story.append(Paragraph("💪 Fitness Training Plan", self.title_style))
        else:
            story.append(Paragraph("🏃‍♂️ Personalized Running Training Plan", self.title_style))
        story.append(Spacer(1, 0.5 * cm))

        if is_fitness:
            focus = training_plan.target_distance.replace("fitness_", "").replace("_", " ").title()
            subtitle = f"Focus: {focus} | {training_plan.weeks_duration} Weeks"
        else:
            subtitle = f"Target: {training_plan.target_distance}km Race | {training_plan.weeks_duration} Weeks"
        story.append(Paragraph(subtitle, self.subtitle_style))
        story.append(Spacer(1, 0.3 * cm))

        created_date = training_plan.created_at.strftime('%B %d, %Y')
        story.append(Paragraph(f"Generated on {created_date}", self.normal_style))

        strava_multiplier = getattr(training_plan, 'adjustment_multiplier', None)
        if strava_multiplier:
            adapted_style = ParagraphStyle(
                'StravaAdapted',
                parent=self.normal_style,
                textColor=colors.HexColor('#fc4c02'),
                fontName='Helvetica-Bold',
            )
            story.append(Paragraph(
                f"★ Strava Adjusted (multiplier ×{strava_multiplier:.2f}) — distances reflect your current fitness",
                adapted_style,
            ))

        story.append(Spacer(1, 2 * cm))

        target_distance_float = training_plan.target_distance_km
        if is_fitness:
            focus = training_plan.target_distance.replace("fitness_", "").replace("_", " ").title()
            target_display = focus
        elif target_distance_float == 30.0:
            target_display = "Trail Running"
        else:
            target_display = f"{training_plan.target_distance} km"

        if is_performance and training_plan.current_pace and training_plan.goal_pace:
            improvement = ((training_plan.current_pace - training_plan.goal_pace) / training_plan.current_pace) * 100
            stats_data = [
                ['Target Distance', target_display],
                ['Current Pace', self._format_pace(training_plan.current_pace)],
                ['Goal Pace', self._format_pace(training_plan.goal_pace)],
                ['Target Improvement', f"{improvement:.1f}%"],
                ['Training Duration', f"{training_plan.weeks_duration} weeks"],
                ['Weekly Mileage', f"{training_plan.current_weekly_km:.1f} km"]
            ]
        else:
            stats_data = [
                ['Current Weekly Mileage', f"{training_plan.current_weekly_km} km"],
                ['Target Distance', target_display],
                ['Training Duration', f"{training_plan.weeks_duration} weeks"],
                ['Peak Week Mileage', f"{max(week['total_km'] for week in plan_data):.1f} km"]
            ]

        stats_table = Table(stats_data, colWidths=[5 * cm, 3 * cm])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6'))
        ]))

        story.append(stats_table)
        story.append(Spacer(1, 2 * cm))

    def _add_plan_summary(self, story: List, training_plan: TrainingPlan, plan_data: List[Dict]):
        story.append(Paragraph("Training Plan Overview", self.section_style))

        plan_type = getattr(training_plan, 'plan_type', 'distance')
        is_performance = plan_type == 'performance'
        is_fitness = plan_type == 'fitness'
        max_mileage = max(week['total_km'] for week in plan_data)

        if is_performance or is_fitness:
            chart_data = [['Week', 'Phase', 'Mileage (km)', 'Progress']]
            for week in plan_data:
                progress_bar = self._create_progress_bar(week['total_km'], max_mileage)
                phase = week.get('phase', '').title()
                chart_data.append([
                    f"Week {week['week']}", phase, f"{week['total_km']:.1f}", progress_bar
                ])
            chart_table = Table(chart_data, colWidths=[2 * cm, 2 * cm, 2 * cm, 5 * cm])
        else:
            chart_data = [['Week', 'Mileage (km)', 'Progress']]
            for week in plan_data:
                progress_bar = self._create_progress_bar(week['total_km'], max_mileage)
                chart_data.append([f"Week {week['week']}", f"{week['total_km']:.1f}", progress_bar])
            chart_table = Table(chart_data, colWidths=[2 * cm, 2 * cm, 6 * cm])

        chart_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6'))
        ]))

        story.append(chart_table)
        story.append(Spacer(1, 1 * cm))

    def _create_progress_bar(self, current: float, maximum: float) -> str:
        if maximum == 0:
            return "░" * 20 + " 0%"
        percentage = min(current / maximum, 1.0)
        bar_length = 20
        filled_length = int(bar_length * percentage)
        bar = "█" * filled_length + "░" * (bar_length - filled_length)
        return f"{bar} {percentage * 100:.0f}%"

    def _add_weekly_plan(self, story: List, week: Dict[str, Any]):
        if 'phase' in week and 'phase_description' in week:
            title = f"Week {week['week']} - {week['total_km']:.1f} km | {week['phase'].title()} Phase"
            story.append(Paragraph(title, self.section_style))
            story.append(Paragraph(f"<i>{week['phase_description']}</i>", self.normal_style))
            story.append(Spacer(1, 0.3 * cm))
        else:
            story.append(Paragraph(f"Week {week['week']} - {week['total_km']:.1f} km", self.section_style))

        workout_data = [['Day', 'Workout', 'Distance', 'Intensity', 'Notes']]

        for workout in week.get('daily_workouts', []):
            workout_data.append([
                Paragraph(self._get_day_name(workout['day']), self.table_cell_style),
                Paragraph(workout['type'].title(), self.table_cell_style),
                Paragraph(f"{workout.get('distance', 0):.1f} km" if workout.get('distance', 0) > 0 else "-", self.table_cell_style),
                Paragraph(workout.get('intensity', '-').title(), self.table_cell_style),
                Paragraph(workout.get('description', ''), self.table_cell_style)
            ])

        header_styles = [self.table_header_style] * len(workout_data[0])
        header_styles[0] = ParagraphStyle('DayHeader', parent=self.table_header_style, alignment=TA_CENTER)
        for i in range(len(workout_data[0])):
            workout_data[0][i] = Paragraph(workout_data[0][i], header_styles[i])

        workout_table = Table(workout_data, colWidths=[2.5 * cm, 2 * cm, 1.5 * cm, 1.5 * cm, 5 * cm])
        workout_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8)
        ]))

        story.append(workout_table)
        story.append(Spacer(1, 0.4 * cm))

        self._add_workout_steps_block(story, week.get('daily_workouts', []))

        if week.get('strength_training'):
            count = len(week['strength_training'])
            label = f"💪 Strength Training ({count} session{'s' if count != 1 else ''})"
            story.append(Paragraph(label, self.normal_style))
            for st in week['strength_training']:
                focus = (st.get('focus') or st.get('type', '')).replace('_', ' ').title()
                level = st.get('level', '')
                header = f"{focus} — {st.get('duration', '')}"
                if level:
                    header += f" ({level.title()})"
                story.append(Paragraph(header, self.small_style))
                if st.get('warm_up'):
                    story.append(Paragraph("Warm-up:", self.small_style))
                    for item in st['warm_up']:
                        story.append(Paragraph(f"  • {item}", self.small_style))
                story.append(Paragraph("Exercises:", self.small_style))
                for ex in st.get('exercises', []):
                    if isinstance(ex, dict):
                        story.append(Paragraph(f"  • {ex['name']} — {ex['sets']}×{ex['reps']}", self.small_style))
                    else:
                        story.append(Paragraph(f"  • {ex}", self.small_style))
                if st.get('cool_down'):
                    story.append(Paragraph("Cool-down:", self.small_style))
                    for item in st['cool_down']:
                        story.append(Paragraph(f"  • {item}", self.small_style))
                story.append(Spacer(1, 0.2 * cm))
            story.append(Spacer(1, 0.1 * cm))

        if week.get('training_tips'):
            story.append(Paragraph("🎯 Training Tips", self.normal_style))
            for tip in week['training_tips']:
                story.append(Paragraph(f"• {tip}", self.small_style))
            story.append(Spacer(1, 0.5 * cm))

    def _add_workout_steps_block(self, story: List, workouts: List[Dict[str, Any]]):
        """Render structured session blocks for any workouts that have steps."""
        from reportlab.lib.enums import TA_LEFT

        stepped = [w for w in workouts if w.get('steps') and w.get('type') not in ('rest', 'recovery')]
        if not stepped:
            return

        heading_style = ParagraphStyle(
            'StepsHeading',
            parent=self.small_style,
            fontName='Helvetica-Bold',
            fontSize=8,
            textColor=colors.HexColor('#4a5568'),
            spaceAfter=2,
        )
        step_style = ParagraphStyle(
            'StepLine',
            parent=self.small_style,
            fontName='Helvetica',
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor('#2d3748'),
            leftIndent=10,
            alignment=TA_LEFT,
        )

        zone_colors = {
            'E': '#10b981',
            'M': '#3b82f6',
            'T': '#f59e0b',
            'I': '#ef4444',
            'R': '#8b5cf6',
        }

        for workout in stepped:
            day_name = self._get_day_name(workout.get('day', 0))
            w_type = workout.get('type', '').replace('_', ' ').title()
            story.append(Paragraph(f"▸ {day_name} — {w_type} · Session blocks", heading_style))

            for step in workout['steps']:
                label = step.get('label', '')
                meta_parts = []
                if step.get('distance_m'):
                    if step['distance_m'] >= 1000:
                        meta_parts.append(f"{step['distance_m'] / 1000:.1f} km")
                    else:
                        meta_parts.append(f"{step['distance_m']} m")
                if step.get('duration_s'):
                    secs = step['duration_s']
                    if secs >= 60:
                        meta_parts.append(f"{secs // 60}:{secs % 60:02d}")
                    else:
                        meta_parts.append(f"{secs}s")
                if step.get('pace_str'):
                    meta_parts.append(step['pace_str'])
                if step.get('effort'):
                    meta_parts.append(step['effort'])

                meta = " · ".join(meta_parts)
                zone = step.get('pace_zone')
                if zone:
                    color = zone_colors.get(zone, '#6b7280')
                    zone_tag = f' <font color="{color}"><b>[{zone}]</b></font>'
                else:
                    zone_tag = ''

                line = f"• <b>{label}</b>{zone_tag}"
                if meta:
                    line += f" — <font color='#6b7280'>{meta}</font>"
                story.append(Paragraph(line, step_style))

            story.append(Spacer(1, 0.15 * cm))

        story.append(Spacer(1, 0.25 * cm))

    def _format_pace(self, pace_min_per_km: float) -> str:
        return _shared_format_pace(pace_min_per_km)

    def _add_performance_philosophy(self, story: List):
        story.append(Paragraph("Plan Philosophy", self.section_style))
        philosophy_text = (
            "This performance plan uses a zone-based training approach with four phases: "
            "<b>Base</b> (aerobic foundation), <b>Build</b> (increasing intensity), "
            "<b>Sharpen</b> (peak race-specific work), and <b>Taper</b> (volume reduction "
            "while maintaining sharpness). Each workout targets a specific training zone "
            "to develop the physiological systems needed for your goal pace. "
            "Trust the process: easy days should feel genuinely easy so your body can "
            "absorb the hard sessions."
        )
        story.append(Paragraph(philosophy_text, self.normal_style))
        story.append(Spacer(1, 0.5 * cm))

    def _add_pace_improvement_summary(self, story: List, training_plan: TrainingPlan):
        if not training_plan.current_pace or not training_plan.goal_pace:
            return

        current_formatted = self._format_pace(training_plan.current_pace)
        goal_formatted = self._format_pace(training_plan.goal_pace)
        improvement = ((training_plan.current_pace - training_plan.goal_pace)
                       / training_plan.current_pace * 100)

        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("Pace Improvement Target", self.section_style))

        pace_data = [
            ['Current Pace', 'Goal Pace', 'Improvement'],
            [current_formatted, goal_formatted, f"{improvement:.1f}%"]
        ]

        pace_table = Table(pace_data, colWidths=[4 * cm, 4 * cm, 4 * cm])
        pace_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#764ba2')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))

        story.append(pace_table)
        story.append(Spacer(1, 0.5 * cm))

    def _add_training_zones_page(self, story: List, training_plan: TrainingPlan):
        from app.core.generators.performance_plan_generator import PerformancePlanGenerator

        gen = PerformancePlanGenerator()
        zones = gen.calculate_training_zones(
            training_plan.goal_pace,
            training_plan.max_heart_rate
        )

        story.append(Paragraph("Training Zones", self.section_style))
        story.append(Spacer(1, 0.3 * cm))

        header = ['Zone', 'Name', 'Pace', 'Pace Range', 'HR Range', 'Description']
        table_data = [[Paragraph(h, self.table_header_style) for h in header]]

        zone_display = [
            ('zone_1_recovery', '1', 'Recovery'),
            ('zone_2_aerobic', '2', 'Aerobic'),
            ('zone_3_tempo', '3', 'Tempo'),
            ('zone_4_vo2max', '4', 'VO2 Max'),
            ('zone_5_race', '5', 'Race Pace'),
        ]

        zone_colors = []
        for zone_key, zone_num, zone_name in zone_display:
            z = zones[zone_key]
            pace_str = self._format_pace(z['pace'])
            pr = z.get('pace_range', (0, 0))
            pace_range_str = f"{self._format_pace(pr[0])} - {self._format_pace(pr[1])}"
            hr_str = z.get('hr_bpm_range', z.get('hr_range', '-'))
            desc = z.get('description', '')
            zone_colors.append(colors.HexColor(z.get('color', '#cccccc')))

            table_data.append([
                Paragraph(zone_num, self.table_cell_style),
                Paragraph(zone_name, self.table_cell_style),
                Paragraph(pace_str, self.table_cell_style),
                Paragraph(pace_range_str, self.table_cell_style),
                Paragraph(hr_str, self.table_cell_style),
                Paragraph(desc, self.table_cell_style),
            ])

        zone_table = Table(table_data, colWidths=[1.2 * cm, 2 * cm, 2 * cm, 3.5 * cm, 2.5 * cm, 5.3 * cm])
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]
        for i, zc in enumerate(zone_colors):
            row = i + 1
            style_cmds.append(('BACKGROUND', (0, row), (0, row), zc))

        zone_table.setStyle(TableStyle(style_cmds))
        story.append(zone_table)
        story.append(Spacer(1, 1 * cm))

    def _add_performance_weekly_plan(self, story: List, week: Dict[str, Any]):
        phase = week.get('phase', '')
        phase_desc = week.get('phase_description', '')
        title = f"Week {week['week']} - {week['total_km']:.1f} km | {phase.title()} Phase"
        story.append(Paragraph(title, self.section_style))
        if phase_desc:
            story.append(Paragraph(f"<i>{phase_desc}</i>", self.normal_style))
        story.append(Spacer(1, 0.3 * cm))

        for workout in week.get('daily_workouts', []):
            day_name = self._get_day_name(workout.get('day', 0))
            w_type = workout.get('type', 'easy').replace('_', ' ').title()
            dist = workout.get('distance', 0)
            target_pace = workout.get('target_pace_formatted', '-')
            desc = workout.get('description', '')

            header_text = f"<b>{day_name}</b> | {w_type} | {dist:.1f} km | {target_pace}"
            story.append(Paragraph(header_text, self.normal_style))

            if desc:
                story.append(Paragraph(f"<i>{desc}</i>", self.small_style))

            segments = workout.get('segments', [])
            if segments:
                seg_header = ['Segment', 'Distance', 'Pace', 'Zone']
                seg_data = [[Paragraph(h, self.table_header_style) for h in seg_header]]

                for seg in segments:
                    seg_name = seg.get('name', '')
                    seg_dist = f"{seg.get('distance_km', 0):.1f} km"
                    seg_pace = seg.get('pace_formatted', '-')
                    seg_zone = seg.get('zone_label', '-')

                    intervals = seg.get('intervals')
                    if intervals:
                        reps = intervals.get('reps', '')
                        interval_m = intervals.get('interval_m', '')
                        recovery = intervals.get('recovery_min')
                        detail = f"{reps}x{interval_m}"
                        if recovery:
                            detail += f" ({recovery}min rec.)"
                        seg_name = f"{seg_name} - {detail}"

                    seg_data.append([
                        Paragraph(seg_name, self.table_cell_style),
                        Paragraph(seg_dist, self.table_cell_style),
                        Paragraph(seg_pace, self.table_cell_style),
                        Paragraph(seg_zone, self.table_cell_style),
                    ])

                seg_table = Table(seg_data, colWidths=[5.5 * cm, 2.5 * cm, 3.5 * cm, 2.5 * cm])
                seg_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#764ba2')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 4),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(seg_table)

            story.append(Spacer(1, 0.4 * cm))

    def _get_day_name(self, day_number: int) -> str:
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        if 1 <= day_number <= 7:
            return days[day_number - 1]
        return f"Day {day_number}"
