"""Langfuse integration service for tracing and monitoring."""
import logging
from typing import Optional, Dict, Any, List

from app.config import settings

logger = logging.getLogger(__name__)


class LangfuseService:
    """Langfuse service for LLM observability and monitoring using LangChain callback."""

    def __init__(self):
        self._enabled = False
        self._callback = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Langfuse client with LangChain callback."""
        try:
            if settings.is_langfuse_configured:
                from langfuse import Langfuse
                from langfuse.callback import CallbackHandler
                
                logger.info(f"Initializing Langfuse with public_key: {settings.langfuse_public_key[:10]}...")
                
                # Create Langfuse client (for configuration)
                self._client = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host,
                )
                
                # Create LangChain callback handler
                self._callback = CallbackHandler(
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
    def callback(self):
        """Get the LangChain callback handler for tracing."""
        return self._callback

    @property
    def client(self):
        return self._client

    async def generate_with_trace(
        self,
        model,
        messages: List,
        task_id: str,
        step_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Generate with Langfuse tracing using callback."""
        if not self._enabled or not self._callback:
            return await model.ainvoke(messages)

        try:
            # Use the callback handler for tracing
            response = await model.ainvoke(
                messages,
                config={"callbacks": [self._callback]}
            )
            return response
        except Exception as e:
            logger.error(f"LLM call failed during Langfuse tracing: {e}")
            # Fallback to regular call without tracing
            return await model.ainvoke(messages)

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
            return self._client is not None and self._callback is not None
        except Exception:
            return False


# Global Langfuse service instance
langfuse_service = LangfuseService()
