"""
ScrumMaster AI Bot Configuration
A bot that automates Scrum processes by leveraging RingCentral, JIRA, and LLMs.
"""

import os
import re
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
JIRA_HOST = os.environ.get('JIRA_HOST', 'https://jira.company.com')
JIRA_PAT = os.environ.get('JIRA_PAT')
JIRA_STORY_POINTS_FIELD = os.environ.get('JIRA_STORY_POINTS_FIELD', 'customfield_10002')

# Initialize module-level dictionaries to store data
meeting_memory = {}
dev_tasks = {}
sprint_data = {}

__name__ = 'localConfig'
__package__ = 'ringcentral_bot_framework'

# Help message function
def helpMsg(botId):
    """Return a help message for the bot."""
    return f'''
    **Hello! I am your ScrumMaster AI Assistant.**

    I can help you with:
    - 📝 Managing JIRA tickets (create, update, assign)
    - 🗣️ Summarizing meeting transcripts
    - ⏱️ Tracking time and story points
    - 🧠 Remembering past discussions
    - 📊 Providing sprint insights
    - 📌 Task reminders and follow-ups

    **Ticket Commands:**
    ```
    ![:Person]({botId}) create-ticket project: KEY, summary: TEXT, [type: TYPE], [priority: PRIORITY], [description: TEXT]
    ![:Person]({botId}) update-ticket KEY, [status: STATUS], [assignee: USER], [story-points: POINTS], [comment: TEXT]
    ![:Person]({botId}) log-time TICKET_KEY hours: HOURS [comment: COMMENT]
    ```

    **Meeting & Memory Commands:**
    ```
    ![:Person]({botId}) daily-summary [sprint: SPRINT_ID]
    ![:Person]({botId}) meeting-memory [topic: TOPIC]
    ![:Person]({botId}) sprint-health [sprint: SPRINT_ID]
    ```

    **Task & Reminder Commands:**
    ```
    ![:Person]({botId}) add-task description: TASK, [due: YYYY-MM-DD], [jira: TICKET_KEY]
    ![:Person]({botId}) update-task TASK_ID status: STATUS
    ![:Person]({botId}) my-tasks
    ![:Person]({botId}) send-reminders
    ```

    I'll also listen to your meetings and help manage your sprint!
    '''

# Bot Lifecycle Events
def botJoinPrivateChatAction(bot, groupId, user, dbAction):
    """This is invoked when the bot is added to a private group."""
    bot.sendMessage(
        groupId,
        {
            'text': helpMsg(bot.id)
        }
    )

def botGotPostAddAction(bot, groupId, creatorId, user, text, dbAction, handledByExtension, event):
    """This is invoked when the user sends a message to the bot."""
    if handledByExtension:
        return

    # Check if the message is directed to the bot
    if f'![:Person]({bot.id})' in text:
        # Extract the command from the message text
        command_match = re.search(r'![:Person]\([^)]+\)\s+(\w+)', text)
        
        if command_match:
            command = command_match.group(1).lower()
            handle_command(bot, groupId, creatorId, command, text, event)
        else:
            # No specific command, show help
            bot.sendMessage(
                groupId,
                {
                    'text': helpMsg(bot.id)
                }
            )

