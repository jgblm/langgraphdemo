"""SQLAlchemy database models."""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, DateTime, Integer, ForeignKey,
    JSON, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from app.database import Base


class TaskStatus(str, enum.Enum):
    """Task status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    TAGS_COMPLETED = "tags_completed"
    PERSONA_COMPLETED = "persona_completed"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisTask(Base):
    """Main analysis task model."""
    __tablename__ = "analysis_tasks"

    id = Column(String(36), primary_key=True)
    brand = Column(String(255), nullable=False)
    region = Column(String(255), nullable=False)
    status = Column(
        SQLEnum(TaskStatus, values_callable=lambda x: [e.value for e in x]),
        default=TaskStatus.PENDING,
        nullable=False
    )

    # Step results stored as JSON
    tags = Column(JSON, nullable=True)
    tags_raw = Column(Text, nullable=True)

    persona = Column(JSON, nullable=True)
    persona_raw = Column(Text, nullable=True)

    scenes = Column(JSON, nullable=True)
    scenes_raw = Column(Text, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)
    error_step = Column(String(50), nullable=True)

    # Checkpoint: stores the current step for resume (tags_completed, persona_completed, completed)
    checkpoint_step = Column(String(50), nullable=True, default="pending")

    # Metadata
    langsmith_trace_id = Column(String(255), nullable=True)
    langsmith_observation_ids = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<AnalysisTask(id={self.id}, brand={self.brand}, status={self.status})>"

    def _get_status_value(self) -> str:
        """Get status as string value."""
        if isinstance(self.status, str):
            return self.status
        return self.status.value if hasattr(self.status, 'value') else str(self.status)

    @property
    def current_step(self) -> str:
        """
        Get current step name for workflow.
        
        Priority:
        1. checkpoint_step (explicit checkpoint from workflow)
        2. error_step (step where task failed)
        3. Status-based inference
        """
        # Priority 1: Explicit checkpoint
        if self.checkpoint_step is not None:
            return self.checkpoint_step
        
        # Priority 2: Error step
        if self.error_step is not None:
            return self.error_step
        
        # Priority 3: Status-based inference
        status_val = self._get_status_value()
        step_map = {
            "pending": "pending",
            "processing": "generating_tags",
            "tags_completed": "tags_completed",
            "persona_completed": "persona_completed",
            "completed": "completed",
            "failed": "failed",
        }
        return step_map.get(status_val, "unknown")

    def get_progress(self) -> float:
        """Get progress percentage."""
        status_val = self._get_status_value()
        progress_map = {
            "pending": 0.0,
            "processing": 0.25,
            "tags_completed": 0.5,
            "persona_completed": 0.75,
            "completed": 1.0,
            "failed": 0.0,
        }
        return progress_map.get(status_val, 0.0)
