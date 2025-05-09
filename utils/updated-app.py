from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Type, Dict
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import chromadb
from chromadb.config import Settings
import openai, os, json, random, re, requests
from sentence_transformers import SentenceTransformer
from datetime import datetime, timezone
from openai import OpenAI
from models import (
    Base, Agent, Supervisor, Transcript, Task, TaskStatus,
    AgentCreate, SupervisorCreate, AssignRequest, TranscriptCreate,
    TaskList, TaskCompletionTimes, KBChunkList, ChatResponse,
    DifyResponse, TaskWithDuration, TaskWithDurationList,
    TaskInfoResponse, TranscriptTasksResponse
)

# Constants & Config
DIFY_API_URL = "https://dify.int.rclabenv.com/v1/chat-messages"
DIFY_API_TOKEN = os.getenv("DIFY_API_TOKEN")  # set your token in env

# Hardcoded fallback conversation if none provided
SAMPLE_CONVERSATION = (
    "User:<2028>Please follow up with DevOps about the deployment failure from last night. "
    "I think the rollback script didn't trigger correctly.\n"
    "Agent:<2028>Understood. I'll check in with the DevOps team regarding the failed deployment and investigate the rollback issue.\n"
    "User:<2028>Also, can you generate a summary of the QA test results from yesterday's regression suite "
    "and send it to the Slack #qa-updates channel?\n"
    "Agent:<2028>Will do. Anything else?\n"
    "User:<2028>Yes, fetch the latest ticket statuses from Jira for the \"Unified Notification Service\" project "
    "and email me a summary.\n"
    "Agent:<2028>I'll retrieve the Jira statuses and send the summary to your email.\n"
    "User:<2028>And lastly, remind the design team to finalize the mobile wireframes by end of day Friday.\n"
    "Agent:<2028>I'll set a reminder for the design team to complete the wireframes by EOD Friday."
)

# Initialize ChromaDB client for tasks
tasks_chroma_client = chromadb.Client(Settings(
    chroma_db_impl="duckdb+parquet",
    persist_directory="./chroma_tasks"
))

# Create or get a collection for tasks
task_collection = tasks_chroma_client.get_or_create_collection("tasks")

# Initialize ChromaDB client for knowledge base 
kb_chroma_client = chromadb.Client(Settings(
    chroma_db_impl="duckdb+parquet",
    persist_directory="./chroma_kb"
))

# Create or get a collection for knowledge base
kb_collection = kb_chroma_client.get_or_create_collection("kb")