def handle_command(bot, groupId, creatorId, command, text, event):
    """Handle bot commands."""
    # Get attachments if any
    attachments = event.get("body", {}).get("body", {}).get("attachments", []) or []
    
    if command == "help":
        bot.sendMessage(
            groupId,
            {
                'text': helpMsg(bot.id)
            }
        )
    
    elif command == "create-ticket":
        handle_create_ticket(bot, groupId, creatorId, text, attachments)
    
    elif command == "update-ticket":
        handle_update_ticket(bot, groupId, creatorId, text)
    
    elif command == "log-time":
        handle_log_time(bot, groupId, creatorId, text)
    
    elif command == "daily-summary":
        handle_daily_summary(bot, groupId, creatorId, text)
    
    elif command == "meeting-memory":
        handle_meeting_memory(bot, groupId, creatorId, text)
    
    elif command == "sprint-health":
        handle_sprint_health(bot, groupId, creatorId, text)
        
    elif command == "add-task":
        handle_add_task(bot, groupId, creatorId, text)
        
    elif command == "update-task":
        handle_update_task(bot, groupId, creatorId, text)
        
    elif command == "my-tasks":
        handle_my_tasks(bot, groupId, creatorId)
        
    elif command == "send-reminders":
        handle_send_reminders(bot, groupId, creatorId)
    
    else:
        # Unknown command
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), I don't recognize that command. Type `![:Person]({bot.id}) help` for a list of available commands."
            }
        )

# Command handlers
def handle_create_ticket(bot, groupId, creatorId, text, attachments):
    """Handle ticket creation command."""
    from services.jira_service import create_jira_ticket
    
    # Parse the command
    project_match = re.search(r'project\s*:\s*([^,]+)', text, re.IGNORECASE)
    summary_match = re.search(r'summary\s*:\s*([^,]+)', text, re.IGNORECASE)
    type_match = re.search(r'type\s*:\s*([^,]+)', text, re.IGNORECASE)
    priority_match = re.search(r'priority\s*:\s*([^,]+)', text, re.IGNORECASE)
    desc_match = re.search(r'description\s*:\s*([^,]+)', text, re.IGNORECASE)
    os_match = re.search(r'os\s*:\s*([^,]+)', text, re.IGNORECASE)
    
    if not project_match or not summary_match:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), please provide at least the project and summary to create a ticket."
            }
        )
        return
        
    # Extract parameters
    project = project_match.group(1).strip()
    summary = summary_match.group(1).strip()
    issue_type = type_match.group(1).strip() if type_match else "Bug"
    priority = priority_match.group(1).strip() if priority_match else "Normal"
    description = desc_match.group(1).strip() if desc_match else ""
    os = os_match.group(1).strip() if os_match else ""
    
    # Create the ticket
    access_token = bot.token['access_token']
    ticket_id = create_jira_ticket(project, summary, os, creatorId, attachments, access_token, description, issue_type, priority)
    
    if ticket_id:
        jira_url = f"{JIRA_HOST}/browse/{ticket_id}"
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), a JIRA ticket has been created for the issue: \"{summary}\".\n\n"
                        f"**Details:**\n"
                        f"- **Description:** {description}\n"
                        f"- **Issue Type:** {issue_type}\n"
                        f"Ticket ID: \"{ticket_id}\". [View Ticket]({jira_url})"
            }
        )
    else:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), failed to create a JIRA ticket for the issue: \"{summary}\".\n"
                        f"Please try again later."
            }
        )

def handle_update_ticket(bot, groupId, creatorId, text):
    """Handle ticket update command."""
    from services.jira_service import update_jira_ticket
    
    # Parse the command
    ticket_match = re.search(r'update-ticket\s+(\w+-\d+)', text, re.IGNORECASE)
    
    if not ticket_match:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), please provide a valid ticket key to update."
            }
        )
        return
        
    ticket_key = ticket_match.group(1).strip()
    
    # Extract update parameters
    status_match = re.search(r'status\s*:\s*([^,]+)', text, re.IGNORECASE)
    assignee_match = re.search(r'assignee\s*:\s*([^,]+)', text, re.IGNORECASE)
    points_match = re.search(r'story-points\s*:\s*(\d+)', text, re.IGNORECASE)
    comment_match = re.search(r'comment\s*:\s*([^,]+)', text, re.IGNORECASE)
    
    status = status_match.group(1).strip() if status_match else None
    assignee = assignee_match.group(1).strip() if assignee_match else None
    points = int(points_match.group(1)) if points_match else None
    comment = comment_match.group(1).strip() if comment_match else None
    
    # Update the ticket
    success = update_jira_ticket(ticket_key, status, assignee, points, comment)
    
    if success:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), successfully updated ticket {ticket_key}."
            }
        )
    else:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), failed to update ticket {ticket_key}."
            }
        )

