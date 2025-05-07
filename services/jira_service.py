"""
Service for interacting with JIRA API.
"""

import os
import requests
import logging
from datetime import datetime
from jira import JIRA
from config import JIRA_HOST, JIRA_PAT, JIRA_STORY_POINTS_FIELD

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_jira_client():
    """Initialize and return a JIRA client."""
    try:
        headers = JIRA.DEFAULT_OPTIONS["headers"].copy()
        headers["Authorization"] = f"Bearer {JIRA_PAT}"
        return JIRA(server=JIRA_HOST, options={"headers": headers})
    except Exception as e:
        logger.error(f"Failed to initialize JIRA client: {str(e)}")
        return None

def create_jira_ticket(project, summary, os="", reporter_id=None, attachments=None, 
                     access_token=None, description="", issue_type="Bug", priority="Normal"):
    """Create a new JIRA ticket with the provided details."""
    if not attachments:
        attachments = []
        
    try:
        jira = get_jira_client()
        if not jira:
            return None
            
        # Prepare issue data
        os_title = f'[{os}]' if os else ""
        issue_data = {
            "project": {"key": project},
            "summary": f"[UAT]{os_title}{summary}",
            "description": description,
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
        }
        
        # Create the issue
        new_issue = jira.create_issue(fields=issue_data)
        logger.info(f"Issue created successfully: {new_issue.key}")
        
        # Process attachments if any
        for attachment in attachments:
            file_name = attachment['name']
            file_url = attachment['contentUri']
            
            headers = {}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            
            # Download the file
            response = requests.get(file_url, headers=headers, stream=True)
            if response.status_code == 200:
                # Save the file temporarily
                temp_file_path = os.path.join("/tmp", file_name)
                with open(temp_file_path, 'wb') as f:
                    f.write(response.content)
                    
                # Attach the file to the issue
                with open(temp_file_path, 'rb') as f:
                    jira.add_attachment(issue=new_issue, attachment=f)
                    
                # Clean up
                os.remove(temp_file_path)
                logger.info(f"Attachment '{file_name}' uploaded successfully.")
            else:
                logger.error(f"Failed to download attachment from {file_url}")
        
        return new_issue.key
        
    except Exception as e:
        logger.error(f"Failed to create issue: {str(e)}")
        return None

def update_jira_ticket(ticket_key, status=None, assignee=None, story_points=None, comment=None):
    """Update a JIRA ticket with the provided details."""
    try:
        jira = get_jira_client()
        if not jira:
            return False
            
        # Get the issue
        issue = jira.issue(ticket_key)
        
        # Update status if provided
        if status:
            transition_issue(jira, issue, status)
            
        # Update assignee if provided
        if assignee:
            jira.assign_issue(issue, assignee)
            
        # Update story points if provided
        if story_points is not None:
            jira.update_issue_field(ticket_key, {JIRA_STORY_POINTS_FIELD: story_points})
            
        # Add comment if provided
        if comment:
            jira.add_comment(issue, comment)
            
        return True
        
    except Exception as e:
        logger.error(f"Failed to update ticket {ticket_key}: {str(e)}")
        return False

def transition_issue(jira, issue, target_status):
    """Move a JIRA issue to the specified status."""
    try:
        # Get available transitions
        transitions = jira.transitions(issue)
        
        # Find the transition that matches the target status
        for t in transitions:
            if t['name'].lower() == target_status.lower():
                jira.transition_issue(issue, t['id'])
                return True
                
        logger.warning(f"No transition found for status: {target_status}")
        return False
    except Exception as e:
        logger.error(f"Error transitioning issue: {str(e)}")
        return False

def log_time_to_jira(ticket_key, hours, comment=None, developer_id=None):
    """Log time on a JIRA ticket."""
    try:
        jira = get_jira_client()
        if not jira:
            return False
            
        # Convert hours to seconds
        seconds = int(float(hours) * 3600)
        
        # Prepare worklog data
        worklog_data = {
            "timeSpentSeconds": seconds,
            "comment": comment or f"Logged {hours} hours"
        }
        
        # Add worklog
        jira.add_worklog(ticket_key, **worklog_data)
        logger.info(f"Successfully logged {hours} hours to {ticket_key}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to log time on {ticket_key}: {str(e)}")
        return False

def get_sprint_health(sprint_id=None):
    """Get sprint health metrics."""
    try:
        jira = get_jira_client()
        if not jira:
            return {"error": "Failed to connect to JIRA"}
            
        # If no sprint ID is provided, get the active sprint
        if not sprint_id:
            # This depends on your JIRA configuration 
            boards = jira.boards()
            active_sprints = []
            
            for board in boards:
                sprints = jira.sprints(board.id, state='active')
                active_sprints.extend(sprints)
            
            if not active_sprints:
                return {"error": "No active sprints found"}
                
            sprint = active_sprints[0]
            sprint_id = sprint.id
        else:
            sprint = jira.sprint(sprint_id)
        
        # Get sprint issues
        sprint_issues = jira.sprint_issues(sprint_id)
        
        # Calculate metrics
        total_issues = len(sprint_issues)
        completed_issues = sum(1 for i in sprint_issues if hasattr(i.fields, 'status') and 
                              i.fields.status.name.lower() in ('done', 'closed'))
        
        # Calculate story points
        total_points = 0
        completed_points = 0
        
        for issue in sprint_issues:
            # Get story points (custom field)
            story_points = getattr(issue.fields, JIRA_STORY_POINTS_FIELD, 0) or 0
            total_points += story_points
            
            if hasattr(issue.fields, 'status') and issue.fields.status.name.lower() in ('done', 'closed'):
                completed_points += story_points
        
        # Calculate days in sprint
        if hasattr(sprint, 'startDate') and hasattr(sprint, 'endDate'):
            start_date = datetime.fromisoformat(sprint.startDate.replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(sprint.endDate.replace('Z', '+00:00'))
            now = datetime.now(start_date.tzinfo)
            
            total_days = (end_date - start_date).days
            elapsed_days = (now - start_date).days
            remaining_days = max(0, (end_date - now).days)
            
            # Ideal burndown vs actual
            ideal_completion_rate = elapsed_days / total_days if total_days > 0 else 0
            actual_completion_rate = completed_points / total_points if total_points > 0 else 0
            
            # Health status
            health_status = "On Track"
            if actual_completion_rate < ideal_completion_rate * 0.8:
                health_status = "At Risk"
            elif actual_completion_rate < ideal_completion_rate * 0.5:
                health_status = "Critical"
        else:
            total_days = 0
            elapsed_days = 0
            remaining_days = 0
            ideal_completion_rate = 0
            actual_completion_rate = 0
            health_status = "Unknown"
        
        # Assemble the response
        return {
            "sprint_name": sprint.name,
            "start_date": getattr(sprint, 'startDate', 'Unknown'),
            "end_date": getattr(sprint, 'endDate', 'Unknown'),
            "total_issues": total_issues,
            "completed_issues": completed_issues,
            "total_points": total_points,
            "completed_points": completed_points,
            "completion_percentage": round(completed_points / total_points * 100 if total_points > 0 else 0, 1),
            "days_elapsed": elapsed_days,
            "days_remaining": remaining_days,
            "ideal_completion_percentage": round(ideal_completion_rate * 100, 1),
            "actual_completion_percentage": round(actual_completion_rate * 100, 1),
            "health_status": health_status
        }
        
    except Exception as e:
        logger.error(f"Failed to get sprint health: {str(e)}")
        return {"error": str(e)}