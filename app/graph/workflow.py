"""LangGraph workflow for marketing analysis chain with native PostgresSaver checkpointing."""
import json
import re
import logging
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.graph.prompts import (
    TAG_GENERATION_PROMPT,
    PERSONA_GENERATION_PROMPT,
    SCENE_GENERATION_PROMPT,
    SYSTEM_PROMPT
)
from app.services.langsmith_service import langsmith_service
from app.services.langfuse_service import langfuse_service

logger = logging.getLogger(__name__)


class MarketingAnalysisState(TypedDict):
    """State for the marketing analysis workflow."""
    task_id: str
    brand: str
    region: str

    # Step 1: Tags
    tags: Optional[List[str]]
    tags_raw: Optional[str]

    # Step 2: Persona
    persona: Optional[List[Dict[str, Any]]]
    persona_raw: Optional[str]

    # Step 3: Scenes
    scenes: Optional[List[Dict[str, Any]]]
    scenes_raw: Optional[str]

    # Metadata
    error: Optional[str]
    current_step: str


def create_llm():
    """Create LLM instance with or without LangSmith tracing."""
    # LangSmith tracing is enabled via environment variables in config
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def parse_json_response(response: str, expected_dict_fields: Optional[List[str]] = None) -> Any:
    """
    Parse JSON from LLM response, handling various formats.
    """
    response = response.strip()

    # Remove markdown code blocks
    if "```json" in response:
        response = response.split("```json")[1].split("```")[0]
    elif "```" in response:
        parts = response.split("```")
        if len(parts) >= 3:
            response = parts[1]

    # Extract JSON array or object
    start_idx = response.find("[")
    end_idx = response.rfind("]")
    
    if start_idx == -1:
        start_idx = response.find("{")
        end_idx = response.rfind("}")
    
    if start_idx != -1 and end_idx != -1:
        json_str = response[start_idx:end_idx + 1]
    else:
        json_str = response

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Fix common JSON issues
    fixed = json_str
    
    # Remove trailing commas
    fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)
    
    # Fix unquoted property names
    fixed = re.sub(r"'([^']+)':", r'"\1":', fixed)
    
    # Handle newlines and special chars inside strings
    fixed = re.sub(r'(?<=:)\s*"([^"]*)"', 
                   lambda m: ': "' + m.group(1).replace('\n', '\\n').replace('\r', '\\r').replace('"', '\\"') + '"', 
                   fixed)
    
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Last resort: extract string list
    try:
        if response.strip().startswith('['):
            items = re.findall(r'"([^"]*)"', response)
            if items:
                # Validate expected_dict_fields if provided
                if expected_dict_fields and isinstance(expected_dict_fields, list):
                    if len(items) > len(expected_dict_fields):
                        dicts = try_reconstruct_dicts(items, expected_dict_fields)
                        if dicts:
                            return dicts
                return items
    except Exception as e:
        logger.warning(f"Last resort parsing failed: {e}")

    raise ValueError(f"JSON parse failed, LLM returned: {response[:100]}...")


def try_reconstruct_dicts(items: List[str], expected_fields: List[str]) -> Optional[List[Dict[str, Any]]]:
    """Try to reconstruct dicts from flat string list (key-value alternating pattern)."""
    logger.debug(f"try_reconstruct_dicts called with {len(items)} items, expected_fields={expected_fields[:5]}...")
    
    # Validate expected_fields contains strings only
    if not expected_fields or not all(isinstance(f, str) for f in expected_fields):
        logger.warning(f"expected_fields contains invalid items")
        return None
    
    logger.debug(f"First 20 items: {items[:20]}")
    
    # Build a set of expected field names for faster lookup
    expected_fields_set = set(expected_fields)
    expected_fields_lower = {f.lower() for f in expected_fields}
    
    result = []
    current_dict = {}
    
    # Method 1: Try alternating key-value pattern (index-based)
    # items[0]=key1, items[1]=value1, items[2]=key2, items[3]=value2, ...
    i = 0
    while i < len(items) - 1:
        potential_key = items[i]
        potential_value = items[i + 1]
        
        # Check if potential_key matches an expected field
        key_match = None
        for field in expected_fields:
            if potential_key.lower() == field.lower():
                key_match = field
                break
        
        if key_match:
            # Check if next item looks like a value (not a field name)
            if potential_value.lower() not in expected_fields_lower:
                current_dict[key_match] = potential_value
                i += 2
                continue
        
        # Check if current item could be a primary field (name)
        primary_fields = ["name", "场景名称", "场景"]
        if potential_key.lower() in [f.lower() for f in primary_fields]:
            # This looks like the start of a new dict
            if current_dict and "name" in current_dict:
                result.append(current_dict)
                current_dict = {}
            current_dict["name"] = potential_value
            i += 2
            continue
        
        i += 1
    
    if current_dict and "name" in current_dict:
        result.append(current_dict)
    
    if result and all("name" in d for d in result):
        logger.info(f"Reconstructed {len(result)} dicts from flat list")
        return result
    
    logger.warning(f"Failed to reconstruct dicts. Got {len(result)} partial results, last dict: {current_dict}")
    return None


