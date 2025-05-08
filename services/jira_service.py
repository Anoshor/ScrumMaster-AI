"""
Service for interacting with JIRA API using direct REST calls.
"""

import os
import json
import requests
import logging
from datetime import datetime
from config import JIRA_HOST, JIRA_PAT, JIRA_STORY_POINTS_FIELD

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Base URL for JIRA REST API
BASE_API_URL = f"{JIRA_HOST}/rest/api/2"

def get_auth_headers():
    """Get authentication headers for JIRA API."""
    return {
        "Authorization": f"Bearer {JIRA_PAT}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

def create_jira_ticket(project, summary, os="", reporter_id=None, attachments=None, 
                     access_token=None, description="", issue_type="Bug", priority="Normal"):
    """Create a new JIRA ticket with the provided details."""
    if not attachments:
        attachments = []
        
    try:
        # Prepare issue data
        os_title = f'[{os}]' if os else ""
        issue_data = {
            "fields": {
                "project": {"key": project},
                "summary": f"[UAT]{os_title}{summary}",
                "description": description,
                "issuetype": {"name": issue_type},
                "priority": {"name": priority}
            }
        }
        
        # Make the API call to create the issue
        url = f"{BASE_API_URL}/issue"
        response = requests.post(
            url, 
            headers=get_auth_headers(),
            data=json.dumps(issue_data)
        )
        
        if response.status_code not in [200, 201]:
            logger.error(f"Failed to create issue: {response.status_code} - {response.text}")
            return None
            
        # Get the issue key from the response
        issue_data = response.json()
        issue_key = issue_data.get("key")
        logger.info(f"Issue created successfully: {issue_key}")
        
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
                attach_url = f"{BASE_API_URL}/issue/{issue_key}/attachments"
                attach_headers = get_auth_headers()
                attach_headers["X-Atlassian-Token"] = "no-check"  # Required for file uploads
                attach_headers.pop("Content-Type", None)  # Remove content-type for multipart
                
                with open(temp_file_path, 'rb') as f:
                    files = {'file': (file_name, f)}
                    attach_response = requests.post(attach_url, headers=attach_headers, files=files)
                    
                    if attach_response.status_code not in [200, 201]:
                        logger.error(f"Failed to attach file: {attach_response.status_code} - {attach_response.text}")
                    else:
                        logger.info(f"Attachment '{file_name}' uploaded successfully.")
                
                # Clean up
                os.remove(temp_file_path)
            else:
                logger.error(f"Failed to download attachment from {file_url}")
        
        return issue_key
        
    except Exception as e:
        logger.error(f"Failed to create issue: {str(e)}")
        return None

def get_issue(issue_key):
    """Get details of a JIRA issue."""
    try:
        url = f"{BASE_API_URL}/issue/{issue_key}"
        response = requests.get(url, headers=get_auth_headers())
        
        if response.status_code != 200:
            logger.error(f"Failed to get issue {issue_key}: {response.status_code} - {response.text}")
            return None
            
        return response.json()
        
    except Exception as e:
        logger.error(f"Error getting issue {issue_key}: {str(e)}")
        return None

def update_jira_ticket(ticket_key, status=None, assignee=None, story_points=None, comment=None):
    """Update a JIRA ticket with the provided details."""
    try:
        # First get the current issue to check if it exists
        issue = get_issue(ticket_key)
        if not issue:
            return False
            
        # Prepare the update data
        update_data = {"fields": {}}
        
        # Update story points if provided
        if story_points is not None:
            update_data["fields"][JIRA_STORY_POINTS_FIELD] = float(story_points)
            
        # Make the API call to update the issue
        if update_data["fields"]:
            url = f"{BASE_API_URL}/issue/{ticket_key}"
            response = requests.put(
                url,
                headers=get_auth_headers(),
                data=json.dumps(update_data)
            )
            
            if response.status_code not in [200, 204]:
                logger.error(f"Failed to update issue {ticket_key}: {response.status_code} - {response.text}")
                return False
        
        # Update status if provided
        if status:
            success = transition_issue(ticket_key, status)
            if not success:
                return False
                
        # Update assignee if provided
        if assignee:
            success = assign_issue(ticket_key, assignee)
            if not success:
                return False
                
        # Add comment if provided
        if comment:
            success = add_comment(ticket_key, comment)
            if not success:
                return False
                
        return True
        
    except Exception as e:
        logger.error(f"Failed to update ticket {ticket_key}: {str(e)}")
        return False

def get_transitions(issue_key):
    """Get available transitions for an issue."""
    try:
        url = f"{BASE_API_URL}/issue/{issue_key}/transitions"
        response = requests.get(url, headers=get_auth_headers())
        
        if response.status_code != 200:
            logger.error(f"Failed to get transitions for {issue_key}: {response.status_code} - {response.text}")
            return []
            
        data = response.json()
        return data.get("transitions", [])
        
    except Exception as e:
        logger.error(f"Error getting transitions for {issue_key}: {str(e)}")
        return []

def transition_issue(issue_key, target_status):
    """Move a JIRA issue to the specified status."""
    try:
        # Get available transitions
        transitions = get_transitions(issue_key)
        
        # Find the transition that matches the target status
        transition_id = None
        for t in transitions:
            if t['name'].lower() == target_status.lower():
                transition_id = t['id']
                break
                
        if not transition_id:
            logger.warning(f"No transition found for status: {target_status}")
            return False
            
        # Make the API call to transition the issue
        url = f"{BASE_API_URL}/issue/{issue_key}/transitions"
        data = {
            "transition": {
                "id": transition_id
            }
        }
        
        response = requests.post(
            url,
            headers=get_auth_headers(),
            data=json.dumps(data)
        )
        
        if response.status_code not in [200, 204]:
            logger.error(f"Failed to transition issue {issue_key}: {response.status_code} - {response.text}")
            return False
            
        logger.info(f"Issue {issue_key} transitioned to {target_status}")
        return True
        
    except Exception as e:
        logger.error(f"Error transitioning issue {issue_key}: {str(e)}")
        return False

def assign_issue(issue_key, assignee):
    """Assign a JIRA issue to a user."""
    try:
        url = f"{BASE_API_URL}/issue/{issue_key}/assignee"
        data = {
            "name": assignee
        }
        
        response = requests.put(
            url,
            headers=get_auth_headers(),
            data=json.dumps(data)
        )
        
        if response.status_code not in [200, 204]:
            logger.error(f"Failed to assign issue {issue_key}: {response.status_code} - {response.text}")
            return False
            
        logger.info(f"Issue {issue_key} assigned to {assignee}")
        return True
        
    except Exception as e:
        logger.error(f"Error assigning issue {issue_key}: {str(e)}")
        return False

def add_comment(issue_key, comment_text):
    """Add a comment to a JIRA issue."""
    try:
        url = f"{BASE_API_URL}/issue/{issue_key}/comment"
        data = {
            "body": comment_text
        }
        
        response = requests.post(
            url,
            headers=get_auth_headers(),
            data=json.dumps(data)
        )
        
        if response.status_code not in [200, 201]:
            logger.error(f"Failed to add comment to {issue_key}: {response.status_code} - {response.text}")
            return False
            
        logger.info(f"Comment added to issue {issue_key}")
        return True
        
    except Exception as e:
        logger.error(f"Error adding comment to {issue_key}: {str(e)}")
        return False

def log_time_to_jira(ticket_key, hours, comment=None, developer_id=None):
    """Log time on a JIRA ticket."""
    try:
        # First check if the issue exists
        issue = get_issue(ticket_key)
        if not issue:
            return False
            
        # Convert hours to seconds
        seconds = int(float(hours) * 3600)
        
        # Prepare worklog data
        url = f"{BASE_API_URL}/issue/{ticket_key}/worklog"
        data = {
            "timeSpentSeconds": seconds,
            "comment": comment or f"Logged {hours} hours"
        }
        
        # Make the API call to add worklog
        response = requests.post(
            url,
            headers=get_auth_headers(),
            data=json.dumps(data)
        )
        
        if response.status_code not in [200, 201]:
            logger.error(f"Failed to log time on {ticket_key}: {response.status_code} - {response.text}")
            return False
            
        logger.info(f"Successfully logged {hours} hours to {ticket_key}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to log time on {ticket_key}: {str(e)}")
        return False

def get_boards():
    """Get all boards."""
    try:
        url = f"{JIRA_HOST}/rest/agile/1.0/board"
        response = requests.get(url, headers=get_auth_headers())
        
        if response.status_code != 200:
            logger.error(f"Failed to get boards: {response.status_code} - {response.text}")
            return []
            
        data = response.json()
        return data.get("values", [])
        
    except Exception as e:
        logger.error(f"Error getting boards: {str(e)}")
        return []

def get_sprints(board_id, state="active"):
    """Get sprints for a board."""
    try:
        url = f"{JIRA_HOST}/rest/agile/1.0/board/{board_id}/sprint"
        if state:
            url += f"?state={state}"
            
        response = requests.get(url, headers=get_auth_headers())
        
        if response.status_code != 200:
            logger.error(f"Failed to get sprints for board {board_id}: {response.status_code} - {response.text}")
            return []
            
        data = response.json()
        return data.get("values", [])
        
    except Exception as e:
        logger.error(f"Error getting sprints for board {board_id}: {str(e)}")
        return []

def get_sprint(sprint_id):
    """Get sprint details."""
    try:
        url = f"{JIRA_HOST}/rest/agile/1.0/sprint/{sprint_id}"
        response = requests.get(url, headers=get_auth_headers())
        
        if response.status_code != 200:
            logger.error(f"Failed to get sprint {sprint_id}: {response.status_code} - {response.text}")
            return None
            
        return response.json()
        
    except Exception as e:
        logger.error(f"Error getting sprint {sprint_id}: {str(e)}")
        return None

def get_sprint_issues(sprint_id):
    """Get issues in a sprint."""
    try:
        url = f"{JIRA_HOST}/rest/agile/1.0/sprint/{sprint_id}/issue"
        response = requests.get(url, headers=get_auth_headers())
        
        if response.status_code != 200:
            logger.error(f"Failed to get issues for sprint {sprint_id}: {response.status_code} - {response.text}")
            return []
            
        data = response.json()
        return data.get("issues", [])
        
    except Exception as e:
        logger.error(f"Error getting issues for sprint {sprint_id}: {str(e)}")
        return []

def get_sprint_health(sprint_id=None):
    """Get sprint health metrics."""
    try:
        # If no sprint ID is provided, get the active sprint
        if not sprint_id:
            boards = get_boards()
            active_sprints = []
            
            for board in boards:
                board_id = board.get("id")
                sprints = get_sprints(board_id, state="active")
                active_sprints.extend(sprints)
            
            if not active_sprints:
                return {"error": "No active sprints found"}
                
            sprint = active_sprints[0]
            sprint_id = sprint.get("id")
        else:
            sprint = get_sprint(sprint_id)
            if not sprint:
                return {"error": f"Sprint {sprint_id} not found"}
        
        # Get sprint issues
        issues = get_sprint_issues(sprint_id)
        
        # Calculate metrics
        total_issues = len(issues)
        completed_issues = sum(1 for i in issues if i.get("fields", {}).get("status", {}).get("name", "").lower() in ('done', 'closed'))
        
        # Calculate story points
        total_points = 0
        completed_points = 0
        
        for issue in issues:
            # Get story points (custom field)
            fields = issue.get("fields", {})
            story_points = fields.get(JIRA_STORY_POINTS_FIELD, 0) or 0
            total_points += story_points
            
            if fields.get("status", {}).get("name", "").lower() in ('done', 'closed'):
                completed_points += story_points
        
        # Calculate sprint dates
        start_date = sprint.get("startDate")
        end_date = sprint.get("endDate")
        
        if start_date and end_date:
            start_date_obj = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end_date_obj = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            now = datetime.now(start_date_obj.tzinfo)
            
            total_days = (end_date_obj - start_date_obj).days
            elapsed_days = (now - start_date_obj).days
            remaining_days = max(0, (end_date_obj - now).days)
            
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
            "sprint_name": sprint.get("name", "Unknown"),
            "start_date": start_date or "Unknown",
            "end_date": end_date or "Unknown",
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