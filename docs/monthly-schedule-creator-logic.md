# Automated Task System: Schedule Creator & Requirement Archiver

This document explains the automated task system that manages program requirements and schedules for the SIT Cert application.

## Overview

The SIT Cert includes two automated tasks that manage the lifecycle of program requirements:

1. **Monthly Schedule Creator** (`app/tasks/monthly_schedule_creator.py`)
   - Runs on the 1st of every month at midnight Bangkok time
   - Creates program requirement schedules for student cohorts
   - Handles complex academic year calculations and timing logic

2. **Annual Requirement Archiver** (`app/tasks/annual_requirement_archiver.py`)
   - Runs on the second Monday of August every year at 2:00 AM Bangkok time
   - Archives expired program requirements automatically
   - Maintains data integrity by deactivating outdated requirements

## Core Concepts

### Academic Year System
- **Academic Year runs August to May**: Aug 2024 - May 2025 = Academic Year 2024
- **Current Academic Year Calculation**: 
  - If current month ≥ August: Academic Year = current year
  - If current month < August: Academic Year = current year - 1
  - Examples:
    - January 2025 → Academic Year 2024
    - August 2024 → Academic Year 2024  
    - July 2024 → Academic Year 2023

### Student Cohort vs Deadline Year
The system distinguishes between when students started (cohort year) and when they need to submit (deadline year):

- **Student Cohort Year**: When students started their program
  - Formula: `current_academic_year - target_year + 1`
  - Example: Current year 2024, target year 4 → Student cohort 2021 (seniors who started in 2021)

- **Deadline Academic Year**: When the deadline actually occurs  
  - Formula: `student_cohort_year + target_year - 1`
  - Example: Cohort 2021, target year 4 → Deadline year 2024 (they submit in their 4th year)

### Database Storage Logic
- **`academic_year_id`**: Points to student cohort year (when they started)
- **Deadline calculations**: Use deadline academic year (when they submit)
- **`last_recurrence_at`**: Stores August 1st of student cohort year for graceful handling of deadline changes

## Task Workflow

### 1. Initialization
```python
current_datetime = datetime.now()
current_academic_year = _calculate_current_academic_year(current_datetime)
```

### 2. Data Loading
- Fetch all active program requirements with `months_before_deadline` set
- Load existing academic years for efficient lookups
- Get existing schedules to prevent duplicates

### 3. Requirement Processing Loop

For each program requirement, the task:

#### A. Calculate Student Cohort Year
```python
student_cohort_year = current_academic_year - requirement.target_year + 1
```

**Example**: Current academic year 2024, target year 4 (seniors)
→ Student cohort year = 2024 - 4 + 1 = 2021

#### B. Check Requirement Effectiveness
Verify the requirement applies to this cohort using `effective_from_year` and `effective_until_year`.

#### C. Deduplication Checks
1. **Database Schedule Check**: Query existing schedules for (requirement_id, student_cohort_year)
2. **Recurrence Check**: Compare `last_recurrence_at.year` with `student_cohort_year`

#### D. Calculate Deadline Academic Year
```python
deadline_academic_year = student_cohort_year + requirement.target_year - 1
```

**Example**: Student cohort 2021, target year 4
→ Deadline academic year = 2021 + 4 - 1 = 2024

#### E. Schedule Creation Timing
```python
schedule_creation_date = deadline_datetime - relativedelta(months=requirement.months_before_deadline)
```

Only create schedules if creation date is within the next 30 days.

#### F. Timezone Handling
All deadline calculations use Bangkok timezone for business logic, then convert to UTC for database storage:

```python
deadline_bangkok = datetime(
    year=deadline_academic_year,
    month=deadline_month,
    day=deadline_day,
    hour=23, minute=59, second=59,
    tzinfo=BANGKOK_TZ,
)
deadline_utc = deadline_bangkok.astimezone(timezone.utc)
```

### 4. Batch Schedule Creation
- Create all schedules in a single database transaction
- Update `last_recurrence_at` timestamps to August 1st of student cohort year
- Use academic year for student cohort (not deadline year)

## Complex Examples

### Example 1: Senior CITI Requirement

**Requirement Setup**:
- Program: CS-BACHELOR
- Certificate: CITI
- Target Year: 4 (seniors)
- Deadline: March 15 (date(2000, 3, 15))
- Months Before Deadline: 6

**Current Date**: January 1, 2025 (Academic Year 2024)

**Calculations**:
1. Student cohort year = 2024 - 4 + 1 = **2021** (seniors who started in 2021)
2. Deadline academic year = 2021 + 4 - 1 = **2024** (they submit in 2024)
3. Actual deadline = **March 15, 2024** 23:59:59 Bangkok → UTC
4. Schedule creation date = March 15, 2024 - 6 months = **September 15, 2023**
5. Days until creation = (Sept 15, 2023 - Jan 1, 2025) = **negative** → Skip (too late)

### Example 2: Freshman Ethics Requirement

**Current Date**: December 1, 2024 (Academic Year 2024)