def try_group_by_names(items: List[str]) -> Optional[List[Dict[str, Any]]]:
    """
    Try to reconstruct personas by grouping consecutive items after a 'name' field.
    This handles the case where LLM outputs alternating key-value pairs.
    """
    logger.debug(f"try_group_by_names called with {len(items)} items")

    if not items:
        return None

    # Fields that typically follow a name and start a new persona
    name_fields = {"name", "姓名", "名称"}
    # Fields that indicate a new persona section
    new_persona_fields = {"age_range", "age", "年龄段", "gender", "性别",
                          "occupation", "职业", "income_level", "income", "收入水平"}

    result = []
    current_persona = {}

    i = 0
    while i < len(items):
        item = items[i]

        # Check if this item looks like a name field
        if item.lower() in {f.lower() for f in name_fields}:
            # Save previous persona if exists
            if current_persona and "name" in current_persona:
                result.append(current_persona)
            # Get the name value
            if i + 1 < len(items):
                current_persona = {"name": items[i + 1]}
                i += 2
                continue

        # Check if this looks like a new persona marker
        if item.lower() in {f.lower() for f in new_persona_fields}:
            # Save previous persona if exists
            if current_persona and "name" in current_persona:
                result.append(current_persona)
                current_persona = {}
            # This item is a field name, next item is value
            if i + 1 < len(items):
                current_persona[item] = items[i + 1]
                i += 2
                continue

        # Regular key-value pair
        if i + 1 < len(items):
            next_item = items[i + 1]
            # Only add if next item doesn't look like a field name
            if next_item.lower() not in {f.lower() for f in name_fields}:
                current_persona[item] = next_item
                i += 2
                continue

        i += 1

    # Don't forget the last persona
    if current_persona and "name" in current_persona:
        result.append(current_persona)

    if result and all("name" in d for d in result):
        logger.info(f"Reconstructed {len(result)} personas by name grouping")
        return result

    logger.warning(f"Name grouping failed. Got {len(result)} partial results")
    return None if not result else result


async def generate_tags(state: MarketingAnalysisState) -> MarketingAnalysisState:
    """Step 1: Generate marketing tags based on brand and region."""
    logger.info(f"[{state['task_id']}] Generating tags for {state['brand']} in {state['region']}")

    task_id = state['task_id']

    # Create Langfuse span for this step
    span = langfuse_service.create_span(
        name="generate_tags",
        input={"brand": state["brand"], "region": state["region"]},
        metadata={"task_id": task_id},
        session_id=task_id,
    )

    try:
        llm = create_llm()

        prompt = TAG_GENERATION_PROMPT.format(
            brand=state["brand"],
            region=state["region"]
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]

        # Use Langfuse tracing if enabled
        if langfuse_service.is_enabled:
            response = await langfuse_service.generate_with_trace(
                llm,
                messages,
                task_id=task_id,
                step_name="generate_tags",
                metadata={"step": "tags"}
            )
        else:
            response = await llm.ainvoke(messages)
        
        response_content = response.content

        tags = parse_json_response(response_content)

        state["tags"] = tags if isinstance(tags, list) else []
        state["tags_raw"] = response_content
        state["current_step"] = "tags_completed"

        # Update span with output
        langfuse_service.update_span(
            span,
            output={"tags": state["tags"], "count": len(state["tags"])}
        )

        logger.info(f"[{state['task_id']}] Generated {len(state['tags'])} tags")

    except Exception as e:
        logger.error(f"[{state['task_id']}] Error generating tags: {str(e)}", exc_info=True)
        state["error"] = str(e)
        state["current_step"] = "failed"
        langfuse_service.update_span(span, output={"error": str(e)})

    return state