def handle_log_time(bot, groupId, creatorId, text):
    """Handle time logging command."""
    from services.jira_service import log_time_to_jira
    
    # Parse the command
    ticket_match = re.search(r'log-time\s+(\w+-\d+)', text, re.IGNORECASE)
    hours_match = re.search(r'hours\s*:\s*(\d+\.?\d*)', text, re.IGNORECASE)
    comment_match = re.search(r'comment\s*:\s*([^,]+)', text, re.IGNORECASE)
    
    if not ticket_match or not hours_match:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), please provide both ticket key and hours to log time."
            }
        )
        return
        
    ticket_key = ticket_match.group(1).strip()
    hours = float(hours_match.group(1))
    comment = comment_match.group(1).strip() if comment_match else f"Time logged by {user.get('name', 'user')} via ScrumMaster AI"
    
    # Log time to JIRA
    success = log_time_to_jira(ticket_key, hours, comment, creatorId)
    
    if success:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), successfully logged {hours} hours to ticket {ticket_key}."
            }
        )
    else:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), failed to log time to ticket {ticket_key}."
            }
        )

def handle_daily_summary(bot, groupId, creatorId, text):
    """Handle daily summary command."""
    from services.meeting_service import generate_daily_summary
    
    # Parse sprint ID if provided
    sprint_match = re.search(r'sprint\s*:\s*(\d+)', text, re.IGNORECASE)
    sprint_id = sprint_match.group(1) if sprint_match else None
    
    # Generate the summary
    summary = generate_daily_summary(sprint_id)
    
    bot.sendMessage(
        groupId,
        {
            'text': summary
        }
    )

def handle_meeting_memory(bot, groupId, creatorId, text):
    """Handle meeting memory search command."""
    from services.meeting_service import search_meeting_memory
    
    # Parse topic if provided
    topic_match = re.search(r'topic\s*:\s*([^,]+)', text, re.IGNORECASE)
    topic = topic_match.group(1).strip() if topic_match else None
    
    # Search meeting memory
    results = search_meeting_memory(topic)
    
    bot.sendMessage(
        groupId,
        {
            'text': results
        }
    )

def handle_sprint_health(bot, groupId, creatorId, text):
    """Handle sprint health command."""
    from services.jira_service import get_sprint_health
    
    # Parse sprint ID if provided
    sprint_match = re.search(r'sprint\s*:\s*(\d+)', text, re.IGNORECASE)
    sprint_id = sprint_match.group(1) if sprint_match else None
    
    # Get sprint health metrics
    health_metrics = get_sprint_health(sprint_id)
    
    if "error" in health_metrics:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), error retrieving sprint health: {health_metrics['error']}"
            }
        )
    else:
        health_text = f"""
        **Sprint Health: {health_metrics['sprint_name']}**
        
        **Progress:** {health_metrics['completion_percentage']}% completed
        **Status:** {health_metrics['health_status']}
        **Time:** {health_metrics['days_elapsed']} days elapsed, {health_metrics['days_remaining']} days remaining
        
        **Stories:** {health_metrics['completed_issues']}/{health_metrics['total_issues']} completed
        **Points:** {health_metrics['completed_points']}/{health_metrics['total_points']} points completed
        
        **Burndown Analysis:**
        Ideal progress at this point: {health_metrics['ideal_completion_percentage']}%
        Actual progress: {health_metrics['actual_completion_percentage']}%
        """
        
        bot.sendMessage(
            groupId,
            {
                'text': health_text
            }
        )

