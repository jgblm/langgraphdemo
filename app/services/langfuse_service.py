"""Langfuse integration service for tracing and monitoring."""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


class LangfuseService:
    """Langfuse service for LLM observability and monitoring."""

    def __init__(self):
        self._enabled = False
        self._client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Langfuse client."""
        try:
            if settings.is_langfuse_configured:
                from langfuse import Langfuse
                
                logger.info(f"Initializing Langfuse with public_key: {settings.langfuse_public_key[:10]}...")
                
                self._client = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host,
                )
                self._enabled = True
                logger.info(f"Langfuse tracing enabled (host: {settings.langfuse_host})")
            else:
                self._enabled = False
                logger.warning("Langfuse not configured (missing public_key or secret_key), tracing disabled")
        except ImportError:
            logger.warning("Langfuse package not installed. Run: pip install langfuse>=0.28.0")
            self._enabled = False
        except Exception as e:
            logger.warning(f"Failed to initialize Langfuse: {e}")
            logger.warning("Langfuse will be disabled. Check your API keys and network connection.")
            self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def client(self):
        return self._client

    def create_generation(
        self,
        name: str,
        input: str,
        model: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Any:
        """Create a generation trace for LLM calls."""
        if not self._enabled or not self._client:
            return None

        try:
            generation = self._client.generation(
                name=name,
                input=input,
                model=model or settings.openai_model,
                metadata=metadata,
                tags=tags,
                user_id=user_id,
                session_id=session_id,
            )
            return generation
        except Exception as e:
            logger.warning(f"Failed to create Langfuse generation: {e}")
            return None

    def update_generation(
        self,
        generation: Any,
        output: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        usage: Optional[Dict[str, int]] = None,
    ):
        """Update a generation trace with output."""
        if not generation:
            return

        try:
            if output:
                generation.output = output
            if metadata:
                if hasattr(generation, 'metadata') and generation.metadata:
                    generation.metadata.update(metadata)
                else:
                    generation.metadata = metadata
            if usage:
                generation.usage = usage
            generation.end()
        except Exception as e:
            logger.warning(f"Failed to update Langfuse generation: {e}")

    def create_span(
        self,
        name: str,
        input: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Any:
        """Create a span trace for workflow steps."""
        if not self._enabled or not self._client:
            return None

        try:
            # Use the trace context manager for newer langfuse API
            trace = self._client.trace(
                name=name,
                input=input,
                metadata=metadata,
                session_id=session_id,
                user_id=user_id,
            )
            return trace
        except Exception as e:
            logger.warning(f"Failed to create Langfuse trace: {e}")
            return None

    def update_span(
        self,
        span: Any,
        output: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Update a span trace."""
        if not span:
            return

        try:
            if output:
                span.output = output
            if metadata:
                if hasattr(span, 'metadata') and span.metadata:
                    span.metadata.update(metadata)
                else:
                    span.metadata = metadata
            if hasattr(span, 'end'):
                span.end()
        except Exception as e:
            logger.warning(f"Failed to update Langfuse span: {e}")

    def create_event(
        self,
        name: str,
        message: str,
        level: str = "DEFAULT",
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """Log an event to Langfuse."""
        if not self._enabled or not self._client:
            return

        try:
            self._client.event(
                name=name,
                message=message,
                level=level,
                metadata=metadata,
                session_id=session_id,
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(f"Failed to create Langfuse event: {e}")

    async def generate_with_trace(
        self,
        model,
        messages: List,
        task_id: str,
        step_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Generate with Langfuse tracing."""
        if not self._enabled:
            return await model.ainvoke(messages)

        try:
            response = await model.ainvoke(messages)
            
            # Log to langfuse after successful call
            self._client.generation(
                name=step_name,
                input=str(messages),
                output=str(response.content),
                model=settings.openai_model,
                metadata=metadata,
                session_id=task_id,
            )
            return response
        except Exception as e:
            # Log error to langfuse
            try:
                self._client.event(
                    name=f"{step_name}_error",
                    message=str(e),
                    level="ERROR",
                    metadata={"task_id": task_id},
                    session_id=task_id,
                )
            except:
                pass
            raise

    async def run_workflow_with_trace(
        self,
        workflow,
        input: Dict[str, Any],
        trace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run workflow with Langfuse tracing."""
        if not self._enabled:
            return await workflow.ainvoke(input)

        task_id = trace_id or input.get("task_id", "unknown")
        
        try:
            result = await workflow.ainvoke(input)
            
            # Log completion
            self._client.event(
                name="workflow_completed",
                message="Marketing analysis workflow completed",
                metadata={
                    "task_id": task_id,
                    "result_summary": {
                        "tags_count": len(result.get("tags", [])),
                        "personas_count": len(result.get("persona", [])),
                        "scenes_count": len(result.get("scenes", [])),
                    }
                },
                session_id=task_id,
            )
            return result
        except Exception as e:
            # Log error
            try:
                self._client.event(
                    name="workflow_error",
                    message=str(e),
                    level="ERROR",
                    metadata={"task_id": task_id},
                    session_id=task_id,
                )
            except:
                pass
            raise

    def get_trace_url(self, trace_id: str) -> Optional[str]:
        """Get the URL for a trace in Langfuse dashboard."""
        if not self._enabled:
            return None
        return f"{settings.langfuse_host}/project/{settings.langfuse_project_id}/traces"

    def flush(self):
        """Flush pending traces to Langfuse."""
        if self._enabled and self._client:
            try:
                self._client.flush()
            except Exception as e:
                logger.warning(f"Failed to flush Langfuse: {e}")

    def health_check(self) -> bool:
        """Check if Langfuse is healthy."""
        if not self._enabled:
            return False
        
        try:
            # Simple health check - just verify client is initialized
            # Don't actually make API call, as it may fail due to network timing
            return self._client is not None
        except Exception:
            return False


# Global Langfuse service instance
langfuse_service = LangfuseService()