# Initialize database (SQLite)
engine = create_engine("sqlite:///acw.db", echo=False)
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Allow CORS for local development (React at localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- Utilities ---
# Load the BAAI/bge-small-en model once during application startup
embedding_model = SentenceTransformer("BAAI/bge-small-en")

def get_embedding(text: str) -> list:
    """
    Generate an embedding for the given text using the BAAI/bge-small-en model.
    Args:
        text (str): The input text to generate the embedding for.
    Returns:
        list: A list of floats representing the embedding vector.
    """
    try:
        # Generate embedding for the input text
        embedding = embedding_model.encode([text])[0]
        return embedding.tolist()  # Convert to list for compatibility
    except Exception as e:
        raise RuntimeError(f"Failed to generate embedding: {e}")

def llm_call(prompt: str, response_format: Type[BaseModel]) -> Type[BaseModel]:
    client = OpenAI(
    )
    model_name = "gpt-4o-mini"
    messages = [{"role": "user", "content": prompt}]
    completion = client.beta.chat.completions.parse(
        temperature=1,
        messages=messages,
        model=model_name,
        response_format=response_format,
    )
    return json.loads(completion.choices[0].message.content)

def convert_duration_to_minutes(duration_str: str) -> float:
    """
    Convert a duration string like '2 hours' or '45 minutes' to minutes.
    """
    duration_str = duration_str.lower()
    if 'hour' in duration_str:
        # Extract the numeric part before 'hour'
        hours = float(re.search(r'(\d+(\.\d+)?)', duration_str).group(1))
        return hours * 60
    elif 'minute' in duration_str:
        # Extract the numeric part before 'minute'
        minutes = float(re.search(r'(\d+(\.\d+)?)', duration_str).group(1))
        return minutes
    else:
        # Default to returning as is if format not recognized
        try:
            return float(duration_str)
        except:
            return 30.0  # Default 30 minutes if unparseable

# --- Admin Endpoints ---
@app.post("/admin/agents")
def add_agent(agent: AgentCreate):
    """Add a new agent."""
    db = SessionLocal()
    db_agent = Agent(name=agent.name)
    db.add(db_agent); db.commit(); db.refresh(db_agent)
    db.close()
    return {"id": db_agent.id, "name": db_agent.name}

@app.get("/admin/agents")
def get_agents():
    """List all agents."""
    db = SessionLocal()
    agents = db.query(Agent).all()
    result = [{"id": a.id, "name": a.name, "sup_id": a.sup_id} for a in agents]
    db.close()
    return result

@app.post("/admin/supervisors")
def add_supervisor(supervisor: SupervisorCreate):
    """Add a new supervisor."""
    db = SessionLocal()
    db_sup = Supervisor(name=supervisor.name)
    db.add(db_sup); db.commit(); db.refresh(db_sup)
    db.close()
    return {"id": db_sup.id, "name": db_sup.name}

@app.get("/admin/supervisors")
def get_supervisors():
    """List all supervisors."""
    db = SessionLocal()
    supers = db.query(Supervisor).all()
    result = [{"id": s.id, "name": s.name} for s in supers]
    db.close()
    return result

@app.post("/admin/assign")
def assign_agent(req: AssignRequest):
    """Assign an agent to a supervisor."""
    db = SessionLocal()
    agent = db.query(Agent).get(req.agent_id)
    sup = db.query(Supervisor).get(req.supervisor_id)
    if not agent or not sup:
        db.close()
        raise HTTPException(status_code=404, detail="Agent or Supervisor not found")
    agent.sup_id = req.supervisor_id
    db.commit(); db.refresh(agent)
    db.close()
    return {"status": "assigned", "agent_id": agent.id, "supervisor_id": sup.id}

@app.post("/admin/knowledge-base")
def manage_knowledge_base(knowledge_base: str):
    """
    Admin uploads a big piece of text as the knowledge base. This endpoint processes the text,
    breaks it into chunks using an LLM, and stores the chunks and their embeddings in the ChromaDB
    for the knowledge base. If the knowledge base already exists, it is destroyed and recreated.
    """
    
    existing_chunks = kb_collection.get()
    if existing_chunks["ids"]:
        # If the knowledge base exists, delete it
        kb_collection.delete(where={})  # Deletes all entries in the collection
    kb_chunk_generation_prompt = f"""
    You are an assistant that organizes knowledge bases. Break the following text into smaller chunks,
    where each chunk represents a specific topic or subtopic. Ensure the chunks are concise and meaningful.
    Knowledge Base Text:
    {knowledge_base}
    Output a JSON array of chunks, where each chunk is a string.
    """
    kb_chunks = llm_call(kb_chunk_generation_prompt, KBChunkList)
    for idx, chunk in enumerate(kb_chunks.chunks):
        # Generate embedding for the chunk
        embedding = get_embedding(chunk)
        # Add the chunk to the ChromaDB knowledge base collection
        kb_collection.add(
            ids=[f"chunk-{idx + 1}"],  # Unique ID for each chunk
            embeddings=[embedding],
            metadatas=[{"chunk_text": chunk}]
        )
    return {"status": "success", "message": "Knowledge base has been created/updated successfully."}

# Utility: call Dify chatbot and parse response
def call_chatbot(conversation: str) -> List[Dict]:
    headers = {
        "Authorization": f"Bearer {DIFY_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": {},
        "query": conversation,
        "response_mode": "blocking",
        "user": "abc-123",
        "conversation_id": ""
    }
    
    try:
        resp = requests.post(DIFY_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        
        # Extract the answer from the response
        raw_answer = data.get("answer", "")
        
        # Strip <think> blocks
        sanitized = re.sub(r"<think>.*?</think>\s*", "", raw_answer, flags=re.DOTALL)
        
        # Find JSON content in the answer (it's enclosed in ```json ... ```)
        json_match = re.search(r'```json\s*(.*?)\s*```', sanitized, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(1)
            # Parse the JSON content
            task_list = json.loads(json_str)
            return task_list
        else:
            # If no JSON found, return an empty list
            return []
            
    except Exception as e:
        # Log the error
        print(f"Error calling chatbot: {str(e)}")
        return []

# --- Transcript and Task Endpoints ---
@app.post("/transcripts", response_model=TranscriptTasksResponse)
def create_transcript(transcript: TranscriptCreate):
    """
    Agent uploads a call transcript. We create a Transcript entry, then use LLM
    to extract tasks with estimated durations, create Task entries, and store them.
    """
    db = SessionLocal()
    agent = db.query(Agent).get(transcript.agent_id)
    if not agent:
        db.close()
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Save transcript in DB
    content = transcript.content.strip() or SAMPLE_CONVERSATION
    db_trans = Transcript(
        agent_id=transcript.agent_id, 
        content=content, 
        created_at=datetime.now(timezone.utc)
    )
    db.add(db_trans)
    db.commit()
    db.refresh(db_trans)
    
    # Extract tasks from transcript using Dify
    try:
        task_items = call_chatbot(content)
    except Exception as e:
        # fallback to hardcoded if API fails
        task_items = call_chatbot(SAMPLE_CONVERSATION)
    
    # If no tasks were found, return an empty list
    if not task_items:
        db.close()
        return {"transcript_id": db_trans.id, "tasks": []}
    
    # Process tasks: store in DB and ChromaDB
    tasks_info = []
    for idx, task_item in enumerate(task_items):
        # Extract task description and duration
        description = task_item.get("task", "")
        duration_str = task_item.get("estimated_duration", "30 minutes")
        
        # Convert duration string to minutes
        duration_minutes = convert_duration_to_minutes(duration_str)
        
        # Create a new Task entry
        db_task = Task(
            transcript_id=db_trans.id,
            agent_id=transcript.agent_id,
            description=description,
            estimated_duration=duration_minutes,
            actual_duration=None,
            status=TaskStatus.PENDING.value,
            created_at=datetime.now(timezone.utc),
            completed_at=None
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        
        # Generate embedding for the task description
        embedding = get_embedding(description)
        
        # Add task to ChromaDB
        task_collection.add(
            ids=[f"{db_trans.id}-{idx + 1}"],
            embeddings=[embedding],
            metadatas=[{
                "id": str(db_task.id),
                "transcript_id": db_trans.id,
                "agent_id": transcript.agent_id,
                "description": description,
                "estimated_duration": duration_minutes,
                "status": TaskStatus.PENDING.value,
                "created_at": datetime.now(timezone.utc).isoformat()
            }]
        )
        
        # Add to response
        tasks_info.append(TaskInfoResponse(
            id=str(db_task.id),
            transcript_id=db_trans.id,
            agent_id=transcript.agent_id,
            description=description,
            estimated_duration=duration_minutes,
            actual_duration=None,
            status=TaskStatus.PENDING.value,
            created_at=datetime.now(timezone.utc).isoformat(),
            completed_at=None
        ))
    
    db.close()
    return {"transcript_id": db_trans.id, "tasks": tasks_info}

@app.get("/agents/{agent_id}/tasks")
def get_agent_tasks(agent_id: int):
    """Get all tasks for a given agent."""
    db = SessionLocal()
    agent = db.query(Agent).get(agent_id)
    if not agent:
        db.close()
        raise HTTPException(status_code=404, detail="Agent not found")
    tasks = db.query(Task).filter(Task.agent_id == agent_id).all()
    result = [{
        "id": t.id,
        "transcript_id": t.transcript_id,
        "description": t.description,
        "estimated_duration": t.estimated_duration,
        "actual_duration": t.actual_duration,
        "status": t.status
    } for t in tasks]
    db.close()
    return result

@app.get("/supervisors/{sup_id}/metrics")
def get_supervisor_metrics(sup_id: int):
    """
    Calculate performance metrics for each agent under this supervisor:
    - Avg ACW time (avg of actual durations for completed tasks)
    - Percentage of tasks delayed
    - Percentage of tasks agent couldn't do
    """
    db = SessionLocal()
    sup = db.query(Supervisor).get(sup_id)
    if not sup:
        db.close()
        raise HTTPException(status_code=404, detail="Supervisor not found")
    metrics = []
    for agent in sup.agents:
        tasks = agent.tasks
        total_tasks = len(tasks)
        done_tasks = [t for t in tasks if t.status != "cant_do"]
        total_time = sum(t.actual_duration for t in done_tasks if t.actual_duration is not None)
        count_done = len([t for t in done_tasks if t.actual_duration is not None])
        avg_acw = (total_time / count_done) if count_done > 0 else 0.0
        delays = sum(1 for t in tasks if t.status == "delayed")
        cants = sum(1 for t in tasks if t.status == "cant_do")
        delay_pct = (delays / total_tasks * 100) if total_tasks else 0.0
        cant_pct = (cants / total_tasks * 100) if total_tasks else 0.0
        metrics.append({
            "agent_id": agent.id,
            "agent_name": agent.name,
            "avg_acw": round(avg_acw, 2),
            "delay_percent": round(delay_pct, 1),
            "cant_do_percent": round(cant_pct, 1)
        })
    db.close()
    return {"metrics": metrics}

@app.get("/supervisors/{sup_id}/alerts")
def get_supervisor_alerts(sup_id: int):
    """
    Return tasks under this supervisor's agents that are delayed or can't be done.
    Each alert includes agent ID, transcript ID, task ID, description, and status.
    """
    db = SessionLocal()
    sup = db.query(Supervisor).get(sup_id)
    if not sup:
        db.close()
        raise HTTPException(status_code=404, detail="Supervisor not found")
    alerts = []
    for agent in sup.agents:
        for t in agent.tasks:
            if t.status in ("delayed", "cant_do"):
                alerts.append({
                    "agent_id": agent.id,
                    "transcript_id": t.transcript_id,
                    "task_id": t.id,
                    "description": t.description,
                    "status": t.status
                })
    db.close()
    return {"alerts": alerts}

# Optional: Endpoint to update task status
@app.post("/tasks/{task_id}/status")
def update_task_status(task_id: int, status: str):
    """Update the status of a task"""
    db = SessionLocal()
    task = db.query(Task).get(task_id)
    if not task:
        db.close()
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Validate status
    valid_statuses = [status.value for status in TaskStatus]
    if status not in valid_statuses:
        db.close()
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
    
    # Update task status
    task.status = status
    
    # If status is DONE, update completed_at
    if status == TaskStatus.DONE.value:
        task.completed_at = datetime.now(timezone.utc)
    
    db.commit()
    db.close()
    
    return {"task_id": task_id, "status": status}

# Optional: Endpoint to update task actual duration
@app.post("/tasks/{task_id}/duration")
def update_task_duration(task_id: int, actual_duration: float):
    """Update the actual duration of a task"""
    db = SessionLocal()
    task = db.query(Task).get(task_id)
    if not task:
        db.close()
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Update task actual duration
    task.actual_duration = actual_duration
    
    db.commit()
    db.close()
    
    return {"task_id": task_id, "actual_duration": actual_duration}
