import os
import io
import base64
import hashlib
import json
import logging
import shutil
import time
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
import tempfile

from app.models import TrainingPlan
from app.utils import format_pace as _shared_format_pace

logger = logging.getLogger(__name__)

class PDFGenerator:
    CACHE_TTL_SECONDS = 3600  # Evict cached PDFs older than 1 hour

    def __init__(self, cache_dir: str = "./pdf_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _evict_stale_cache(self) -> None:
        """Remove cached PDFs older than CACHE_TTL_SECONDS."""
        cutoff = time.time() - self.CACHE_TTL_SECONDS
        try:
            for entry in self.cache_dir.iterdir():
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    entry.unlink(missing_ok=True)
        except OSError:
            pass  # Best-effort cleanup
        
    def _setup_custom_styles(self):
        """Setup custom styles for the PDF"""
        # Title style
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#667eea'),
            alignment=TA_CENTER
        )
        
        # Subtitle style
        self.subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceAfter=20,
            textColor=colors.HexColor('#764ba2'),
            alignment=TA_CENTER
        )
        
        # Section header style
        self.section_style = ParagraphStyle(
            'SectionHeader',
            parent=self.styles['Heading3'],
            fontSize=14,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.HexColor('#667eea'),
            alignment=TA_LEFT
        )
        
        # Normal text style
        self.normal_style = ParagraphStyle(
            'CustomNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            leading=14
        )
        
        # Small text style
        self.small_style = ParagraphStyle(
            'CustomSmall',
            parent=self.styles['Normal'],
            fontSize=8,
            spaceAfter=3,
            leading=10
        )
        
        # Table cell style with text wrapping
        self.table_cell_style = ParagraphStyle(
            'TableCell',
            parent=self.styles['Normal'],
            fontSize=8,
            leading=10,
            wordWrap='CJK'
        )
        
        # Table header style
        self.table_header_style = ParagraphStyle(
            'TableHeader',
            parent=self.styles['Normal'],
            fontSize=9,
            leading=11,
            wordWrap='CJK',
            alignment=TA_CENTER
        )

    def _get_cache_key(self, plan_data: list, training_plan) -> str:
        """Generate a unique cache key based on plan content."""
        plan_str = json.dumps(plan_data, sort_keys=True)
        content_hash = hashlib.md5(plan_str.encode()).hexdigest()
        return f"{training_plan.id}_{content_hash}.pdf"

    def generate_pdf(self, plan_data: List[Dict[str, Any]], training_plan: TrainingPlan) -> str:
        """
        Generate a professional PDF training plan using ReportLab

        Args:
            plan_data: List of weekly training plans
            training_plan: Database training plan object

        Returns:
            Path to generated PDF file
        """
        self._evict_stale_cache()

        cache_key = self._get_cache_key(plan_data, training_plan)
        cache_path = self.cache_dir / cache_key

        if cache_path.exists():
            logger.info(f"Using cached PDF: {cache_key}")
            return str(cache_path)

        logger.info(f"Generating new PDF: {cache_key}")

        temp_dir = tempfile.mkdtemp()
        pdf_path = os.path.join(temp_dir, f"running_plan_{training_plan.id}.pdf")

        # Create PDF document
        doc = SimpleDocTemplate(pdf_path, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                               topMargin=2*cm, bottomMargin=2*cm)

        # Build story (content)
        story = []

        is_performance = getattr(training_plan, 'plan_type', 'distance') == 'performance'

        # First page: Title and overview only
        self._add_title_page(story, training_plan, plan_data)
        self._add_plan_summary(story, training_plan, plan_data)

        if is_performance:
            # Plan philosophy intro
            story.append(Spacer(1, 0.5*cm))
            self._add_performance_philosophy(story)

            # Training zones page with pace summary
            story.append(PageBreak())
            self._add_training_zones_page(story, training_plan)
            self._add_pace_improvement_summary(story, training_plan)

            # Weekly plans with performance-specific rendering
            for week in plan_data:
                story.append(PageBreak())
                self._add_performance_weekly_plan(story, week)

            # Add nutrition for performance plans
            if training_plan.nutrition_plan_data:
                story.append(PageBreak())
                self._add_personalized_nutrition_plan(story, training_plan)

            # Add general nutrition guidance
            story.append(PageBreak())
            self._add_nutrition_guidance(story)
        else:
            # Add page break before weekly plans
            story.append(PageBreak())

            # Add weekly plans - each week on its own page
            for week in plan_data:
                self._add_weekly_plan(story, week)
                story.append(PageBreak())

            # Remove the last page break if it's the final element
            if story and isinstance(story[-1], PageBreak):
                story.pop()

            # Add personalized nutrition plan if available
            if training_plan.nutrition_plan_data:
                story.append(PageBreak())
                self._add_personalized_nutrition_plan(story, training_plan)

            # Add general nutrition guidance
            story.append(PageBreak())
            self._add_nutrition_guidance(story)

            # Add injury prevention
            story.append(PageBreak())
            self._add_injury_prevention(story)

        # Add footer
        self._add_footer(story)
        
        # Build PDF
        doc.build(story)

        # Move to cache
        shutil.move(pdf_path, cache_path)
        shutil.rmtree(temp_dir, ignore_errors=True)

        return str(cache_path)
    
    def _add_title_page(self, story: List, training_plan: TrainingPlan, plan_data: List[Dict]):
        """Add title page"""
        # Check if this is a performance plan
        is_performance = getattr(training_plan, 'plan_type', 'distance') == 'performance'

        if is_performance:
            story.append(Paragraph("⚡ Performance Training Plan", self.title_style))
        else:
            story.append(Paragraph("🏃‍♂️ Personalized Running Training Plan", self.title_style))
        story.append(Spacer(1, 0.5*cm))

        subtitle = f"Target: {training_plan.target_distance}km Race | {training_plan.weeks_duration} Weeks"
        story.append(Paragraph(subtitle, self.subtitle_style))
        story.append(Spacer(1, 0.3*cm))

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

        story.append(Spacer(1, 2*cm))

        # Add key stats (30.0 = Trail Running)
        target_distance_float = training_plan.target_distance_km
        target_display = "Trail Running" if target_distance_float == 30.0 else f"{training_plan.target_distance} km"

        if is_performance and training_plan.current_pace and training_plan.goal_pace:
            # Performance plan stats
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
            # Distance plan stats
            stats_data = [
                ['Current Weekly Mileage', f"{training_plan.current_weekly_km} km"],
                ['Target Distance', target_display],
                ['Training Duration', f"{training_plan.weeks_duration} weeks"],
                ['Peak Week Mileage', f"{max(week['total_km'] for week in plan_data):.1f} km"]
            ]
        
        stats_table = Table(stats_data, colWidths=[5*cm, 3*cm])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6'))
        ]))
        
        story.append(stats_table)
        story.append(Spacer(1, 2*cm))
    
    def _add_plan_summary(self, story: List, training_plan: TrainingPlan, plan_data: List[Dict]):
        """Add plan overview with progress chart"""
        story.append(Paragraph("Training Plan Overview", self.section_style))

        is_performance = getattr(training_plan, 'plan_type', 'distance') == 'performance'

        if is_performance:
            # Performance plan: include phase column
            chart_data = [['Week', 'Phase', 'Mileage (km)', 'Progress']]
            max_mileage = max(week['total_km'] for week in plan_data)

            for week in plan_data:
                progress_bar = self._create_progress_bar(week['total_km'], max_mileage)
                phase = week.get('phase', '').title()
                chart_data.append([
                    f"Week {week['week']}",
                    phase,
                    f"{week['total_km']:.1f}",
                    progress_bar
                ])

            chart_table = Table(chart_data, colWidths=[2 * cm, 2 * cm, 2 * cm, 5 * cm])
        else:
            # Distance plan: original layout
            chart_data = [['Week', 'Mileage (km)', 'Progress']]
            max_mileage = max(week['total_km'] for week in plan_data)

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
        """Create a simple text-based progress bar"""
        if maximum == 0:
            return "░" * 20 + " 0%"
        
        percentage = min(current / maximum, 1.0)
        bar_length = 20
        filled_length = int(bar_length * percentage)
        bar = "█" * filled_length + "░" * (bar_length - filled_length)
        return f"{bar} {percentage*100:.0f}%"
    
    def _add_weekly_plan(self, story: List, week: Dict[str, Any]):
        """Add weekly training plan"""
        # Add phase info if this is a performance plan
        if 'phase' in week and 'phase_description' in week:
            title = f"Week {week['week']} - {week['total_km']:.1f} km | {week['phase'].title()} Phase"
            story.append(Paragraph(title, self.section_style))
            story.append(Paragraph(f"<i>{week['phase_description']}</i>", self.normal_style))
            story.append(Spacer(1, 0.3*cm))
        else:
            story.append(Paragraph(f"Week {week['week']} - {week['total_km']:.1f} km", self.section_style))
        
        # Create workout table with proper text wrapping
        workout_data = [['Day', 'Workout', 'Distance', 'Intensity', 'Notes']]
        
        for workout in week.get('daily_workouts', []):
            # Convert all text to Paragraph objects for proper wrapping
            workout_data.append([
                Paragraph(self._get_day_name(workout['day']), self.table_cell_style),
                Paragraph(workout['type'].title(), self.table_cell_style),
                Paragraph(f"{workout.get('distance', 0):.1f} km" if workout.get('distance', 0) > 0 else "-", self.table_cell_style),
                Paragraph(workout.get('intensity', '-').title(), self.table_cell_style),
                Paragraph(workout.get('description', ''), self.table_cell_style)
            ])
        
        # Convert headers to Paragraph objects with proper alignment
        header_styles = [self.table_header_style] * len(workout_data[0])
        header_styles[0] = ParagraphStyle(
            'DayHeader',
            parent=self.table_header_style,
            alignment=TA_CENTER
        )
        for i in range(len(workout_data[0])):
            workout_data[0][i] = Paragraph(workout_data[0][i], header_styles[i])
        
        workout_table = Table(workout_data, colWidths=[2.5*cm, 2*cm, 1.5*cm, 1.5*cm, 5*cm])
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
        story.append(Spacer(1, 0.5*cm))
        
        # Add strength training if available
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
                story.append(Spacer(1, 0.2*cm))
            story.append(Spacer(1, 0.1*cm))
        
        # Add training tips if available
        if week.get('training_tips'):
            story.append(Paragraph("🎯 Training Tips", self.normal_style))
            for tip in week['training_tips']:
                story.append(Paragraph(f"• {tip}", self.small_style))
            story.append(Spacer(1, 0.5*cm))
    
    def _format_pace(self, pace_min_per_km: float) -> str:
        """Format pace as MM:SS/km."""
        return _shared_format_pace(pace_min_per_km)

    def _add_performance_philosophy(self, story: List):
        """Add a brief plan philosophy section for performance PDFs."""
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
        story.append(Spacer(1, 0.5*cm))

    def _add_pace_improvement_summary(self, story: List, training_plan: TrainingPlan):
        """Add current pace -> goal pace improvement summary."""
        if not training_plan.current_pace or not training_plan.goal_pace:
            return

        current_formatted = self._format_pace(training_plan.current_pace)
        goal_formatted = self._format_pace(training_plan.goal_pace)
        improvement = ((training_plan.current_pace - training_plan.goal_pace)
                       / training_plan.current_pace * 100)

        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("Pace Improvement Target", self.section_style))

        pace_data = [
            ['Current Pace', 'Goal Pace', 'Improvement'],
            [current_formatted, goal_formatted, f"{improvement:.1f}%"]
        ]

        pace_table = Table(pace_data, colWidths=[4*cm, 4*cm, 4*cm])
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
        story.append(Spacer(1, 0.5*cm))

    def _add_training_zones_page(self, story: List, training_plan: TrainingPlan):
        """Add training zones table for performance plans."""
        from app.core.performance_plan_generator import PerformancePlanGenerator

        gen = PerformancePlanGenerator()
        zones = gen.calculate_training_zones(
            training_plan.goal_pace,
            training_plan.max_heart_rate
        )

        story.append(Paragraph("Training Zones", self.section_style))
        story.append(Spacer(1, 0.3 * cm))

        # Build table data
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

        # Color-code each zone row
        for i, zc in enumerate(zone_colors):
            row = i + 1  # offset for header
            style_cmds.append(('BACKGROUND', (0, row), (0, row), zc))

        zone_table.setStyle(TableStyle(style_cmds))
        story.append(zone_table)
        story.append(Spacer(1, 1 * cm))

    def _add_performance_weekly_plan(self, story: List, week: Dict[str, Any]):
        """Add a performance-specific weekly plan with segments."""
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
            zone_label = workout.get('zone', '-')
            target_pace = workout.get('target_pace_formatted', '-')
            desc = workout.get('description', '')

            # Workout header row
            header_text = f"<b>{day_name}</b> | {w_type} | {dist:.1f} km | {target_pace}"
            story.append(Paragraph(header_text, self.normal_style))

            if desc:
                story.append(Paragraph(f"<i>{desc}</i>", self.small_style))

            # Segments sub-table
            segments = workout.get('segments', [])
            if segments:
                seg_header = ['Segment', 'Distance', 'Pace', 'Zone']
                seg_data = [[Paragraph(h, self.table_header_style) for h in seg_header]]

                for seg in segments:
                    seg_name = seg.get('name', '')
                    seg_dist = f"{seg.get('distance_km', 0):.1f} km"
                    seg_pace = seg.get('pace_formatted', '-')
                    seg_zone = seg.get('zone_label', '-')

                    # Add interval detail if present
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

    def _add_bullet_list(self, story: List, items: List[str], spacing: float = 0.3):
        """Append a bulleted list to the PDF story."""
        for item in items:
            story.append(Paragraph(f"• {item}", self.small_style))
        story.append(Spacer(1, spacing * cm))

    def _add_nutrition_guidance(self, story: List):
        """Add comprehensive nutrition guidance section."""
        story.append(Paragraph("🥗 Complete Nutrition Guide for Runners", self.section_style))
        self._add_pre_run_fuel(story)
        self._add_post_run_recovery(story)
        self._add_daily_meal_plans(story)
        self._add_hydration_strategy(story)
        self._add_race_week_nutrition(story)

    def _add_pre_run_fuel(self, story: List):
        story.append(Paragraph("⚡ Pre-Run Fuel (30-90 minutes before)", self.normal_style))
        self._add_bullet_list(story, [
            "Quick Energy: Banana + 1 tbsp peanut butter",
            "Sustained Energy: Oatmeal with berries + honey",
            "Light Option: Toast with avocado + sea salt",
            "Hydration Focus: Smoothie with spinach, banana, almond milk",
            "Race Day: Plain bagel with jam (low fiber)",
        ])

    def _add_post_run_recovery(self, story: List):
        story.append(Paragraph("🔄 Post-Run Recovery (within 30 minutes)", self.normal_style))
        self._add_bullet_list(story, [
            "Protein + Carbs: Chocolate milk (8oz)",
            "Muscle Repair: Greek yogurt + granola + berries",
            "Hydration + Energy: Coconut water + banana",
            "Complete Recovery: Protein smoothie (1 scoop protein, banana, spinach)",
            "Quick Option: Recovery bar with 3:1 carb:protein ratio",
        ])

    def _add_daily_meal_plans(self, story: List):
        story.append(Paragraph("🍽️ Comprehensive Daily Meal Plans", self.normal_style))

        meal_plan_data = [
            ['Meal', 'Training Day Options', 'Rest Day Options'],
            ['Breakfast',
             'Oatmeal with nuts, berries, honey\nWhole grain toast + eggs + avocado\nSmoothie with spinach, banana, protein powder\nGreek yogurt + granola + berries\nBreakfast burrito with black beans, eggs',
             'Greek yogurt parfait\nSmoothie bowl with granola\nOvernight oats with chia seeds\nWhole grain pancakes with fruit\nAvocado toast with poached eggs'],
            ['Lunch',
             'Quinoa bowl with roasted vegetables + chicken\nLarge salad with salmon + sweet potato\nTurkey wrap with hummus + vegetables\nLentil soup + whole grain bread\nBuddha bowl with tahini dressing',
             'Vegetable soup + whole grain bread\nLentil salad with feta cheese\nCaprese salad with whole grain pasta\nChickpea salad sandwich\nQuinoa tabbouleh with grilled vegetables'],
            ['Afternoon Snack',
             'Apple + almond butter\nTrail mix + dried fruit\nProtein smoothie with banana\nRice cakes with hummus\nEnergy balls with dates + nuts',
             'Hummus + vegetable sticks\nCottage cheese + peaches\nGreek yogurt with honey\nMixed berries + nuts\nDark chocolate + almonds'],
            ['Pre-Run Fuel',
             'Banana + peanut butter\nToast with jam + honey\nEnergy gel + water\nDates + almond butter\nOatmeal bar + sports drink',
             'Light fruit + water\nHerbal tea + honey\nElectrolyte drink\nCoconut water\nRice cakes with banana'],
            ['Post-Run Recovery',
             'Chocolate milk + banana\nProtein shake with berries\nGreek yogurt + granola\nRecovery smoothie with spinach\nCottage cheese + pineapple',
             'Green smoothie + protein\nGreek yogurt + nuts\nOvernight oats + protein powder\nQuinoa bowl + fruit\nEggs + whole grain toast'],
            ['Dinner',
             'Grilled salmon + brown rice + broccoli\nLean beef + roasted vegetables + quinoa\nChicken stir-fry with brown rice\nTurkey meatballs + whole wheat pasta\nFish tacos with slaw + beans',
             'Vegetable stir-fry + tofu\nPasta primavera with olive oil\nBlack bean burgers + sweet potato\nLentil shepherd\'s pie\nRoasted vegetable + chickpea curry']
        ]

        paragraph_data = []
        for row in meal_plan_data:
            paragraph_data.append([Paragraph(cell, self.table_cell_style) for cell in row])
        for i in range(len(paragraph_data[0])):
            paragraph_data[0][i] = Paragraph(meal_plan_data[0][i], self.table_header_style)

        meal_table = Table(paragraph_data, colWidths=[2.5*cm, 5*cm, 5*cm])
        meal_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#9c27b0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8)
        ]))
        story.append(meal_table)
        story.append(Spacer(1, 0.5*cm))

    def _add_hydration_strategy(self, story: List):
        story.append(Paragraph("💧 Hydration Strategy", self.normal_style))
        self._add_bullet_list(story, [
            "Daily Base: 2.5-3L water + electrolytes",
            "Pre-Run: 500ml 2 hours before, 250ml 30 minutes before",
            "During Run: 150-200ml every 15-20 minutes (over 60 minutes)",
            "Post-Run: 500-750ml per kg of body weight lost",
            "Electrolyte Sources: Coconut water, sports drinks, salt tabs",
            "Urine Color Test: Pale yellow = well hydrated",
        ], spacing=0.5)

    def _add_race_week_nutrition(self, story: List):
        story.append(Paragraph("🏁 Race Week Nutrition Strategy", self.normal_style))
        self._add_bullet_list(story, [
            "7 Days Before: Increase carbs to 70% of calories",
            "3 Days Before: Carb-load with pasta, rice, potatoes",
            "2 Days Before: Reduce fiber, avoid spicy foods",
            "Day Before: Simple carbs, hydrate well, early dinner",
            "Race Morning: Familiar breakfast, 2-3 hours before start",
            "During Race: Energy gels every 45 minutes + water",
        ], spacing=1.0)
    
    def _add_personalized_nutrition_plan(self, story: List, training_plan: TrainingPlan):
        """Add personalized nutrition plan with meals"""
        try:
            nutrition_plan = json.loads(training_plan.nutrition_plan_data)
        except (json.JSONDecodeError, AttributeError):
            return
        
        story.append(Paragraph("🍽️ Your Personalized Nutrition Plan", self.section_style))
        
        # Add nutrition targets
        if "nutrition_targets" in nutrition_plan:
            targets = nutrition_plan["nutrition_targets"]
            story.append(Paragraph("📊 Your Daily Nutrition Targets", self.normal_style))
            
            targets_data = [
                ['Nutrient', 'Daily Target', 'Notes'],
                ['Calories', f"{targets.get('calories', 0)} kcal", "Based on your training volume"],
                ['Protein', f"{targets.get('protein', 0)} g", "For muscle repair and recovery"],
                ['Carbs', f"{targets.get('carbs', 0)} g", "Primary fuel for running"],
                ['Fat', f"{targets.get('fat', 0)} g", "For hormone production and health"],
                ['Fiber', f"{targets.get('fiber', 0)} g", "For digestive health and satiety"]
            ]
            
            targets_table = Table(targets_data, colWidths=[3*cm, 3*cm, 6*cm])
            targets_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#9c27b0')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
            ]))
            
            story.append(targets_table)
            story.append(Spacer(1, 0.5*cm))
        
        # Add meal options
        if "meal_options" in nutrition_plan:
            story.append(Paragraph("🥗 Your Personalized Meal Options", self.normal_style))
            
            meal_options = nutrition_plan["meal_options"]
            
            # Create meal plan table
            meal_plan_data = [['Meal Type', 'Recommended Options', 'Key Benefits']]
            
            meal_benefits = {
                'breakfast': 'Energy for morning runs',
                'lunch': 'Sustained afternoon energy',
                'dinner': 'Muscle recovery overnight',
                'snack': 'Quick energy between meals',
                'post_workout': 'Optimal recovery nutrition'
            }
            
            for meal_type, meals in meal_options.items():
                if meals and len(meals) > 0:
                    # List top 2-3 meal options
                    meal_list = []
                    for meal in meals[:3]:
                        meal_name = meal.get('name', 'Unknown meal')
                        protein = meal.get('protein', 0)
                        fiber = meal.get('fiber', 0)
                        meal_list.append(f"• {meal_name} (P:{protein}g, F:{fiber}g)")
                    
                    meal_text = "\n".join(meal_list)
                    benefits = meal_benefits.get(meal_type, 'Balanced nutrition')
                    
                    meal_plan_data.append([
                        Paragraph(meal_type.title(), self.table_cell_style),
                        Paragraph(meal_text, self.table_cell_style),
                        Paragraph(benefits, self.table_cell_style)
                    ])
            
            if len(meal_plan_data) > 1:  # Only add if we have meal data
                meal_table = Table(meal_plan_data, colWidths=[3*cm, 7*cm, 4*cm])
                meal_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4caf50')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8)
                ]))
                
                story.append(meal_table)
                story.append(Spacer(1, 0.5*cm))
        
        # Add general nutrition tips
        if "general_tips" in nutrition_plan:
            story.append(Paragraph("💡 Your Personalized Nutrition Tips", self.normal_style))
            for tip in nutrition_plan["general_tips"][:5]:  # Show top 5 tips
                story.append(Paragraph(f"• {tip}", self.small_style))
            story.append(Spacer(1, 0.5*cm))
        
        # Add hydration guide
        if "hydration_guide" in nutrition_plan:
            hydration = nutrition_plan["hydration_guide"]
            story.append(Paragraph("💧 Your Personalized Hydration Plan", self.normal_style))
            
            hydration_data = [
                ['Timing', 'Target', 'Notes'],
                ['Daily Base', hydration.get('daily_target', '2000ml'), 'Maintain throughout the day'],
                ['Pre-Run', hydration.get('pre_run', '300-500ml'), '2 hours before training'],
                ['During Run', hydration.get('during_run', '200-400ml/hour'), 'Adjust for intensity and heat'],
                ['Post-Run', hydration.get('post_run', '150% loss'), 'Replace lost fluids'],
                ['Race Day', hydration.get('race_day', '400-600ml/hour'), 'With electrolytes for longer events']
            ]
            
            hydration_table = Table(hydration_data, colWidths=[3*cm, 4*cm, 6*cm])
            hydration_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196f3')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
            ]))
            
            story.append(hydration_table)
            story.append(Spacer(1, 0.5*cm))
        
        story.append(Spacer(1, 1*cm))
    
    def _add_injury_prevention(self, story: List):
        """Add comprehensive injury prevention section"""
        story.append(Paragraph("🏥 Complete Injury Prevention Guide", self.section_style))
        
        # Warm-up and Cool-down
        story.append(Paragraph("🔥 Warm-up Protocol (10-15 minutes)", self.normal_style))
        warmup_steps = [
            "Dynamic Stretches: Leg swings, walking lunges, high knees (5 minutes)",
            "Activation Exercises: Glute bridges, monster walks (3 minutes)",
            "Progressive Run: Walk 2min → jog 3min → run 5min (5 minutes)",
            "Sport-Specific Drills: A-skips, B-skips, butt kicks (2 minutes)"
        ]
        for step in warmup_steps:
            story.append(Paragraph(f"• {step}", self.small_style))
        story.append(Spacer(1, 0.3*cm))
        
        story.append(Paragraph("❄️ Cool-down Protocol (10-15 minutes)", self.normal_style))
        cooldown_steps = [
            "Active Recovery: Easy walk or jog (5 minutes)",
            "Static Stretches: Hold each 30 seconds, no bouncing",
            "Focus Areas: Hamstrings, quads, calves, hips, IT band",
            "Foam Rolling: 1-2 minutes per muscle group"
        ]
        for step in cooldown_steps:
            story.append(Paragraph(f"• {step}", self.small_style))
        story.append(Spacer(1, 0.3*cm))
        
        # Strength Training
        story.append(Paragraph("💪 Essential Strength Training (2-3x per week)", self.normal_style))
        strength_exercises = [
            "Lower Body: Squats (3x12), Lunges (3x10 each), Calf raises (3x20)",
            "Core: Plank (3x45sec), Side planks (3x30sec each), Dead bugs (3x10 each)",
            "Hip Stability: Clamshells (3x15 each), Glute bridges (3x15), Monster walks (3x10 each)",
            "Upper Body: Push-ups (3x10), Rows (3x12), Overhead press (3x10)"
        ]
        for exercise in strength_exercises:
            story.append(Paragraph(f"• {exercise}", self.small_style))
        story.append(Spacer(1, 0.3*cm))
        
        # Recovery Strategies
        story.append(Paragraph("🛌 Recovery Strategies", self.normal_style))
        recovery_tips = [
            "Sleep: 7-9 hours nightly, consistent schedule",
            "Nutrition: Protein within 30 minutes post-run, anti-inflammatory foods",
            "Hydration: 2-3L daily + electrolytes on long run days",
            "Active Recovery: Swimming, cycling, yoga on rest days",
            "Massage: Professional monthly + self-massage weekly"
        ]
        for tip in recovery_tips:
            story.append(Paragraph(f"• {tip}", self.small_style))
        story.append(Spacer(1, 0.3*cm))
        
        # Warning Signs
        story.append(Paragraph("⚠️ Warning Signs - When to Stop", self.normal_style))
        warning_signs = [
            "Pain that increases during run (vs. decreases with warm-up)",
            "Sharp, stabbing, or localized pain",
            "Pain that causes limping or form changes",
            "Swelling, redness, or warmth in joints/tissues",
            "Pain that persists >24 hours after rest",
            "Night pain or pain at rest"
        ]
        for sign in warning_signs:
            story.append(Paragraph(f"• {sign}", self.small_style))
        story.append(Spacer(1, 0.3*cm))
        
        # Equipment Management
        story.append(Paragraph("👟 Equipment Management", self.normal_style))
        equipment_tips = [
            "Running Shoes: Replace every 500-800km or 6-12 months",
            "Rotation: Have 2+ pairs, alternate to extend life",
            "Proper Fit: Shop in afternoon, thumb-width space at toe",
            "Surface-Specific: Road shoes for pavement, trail shoes for off-road",
            "Monitoring: Check for uneven wear patterns, midsole compression"
        ]
        for tip in equipment_tips:
            story.append(Paragraph(f"• {tip}", self.small_style))
        story.append(Spacer(1, 0.3*cm))
        
        # Training Progression
        story.append(Paragraph("📈 Smart Training Progression", self.normal_style))
        progression_rules = [
            "10% Rule: Increase weekly mileage by max 10% every 2-3 weeks",
            "Recovery Weeks: Reduce mileage by 20-30% every 4th week",
            "Hard/Easy Balance: Follow hard days with easy or rest days",
            "Listen to Body: Use perceived exertion scale 1-10, stay at 6-7 for easy runs",
            "Cross-Training: Replace 1-2 runs weekly with low-impact activities"
        ]
        for rule in progression_rules:
            story.append(Paragraph(f"• {rule}", self.small_style))
        story.append(Spacer(1, 1*cm))
    
    def _add_footer(self, story: List):
        """Add footer information"""
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph("Generated by RunCoach - Your Personalized Running Training Plan Generator", 
                              ParagraphStyle('Footer', parent=self.styles['Normal'], fontSize=8, 
                                            alignment=TA_CENTER, textColor=colors.gray)))
        story.append(Paragraph("Consult with a healthcare professional before beginning any new training program", 
                              ParagraphStyle('Footer', parent=self.styles['Normal'], fontSize=8, 
                                            alignment=TA_CENTER, textColor=colors.gray)))
    
    def _get_day_name(self, day_number: int) -> str:
        """Convert day number to day name"""
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        if 1 <= day_number <= 7:
            return days[day_number - 1]
        return f"Day {day_number}"