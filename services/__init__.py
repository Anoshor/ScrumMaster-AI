"""
Service modules for the ScrumMaster AI bot.
"""

# Import all services for easier access
from services.jira_service import (
    # Jira service functions
    get_auth_headers,
    create_jira_ticket,
    get_issue,
    update_jira_ticket,
    get_transitions,
    transition_issue,
    assign_issue,
    add_comment,
    log_time_to_jira,
    get_boards,
    get_sprints,
    get_sprint,
    get_sprint_issues,
    get_sprint_health
)

from services.meeting_service import (
    # Meeting service functions
    analyze_transcript,
    apply_meeting_actions,
    search_meeting_memory,
    generate_daily_summary,
    get_meeting_history_for_ticket,
    extract_action_items_from_text,
    parse_transcript_file,
    process_transcript_content,
    get_recent_meetings
)

from services.reminder_service import (
    # Reminder service functions
    track_developer_task,
    update_task_status,
    get_developer_tasks,
    get_pending_tasks,
    get_overdue_tasks,
    send_daily_reminders,
    format_reminder_message,
    sync_tasks_with_jira,
    check_inactive_tickets,
    send_overdue_reminders
)