def handle_add_task(bot, groupId, creatorId, text):
    """Handle adding a task for a developer."""
    from services.reminder_service import track_developer_task
    
    # Parse the task description
    desc_match = re.search(r'description\s*:\s*([^,]+)', text, re.IGNORECASE)
    due_match = re.search(r'due\s*:\s*(\d{4}-\d{2}-\d{2})', text, re.IGNORECASE)
    jira_match = re.search(r'jira\s*:\s*(\w+-\d+)', text, re.IGNORECASE)
    
    if not desc_match:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), please provide a task description."
            }
        )
        return
    
    # Extract parameters
    description = desc_match.group(1).strip()
    jira_ticket = jira_match.group(1).strip() if jira_match else None
    
    # Parse due date if provided
    due_date = None
    if due_match:
        due_date_str = due_match.group(1).strip()
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
        except ValueError:
            bot.sendMessage(
                groupId,
                {
                    'text': f"![:Person]({creatorId}), invalid date format. Please use YYYY-MM-DD."
                }
            )
            return
    
    # Track the task
    task_id = track_developer_task(creatorId, description, jira_ticket, due_date)
    
    if task_id:
        due_text = f", due on {due_date.strftime('%Y-%m-%d')}" if due_date else ""
        jira_text = f", linked to JIRA ticket {jira_ticket}" if jira_ticket else ""
        
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), I've added your task: \"{description}\"{due_text}{jira_text}.\n\n"
                        f"Task ID: {task_id}. You can update it later with `![:Person]({bot.id}) update-task {task_id} status: completed`"
            }
        )
    else:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), failed to add your task. Please try again."
            }
        )

def handle_update_task(bot, groupId, creatorId, text):
    """Handle updating a task status."""
    from services.reminder_service import update_task_status
    
    # Parse the command
    task_match = re.search(r'update-task\s+(\S+)', text, re.IGNORECASE)
    status_match = re.search(r'status\s*:\s*([^,]+)', text, re.IGNORECASE)
    
    if not task_match or not status_match:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), please provide both task ID and status.\n"
                        f"Example: `![:Person]({bot.id}) update-task task-123 status: completed`"
            }
        )
        return
    
    # Extract parameters
    task_id = task_match.group(1).strip()
    status = status_match.group(1).strip()
    
    # Update the task
    success = update_task_status(task_id, status)
    
    if success:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), task {task_id} has been updated to status: {status}."
            }
        )
    else:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), failed to update task {task_id}. Task not found."
            }
        )

def handle_my_tasks(bot, groupId, creatorId):
    """Handle showing a developer's tasks."""
    from services.reminder_service import get_developer_tasks
    
    # Get all tasks for the developer
    tasks = get_developer_tasks(creatorId)
    
    if not tasks:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), you don't have any tasks assigned yet."
            }
        )
        return
    
    # Count tasks by status
    pending_count = sum(1 for t in tasks if t.get("status") == "pending")
    completed_count = sum(1 for t in tasks if t.get("status") == "completed")
    
    # Format the response
    message = f"**Your Tasks ({len(tasks)} total)**\n\n"
    message += f"**Status Summary:** {pending_count} pending, {completed_count} completed\n\n"
    
    # Show pending tasks first
    if pending_count > 0:
        message += "**Pending Tasks:**\n"
        for task in tasks:
            if task.get("status") == "pending":
                created = datetime.fromisoformat(task["created_at"]).strftime("%Y-%m-%d")
                
                due_text = ""
                if task.get("due_date"):
                    due_date = datetime.fromisoformat(task["due_date"])
                    now = datetime.now()
                    
                    if due_date < now:
                        days_overdue = (now - due_date).days
                        due_text = f" (OVERDUE by {days_overdue} days)"
                    else:
                        days_left = (due_date - now).days
                        due_text = f" (Due in {days_left} days)"
                
                jira_text = f" [JIRA: {task['jira_ticket']}]" if task.get("jira_ticket") else ""
                
                message += f"- {task['description']}{due_text}{jira_text} (ID: {task['task_id']})\n"
        
        message += "\n"
    
    # Show a few completed tasks (limit to 5 to avoid long messages)
    completed_tasks = [t for t in tasks if t.get("status") == "completed"]
    if completed_tasks:
        message += "**Recently Completed Tasks:**\n"
        for task in completed_tasks[:5]:  # Show only the last 5 completed tasks
            message += f"- {task['description']} (ID: {task['task_id']})\n"
        
        if len(completed_tasks) > 5:
            message += f"... and {len(completed_tasks) - 5} more completed tasks\n"
    
    bot.sendMessage(
        groupId,
        {
            'text': message
        }
    )