async def generate_persona(state: MarketingAnalysisState) -> MarketingAnalysisState:
    """Step 2: Generate personas based on tags."""
    logger.info(f"[{state['task_id']}] Generating persona from {len(state.get('tags', []))} tags")

    if state.get("error"):
        return state

    task_id = state['task_id']

    # Create Langfuse span for this step
    span = langfuse_service.create_span(
        name="generate_persona",
        input={"brand": state["brand"], "region": state["region"], "tags": state.get("tags", [])},
        metadata={"task_id": task_id},
        session_id=task_id,
    )

    persona_expected_fields = [
        "name", "姓名",
        "age_range", "年龄段", "age",
        "gender", "性别",
        "occupation", "职业",
        "income_level", "收入水平", "income",
        "education", "教育背景", "education_background",
        "family_status", "家庭状况",
        "consumption_habits", "消费习惯",
        "media_preference", "媒体偏好",
        "pain_points", "痛点需求", "pain_point",
        "marketing_channels", "营销触点", "channels",
        "summary", "总结", "描述"
    ]

    try:
        llm = create_llm()

        prompt = PERSONA_GENERATION_PROMPT.format(
            brand=state["brand"],
            region=state["region"],
            tags=", ".join(state.get("tags", []))
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]

        # Use Langfuse tracing if enabled
        if langfuse_service.is_enabled:
            response = await langfuse_service.generate_with_trace(
                llm,
                messages,
                task_id=task_id,
                step_name="generate_persona",
                metadata={"step": "persona", "tags_count": len(state.get("tags", []))}
            )
        else:
            response = await llm.ainvoke(messages)
        
        response_content = response.content

        persona = parse_json_response(response_content, expected_dict_fields=persona_expected_fields)

        # Handle flat list reconstruction
        if isinstance(persona, list):
            # Check if it's a flat list of strings (key-value alternating pattern)
            if persona and all(isinstance(item, str) for item in persona):
                logger.info(f"[{state['task_id']}] Detected flat list with {len(persona)} items, trying to reconstruct")
                reconstructed = try_reconstruct_dicts(persona, persona_expected_fields)
                if reconstructed:
                    persona_list = reconstructed
                    logger.info(f"[{state['task_id']}] Successfully reconstructed {len(persona_list)} persona dicts")
                else:
                    # Fallback: try simple name-based grouping
                    persona_list = try_group_by_names(persona)
                    if persona_list:
                        logger.info(f"[{state['task_id']}] Reconstructed {len(persona_list)} personas by name grouping")
                    else:
                        logger.warning(f"[{state['task_id']}] Could not reconstruct persona dicts, returning empty")
                        persona_list = []
            elif all(isinstance(item, dict) for item in persona):
                persona_list = persona
            else:
                persona_list = [item for item in persona if isinstance(item, dict)]
        else:
            persona_list = []

        # Limit to max 8 personas (safety limit)
        state["persona"] = persona_list[:8]
        state["persona_raw"] = response_content
        state["current_step"] = "persona_completed"

        # Update span with output
        langfuse_service.update_span(
            span,
            output={"personas": state["persona"], "count": len(state["persona"])}
        )

        logger.info(f"[{state['task_id']}] Generated {len(state['persona'])} personas (from {len(persona_list) if isinstance(persona, list) else 0} items)")

    except Exception as e:
        logger.error(f"[{state['task_id']}] Error generating persona: {str(e)}", exc_info=True)
        state["error"] = str(e)
        state["current_step"] = "failed"
        langfuse_service.update_span(span, output={"error": str(e)})

    return state


