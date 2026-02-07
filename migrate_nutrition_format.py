"""Migrate nutrition plans from old list format to new blueprint format."""

import json
import sqlite3

def migrate_list_to_blueprint(old_list_data):
    """Convert old list format to new blueprint format."""
    if not old_list_data:
        return {}
    
    first_day = old_list_data[0]
    targets = first_day.get("nutrition_targets", {})
    
    # Create blueprint structure
    blueprint = {
        "nutrition_targets": targets,
        "meal_options": {
            "breakfast": [],
            "lunch": [],
            "dinner": [],
            "snack": [],
            "post_workout": []
        },
        "general_tips": first_day.get("nutrition_tips", []),
        "hydration_guide": {
            "daily_target": "2000ml",
            "pre_run": "300-500ml, 2 hours before",
            "during_run": "200-400ml per hour",
            "post_run": "150% of fluid lost",
            "tips": ["Stay hydrated throughout the day"]
        }
    }
    
    # Collect unique meals from all days
    seen_meals = {meal_type: set() for meal_type in blueprint["meal_options"].keys()}
    
    for daily_plan in old_list_data:
        for meal_type, meal_data in daily_plan.get("meals", {}).items():
            if meal_type in seen_meals:
                meal_name = meal_data.get("name")
                if meal_name not in seen_meals[meal_type]:
                    seen_meals[meal_type].add(meal_name)
                    blueprint["meal_options"][meal_type].append(meal_data)
    
    return blueprint


def main():
    conn = sqlite3.connect('runcoach.db')
    cursor = conn.cursor()
    
    # Find all plans with list format
    cursor.execute('SELECT id, nutrition_plan_data FROM training_plans WHERE nutrition_plan_data IS NOT NULL')
    
    migrated_count = 0
    skipped_count = 0
    
    for row in cursor.fetchall():
        plan_id, data = row
        parsed = json.loads(data)
        
        if isinstance(parsed, list):
            print(f"Migrating plan {plan_id}...")
            blueprint = migrate_list_to_blueprint(parsed)
            new_data = json.dumps(blueprint)
            
            cursor.execute(
                'UPDATE training_plans SET nutrition_plan_data = ? WHERE id = ?',
                (new_data, plan_id)
            )
            migrated_count += 1
        else:
            skipped_count += 1
    
    conn.commit()
    conn.close()
    
    print(f"\nMigration complete!")
    print(f"Migrated: {migrated_count}")
    print(f"Skipped (already new format): {skipped_count}")


if __name__ == "__main__":
    main()
