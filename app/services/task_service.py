"""Task service for managing analysis tasks."""
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisTask, TaskStatus
from app.graph.workflow import run_marketing_analysis
from app.services.langsmith_service import langsmith_service

logger = logging.getLogger(__name__)


class TaskService:
    """Service for managing marketing analysis tasks."""

    @staticmethod
    def generate_task_id() -> str:
        """Generate a unique task ID."""
        return str(uuid.uuid4())

    @staticmethod
    def _get_step_from_status(status: TaskStatus) -> str:
        """Map status to workflow step name."""
        step_map = {
            TaskStatus.PENDING: "pending",
            TaskStatus.PROCESSING: "pending",
            TaskStatus.TAGS_COMPLETED: "tags_completed",
            TaskStatus.PERSONA_COMPLETED: "persona_completed",
            TaskStatus.COMPLETED: "completed",
            TaskStatus.FAILED: "failed",
        }
        return step_map.get(status, "pending")

    async def create_task(
        self,
        brand: str,
        region: str,
        db: AsyncSession
    ) -> AnalysisTask:
        """Create a new analysis task."""
        task_id = self.generate_task_id()

        # Create LangSmith trace if enabled
        trace_id = None
        if langsmith_service.is_enabled:
            trace_id = "tracing-enabled"

        task = AnalysisTask(
            id=task_id,
            brand=brand,
            region=region,
            status=TaskStatus.PENDING,
            langsmith_trace_id=trace_id
        )

        db.add(task)
        await db.commit()
        await db.refresh(task)

        logger.info(f"Created task {task_id} for {brand} in {region}")

        return task

    async def get_task(
        self,
        task_id: str,
        db: AsyncSession
    ) -> Optional[AnalysisTask]:
        """Get a task by ID."""
        result = await db.execute(
            select(AnalysisTask).where(AnalysisTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        status: Optional[TaskStatus] = None
    ) -> tuple:
        """List tasks with pagination."""
        query = select(AnalysisTask)

        if status:
            query = query.where(AnalysisTask.status == status)

        from sqlalchemy import func
        count_query = select(func.count()).select_from(AnalysisTask)
        if status:
            count_query = count_query.where(AnalysisTask.status == status)
        count_result = await db.execute(count_query)
        total = count_result.scalar()

        query = query.order_by(AnalysisTask.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        tasks = result.scalars().all()

        return tasks, total

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        db: AsyncSession,
        **kwargs
    ) -> Optional[AnalysisTask]:
        """Update task status and optional fields."""
        task = await self.get_task(task_id, db)
        if not task:
            return None

        task.status = status

        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)

        if status == TaskStatus.COMPLETED:
            task.completed_at = datetime.utcnow()

        await db.commit()
        await db.refresh(task)

        return task

    async def save_checkpoint(
        self,
        task_id: str,
        db: AsyncSession,
        step_name: str,
        **kwargs
    ) -> None:
        """
        Save checkpoint at the end of each step.
        
        This allows resuming from this point if the task fails later.
        """
        status_map = {
            "tags_completed": TaskStatus.TAGS_COMPLETED,
            "persona_completed": TaskStatus.PERSONA_COMPLETED,
            "completed": TaskStatus.COMPLETED,
            "failed": TaskStatus.FAILED,
        }

        status = status_map.get(step_name, TaskStatus.PROCESSING)

        await self.update_task_status(
            task_id,
            status,
            db,
            **kwargs
        )

        logger.info(f"[{task_id}] Checkpoint saved at step: {step_name}")

    async def execute_task(
        self,
        task_id: str,
        db: AsyncSession,
        force_resume: bool = False
    ) -> Dict[str, Any]:
        """
        Execute the marketing analysis workflow using native LangGraph checkpointing.
        
        Uses PostgresSaver for automatic state persistence - workflow state is
        automatically saved to PostgreSQL after each step, enabling seamless
        resume from any failure point.
        
        Args:
            task_id: Task ID
            db: Database session
            force_resume: If True, always resume from checkpoint; if False, only resume failed tasks
        """
        task = await self.get_task(task_id, db)
        if not task:
            return {"error": "Task not found"}

        # Check if task can be resumed
        resumable_statuses = [
            TaskStatus.PENDING,
            TaskStatus.PROCESSING,
            TaskStatus.TAGS_COMPLETED,
            TaskStatus.PERSONA_COMPLETED,
            TaskStatus.FAILED
        ]

        if task.status not in resumable_statuses:
            if task.status == TaskStatus.COMPLETED and not force_resume:
                return {"error": "Task already completed", "task": task}

        # Update status to processing
        await self.update_task_status(
            task_id,
            TaskStatus.PROCESSING,
            db
        )

        logger.info(f"Starting analysis for task {task_id}")

        # Run the workflow with native PostgresSaver checkpointing
        # The workflow state is automatically persisted to PostgreSQL
        result = await run_marketing_analysis(
            task_id=task_id,
            brand=task.brand,
            region=task.region,
            trace_id=task.langsmith_trace_id,
            resume_from_checkpoint=force_resume or task.status != TaskStatus.PENDING
        )

        # Map result step to status
        status_map = {
            "tags_completed": TaskStatus.TAGS_COMPLETED,
            "persona_completed": TaskStatus.PERSONA_COMPLETED,
            "completed": TaskStatus.COMPLETED,
            "failed": TaskStatus.FAILED,
        }

        final_status = status_map.get(
            result.get("current_step", ""),
            TaskStatus.FAILED if result.get("error") else TaskStatus.COMPLETED
        )

        # Save final results to database
        await self.update_task_status(
            task_id,
            final_status,
            db,
            tags=result.get("tags"),
            tags_raw=result.get("tags_raw"),
            persona=result.get("persona"),
            persona_raw=result.get("persona_raw"),
            scenes=result.get("scenes"),
            scenes_raw=result.get("scenes_raw"),
            checkpoint_step=result.get("current_step"),
            error_message=result.get("error"),
            error_step=result.get("current_step") if result.get("error") else None
        )

        logger.info(f"Completed analysis for task {task_id}, status: {final_status}")

        return result

    def get_trace_url(self, trace_id: Optional[str]) -> Optional[str]:
        """Get LangSmith trace URL."""
        if not trace_id:
            return None
        return langsmith_service.get_trace_url(trace_id)


# Global task service instance
task_service = TaskService()