def handle_send_reminders(bot, groupId, creatorId):
    """Handle sending reminders to team members."""
    from services.reminder_service import send_daily_reminders
    
    # Only allow admins to trigger reminders
    # In a real implementation, you would check if the user has admin privileges
    # For now, let's assume any user can trigger reminders for demo purposes
    
    # Send reminders
    results = send_daily_reminders(bot)
    
    bot.sendMessage(
        groupId,
        {
            'text': f"![:Person]({creatorId}), sent reminders to {results['reminders_sent']} team members."
        }
    )

def process_meeting_transcript(transcript, bot, groupId, creatorId):
    """Process a meeting transcript and extract actionable information."""
    from services.meeting_service import analyze_transcript, apply_meeting_actions
    
    # Analyze the transcript
    meeting_data = analyze_transcript(transcript)
    
    if meeting_data:
        # Apply actions extracted from the meeting
        action_results = apply_meeting_actions(meeting_data)
        
        # Format and send the summary
        summary_text = format_meeting_summary(meeting_data)
        bot.sendMessage(groupId, {'text': summary_text})
        
        # Report on actions taken
        actions_text = "\n\n**Actions Taken:**\n"
        actions_text += f"- Updated {len(action_results['ticket_updates'])} tickets\n"
        actions_text += f"- Added {len(action_results['blockers_added'])} blockers\n"
        actions_text += f"- Updated {len(action_results['story_points_updated'])} story point estimates\n"
        
        bot.sendMessage(groupId, {'text': actions_text})
        
        # Store the meeting data for future reference
        meeting_id = str(datetime.now().strftime("%Y%m%d%H%M%S"))
        meeting_memory[meeting_id] = {
            "transcript": transcript,
            "summary": meeting_data,
            "timestamp": datetime.now().isoformat()
        }
        
        return True
    else:
        bot.sendMessage(
            groupId,
            {
                'text': f"![:Person]({creatorId}), I couldn't extract useful information from the transcript."
            }
        )
        return False

def format_meeting_summary(data):
    """Format meeting data into a readable summary."""
    summary = "**Meeting Summary**\n\n"
    
    if data.get("action_items"):
        summary += "**Action Items:**\n"
        for item in data["action_items"]:
            summary += f"- {item['task']} → {item['assignee']}\n"
        summary += "\n"
        
    if data.get("ticket_updates"):
        summary += "**Ticket Updates:**\n"
        for update in data["ticket_updates"]:
            summary += f"- {update['ticket_key']}: {update.get('status', 'discussed')} {update.get('comment', '')}\n"
        summary += "\n"
        
    if data.get("story_points"):
        summary += "**Story Points:**\n"
        for sp in data["story_points"]:
            summary += f"- {sp['ticket_key']}: {sp['points']} points\n"
        summary += "\n"
        
    if data.get("blockers"):
        summary += "**Blockers:**\n"
        for blocker in data["blockers"]:
            summary += f"- {blocker['for_ticket']}: {blocker['description']} (mentioned by {blocker['mentioned_by']})\n"
        summary += "\n"
        
    if data.get("decisions"):
        summary += "**Decisions Made:**\n"
        for decision in data["decisions"]:
            summary += f"- {decision['topic']}: {decision['decision']}\n"
            
    return summary