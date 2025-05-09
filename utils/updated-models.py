from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
from enum import Enum
from pydantic import BaseModel
from typing import List, Optional, Union

Base = declarative_base()

class Agent(Base):
    __tablename__ = 'agents'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    sup_id = Column(Integer, ForeignKey('supervisors.id'), nullable=True)
    transcripts = relationship("Transcript", back_populates="agent")
    tasks = relationship("Task", back_populates="agent")
    supervisor = relationship("Supervisor", back_populates="agents")

class Supervisor(Base):
    __tablename__ = 'supervisors'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    agents = relationship("Agent", back_populates="supervisor")

class Transcript(Base):
    __tablename__ = 'transcripts'
    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('agents.id'))
    content = Column(String)
    created_at = Column(DateTime)
    agent = relationship("Agent", back_populates="transcripts")
    tasks = relationship("Task", back_populates="transcript")

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    transcript_id = Column(Integer, ForeignKey('transcripts.id'))
    agent_id = Column(Integer, ForeignKey('agents.id'))
    description = Column(String)
    estimated_duration = Column(Float)  # Stored in minutes
    actual_duration = Column(Float)
    status = Column(String)  # pending, done, delayed, cant_do
    created_at = Column(DateTime)
    completed_at = Column(DateTime, nullable=True)
    transcript = relationship("Transcript", back_populates="tasks")
    agent = relationship("Agent", back_populates="tasks")

class TaskStatus(Enum):
    PENDING = "Pending"
    DONE = "Done"
    DELAYED = "Delayed"
    REJECTED = "Rejected"

# Pydantic models for request/response handling
class AgentCreate(BaseModel):
    name: str

class SupervisorCreate(BaseModel):
    name: str

class AssignRequest(BaseModel):
    agent_id: int
    supervisor_id: int

class TranscriptCreate(BaseModel):
    agent_id: int
    content: str

class TaskItem(BaseModel):
    task: str
    estimated_duration: str

class TaskResponse(BaseModel):
    description: str
    estimated_duration: float  # in minutes
    
class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]

class TaskList(BaseModel):
    tasks: List[str]

class TaskCompletionTimes(BaseModel):
    durations: List[float]

class KBChunkList(BaseModel):
    chunks: List[str]

class DifyResponse(BaseModel):
    event: str
    task_id: str
    id: str
    message_id: str
    conversation_id: str
    mode: str
    answer: str
    metadata: dict
    created_at: int

class ChatResponse(BaseModel):
    answer: str

class TaskWithDuration(BaseModel):
    task: str
    estimated_duration: str

class TaskWithDurationList(BaseModel):
    tasks: List[TaskWithDuration]

class TaskInfoResponse(BaseModel):
    id: str
    transcript_id: int
    agent_id: int
    description: str
    estimated_duration: float
    actual_duration: Optional[float] = None
    status: str
    created_at: str
    completed_at: Optional[str] = None

class TranscriptTasksResponse(BaseModel):
    transcript_id: int
    tasks: List[TaskInfoResponse]
