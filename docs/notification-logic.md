# Notification System Flow

Async notification system for SIT Cert using Celery tasks and template-based messaging.

## Overview

The notification system follows this flow:
1. **Trigger** → Create notification request
2. **Create** → Store notification in database  
3. **Process** → Check expiry and dispatch to channels
4. **Deliver** → Send via in-app or LINE

## Architecture

```
Entry Point (utils.py)
    ↓
notification_creation.py (Celery Task)
    ↓
notification_processing.py (Celery Task)
    ↓
line_notification_sender.py (Celery Task)
```

### Files Structure

```
notifications/
├── utils.py              # Entry point - create_notification_sync()
├── base.py               # Base service class
├── certificate_service.py # Certificate notification logic
├── schedule_service.py    # Schedule notification logic
├── registry.py           # Service factory
└── user_notifications.py # User-facing notifications

tasks/
├── notification_creation.py         # Step 1: Create notification
├── notification_processing.py       # Step 2: Process and dispatch
├── line_notification_sender.py      # Step 3: LINE delivery
├── daily_scheduled_processor.py     # Daily: Process scheduled notifications
└── daily_notification_expiration.py # Daily: Mark expired notifications
```

## Notification Flow

### 1. Entry Point (utils.py)

```python
from app.services.notifications.utils import create_notification_sync

# Trigger async notification
task_id = create_notification_sync(
    request_id="req-123",
    notification_code="certificate_submission_submit",
    entity_id=submission_id,
    actor_type="user", 
    recipient_ids=[user_id],
    verifier_name="Dr. Smith"  # Custom metadata
)
```

### 2. Creation Task (notification_creation.py)

**Purpose**: Creates notification record in database
- Converts strings back to UUIDs
- Uses service registry to find correct handler
- Calls service.create() to store notification
- Triggers processing task if not scheduled

### 3. Processing Task (notification_processing.py)

**Purpose**: Processes notification and dispatches to channels
- Checks if notification expired
- For each recipient:
  - In-app: Mark as delivered immediately
  - LINE: Create LINE delivery task

### 4. LINE Delivery Task (line_notification_sender.py)

**Purpose**: Sends LINE messages
- Gets notification + recipient in single query
- Uses service to format message
- Validates recipient has LINE configured
- Calls mock LINE API (95% success rate)

## Scheduled Tasks

### 5. Daily Scheduled Processor (daily_scheduled_processor.py)

**Purpose**: Process notifications scheduled for current day
- **Schedule**: Runs daily at 9:00 AM Bangkok time
- **Query**: Finds notifications with `scheduled_for` = today
- **Filter**: Only PENDING recipients, not expired
- **Action**: Triggers `process_notification_task` for each notification
- **Retry**: 3 attempts with exponential backoff (max 5 min delay)

### 6. Daily Notification Expiration (daily_notification_expiration.py)

**Purpose**: Mark expired notifications as EXPIRED
- **Schedule**: Runs daily at 00:05 AM Bangkok time  
- **Query**: Finds notifications with `expires_at` <= current datetime
- **Action**: Updates PENDING recipients to EXPIRED status directly
- **Commit**: Batch database update for efficiency
- **Retry**: 3 attempts with exponential backoff (max 5 min delay)

## Notification Types

### Certificate Submissions
- `certificate_submission_submit` - Student uploads certificate
- `certificate_submission_verify` - Staff approves submission  
- `certificate_submission_reject` - Staff rejects submission

### Program Requirements
- `program_requirement_warn` - Approaching deadline
- `program_requirement_overdue` - Deadline passed

## Template System

Templates are stored in database with placeholders:

**Template Example:**
```
Subject: {certificate_name} {status}
Body: Dear {student_name}, your {certificate_name} has been {status}.
```

**Data Sources:**
1. Entity data (from certificate_service.py)
2. Custom metadata (passed in create_notification_sync)
3. Default values

## Performance Optimizations

### Database Queries
- Single join query for notification + recipient
- Proper async session management  
- Optimized imports at module level

### Task Improvements
- Native async tasks (no asyncio.run())
- Capped exponential backoff
- Proper error handling

### Retry Policies
- Creation: 3 retries, max 5 min delay
- Processing: 3 retries, max 5 min delay
- LINE delivery: 5 retries, max 10 min delay
- Scheduled processor: 3 retries, max 5 min delay
- Expiration task: 3 retries, max 5 min delay

## Usage Examples

### Basic Usage
```python
from app.services.notifications.utils import create_notification_sync

# Simple notification
task_id = create_notification_sync(
    request_id="req-123",
    notification_code="certificate_submission_submit",
    entity_id=submission_id,
    actor_type="user",
    recipient_ids=[student_id]
)
```

### With Custom Metadata
```python
# Notification with custom data for templates
task_id = create_notification_sync(
    request_id="req-456", 
    notification_code="certificate_submission_verify",
    entity_id=submission_id,
    actor_type="staff",
    recipient_ids=[student_id],
    verifier_name="Prof. Jane Smith",
    comments="Excellent work",
    in_app_enabled=True,
    line_app_enabled=True
)
```

### Scheduled Notifications
```python
from datetime import datetime, timedelta

# Schedule for later
future_time = datetime.now() + timedelta(hours=2)
task_id = create_notification_sync(
    request_id="req-789",
    notification_code="program_requirement_warn", 
    entity_id=schedule_id,
    actor_type="system",
    recipient_ids=student_ids,
    scheduled_for=future_time
)
```

## Adding New Notification Types

### 1. Database Setup
```sql
-- Add notification type
INSERT INTO notification_types (code, name, description, entity_type) 
VALUES ('new_type', 'New Type', 'Description', 'entity_name');

-- Add template
INSERT INTO notification_channel_templates (notification_type_id, channel_type, template_subject, template_body)
VALUES (
    (SELECT id FROM notification_types WHERE code = 'new_type'),
    'in_app',
    'Subject: {placeholder}',
    'Body: {placeholder} content'
);
```

### 2. Create Service
```python
# new_service.py
from .base import BaseNotificationService

class NewNotificationService(BaseNotificationService):
    async def get_notification_data(self, entity_id, notification_id=None):
        # Fetch entity data
        entity = await self.get_entity(entity_id)
        
        # Get metadata if notification exists
        metadata = await self.get_notification_metadata(notification_id)
        
        return {
            "placeholder": entity.field,
            **metadata  # Custom data overrides defaults
        }

def create_new_service(db_session, notification_code):
    return NewNotificationService(db_session, notification_code)
```

### 3. Register Service
```python
# registry.py
from .new_service import create_new_service

_factories = {
    # ... existing
    "new_type": create_new_service,
}
```

## Troubleshooting

### Common Issues

**"No service found for notification code"**
- Check spelling of notification_code
- Verify code exists in registry._factories
- Ensure database has notification_types record

**"Template formatting error"** 
- Check template placeholders match service data
- Use logger.debug() to see notification_data

**"Task retries exhausted"**
- Check database connectivity
- Monitor Celery worker logs
- Verify async session management

**"Session leak warnings"**
- Ensure proper async context managers
- Check finally blocks close sessions