async def generate_scenes(state: MarketingAnalysisState) -> MarketingAnalysisState:
    """Step 3: Generate marketing scenes based on personas."""
    logger.info(f"[{state['task_id']}] Generating scenes from {len(state.get('persona', []))} personas")

    if state.get("error"):
        return state

    task_id = state['task_id']

    # Create Langfuse span for this step
    span = langfuse_service.create_span(
        name="generate_scenes",
        input={
            "brand": state["brand"],
            "region": state["region"],
            "personas_count": len(state.get("persona", []))
        },
        metadata={"task_id": task_id},
        session_id=task_id,
    )

    scene_expected_fields = [
        "name", "场景名称", "target_persona", "目标人群",
        "scene_description", "场景描述", "timing", "时间节点",
        "marketing_content", "营销内容", "touchpoints", "触达方式",
        "expected_outcome", "预期效果", "creative_highlight", "创意亮点"
    ]

    try:
        llm = create_llm()

        prompt = SCENE_GENERATION_PROMPT.format(
            brand=state["brand"],
            region=state["region"],
            personas=json.dumps(state.get("persona", []), ensure_ascii=False, indent=2)
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]

        # Use Langfuse tracing if enabled
        if langfuse_service.is_enabled:
            response = await langfuse_service.generate_with_trace(
                llm,
                messages,
                task_id=task_id,
                step_name="generate_scenes",
                metadata={"step": "scenes", "personas_count": len(state.get("persona", []))}
            )
        else:
            response = await llm.ainvoke(messages)
        
        response_content = response.content
        
        logger.info(f"[{state['task_id']}] Raw scenes response (first 500 chars): {response_content[:500]}")

        scenes = parse_json_response(response_content, expected_dict_fields=scene_expected_fields)

        if isinstance(scenes, list):
            valid_scenes = [s for s in scenes if isinstance(s, dict)]
            if valid_scenes:
                state["scenes"] = valid_scenes
            else:
                logger.warning(f"[{state['task_id']}] LLM returned flat list ({len(scenes)} items), scenes will be empty. First 5 items: {scenes[:5]}")
                state["scenes"] = []
        else:
            state["scenes"] = []
        
        state["scenes_raw"] = response_content
        state["current_step"] = "completed"

        # Update span with output
        langfuse_service.update_span(
            span,
            output={"scenes": state["scenes"], "count": len(state["scenes"])}
        )

        logger.info(f"[{state['task_id']}] Generated {len(state['scenes'])} scenes")

    except Exception as e:
        logger.error(f"[{state['task_id']}] Error generating scenes: {str(e)}", exc_info=True)
        state["error"] = str(e)
        state["current_step"] = "failed"
        langfuse_service.update_span(span, output={"error": str(e)})

    return state


def create_workflow(checkpointer=None):
    """Create the LangGraph workflow with optional checkpoint support."""
    workflow = StateGraph(MarketingAnalysisState)

    workflow.add_node("generate_tags", generate_tags)
    workflow.add_node("generate_persona", generate_persona)
    workflow.add_node("generate_scenes", generate_scenes)

    workflow.set_entry_point("generate_tags")

    workflow.add_edge("generate_tags", "generate_persona")
    workflow.add_edge("generate_persona", "generate_scenes")
    workflow.add_edge("generate_scenes", END)

    # Compile with checkpointer if provided
    return workflow.compile(checkpointer=checkpointer)


async def setup_checkpointer_async():
    """
    Setup and return the AsyncPostgresSaver checkpointer.
    
    Uses psycopg_pool.AsyncConnectionPool with proper initialization.
    """
    import psycopg
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool
    
    db_url = settings.sync_database_url
    
    # Step 1: Verify psycopg can connect at all
    try:
        conn = await psycopg.AsyncConnection.connect(db_url, connect_timeout=10)
        await conn.execute("SELECT 1")
        await conn.close()
        logger.info("Direct psycopg async connection test: OK")
    except Exception as e:
        logger.error(f"psycopg async connection test FAILED: {e}")
        raise

    # Step 2: Create pool - pass connect_timeout via connection kwargs
    pool = AsyncConnectionPool(
        conninfo=db_url,
        min_size=1,
        max_size=5,
        timeout=60,
        open=False,
        kwargs={"connect_timeout": 30}  # pass to each connection
    )
    
    # Open the pool explicitly
    await pool.open()
    logger.info("Connection pool opened")
    
    # Step 3: Verify pool can get a connection
    try:
        async with pool.connection() as conn:
            result = await conn.execute("SELECT 1")
            row = await result.fetchone()
            logger.info(f"Pool connection test: OK (result={row})")
    except Exception as e:
        logger.error(f"Pool connection test FAILED: {e}")
        raise
    
    # Step 4: Create checkpointer (tables must be created via init_checkpoints.sql)
    checkpointer = AsyncPostgresSaver(pool)
    logger.info("AsyncPostgresSaver checkpointer initialized")
    
    return checkpointer


