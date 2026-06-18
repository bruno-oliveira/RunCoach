"""PDF nutrition content pages — general guidance and personalized plans."""

from typing import List
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from app.infrastructure.export.plan_export_dto import PlanExportDTO


class NutritionPagesMixin:
    """Methods for rendering nutrition-related PDF pages."""

    def _add_bullet_list(self, story: List, items: List[str], spacing: float = 0.3):
        for item in items:
            story.append(Paragraph(f"• {item}", self.small_style))
        story.append(Spacer(1, spacing * cm))

    def _add_nutrition_guidance(self, story: List):
        story.append(
            Paragraph("🥗 Complete Nutrition Guide for Runners", self.section_style)
        )
        self._add_pre_run_fuel(story)
        self._add_post_run_recovery(story)
        self._add_daily_meal_plans(story)
        self._add_hydration_strategy(story)
        self._add_race_week_nutrition(story)

    def _add_pre_run_fuel(self, story: List):
        story.append(
            Paragraph("⚡ Pre-Run Fuel (30-90 minutes before)", self.normal_style)
        )
        self._add_bullet_list(
            story,
            [
                "Quick Energy: Banana + 1 tbsp peanut butter",
                "Sustained Energy: Oatmeal with berries + honey",
                "Light Option: Toast with avocado + sea salt",
                "Hydration Focus: Smoothie with spinach, banana, almond milk",
                "Race Day: Plain bagel with jam (low fiber)",
            ],
        )

    def _add_post_run_recovery(self, story: List):
        story.append(
            Paragraph("🔄 Post-Run Recovery (within 30 minutes)", self.normal_style)
        )
        self._add_bullet_list(
            story,
            [
                "Protein + Carbs: Chocolate milk (8oz)",
                "Muscle Repair: Greek yogurt + granola + berries",
                "Hydration + Energy: Coconut water + banana",
                "Complete Recovery: Protein smoothie (1 scoop protein, banana, spinach)",
                "Quick Option: Recovery bar with 3:1 carb:protein ratio",
            ],
        )

    def _add_daily_meal_plans(self, story: List):
        story.append(Paragraph("🍽️ Comprehensive Daily Meal Plans", self.normal_style))

        meal_plan_data = [
            ["Meal", "Training Day Options", "Rest Day Options"],
            [
                "Breakfast",
                "Oatmeal with nuts, berries, honey\nWhole grain toast + eggs + avocado\nSmoothie with spinach, banana, protein powder\nGreek yogurt + granola + berries\nBreakfast burrito with black beans, eggs",
                "Greek yogurt parfait\nSmoothie bowl with granola\nOvernight oats with chia seeds\nWhole grain pancakes with fruit\nAvocado toast with poached eggs",
            ],
            [
                "Lunch",
                "Quinoa bowl with roasted vegetables + chicken\nLarge salad with salmon + sweet potato\nTurkey wrap with hummus + vegetables\nLentil soup + whole grain bread\nBuddha bowl with tahini dressing",
                "Vegetable soup + whole grain bread\nLentil salad with feta cheese\nCaprese salad with whole grain pasta\nChickpea salad sandwich\nQuinoa tabbouleh with grilled vegetables",
            ],
            [
                "Afternoon Snack",
                "Apple + almond butter\nTrail mix + dried fruit\nProtein smoothie with banana\nRice cakes with hummus\nEnergy balls with dates + nuts",
                "Hummus + vegetable sticks\nCottage cheese + peaches\nGreek yogurt with honey\nMixed berries + nuts\nDark chocolate + almonds",
            ],
            [
                "Pre-Run Fuel",
                "Banana + peanut butter\nToast with jam + honey\nEnergy gel + water\nDates + almond butter\nOatmeal bar + sports drink",
                "Light fruit + water\nHerbal tea + honey\nElectrolyte drink\nCoconut water\nRice cakes with banana",
            ],
            [
                "Post-Run Recovery",
                "Chocolate milk + banana\nProtein shake with berries\nGreek yogurt + granola\nRecovery smoothie with spinach\nCottage cheese + pineapple",
                "Green smoothie + protein\nGreek yogurt + nuts\nOvernight oats + protein powder\nQuinoa bowl + fruit\nEggs + whole grain toast",
            ],
            [
                "Dinner",
                "Grilled salmon + brown rice + broccoli\nLean beef + roasted vegetables + quinoa\nChicken stir-fry with brown rice\nTurkey meatballs + whole wheat pasta\nFish tacos with slaw + beans",
                "Vegetable stir-fry + tofu\nPasta primavera with olive oil\nBlack bean burgers + sweet potato\nLentil shepherd's pie\nRoasted vegetable + chickpea curry",
            ],
        ]

        paragraph_data = []
        for row in meal_plan_data:
            paragraph_data.append(
                [Paragraph(cell, self.table_cell_style) for cell in row]
            )
        for i in range(len(paragraph_data[0])):
            paragraph_data[0][i] = Paragraph(
                meal_plan_data[0][i], self.table_header_style
            )

        meal_table = Table(paragraph_data, colWidths=[2.5 * cm, 5 * cm, 5 * cm])
        meal_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9c27b0")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#dee2e6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(meal_table)
        story.append(Spacer(1, 0.5 * cm))

    def _add_hydration_strategy(self, story: List):
        story.append(Paragraph("💧 Hydration Strategy", self.normal_style))
        self._add_bullet_list(
            story,
            [
                "Daily Base: 2.5-3L water + electrolytes",
                "Pre-Run: 500ml 2 hours before, 250ml 30 minutes before",
                "During Run: 150-200ml every 15-20 minutes (over 60 minutes)",
                "Post-Run: 500-750ml per kg of body weight lost",
                "Electrolyte Sources: Coconut water, sports drinks, salt tabs",
                "Urine Color Test: Pale yellow = well hydrated",
            ],
            spacing=0.5,
        )

    def _add_race_week_nutrition(self, story: List):
        story.append(Paragraph("🏁 Race Week Nutrition Strategy", self.normal_style))
        self._add_bullet_list(
            story,
            [
                "7 Days Before: Increase carbs to 70% of calories",
                "3 Days Before: Carb-load with pasta, rice, potatoes",
                "2 Days Before: Reduce fiber, avoid spicy foods",
                "Day Before: Simple carbs, hydrate well, early dinner",
                "Race Morning: Familiar breakfast, 2-3 hours before start",
                "During Race: Energy gels every 45 minutes + water",
            ],
            spacing=1.0,
        )

    def _add_personalized_nutrition_plan(
        self, story: List, training_plan: PlanExportDTO
    ):
        nutrition_plan = training_plan.nutrition_plan_data
        if not nutrition_plan:
            return

        story.append(
            Paragraph("🍽️ Your Personalized Nutrition Plan", self.section_style)
        )

        if "nutrition_targets" in nutrition_plan:
            self._add_nutrition_targets(story, nutrition_plan["nutrition_targets"])

        if "meal_options" in nutrition_plan:
            self._add_meal_options(story, nutrition_plan["meal_options"])

        if training_plan.is_trail:
            self._add_trail_fuelling(story, nutrition_plan)

        if "general_tips" in nutrition_plan:
            story.append(
                Paragraph("💡 Your Personalized Nutrition Tips", self.normal_style)
            )
            for tip in nutrition_plan["general_tips"][:5]:
                story.append(Paragraph(f"• {tip}", self.small_style))
            story.append(Spacer(1, 0.5 * cm))

        if "hydration_guide" in nutrition_plan:
            self._add_hydration_guide(story, nutrition_plan["hydration_guide"])

        story.append(Spacer(1, 1 * cm))

    def _add_nutrition_targets(self, story: List, targets: dict):
        story.append(Paragraph("📊 Your Daily Nutrition Targets", self.normal_style))

        targets_data = [
            ["Nutrient", "Daily Target", "Notes"],
            [
                "Calories",
                f"{targets.get('calories', 0)} kcal",
                "Based on your training volume",
            ],
            [
                "Protein",
                f"{targets.get('protein', 0)} g",
                "For muscle repair and recovery",
            ],
            ["Carbs", f"{targets.get('carbs', 0)} g", "Primary fuel for running"],
            ["Fat", f"{targets.get('fat', 0)} g", "For hormone production and health"],
            [
                "Fiber",
                f"{targets.get('fiber', 0)} g",
                "For digestive health and satiety",
            ],
        ]

        targets_table = Table(targets_data, colWidths=[3 * cm, 3 * cm, 6 * cm])
        targets_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9c27b0")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#dee2e6")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )

        story.append(targets_table)
        story.append(Spacer(1, 0.5 * cm))

    def _add_meal_options(self, story: List, meal_options: dict):
        story.append(Paragraph("🥗 Your Personalized Meal Options", self.normal_style))

        meal_plan_data = [["Meal Type", "Recommended Options", "Key Benefits"]]

        meal_benefits = {
            "breakfast": "Energy for morning runs",
            "lunch": "Sustained afternoon energy",
            "dinner": "Muscle recovery overnight",
            "snack": "Quick energy between meals",
            "post_workout": "Optimal recovery nutrition",
        }

        for meal_type, meals in meal_options.items():
            if meals and len(meals) > 0:
                meal_list = []
                for meal in meals[:3]:
                    meal_name = meal.get("name", "Unknown meal")
                    protein = meal.get("protein", 0)
                    fiber = meal.get("fiber", 0)
                    meal_list.append(f"• {meal_name} (P:{protein}g, F:{fiber}g)")

                meal_text = "\n".join(meal_list)
                benefits = meal_benefits.get(meal_type, "Balanced nutrition")

                meal_plan_data.append(
                    [
                        Paragraph(meal_type.title(), self.table_cell_style),
                        Paragraph(meal_text, self.table_cell_style),
                        Paragraph(benefits, self.table_cell_style),
                    ]
                )

        if len(meal_plan_data) > 1:
            meal_table = Table(meal_plan_data, colWidths=[3 * cm, 7 * cm, 4 * cm])
            meal_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4caf50")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#dee2e6")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )

            story.append(meal_table)
            story.append(Spacer(1, 0.5 * cm))

    def _add_trail_fuelling(self, story: List, nutrition_plan: dict):
        """Render the trail/ultra fuelling section (mirrors the web Nutrition tab).

        Covers the in-race fuelling table, portable trail-ready fuel grouped by
        race phase, and topic-tagged fuelling tips. Only called for trail plans.
        """
        in_race = nutrition_plan.get("in_race_fueling")
        fuel_ideas = nutrition_plan.get("trail_fuel_ideas") or []
        phases = nutrition_plan.get("trail_fuel_phases") or []
        tips = nutrition_plan.get("trail_tips") or []
        if not (in_race or fuel_ideas or tips):
            return

        story.append(Paragraph("⛰️ Trail Race Fuelling", self.section_style))

        if in_race:
            self._add_in_race_fueling_table(story, in_race)

        if fuel_ideas:
            self._add_trail_fuel_ideas(story, fuel_ideas, phases)

        if tips:
            story.append(Paragraph("💡 Trail Fuelling Tips", self.normal_style))
            for tip in tips:
                topic = escape(str(tip.get("topic", "")))
                text = escape(str(tip.get("text", "")))
                story.append(Paragraph(f"• <b>{topic}:</b> {text}", self.small_style))
            story.append(Spacer(1, 0.5 * cm))

        story.append(Spacer(1, 0.5 * cm))

    def _add_in_race_fueling_table(self, story: List, in_race: dict):
        story.append(Paragraph("🎯 In-Race Fuelling", self.normal_style))

        rows = [["Metric", "Target"]]
        if in_race.get("estimated_duration_hours"):
            rows.append(["Est. Duration", f"~{in_race['estimated_duration_hours']} h"])
        rows.append(["Carbs / Hour", in_race.get("carbs_per_hour", "—")])
        rows.append(["Fluid / Hour", in_race.get("fluid_per_hour_ml", "—")])
        rows.append(["Electrolytes", in_race.get("electrolytes", "—")])

        table = Table(rows, colWidths=[4 * cm, 9 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e7d32")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#dee2e6")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 0.3 * cm))

        for key in ("real_food_strategy", "rehearsal_advice"):
            note = in_race.get(key)
            if note:
                story.append(Paragraph(f"• {escape(str(note))}", self.small_style))
        story.append(Spacer(1, 0.4 * cm))

    def _add_trail_fuel_ideas(self, story: List, fuel_ideas: list, phases: list):
        story.append(Paragraph("🥨 Trail Fuel Ideas", self.normal_style))

        # Group ideas by race phase. Fall back to a single untitled group when
        # the phase metadata is missing so nothing is silently dropped.
        phase_order = phases or [{"key": None, "label": ""}]
        seen_keys = {p.get("key") for p in phase_order}
        for phase in phase_order:
            key = phase.get("key")
            items = [i for i in fuel_ideas if i.get("phase") == key]
            self._add_trail_fuel_phase(story, phase.get("label", ""), items)

        # Any ideas whose phase isn't in the known order still get rendered.
        leftovers = [i for i in fuel_ideas if i.get("phase") not in seen_keys]
        if leftovers:
            self._add_trail_fuel_phase(story, "Other", leftovers)

        story.append(Spacer(1, 0.2 * cm))

    def _add_trail_fuel_phase(self, story: List, label: str, items: list):
        if not items:
            return
        if label:
            story.append(Paragraph(f"<b>{escape(label)}</b>", self.small_style))
        for item in items:
            name = escape(str(item.get("name", "")))
            category = escape(str(item.get("category", "")))
            carbs = escape(str(item.get("carbs", "")))
            note = escape(str(item.get("note", "")))
            meta = " · ".join(p for p in (category, carbs) if p)
            line = f"• <b>{name}</b>"
            if meta:
                line += f" ({meta})"
            if note:
                line += f" — {note}"
            story.append(Paragraph(line, self.small_style))
        story.append(Spacer(1, 0.2 * cm))

    def _add_hydration_guide(self, story: List, hydration: dict):
        story.append(
            Paragraph("💧 Your Personalized Hydration Plan", self.normal_style)
        )

        hydration_data = [
            ["Timing", "Target", "Notes"],
            [
                "Daily Base",
                hydration.get("daily_target", "2000ml"),
                "Maintain throughout the day",
            ],
            [
                "Pre-Run",
                hydration.get("pre_run", "300-500ml"),
                "2 hours before training",
            ],
            [
                "During Run",
                hydration.get("during_run", "200-400ml/hour"),
                "Adjust for intensity and heat",
            ],
            ["Post-Run", hydration.get("post_run", "150% loss"), "Replace lost fluids"],
            [
                "Race Day",
                hydration.get("race_day", "400-600ml/hour"),
                "With electrolytes for longer events",
            ],
        ]

        hydration_table = Table(hydration_data, colWidths=[3 * cm, 4 * cm, 6 * cm])
        hydration_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2196f3")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#dee2e6")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )

        story.append(hydration_table)
        story.append(Spacer(1, 0.5 * cm))
