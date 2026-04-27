"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.api.routes import router
from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting up application...")

    # Initialize LangGraph checkpoint
    from app.graph.workflow import get_checkpointer
    try:
        checkpointer = await get_checkpointer()
        logger.info("LangGraph checkpointer initialized successfully")
    except Exception as e:
        logger.error(f"LangGraph checkpointer init failed: {e}", exc_info=True)
        logger.warning("Checkpoint functionality will be unavailable")

    if settings.is_langsmith_configured:
        logger.info("LangSmith tracing enabled")
    else:
        logger.warning("LangSmith not configured, tracing disabled")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    # Close checkpoint connection pool
    from app.graph.workflow import _checkpointer
    if _checkpointer and hasattr(_checkpointer, 'conn') and hasattr(_checkpointer.conn, 'close'):
        await _checkpointer.conn.close()
        logger.info("Checkpoint connection pool closed")


# Create FastAPI application
app = FastAPI(
    title="Marketing Analysis API",
    description="基于LangGraph的营销三步分析链API：品牌地区 → Tags → Persona → 场景",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint - serve frontend."""
    frontend_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if frontend_path.exists():
        return HTMLResponse(frontend_path.read_text(encoding="utf-8"))
    return {
        "name": "Marketing Analysis API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug
    )