**Requirement Setup**:
- Target Year: 1 (freshmen)
- Deadline: April 30 (date(2000, 4, 30))
- Months Before Deadline: 3

**Calculations**:
1. Student cohort year = 2024 - 1 + 1 = **2024** (current freshmen)
2. Deadline academic year = 2024 + 1 - 1 = **2024** (they submit in their first year)
3. Actual deadline = **April 30, 2025** 23:59:59 Bangkok → UTC  
4. Schedule creation date = April 30, 2025 - 3 months = **January 30, 2025**
5. Days until creation = (Jan 30, 2025 - Dec 1, 2024) = **60 days** → Skip (> 30 days)

### Example 3: Sophomore Lab Safety (Within Window)

**Current Date**: October 15, 2024 (Academic Year 2024)

**Requirement Setup**:
- Target Year: 2 (sophomores)  
- Deadline: December 1 (date(2000, 12, 1))
- Months Before Deadline: 2

**Calculations**:
1. Student cohort year = 2024 - 2 + 1 = **2023** (sophomores who started in 2023)
2. Deadline academic year = 2023 + 2 - 1 = **2024** (they submit in their sophomore year)
3. Actual deadline = **December 1, 2024** 23:59:59 Bangkok → UTC
4. Schedule creation date = December 1, 2024 - 2 months = **October 1, 2024**
5. Days until creation = (Oct 1, 2024 - Oct 15, 2024) = **-14 days** → **CREATE** (within 0-30 day window)

## Key Design Decisions

### 1. Why Store Student Cohort Year in `academic_year_id`?
- Represents when students started their program
- Stable identifier that doesn't change when deadline years shift
- Enables proper deduplication by student cohort

### 2. Why Use August 1st for `last_recurrence_at`?
- Academic years start in August
- Consistent timestamp regardless of actual deadline month/day
- Allows year-only comparison to handle deadline date changes gracefully
- Example: If deadline changes from March 15 to April 15, existing cohorts aren't affected

### 3. Why 30-Day Creation Window?
- Balances advance planning with resource efficiency  
- Prevents creating schedules too far in advance
- Allows monthly cron job to catch most timing requirements
- Monthly frequency means some schedules might be created 0-59 days early

### 4. Bangkok Timezone for Business Logic
- Business operates in Bangkok timezone
- Deadlines are meaningful in local business time
- Database stores UTC for system consistency
- All calculations convert Bangkok → UTC before storage

## Error Handling and Edge Cases

### 1. Leap Year Handling
The system properly handles February 29 deadlines:
- Leap years: Works normally
- Non-leap years: Python raises ValueError (expected behavior)

### 2. Individual Requirement Failures
- Individual requirement processing errors don't fail the entire task
- Errors are logged with full context
- Task continues processing other requirements

### 3. Database Transaction Safety
- All schedule creation happens in a single transaction
- Rollback on errors prevents partial state
- Retry logic with exponential backoff for transient failures

### 4. Academic Year Auto-Creation
- Automatically creates missing academic year records
- Uses Bangkok timezone for start/end dates, converts to UTC
- Updates in-memory cache for subsequent lookups

## Performance Considerations

### 1. Efficient Database Queries
- Single query for all active requirements with eager loading
- Batch loading of academic years and existing schedules
- Minimal database round trips

### 2. Deduplication Strategy
- In-memory set for existing schedule lookups: O(1)
- Database unique constraints as final safety net
- `last_recurrence_at` check prevents unnecessary processing

### 3. Batch Operations
- Create all schedules in single transaction
- Update all `last_recurrence_at` timestamps together
- Minimize database commits

## Monitoring and Observability

### 1. Structured Logging
- Request ID tracking throughout execution
- Detailed context for each decision point
- Performance metrics (processed/created/skipped counts)

### 2. Return Values
```python
{
    "success": True,
    "processed_count": 15,
    "created_count": 3,
    "skipped_count": 12,
    "current_academic_year": 2024,
    "request_id": "req_123"
}
```

### 3. Error Context
- Full requirement details in error logs
- Exception information with stack traces
- Graceful degradation for individual failures

## Testing Considerations

The comprehensive test suite covers:

1. **Academic Year Calculations**: Boundary conditions, leap years
2. **Database Operations**: Active requirement queries, deduplication
3. **Business Logic**: Effectiveness checks, recurrence logic
4. **Date Calculations**: Timezone handling, deadline computations
5. **Integration Tests**: Full task execution scenarios
6. **Error Handling**: Retry behavior, individual failures
7. **Edge Cases**: Leap years, timezone boundaries, timing windows

---

# Annual Requirement Archiver Task

The Annual Requirement Archiver automatically maintains data integrity by deactivating program requirements that are no longer applicable to new student cohorts.

## Purpose

As academic programs evolve, certain requirements become outdated and should no longer apply to new students. Rather than manually tracking and deactivating these requirements, the archiver task automates this process by:

1. Identifying requirements where `effective_until_year < current_academic_year`
2. Setting `is_active = False` for these expired requirements
3. Preserving historical data while preventing future use

## Task Schedule

