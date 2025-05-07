# ScrumMaster AI - Modularized Project Structure

```
scrum_master_ai/
├── __init__.py                     # Package initialization
├── config.py                       # Configuration and environment variables
├── main.py                         # Entry point and bot event handlers
├── services/
│   ├── __init__.py                 # Service package initialization
│   ├── jira_service.py             # JIRA operations and integrations
│   ├── llm_service.py              # LLM operations with OpenAI
│   ├── meeting_service.py          # Meeting transcript processing
│   └── reminder_service.py         # Reminders and notifications
├── models/
│   ├── __init__.py                 # Model package initialization
│   ├── meeting.py                  # Meeting data models
│   ├── sprint.py                   # Sprint data models
│   └── task.py                     # Task and ticket data models
└── utils/
    ├── __init__.py                 # Utility package initialization
    ├── formatters.py               # Text formatting utilities
    └── parsers.py                  # Command parsing utilities
```

## Key Features Implemented

1. **Meeting Transcript Processing**
   - Automatic extraction of action items, ticket updates, and blockers
   - Integration with LLM for natural language understanding
   - Automatic JIRA updates based on meeting discussions

2. **JIRA Integration**
   - Create, update, and manage tickets
   - Track story points and sprint progress
   - Log work time and manage task assignments

3. **Sprint Management**
   - Sprint health monitoring and reporting
   - Team velocity tracking
   - Automated recommendations for sprint improvement

4. **Task Tracking and Reminders**
   - Task assignment and tracking
   - Daily reminders for pending tasks
   - Overdue task notifications

5. **Meeting Memory**
   - Store and retrieve information from past meetings
   - Search for specific topics across meetings
   - Track decisions and their rationales
