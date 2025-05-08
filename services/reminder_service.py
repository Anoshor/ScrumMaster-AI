"""
Service for sending reminders and notifications to team members.
"""

import logging
from datetime import datetime, timedelta
from config import dev_tasks, JIRA_HOST
from services.jira_service import update_jira_ticket, get_issue

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def track_developer_task(developer_id, task_description, jira_ticket=None, due_date=None):
    """Add a task for a developer to track."""
    if developer_id not in dev_tasks:
        dev_tasks[developer_id] = []
    
    # Create a unique task ID
    task_id = f"task-{len(dev_tasks[developer_id]) + 1}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # Add the task
    task = {
        "task_id": task_id,
        "description": task_description,
        "jira_ticket": jira_ticket,
        "created_at": datetime.now().isoformat(),
        "due_date": due_date.isoformat() if due_date else None,
        "status": "pending",
        "reminder_sent": False,
        "last_reminder": None
    }
    
    # If this is a JIRA ticket, get more details
    if jira_ticket:
        try:
            issue = get_issue(jira_ticket)
            if issue:
                fields = issue.get("fields", {})
                task["jira_summary"] = fields.get("summary", "")
                task["jira_status"] = fields.get("status", {}).get("name", "")
                task["jira_assignee"] = fields.get("assignee", {}).get("displayName", "")
                task["jira_url"] = f"{JIRA_HOST}/browse/{jira_ticket}"
        except Exception as e:
            logger.error(f"Error getting JIRA ticket details for {jira_ticket}: {str(e)}")
    
    dev_tasks[developer_id].append(task)
    
    logger.info(f"Task {task_id} added for developer {developer_id}")
    return task_id

def update_task_status(task_id, status):
    """Update the status of a task."""
    for developer_id, tasks in dev_tasks.items():
        for i, task in enumerate(tasks):
            if task.get("task_id") == task_id:
                old_status = task.get("status")
                dev_tasks[developer_id][i]["status"] = status
                dev_tasks[developer_id][i]["updated_at"] = datetime.now().isoformat()
                logger.info(f"Task {task_id} status updated from {old_status} to {status}")
                
                # If task is linked to a JIRA ticket and status is completed, update JIRA
                if (status.lower() in ("done", "completed", "finished") and 
                    task.get("jira_ticket") and 
                    old_status.lower() != status.lower()):
                    try:
                        # Map task status to JIRA status
                        jira_status = "Done"  # Default mapping
                        if status.lower() == "in progress":
                            jira_status = "In Progress"
                        elif status.lower() in ("todo", "to do", "new"):
                            jira_status = "To Do"
                        
                        # Update the JIRA ticket
                        update_result = update_jira_ticket(
                            ticket_key=task["jira_ticket"],
                            status=jira_status,
                            comment=f"Task status updated to {status} via ScrumMaster AI"
                        )
                        
                        if update_result:
                            logger.info(f"JIRA ticket {task['jira_ticket']} updated to {jira_status}")
                            
                            # Update the task with the latest JIRA status
                            issue = get_issue(task["jira_ticket"])
                            if issue:
                                fields = issue.get("fields", {})
                                dev_tasks[developer_id][i]["jira_status"] = fields.get("status", {}).get("name", "")
                        else:
                            logger.error(f"Failed to update JIRA ticket {task['jira_ticket']}")
                    except Exception as e:
                        logger.error(f"Error updating JIRA ticket {task['jira_ticket']}: {str(e)}")
                
                return True
    
    logger.warning(f"Task {task_id} not found")
    return False

def get_developer_tasks(developer_id):
    """Get all tasks for a developer."""
    tasks = dev_tasks.get(developer_id, [])
    
    # Sort tasks - pending first, then by due date
    sorted_tasks = sorted(
        tasks,
        key=lambda t: (
            0 if t.get("status") == "pending" else 1,  # Pending tasks first
            datetime.fromisoformat(t.get("due_date")) if t.get("due_date") else datetime.max,  # Then by due date
            datetime.fromisoformat(t.get("created_at"))  # Then by creation date
        )
    )
    
    return sorted_tasks

def get_pending_tasks(developer_id=None):
    """Get pending tasks, optionally filtered by developer."""
    if developer_id:
        return [t for t in dev_tasks.get(developer_id, []) if t.get("status") == "pending"]
    
    # Get all pending tasks across all developers
    all_pending = []
    for dev_id, tasks in dev_tasks.items():
        pending = [t for t in tasks if t.get("status") == "pending"]
        for task in pending:
            task_copy = task.copy()
            task_copy["developer_id"] = dev_id
            all_pending.append(task_copy)
    
    # Sort by due date
    sorted_pending = sorted(
        all_pending,
        key=lambda t: (
            datetime.fromisoformat(t.get("due_date")) if t.get("due_date") else datetime.max,
            datetime.fromisoformat(t.get("created_at"))
        )
    )
    
    return sorted_pending

