"""LangSmith integration service for tracing."""
import logging
from typing import Optional, Dict, Any, List

from app.config import settings

logger = logging.getLogger(__name__)


class LangSmithService:
    """LangSmith service for LLM observability."""

    def __init__(self):
        self._enabled = False
        self._initialize_client()

    def _initialize_client(self):
        """Initialize LangSmith client."""
        try:
            if settings.is_langsmith_configured:
                settings.setup_langsmith()
                self._enabled = True
                logger.info("LangSmith tracing enabled")
            else:
                self._enabled = False
                logger.warning("LangSmith not configured, tracing disabled")
        except Exception as e:
            logger.warning(f"Failed to initialize LangSmith: {e}")
            self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def generate_with_trace(
        self,
        model,
        messages: List,
        task_id: str,
        step_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Generate with LangSmith tracing."""
        return await model.ainvoke(messages)

    async def run_workflow_with_trace(
        self,
        workflow,
        input: Dict[str, Any],
        trace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run workflow with LangSmith tracing."""
        return await workflow.ainvoke(input)

    def get_trace_url(self, trace_id: str) -> Optional[str]:
        """Get the URL for a trace."""
        if not self._enabled:
            return None
        project = settings.langsmith_project
        return f"https://smith.langchain.com/projects/{project}/traces?session={trace_id}"

    def health_check(self) -> bool:
        """Check if LangSmith is healthy."""
        return self._enabled


# Global LangSmith service instance
langsmith_service = LangSmithService()