# Global checkpointer instance (initialized at startup)
_checkpointer = None


async def get_checkpointer():
    """Get or create the global checkpointer instance."""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = await setup_checkpointer_async()
    return _checkpointer


def create_checkpointed_workflow():
    """Create workflow with PostgresSaver checkpointing enabled."""
    # Note: For sync operations, this returns the plain workflow
    # The async version with checkpointing is used in run_marketing_analysis
    return marketing_workflow_plain


# Workflow instance without checkpointer (used for fresh start)
marketing_workflow_plain = create_workflow(checkpointer=None)

# Workflow instance with checkpointer (initialized lazily)
_marketing_workflow_checkpoint = None


async def get_checkpointed_workflow():
    """Get or create the checkpointed workflow instance."""
    global _marketing_workflow_checkpoint
    if _marketing_workflow_checkpoint is None:
        checkpointer = await get_checkpointer()
        _marketing_workflow_checkpoint = create_workflow(checkpointer=checkpointer)
    return _marketing_workflow_checkpoint


def get_step_from_state(state: Dict[str, Any]) -> str:
    """Get current step name from state."""
    return state.get("current_step", "pending")


async def run_marketing_analysis(
    task_id: str,
    brand: str,
    region: str,
    trace_id: Optional[str] = None,
    saved_state: Optional[Dict[str, Any]] = None,
    resume_from_checkpoint: bool = True
) -> Dict[str, Any]:
    """
    Run the marketing analysis workflow with native checkpoint support.
    
    Uses LangGraph's AsyncPostgresSaver for automatic state persistence.
    On failure, the workflow state is saved to PostgreSQL and can be
    resumed from the exact failure point.
    
    Args:
        task_id: Unique task identifier
        brand: Brand name
        region: Region/area
        trace_id: LangSmith trace ID
        saved_state: (Deprecated) Previous state for backward compatibility
        resume_from_checkpoint: If True, use PostgresSaver; if False, start fresh
    
    Returns:
        Final state after workflow completion
    """
    config = {
        "configurable": {
            "thread_id": task_id,  # Use task_id as the checkpoint thread
        }
    }
    
    initial_state = {
        "task_id": task_id,
        "brand": brand,
        "region": region,
        "tags": saved_state.get("tags") if saved_state else None,
        "tags_raw": saved_state.get("tags_raw") if saved_state else None,
        "persona": saved_state.get("persona") if saved_state else None,
        "persona_raw": saved_state.get("persona_raw") if saved_state else None,
        "scenes": saved_state.get("scenes") if saved_state else None,
        "scenes_raw": saved_state.get("scenes_raw") if saved_state else None,
        "error": None,
        "current_step": saved_state.get("current_step", "pending") if saved_state else "pending"
    }
    
    try:
        if resume_from_checkpoint:
            # Get checkpointed workflow
            workflow = await get_checkpointed_workflow()
            
            # Check current state in checkpoint
            current_state = await workflow.aget_state(config)
            
            if current_state and current_state.values and current_state.values.get("current_step") not in [None, "pending", "failed"]:
                step = current_state.values.get("current_step", "pending")
                logger.info(f"[{task_id}] Resuming from checkpoint step: {step}")
                # Continue from checkpoint (pass None to continue)
                result = await workflow.ainvoke(None, config)
            else:
                # Start fresh (including failed or pending states)
                logger.info(f"[{task_id}] Starting fresh workflow")
                result = await workflow.ainvoke(initial_state, config)
        else:
            # Force fresh start (ignore checkpoint)
            logger.info(f"[{task_id}] Starting fresh (checkpoint ignored)")
            result = await marketing_workflow_plain.ainvoke(initial_state, config)
        
        # Extract values from result
        if isinstance(result, dict):
            return result
        elif hasattr(result, 'values') and isinstance(result.values, dict):
            return dict(result.values)
        elif hasattr(result, 'values'):
            return result.values
        return result
        
    except Exception as e:
        logger.error(f"[{task_id}] Workflow execution failed: {str(e)}", exc_info=True)
        return {
            **initial_state,
            "error": str(e),
            "current_step": "failed"
        }