def get_overdue_tasks():
    """Get tasks that are overdue (past due date and still pending)."""
    now = datetime.now()
    overdue_tasks = []
    
    for developer_id, tasks in dev_tasks.items():
        for task in tasks:
            if (task.get("status") == "pending" and 
                task.get("due_date") and 
                datetime.fromisoformat(task["due_date"]) < now):
                
                task_copy = task.copy()
                task_copy["developer_id"] = developer_id
                overdue_tasks.append(task_copy)
    
    # Sort by most overdue first
    sorted_overdue = sorted(
        overdue_tasks,
        key=lambda t: datetime.fromisoformat(t.get("due_date"))
    )
    
    return sorted_overdue

def send_daily_reminders(bot=None):
    """Send daily reminders to developers about their pending tasks."""
    results = {
        "reminders_sent": 0,
        "developers_notified": []
    }
    
    now = datetime.now()
    
    for developer_id, tasks in dev_tasks.items():
        # Get tasks that are pending
        pending_tasks = [t for t in tasks if t.get("status") == "pending"]
        
        # Filter for tasks that:
        # 1. Have never had a reminder sent OR
        # 2. Last reminder was more than 24 hours ago
        tasks_to_remind = [
            t for t in pending_tasks if (
                not t.get("reminder_sent") or
                (t.get("last_reminder") and 
                 now - datetime.fromisoformat(t["last_reminder"]) > timedelta(hours=24))
            )
        ]
        
        if tasks_to_remind and bot:
            try:
                # Format the reminder message
                reminder = format_reminder_message(developer_id, tasks_to_remind, bot.id)
                
                # In a real implementation, you would get the developer's chat ID
                # For now, we'll just use the group chat ID
                chat_id = f"direct:{developer_id}"  # This will need to be adjusted for actual implementation
                
                try:
                    # Send message
                    bot.sendMessage(
                        chat_id,
                        {
                            'text': reminder
                        }
                    )
                    
                    # Update reminder status
                    for task in tasks_to_remind:
                        task_index = next((i for i, t in enumerate(tasks) if t["task_id"] == task["task_id"]), -1)
                        if task_index >= 0:
                            dev_tasks[developer_id][task_index]["reminder_sent"] = True
                            dev_tasks[developer_id][task_index]["last_reminder"] = now.isoformat()
                    
                    results["reminders_sent"] += 1
                    results["developers_notified"].append(developer_id)
                    
                    logger.info(f"Reminder sent to developer {developer_id} for {len(tasks_to_remind)} tasks")
                except Exception as e:
                    logger.error(f"Failed to send message: {str(e)}")
            except Exception as e:
                logger.error(f"Error preparing reminder for {developer_id}: {str(e)}")
    
    return results

def format_reminder_message(developer_id, tasks, bot_id):
    """Format a reminder message for a developer."""
    message = f"**Daily Task Reminder**\n\n"
    message += f"You have {len(tasks)} pending tasks:\n\n"
    
    # Group tasks by status (overdue, due today, upcoming)
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    overdue_tasks = []
    due_today_tasks = []
    upcoming_tasks = []
    
    for task in tasks:
        if task.get("due_date"):
            due_date = datetime.fromisoformat(task["due_date"])
            if due_date < today:
                overdue_tasks.append(task)
            elif due_date < tomorrow:
                due_today_tasks.append(task)
            else:
                upcoming_tasks.append(task)
        else:
            upcoming_tasks.append(task)
    
    # Format overdue tasks
    if overdue_tasks:
        message += "**Overdue Tasks:**\n"
        for i, task in enumerate(overdue_tasks, 1):
            created = datetime.fromisoformat(task["created_at"]).strftime("%Y-%m-%d")
            due_date = datetime.fromisoformat(task["due_date"])
            days_overdue = (now - due_date).days
            
            jira_text = ""
            if task.get("jira_ticket"):
                jira_url = f"{JIRA_HOST}/browse/{task['jira_ticket']}"
                jira_text = f" [JIRA: {task['jira_ticket']}]({jira_url})"
            
            message += f"{i}. {task['description']} **OVERDUE by {days_overdue} days**{jira_text} (ID: {task['task_id']})\n"
        message += "\n"
    
    # Format tasks due today
    if due_today_tasks:
        message += "**Due Today:**\n"
        for i, task in enumerate(due_today_tasks, 1):
            jira_text = ""
            if task.get("jira_ticket"):
                jira_url = f"{JIRA_HOST}/browse/{task['jira_ticket']}"
                jira_text = f" [JIRA: {task['jira_ticket']}]({jira_url})"
            
            message += f"{i}. {task['description']}{jira_text} (ID: {task['task_id']})\n"
        message += "\n"
    
    # Format upcoming tasks
    if upcoming_tasks:
        message += "**Upcoming Tasks:**\n"
        for i, task in enumerate(upcoming_tasks, 1):
            created = datetime.fromisoformat(task["created_at"]).strftime("%Y-%m-%d")
            
            due_text = ""
            if task.get("due_date"):
                due_date = datetime.fromisoformat(task["due_date"])
                days_left = (due_date - now).days
                due_text = f" (Due in {days_left} days)"
            
            jira_text = ""
            if task.get("jira_ticket"):
                jira_url = f"{JIRA_HOST}/browse/{task['jira_ticket']}"
                jira_text = f" [JIRA: {task['jira_ticket']}]({jira_url})"
            
            message += f"{i}. {task['description']}{due_text}{jira_text} (ID: {task['task_id']})\n"
    
    # Add instructions
    message += "\n"
    message += "**To update a task status, reply with:**\n"
    message += f"`![:Person]({bot_id}) update-task TASK_ID status: completed`\n\n"
    message += "Need help? Reply with:\n"
    message += f"`![:Person]({bot_id}) help`"
    
    return message