```python
# Celery beat schedule - runs on second Monday of August at 2:00 AM Bangkok time
"annual-requirement-archiver": {
    "task": "app.tasks.annual_requirement_archiver.annual_requirement_archiver_task",
    "schedule": crontab(hour=2, minute=0, day_of_week=1, month_of_year=8, day_of_month="8-14"),
    "args": ("annual_requirement_archiver_cron",),
    "options": {"queue": "schedules"},
}
```

**Why Second Monday of August?**
- August marks the start of new academic years
- Perfect timing to clean up expired requirements before new year processing
- Second Monday ensures it's always within the month (8th-14th guarantees second Monday)
- 2:00 AM provides minimal system load impact

## Archiving Logic

### 1. Academic Year Calculation
Uses the same logic as the schedule creator:
```python
def _calculate_current_academic_year(current_datetime: datetime) -> int:
    if current_datetime.month >= 8:  # August or later
        return current_datetime.year
    else:  # Before August
        return current_datetime.year - 1
```

### 2. Expired Requirement Detection
```python
# SQL query to find expired requirements
select(ProgramRequirement)
.where(
    and_(
        ProgramRequirement.is_active == True,  # Only active requirements
        ProgramRequirement.effective_until_year.isnot(None),  # Must have end date
        ProgramRequirement.effective_until_year < current_academic_year,  # Expired
    )
)
```

### 3. Batch Archiving
```python
# Efficient batch update
update(ProgramRequirement)
.where(ProgramRequirement.id.in_(requirement_ids))
.values(is_active=False)
```

## Example Scenarios

### Scenario 1: CITI Requirement Update
**Background**: Faculty decides CITI requirements change format in 2025

**Setup**:
- Old CITI requirement: `effective_from_year=2020, effective_until_year=2024`
- New CITI requirement: `effective_from_year=2025, effective_until_year=None`

**August 2025 Archiver Run**:
- Current academic year: 2025
- Old requirement: `effective_until_year (2024) < current_year (2025)` → **ARCHIVED**
- New requirement: Still active, continues creating schedules

### Scenario 2: Program Discontinuation
**Background**: Lab Safety requirement discontinued for new students

**Setup**:
- Lab Safety requirement: `effective_from_year=2018, effective_until_year=2023`

**August 2024 Archiver Run**:
- Current academic year: 2024  
- Lab Safety: `effective_until_year (2023) < current_year (2024)` → **ARCHIVED**
- Existing schedules for older cohorts remain unaffected

### Scenario 3: Gradual Phase-out
**Background**: Ethics certification transitioning to new provider

**Timeline**:
- 2022: Old ethics requirement set `effective_until_year=2025`
- 2023: New ethics requirement created with `effective_from_year=2026`
- 2024-2025: Both requirements active (transition period)
- August 2026: Archiver automatically deactivates old requirement

## Data Integrity Benefits

### 1. Prevents Future Confusion
- New staff won't accidentally create schedules for outdated requirements
- System automatically maintains requirement currency
- Clear separation between historical and current requirements

### 2. Preserves Historical Data
- Archived requirements remain in database (`is_active = False`)
- Existing schedules and submissions remain linked
- Full audit trail maintained for compliance

### 3. Reduces Manual Maintenance
- No need for annual manual requirement review
- Automated cleanup reduces human error
- Consistent application of archiving rules

## Monitoring and Observability

### Task Results
```python
{
    "success": True,
    "archived_count": 3,  # Number of requirements archived
    "current_academic_year": 2024,
    "request_id": "annual_requirement_archiver_cron"
}
```

### Logging Context
- Detailed logs for each archived requirement
- Academic year calculations
- Error handling with full context
- Performance metrics

## Error Handling

### 1. Database Errors
- Automatic retry with exponential backoff
- Rollback on transaction failures
- Graceful degradation for transient issues

### 2. Edge Cases
- Handles requirements with `effective_until_year = NULL` (never expires)
- Ignores already inactive requirements
- Proper boundary condition handling (`until_year = current_year` is still valid)

## Integration with Schedule Creator

The archiver works in harmony with the monthly schedule creator:

1. **Archiver runs first** (August 2nd Monday) → Clean up expired requirements
2. **Schedule creator runs monthly** → Only processes active requirements
3. **No conflicts** → Archived requirements automatically excluded from future processing

---

# Future Enhancements

### 1. Multiple Timezone Support
- Support institutions in different timezones
- Timezone-aware requirement definitions
- Per-program timezone configuration

### 2. Custom Creation Windows
- Per-requirement creation timing windows
- Flexible scheduling based on requirement complexity
- Different timing patterns (quarterly, semester-based)

### 3. Advanced Recurrence Patterns
- Semester-based requirements
- One-time requirements with expiration
- Conditional requirements based on student status

### 4. Performance Optimizations
- Incremental processing for large datasets
- Parallel processing for independent requirements
- Caching strategies for frequently accessed data

### 5. Enhanced Archiving Features
- Soft delete with restore capability
- Archiving notifications to administrators
- Advanced archiving rules (grace periods, manual overrides)
- Integration with requirement change management workflows