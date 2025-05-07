"""
Service for processing meeting transcripts and managing meeting data.
"""

import os
import json
import logging
import openai
from datetime import datetime
from config import meeting_memory
from services.jira_service import update_jira_ticket

# Configure OpenAI
openai.api_key = os.environ.get('OPENAI_API_KEY')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_transcript(transcript):
    """Process a meeting transcript and extract structured data."""
    if not openai.api_key:
        logger.warning("OpenAI API key not set, using mock data")
        return mock_meeting_data()
        
    prompt = f"""
    Analyze this meeting transcript and extract:
    1. Action items with assignees
    2. Ticket updates (status changes, comments)
    3. Story point estimates discussed
    4. Blockers mentioned
    5. Important decisions made

    Meeting transcript:
    {transcript}
    
    Format the response as JSON with these keys:
    - action_items: list of {{"task": "...", "assignee": "..."}}
    - ticket_updates: list of {{"ticket_key": "...", "status": "...", "comment": "..."}}
    - story_points: list of {{"ticket_key": "...", "points": N}}
    - blockers: list of {{"description": "...", "for_ticket": "...", "mentioned_by": "..."}}
    - decisions: list of {{"topic": "...", "decision": "..."}}
    - attendees: list of names of people who spoke in the meeting
    """
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",  # Use appropriate model
            messages=[
                {"role": "system", "content": "You extract structured information from meeting transcripts."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1  # Lower temperature for more predictable outputs
        )
        
        # Parse the response
        content = response.choices[0].message.content
        extracted_data = json.loads(content)
        
        logger.info(f"Successfully extracted data from transcript: {len(extracted_data.get('action_items', []))} action items, {len(extracted_data.get('ticket_updates', []))} ticket updates")
        
        return extracted_data
        
    except Exception as e:
        logger.error(f"Error extracting data from transcript: {str(e)}")
        return None

def mock_meeting_data():
    """Return mock meeting data for testing when OpenAI is not available."""
    return {
        "action_items": [
            {"task": "Update API documentation", "assignee": "John"},
            {"task": "Fix login bug", "assignee": "Sarah"}
        ],
        "ticket_updates": [
            {"ticket_key": "PROJ-123", "status": "In Progress", "comment": "Working on authentication flow"},
            {"ticket_key": "PROJ-124", "status": "Done", "comment": "UI improvements completed"}
        ],
        "story_points": [
            {"ticket_key": "PROJ-125", "points": 5},
            {"ticket_key": "PROJ-126", "points": 3}
        ],
        "blockers": [
            {"description": "Waiting for design team input", "for_ticket": "PROJ-127", "mentioned_by": "David"}
        ],
        "decisions": [
            {"topic": "API Design", "decision": "We will use REST architecture for the new endpoints"}
        ],
        "attendees": ["John", "Sarah", "David", "Emily"]
    }

def apply_meeting_actions(meeting_data):
    """Apply actions extracted from a meeting to JIRA."""
    results = {
        "ticket_updates": [],
        "blockers_added": [],
        "story_points_updated": []
    }
    
    # Process ticket updates
    for update in meeting_data.get("ticket_updates", []):
        if "ticket_key" in update:
            try:
                success = update_jira_ticket(
                    ticket_key=update["ticket_key"],
                    status=update.get("status"),
                    comment=update.get("comment")
                )
                
                results["ticket_updates"].append({
                    "ticket_key": update["ticket_key"],
                    "success": success
                })
            except Exception as e:
                logger.error(f"Error updating ticket {update['ticket_key']}: {str(e)}")
                results["ticket_updates"].append({
                    "ticket_key": update["ticket_key"],
                    "success": False,
                    "error": str(e)
                })
    
    # Process blockers
    for blocker in meeting_data.get("blockers", []):
        if "for_ticket" in blocker:
            try:
                comment = f"🚫 **BLOCKER** reported by {blocker.get('mentioned_by', 'someone')}: {blocker.get('description', 'No description')}"
                success = update_jira_ticket(
                    ticket_key=blocker["for_ticket"],
                    comment=comment
                )
                
                results["blockers_added"].append({
                    "ticket_key": blocker["for_ticket"],
                    "success": success
                })
            except Exception as e:
                logger.error(f"Error adding blocker for {blocker['for_ticket']}: {str(e)}")
                results["blockers_added"].append({
                    "ticket_key": blocker["for_ticket"],
                    "success": False,
                    "error": str(e)
                })
    
    # Process story points
    for sp_update in meeting_data.get("story_points", []):
        if "ticket_key" in sp_update and "points" in sp_update:
            try:
                success = update_jira_ticket(
                    ticket_key=sp_update["ticket_key"],
                    story_points=sp_update["points"]
                )
                
                results["story_points_updated"].append({
                    "ticket_key": sp_update["ticket_key"],
                    "points": sp_update["points"],
                    "success": success
                })
            except Exception as e:
                logger.error(f"Error updating story points for {sp_update['ticket_key']}: {str(e)}")
                results["story_points_updated"].append({
                    "ticket_key": sp_update["ticket_key"],
                    "success": False,
                    "error": str(e)
                })
    
    return results

def search_meeting_memory(topic=None):
    """Search through meeting memory for information about a topic."""
    if not meeting_memory:
        return "No meetings have been recorded yet."
        
    if topic:
        # If OpenAI API is available, use it to search through meeting memory
        if openai.api_key:
            try:
                meetings_json = json.dumps(meeting_memory)
                
                prompt = f"""
                Search through these meeting records and find information about: "{topic}"
                
                Meeting records:
                {meetings_json}
                
                Return a concise summary of what was discussed about this topic across all meetings,
                including when it was discussed, decisions made, and any action items.
                """
                
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You search through meeting records and provide concise summaries."},
                        {"role": "user", "content": prompt}
                    ]
                )
                
                return response.choices[0].message.content
                
            except Exception as e:
                logger.error(f"Error searching meeting memory: {str(e)}")
                return f"Error searching meeting memory: {str(e)}"
        
        # If OpenAI is not available, do a simple keyword search
        results = []
        for meeting_id, data in meeting_memory.items():
            transcript = data.get("transcript", "").lower()
            summary = json.dumps(data.get("summary", {})).lower()
            
            if topic.lower() in transcript or topic.lower() in summary:
                timestamp = data.get("timestamp", "Unknown")
                results.append(f"- Meeting on {timestamp}: Found mention of '{topic}'")
        
        if results:
            return f"**Search Results for '{topic}'**\n\n" + "\n".join(results)
        else:
            return f"No information found about '{topic}' in the meeting records."
    else:
        # Return a list of all recorded meetings
        meetings_list = []
        for meeting_id, data in meeting_memory.items():
            timestamp = data.get("timestamp", "Unknown")
            summary = data.get("summary", {})
            decisions = summary.get("decisions", [])
            topics = [d.get("topic", "Unknown topic") for d in decisions]
            topics_text = ", ".join(topics[:3]) if topics else "No specific topics"
            
            meetings_list.append(f"- Meeting on {timestamp}: {topics_text}")
        
        if meetings_list:
            return "**Recorded Meetings**\n\n" + "\n".join(meetings_list)
        else:
            return "No meetings have been recorded yet."

def generate_daily_summary(sprint_id=None):
    """Generate a daily summary of sprint activity."""
    # This would normally query JIRA for today's activity
    # For now, return a simple placeholder
    return """
    **Daily Sprint Summary**
    
    **Today's Progress**
    - 3 tickets moved to Done
    - 2 new tickets created
    - 5 story points completed
    
    **Active Blockers**
    - PROJ-123: Waiting for design team input
    
    **Upcoming Deadlines**
    - Sprint ends in 3 days
    - 8 tickets still in progress
    
    **Team Velocity**
    - Current: 4.2 points/day
    - Expected: 5 points/day
    """