"""Pydantic schemas for API request/response."""
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, field_validator, model_validator
from app.models import TaskStatus


def _fix_flat_list_to_dicts(items: Any, expected_fields: set) -> Optional[List[Dict[str, Any]]]:
    """
    Fix data that might be in wrong format (flat list instead of dict list).
    Returns a clean list of dicts or None.
    """
    if items is None:
        return None

    if not isinstance(items, list):
        return None

    # Already correct format
    if all(isinstance(item, dict) for item in items):
        return items

    # Flat list detected - try to reconstruct
    if items and all(isinstance(item, str) for item in items):
        result = []
        current = {}

        i = 0
        while i < len(items):
            item = items[i]
            # Check if this is a name field
            if item.lower() in {"name", "姓名", "名称"}:
                if current:
                    result.append(current)
                if i + 1 < len(items):
                    current = {"name": items[i + 1]}
                    i += 2
                    continue
            # Check if this is a field name
            elif item.lower() in {f.lower() for f in expected_fields}:
                if current and "name" in current:
                    result.append(current)
                    current = {}
                if i + 1 < len(items):
                    current[item] = items[i + 1]
                    i += 2
                    continue
            # Regular key-value pair
            if i + 1 < len(items):
                next_item = items[i + 1]
                if next_item.lower() not in {"name", "姓名", "名称"}:
                    current[item] = next_item
                    i += 2
                    continue
            i += 1

        if current:
            result.append(current)

        return result if result else None

    return None


class TaskCreateRequest(BaseModel):
    """Request schema for creating a new analysis task."""
    brand: str = Field(..., min_length=1, max_length=255, description="品牌名称")
    region: str = Field(..., min_length=1, max_length=255, description="地区/城市")


class TaskResponse(BaseModel):
    """Response schema for task information."""
    id: str
    brand: str
    region: str
    status: str
    progress: float = Field(description="进度百分比 (0.0-1.0)")
    current_step: str
    tags: Optional[List[str]] = None
    persona: Optional[List[Dict[str, Any]]] = None
    scenes: Optional[List[Dict[str, Any]]] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator('persona', mode='before')
    @classmethod
    def fix_persona_field(cls, v):
        """Auto-fix persona if it's in wrong format (flat list)."""
        persona_fields = {
            "name", "姓名", "age_range", "age", "年龄段", "gender", "性别",
            "occupation", "职业", "income_level", "income", "收入水平",
            "education", "教育背景", "family_status", "家庭状况",
            "consumption_habits", "消费习惯", "media_preference", "媒体偏好",
            "pain_points", "pain_point", "营销触点", "marketing_channels",
            "summary", "总结", "描述"
        }
        fixed = _fix_flat_list_to_dicts(v, persona_fields)
        return fixed if fixed is not None else []

    @field_validator('scenes', mode='before')
    @classmethod
    def fix_scenes_field(cls, v):
        """Auto-fix scenes if it contains invalid items."""
        scene_fields = {
            "name", "场景名称", "target_persona", "目标人群",
            "scene_description", "场景描述", "timing", "时间节点",
            "marketing_content", "营销内容", "touchpoints", "触达方式",
            "expected_outcome", "预期效果", "creative_highlight", "创意亮点"
        }
        fixed = _fix_flat_list_to_dicts(v, scene_fields)
        return fixed if fixed is not None else []

    @classmethod
    def from_orm_model(cls, task) -> "TaskResponse":
        """Create from ORM model, converting status to string."""
        status_str = task.status.value if hasattr(task.status, 'value') else str(task.status)
        return cls(
            id=task.id,
            brand=task.brand,
            region=task.region,
            status=status_str,
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


class TaskListResponse(BaseModel):
    """Response schema for listing tasks."""
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int


class TaskResultResponse(BaseModel):
    """Response schema for task result."""
    task_id: str
    brand: str
    region: str
    status: str
    tags: Optional[List[str]] = None
    persona: Optional[List[Dict[str, Any]]] = None
    scenes: Optional[List[Dict[str, Any]]] = None
    langsmith_trace_url: Optional[str] = None

    @field_validator('persona', mode='before')
    @classmethod
    def fix_persona_field(cls, v):
        """Auto-fix persona if it's in wrong format (flat list)."""
        persona_fields = {
            "name", "姓名", "age_range", "age", "年龄段", "gender", "性别",
            "occupation", "职业", "income_level", "income", "收入水平",
            "education", "教育背景", "family_status", "家庭状况",
            "consumption_habits", "消费习惯", "media_preference", "媒体偏好",
            "pain_points", "pain_point", "营销触点", "marketing_channels",
            "summary", "总结", "描述"
        }
        fixed = _fix_flat_list_to_dicts(v, persona_fields)
        return fixed if fixed is not None else []

    @field_validator('scenes', mode='before')
    @classmethod
    def fix_scenes_field(cls, v):
        """Auto-fix scenes if it contains invalid items."""
        scene_fields = {
            "name", "场景名称", "target_persona", "目标人群",
            "scene_description", "场景描述", "timing", "时间节点",
            "marketing_content", "营销内容", "touchpoints", "触达方式",
            "expected_outcome", "预期效果", "creative_highlight", "创意亮点"
        }
        fixed = _fix_flat_list_to_dicts(v, scene_fields)
        return fixed if fixed is not None else []


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    database: str
    langsmith: str
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    """Error response schema."""
    error: str
    detail: Optional[str] = None
    task_id: Optional[str] = None
