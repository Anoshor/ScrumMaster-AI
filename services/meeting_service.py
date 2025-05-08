"""
Service for processing meeting transcripts and managing meeting data.
"""

import os
import json
import logging
import openai
from datetime import datetime
from config import meeting_memory, JIRA_HOST
from services.jira_service import update_jira_ticket, get_issue

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
    - story_points: list of {{"ticket_key": "...", "points": number}}
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
            {"task": "Fix login bug in mobile app", "assignee": "Sarah"}
        ],
        "ticket_updates": [
            {"ticket_key": "RCVNC-123", "status": "In Progress", "comment": "Working on authentication flow"},
            {"ticket_key": "RCVNC-124", "status": "Done", "comment": "UI improvements completed"}
        ],
        "story_points": [
            {"ticket_key": "RCVNC-125", "points": 5},
            {"ticket_key": "RCVNC-126", "points": 3}
        ],
        "blockers": [
            {"description": "Waiting for design team input", "for_ticket": "RCVNC-127", "mentioned_by": "David"}
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
                timestamp_display = datetime.fromisoformat(timestamp) if timestamp != "Unknown" else "Unknown time"
                results.append(f"- Meeting on {timestamp_display}: Found mention of '{topic}'")
        
        if results:
            return f"**Search Results for '{topic}'**\n\n" + "\n".join(results)
        else:
            return f"No information found about '{topic}' in the meeting records."
    else:
        # Return a list of all recorded meetings
        meetings_list = []
        for meeting_id, data in meeting_memory.items():
            timestamp = data.get("timestamp", "Unknown")
            timestamp_display = datetime.fromisoformat(timestamp) if timestamp != "Unknown" else "Unknown time"
            summary = data.get("summary", {})
            decisions = summary.get("decisions", [])
            topics = [d.get("topic", "Unknown topic") for d in decisions]
            topics_text = ", ".join(topics[:3]) if topics else "No specific topics"
            
            meetings_list.append(f"- Meeting on {timestamp_display}: {topics_text}")
        
        if meetings_list:
            return "**Recorded Meetings**\n\n" + "\n".join(meetings_list)
        else:
            return "No meetings have been recorded yet."

def generate_daily_summary(sprint_id=None):
    """Generate a daily summary of sprint activity."""
    # Use JIRA API to get recent activity
    
    # This is a placeholder implementation
    # In a real implementation, you would:
    # 1. Query JIRA for today's activity in the sprint
    # 2. Get updated tickets, new tickets, and completed tickets
    # 3. Calculate progress metrics
    # 4. Format the summary
    
    return """
    **Daily Sprint Summary** (Generated: May 8, 2025)
    
    **Today's Progress**
    - 3 tickets moved to Done
    - 2 new tickets created
    - 5 story points completed
    
    **Active Blockers**
    - RCVNC-123: Waiting for design team input
    
    **Upcoming Deadlines**
    - Sprint ends in 3 days
    - 8 tickets still in progress
    
    **Team Velocity**
    - Current: 4.2 points/day
    - Expected: 5 points/day
    
    **Tickets to Review**
    - RCVNC-124: UI improvements completed (ready for code review)
    """

def get_meeting_history_for_ticket(ticket_key):
    """Get meeting history related to a specific ticket."""
    if not meeting_memory:
        return "No meeting records found for this ticket."
        
    ticket_mentions = []
    
    for meeting_id, data in meeting_memory.items():
        timestamp = data.get("timestamp", "Unknown")
        timestamp_display = datetime.fromisoformat(timestamp) if timestamp != "Unknown" else "Unknown time"
        summary = data.get("summary", {})
        
        # Check for ticket mentions in different sections
        mentioned = False
        mention_context = []
        
        # Check ticket updates
        for update in summary.get("ticket_updates", []):
            if update.get("ticket_key") == ticket_key:
                status_text = f" → {update.get('status')}" if update.get("status") else ""
                comment_text = f": {update.get('comment')}" if update.get("comment") else ""
                mention_context.append(f"Status update{status_text}{comment_text}")
                mentioned = True
        
        # Check story points
        for sp in summary.get("story_points", []):
            if sp.get("ticket_key") == ticket_key:
                mention_context.append(f"Story points estimated: {sp.get('points')}")
                mentioned = True
        
        # Check blockers
        for blocker in summary.get("blockers", []):
            if blocker.get("for_ticket") == ticket_key:
                mention_context.append(f"Blocker reported: {blocker.get('description')} (by {blocker.get('mentioned_by')})")
                mentioned = True
        
        # If ticket was mentioned, add to results
        if mentioned:
            context_text = ", ".join(mention_context)
            ticket_mentions.append(f"- Meeting on {timestamp_display}: {context_text}")
    
    if ticket_mentions:
        return f"**Meeting History for {ticket_key}**\n\n" + "\n".join(ticket_mentions)
    else:
        return f"No meeting discussions found for ticket {ticket_key}."

def extract_action_items_from_text(text):
    """Extract action items from free-form text."""
    if not openai.api_key:
        logger.warning("OpenAI API key not set, using basic extraction")
        # Basic extraction with regex could be implemented here
        return []
        
    prompt = f"""
    Extract action items from this text. An action item is a task that needs to be done, preferably with an assignee.
    
    Text:
    {text}
    
    Format the response as JSON with a list of action items, each with:
    - task: the task to be done
    - assignee: the person assigned to the task (if mentioned)
    """
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You extract action items from text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        
        # Parse the response
        content = response.choices[0].message.content
        action_items = json.loads(content)
        
        return action_items.get("action_items", [])
        
    except Exception as e:
        logger.error(f"Error extracting action items: {str(e)}")
        return []

def parse_transcript_file(file_path):
    """Parse a transcript file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            transcript = f.read()
        return transcript
    except Exception as e:
        logger.error(f"Error parsing transcript file: {str(e)}")
        return None

def process_transcript_content(transcript_content):
    """Process transcript content from a file or input."""
    if not transcript_content:
        return None
        
    # Analyze the transcript
    meeting_data = analyze_transcript(transcript_content)
    
    if meeting_data:
        # Store in meeting memory
        meeting_id = datetime.now().strftime("%Y%m%d%H%M%S")
        meeting_memory[meeting_id] = {
            "transcript": transcript_content,
            "summary": meeting_data,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Stored meeting transcript with ID {meeting_id}")
        
        # Apply actions
        action_results = apply_meeting_actions(meeting_data)
        logger.info(f"Applied actions: {len(action_results['ticket_updates'])} ticket updates, {len(action_results['blockers_added'])} blockers added")
        
        # Return meeting data and action results
        return {
            "meeting_id": meeting_id,
            "meeting_data": meeting_data,
            "action_results": action_results
        }
    
    return None

def get_recent_meetings(max_count=5):
    """Get the most recent meetings."""
    if not meeting_memory:
        return []
        
    # Sort meetings by timestamp (newest first)
    sorted_meetings = sorted(
        [(meeting_id, data) for meeting_id, data in meeting_memory.items()],
        key=lambda x: x[1].get("timestamp", "0"),
        reverse=True
    )
    
    # Take the most recent ones
    recent_meetings = sorted_meetings[:max_count]
    
    # Format the results
    formatted_meetings = []
    for meeting_id, data in recent_meetings:
        timestamp = data.get("timestamp", "Unknown")
        timestamp_display = datetime.fromisoformat(timestamp) if timestamp != "Unknown" else "Unknown time"
        summary = data.get("summary", {})
        
        # Get key metrics
        action_items_count = len(summary.get("action_items", []))
        ticket_updates_count = len(summary.get("ticket_updates", []))
        decisions_count = len(summary.get("decisions", []))
        
        formatted_meetings.append({
            "meeting_id": meeting_id,
            "timestamp": timestamp_display,
            "action_items_count": action_items_count,
            "ticket_updates_count": ticket_updates_count,
            "decisions_count": decisions_count
        })
    
    return formatted_meetings