def sync_tasks_with_jira(developer_id=None):
    """Sync developer tasks with JIRA tickets assigned to them."""
    results = {
        "tasks_added": 0,
        "tasks_updated": 0,
        "errors": []
    }
    
    # This is a placeholder implementation
    # In a real implementation, you would:
    # 1. Query JIRA for assigned tickets for the developer
    # 2. Compare with the tasks in dev_tasks
    # 3. Add new tickets as tasks
    # 4. Update existing tasks based on ticket status
    
    logger.info("Task syncing with JIRA is not yet implemented")
    return results

def check_inactive_tickets():
    """Check for tickets that haven't been updated in a while."""
    results = {
        "inactive_tickets": []
    }
    
    # This is a placeholder implementation
    # In a real implementation, you would query JIRA for tickets
    # that haven't been updated in a certain period
    
    logger.info("Inactive ticket checking is not yet implemented")
    return results

def send_overdue_reminders(bot=None):
    """Send reminders specifically for overdue tasks."""
    results = {
        "reminders_sent": 0,
        "tasks_reminded": []
    }
    
    if not bot:
        return results
    
    overdue_tasks = get_overdue_tasks()
    
    # Group overdue tasks by developer
    dev_overdue = {}
    for task in overdue_tasks:
        dev_id = task["developer_id"]
        if dev_id not in dev_overdue:
            dev_overdue[dev_id] = []
        dev_overdue[dev_id].append(task)
    
    # Send reminders to each developer
    for dev_id, tasks in dev_overdue.items():
        try:
            # Format the message
            message = "**⚠️ OVERDUE TASKS REMINDER ⚠️**\n\n"
            message += f"You have {len(tasks)} overdue tasks that need immediate attention:\n\n"
            
            for i, task in enumerate(tasks, 1):
                created = datetime.fromisoformat(task["created_at"]).strftime("%Y-%m-%d")
                due_date = datetime.fromisoformat(task["due_date"])
                now = datetime.now()
                days_overdue = (now - due_date).days
                
                jira_text = ""
                if task.get("jira_ticket"):
                    jira_url = f"{JIRA_HOST}/browse/{task['jira_ticket']}"
                    jira_text = f" [JIRA: {task['jira_ticket']}]({jira_url})"
                
                message += f"{i}. {task['description']} **OVERDUE by {days_overdue} days**{jira_text} (ID: {task['task_id']})\n"
            
            message += "\n"
            message += "Please update these tasks as soon as possible.\n\n"
            message += "To mark a task as complete, reply with:\n"
            message += f"`![:Person]({bot.id}) update-task TASK_ID status: completed`"
            
            # Send the message
            chat_id = f"direct:{dev_id}"  # This will need to be adjusted for actual implementation
            
            bot.sendMessage(
                chat_id,
                {
                    'text': message
                }
            )
            
            results["reminders_sent"] += 1
            results["tasks_reminded"].extend([t["task_id"] for t in tasks])
            
            logger.info(f"Overdue reminder sent to developer {dev_id} for {len(tasks)} tasks")
        except Exception as e:
            logger.error(f"Error sending overdue reminder to {dev_id}: {str(e)}")
    
    return results