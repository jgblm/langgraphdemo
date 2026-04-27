"""API routes for marketing analysis."""
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import (
    TaskCreateRequest,
    TaskResponse,
    TaskListResponse,
    TaskResultResponse,
    HealthResponse,
    ErrorResponse
)
from app.services.task_service import task_service
from app.services.langsmith_service import langsmith_service
from app.models import TaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Marketing Analysis"])


async def run_task_background(task_id: str, full_restart: bool = False):
    """Background task to execute analysis."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            # full_restart=True means clear checkpoint and start fresh
            await task_service.execute_task(task_id, db, force_resume=not full_restart)
        except Exception as e:
            logger.error(f"Background task failed: {e}")
            await task_service.update_task_status(
                task_id,
                TaskStatus.FAILED,
                db,
                error_message=str(e),
                error_step="execution"
            )


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=201,
    summary="创建分析任务",
    description="创建一个新的营销分析任务，立即开始执行"
)
async def create_task(
    request: TaskCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Create a new marketing analysis task."""
    # Create task in database
    task = await task_service.create_task(
        brand=request.brand,
        region=request.region,
        db=db
    )

    # Start background execution
    background_tasks.add_task(run_task_background, task.id)

    return TaskResponse(
        id=task.id,
        brand=task.brand,
        region=task.region,
        status=task.status.value if hasattr(task.status, 'value') else str(task.status),
        progress=task.get_progress(),
        current_step=task.current_step,
        created_at=task.created_at,
        updated_at=task.updated_at
    )


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    summary="获取任务列表",
    description="分页获取所有分析任务"
)
async def list_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[TaskStatus] = Query(None, description="按状态筛选"),
    db: AsyncSession = Depends(get_db)
):
    """List all analysis tasks with pagination."""
    tasks, total = await task_service.list_tasks(
        db=db,
        page=page,
        page_size=page_size,
        status=status
    )

    return TaskListResponse(
        tasks=[
            TaskResponse(
                id=t.id,
                brand=t.brand,
                region=t.region,
                status=t.status.value if hasattr(t.status, 'value') else str(t.status),
                progress=t.get_progress(),
                current_step=t.current_step,
                tags=t.tags,
                persona=t.persona,
                scenes=t.scenes,
                error_message=t.error_message,
                created_at=t.created_at,
                updated_at=t.updated_at,
                completed_at=t.completed_at
            )
            for t in tasks
        ],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="获取任务详情",
    description="根据ID获取任务详情和当前进度"
)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get task details by ID."""
    task = await task_service.get_task(task_id, db)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskResponse(
        id=task.id,
        brand=task.brand,
        region=task.region,
        status=task.status.value if hasattr(task.status, 'value') else str(task.status),
        progress=task.get_progress(),
        current_step=task.current_step,
        tags=task.tags,
        persona=task.persona,
        scenes=task.scenes,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at
    )


@router.get(
    "/tasks/{task_id}/result",
    response_model=TaskResultResponse,
    summary="获取任务结果",
    description="获取任务的完整分析结果"
)
async def get_task_result(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get the complete result of an analysis task."""
    task = await task_service.get_task(task_id, db)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not completed. Current status: {task.status}"
        )

    trace_url = task_service.get_trace_url(task.langsmith_trace_id)

    return TaskResultResponse(
        task_id=task.id,
        brand=task.brand,
        region=task.region,
        status=task.status.value if hasattr(task.status, 'value') else str(task.status),
        tags=task.tags,
        persona=task.persona,
        scenes=task.scenes,
        langsmith_trace_url=trace_url
    )


@router.post(
    "/tasks/{task_id}/rerun",
    response_model=TaskResponse,
    summary="重新执行任务",
    description="重新执行任务，支持断点续传(默认)或从头重试"
)
async def rerun_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    resume: bool = Query(True, description="是否从断点续传(True)或从头重试(False)")
):
    """
    Re-run an existing task.
    
    - resume=True (默认): 从上次失败的步骤继续执行，保留已完成的结果
    - resume=False: 完全从头开始，清除所有中间结果
    """
    task = await task_service.get_task(task_id, db)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if resume:
        # Resume from checkpoint - keep existing results
        logger.info(f"[{task_id}] Resuming task from checkpoint")
    else:
        # Full restart - clear all results
        await task_service.update_task_status(
            task_id,
            TaskStatus.PENDING,
            db,
            tags=None,
            tags_raw=None,
            persona=None,
            persona_raw=None,
            scenes=None,
            scenes_raw=None,
            error_message=None,
            error_step=None,
            completed_at=None
        )
        logger.info(f"[{task_id}] Restarting task from scratch")

    # Start background execution
    background_tasks.add_task(run_task_background, task.id, not resume)

    await db.refresh(task)

    return TaskResponse(
        id=task.id,
        brand=task.brand,
        region=task.region,
        status=task.status.value if hasattr(task.status, 'value') else str(task.status),
        progress=task.get_progress(),
        current_step=task.current_step,
        created_at=task.created_at,
        updated_at=task.updated_at
    )


@router.delete(
    "/tasks/{task_id}",
    status_code=204,
    summary="删除任务",
    description="删除一个分析任务"
)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a task."""
    task = await task_service.get_task(task_id, db)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    await db.delete(task)
    await db.commit()

    return None


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="健康检查",
    description="检查服务健康状态"
)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint."""
    # Check database
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    # Check LangSmith
    langsmith_status = "disabled"
    if langsmith_service.is_enabled:
        langsmith_status = "healthy" if langsmith_service.health_check() else "unhealthy"

    return HealthResponse(
        status="healthy" if db_status == "healthy" else "degraded",
        database=db_status,
        langsmith=langsmith_status
    )
