# RunCoach Agent Guidelines

## Development Commands
- Start server: `python3 -m uvicorn app.main:app --reload --port 8000`
- Install dependencies: `python3 -m pip install -r requirements.txt`
- Test PDF generation: `python3 -c "from app.core.pdf_generator import PDFGenerator; from app.core.plan_generator import TrainingPlanGenerator; TrainingPlanGenerator().generate_plan(20, 10, 8)"`
- Run database migrations: `python3 migrate_add_workout_links.py`

## Code Style Guidelines
- **Imports**: Group standard library, third-party, then local imports. Use relative imports for local modules.
- **Formatting**: Follow PEP 8, use descriptive variable names, max line length 88 characters.
- **Types**: Use type hints for all function parameters and return values (`List[Dict[str, Any]]`).
- **Naming**: Use snake_case for variables/functions, PascalCase for classes, UPPER_CASE for constants.
- **Error Handling**: Use specific HTTP status codes, wrap database operations in try/finally, validate with Pydantic models.
- **Documentation**: Add docstrings for all public methods explaining purpose, parameters, and return values.
- **Database**: Always close sessions with `finally: db.close()`, use context managers for resources.

## Adaptive Plans System
- **Performance Analysis**: Uses `app/services/adaptation_service.py` to analyze logged runs
- **Adaptation Logic**: Automatically adjusts future weeks based on effort, adherence, and trends
- **Minimum Data**: Requires 3+ logged runs before adapting plans
- **Thresholds**: Effort >9 = reduce load, <3 = increase load, adherence <60% = too aggressive
- **UI Integration**: Plan view shows performance analysis, completed workout indicators, and adaptation options