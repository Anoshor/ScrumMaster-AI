"""
Service for sending reminders and notifications to team members.
"""

import logging
from datetime import datetime, timedelta
from config import dev_tasks
from services.jira_service import update_jira_ticket, get_jira_client

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
    dev_tasks[developer_id].append({
        "task_id": task_id,
        "description": task_description,
        "jira_ticket": jira_ticket,
        "created_at": datetime.now().isoformat(),
        "due_date": due_date.isoformat() if due_date else None,
        "status": "pending",
        "reminder_sent": False,
        "last_reminder": None
    })
    
    logger.info(f"Task {task_id} added for developer {developer_id}")
    return task_id

def update_task_status(task_id, status):
    """Update the status of a task."""
    for developer_id, tasks in dev_tasks.items():
        for i, task in enumerate(tasks):
            if task.get("task_id") == task_id:
                dev_tasks[developer_id][i]["status"] = status
                logger.info(f"Task {task_id} status updated to {status}")
                
                # If task is linked to a JIRA ticket and status is completed, update JIRA
                if status.lower() in ("done", "completed", "finished") and task.get("jira_ticket"):
                    try:
                        update_jira_ticket(
                            ticket_key=task["jira_ticket"],
                            status="Done",
                            comment=f"Task marked as {status} via ScrumMaster AI"
                        )
                        logger.info(f"JIRA ticket {task['jira_ticket']} updated to Done")
                    except Exception as e:
                        logger.error(f"Error updating JIRA ticket {task['jira_ticket']}: {str(e)}")
                
                return True
    
    logger.warning(f"Task {task_id} not found")
    return False

def get_developer_tasks(developer_id):
    """Get all tasks for a developer."""
    return dev_tasks.get(developer_id, [])

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
    
    return all_pending

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
    
    return overdue_tasks

def send_daily_reminders(bot=None):
    """Send daily reminders to developers about their pending tasks."""
    results = {
        "reminders_sent": 0,
        "developers_notified": []
    }
    
    now = datetime.now()
    
    for developer_id, tasks in dev_tasks.items():
        pending_tasks = [t for t in tasks if t.get("status") == "pending"]
        
        if pending_tasks and bot:
            # Format the reminder message
            reminder = format_reminder_message(developer_id, pending_tasks)
            
            # In a real implementation, you would have a way to get the developer's chat ID
            # This is just a placeholder implementation
            try:
                # Get developer chat ID (in real implementation)
                chat_id = f"direct:{developer_id}"  # Placeholder
                
                # Send message
                bot.sendMessage(
                    chat_id,
                    {
                        'text': reminder
                    }
                )
                
                # Update reminder status
                for i, task in enumerate(pending_tasks):
                    task_index = tasks.index(task)
                    dev_tasks[developer_id][task_index]["reminder_sent"] = True
                    dev_tasks[developer_id][task_index]["last_reminder"] = now.isoformat()
                
                results["reminders_sent"] += 1
                results["developers_notified"].append(developer_id)
                
                logger.info(f"Reminder sent to developer {developer_id} for {len(pending_tasks)} tasks")
            except Exception as e:
                logger.error(f"Error sending reminder to {developer_id}: {str(e)}")
    
    return results

def format_reminder_message(developer_id, tasks):
    """Format a reminder message for a developer."""
    message = f"**Daily Task Reminder**\n\n"
    message += f"You have {len(tasks)} pending tasks:\n\n"
    
    for i, task in enumerate(tasks, 1):
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
        
        message += f"{i}. {task['description']}{due_text}{jira_text} (created on {created})\n"
    
    message += "\n"
    message += "To mark a task as complete, reply with:\n"
    message += "`![:Person]({bot_id}) update-task TASK_ID status: completed`\n\n"
    message += "Need help? Reply with `![:Person]({bot_id}) help`"
    
    return message

def sync_tasks_with_jira():
    """Sync developer tasks with JIRA tickets."""
    results = {
        "tasks_added": 0,
        "tasks_updated": 0,
        "errors": []
    }
    
    try:
        jira = get_jira_client()
        if not jira:
            results["errors"].append("Failed to connect to JIRA")
            return results
            
        # This is a placeholder implementation
        # In a real implementation, you would:
        # 1. Query JIRA for assigned tickets for each developer
        # 2. Compare with the tasks in dev_tasks
        # 3. Add new tickets as tasks
        # 4. Update existing tasks based on ticket status
        
        # For now, just return a placeholder result
        results["tasks_added"] = 0
        results["tasks_updated"] = 0
        
        return results
        
    except Exception as e:
        logger.error(f"Error syncing tasks with JIRA: {str(e)}")
        results["errors"].append(str(e))
        return results

def check_inactive_tickets():
    """Check for tickets that haven't been updated in a while."""
    results = {
        "inactive_tickets": []
    }
    
    try:
        jira = get_jira_client()
        if not jira:
            return results
            
        # This is a placeholder implementation
        # In a real implementation, you would query JIRA for tickets
        # that haven't been updated in a certain period
        
        return results
        
    except Exception as e:
        logger.error(f"Error checking inactive tickets: {str(e)}")
        return results