
from contextlib import asynccontextmanager
import datetime
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from agent_test_platform.config.settings import settings
from agent_test_platform.config.logger import setup_logging, logger
from agent_test_platform.api import routes
from agent_test_platform.api import multi_turn
from agent_test_platform.api import node_config_routes
from agent_test_platform.storage.database import Database
from agent_test_platform.storage.query import ResultQuery
from agent_test_platform.ws.manager import WSConnectionManager
from agent_test_platform.core.orchestrator import TestOrchestrator
from agent_test_platform.core.smart_orchestrator import SmartTestOrchestrator
from agent_test_platform.services.node_config_service import NodeConfigService
from agent_test_platform.services.scenario_service import ScenarioService

# 全局实例
db_instance: Optional[Database] = None
orchestrator_instance: Optional[TestOrchestrator] = None
ws_manager_instance: Optional[WSConnectionManager] = None
result_query_instance: Optional[ResultQuery] = None
smart_orchestrator_instance: Optional[SmartTestOrchestrator] = None
node_config_service_instance: Optional[NodeConfigService] = None
scenario_service_instance: Optional[ScenarioService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""

    global db_instance
    global orchestrator_instance
    global ws_manager_instance
    global result_query_instance
    global smart_orchestrator_instance
    global node_config_service_instance
    global scenario_service_instance

    logger.info("=" * 60)
    logger.info(f"Starting {settings.APP_NAME}...")
    logger.info("=" * 60)

    try:
        # 1) 初始化数据库
        db_instance = Database()
        await db_instance.initialize()

        # 2) 初始化编排器
        orchestrator_instance = TestOrchestrator(db_instance)

        # 3) 初始化 WebSocket 管理器
        ws_manager_instance = WSConnectionManager()

        # 4) 注册进度回调
        async def progress_callback(**kwargs):
            if not ws_manager_instance:
                return

            if hasattr(ws_manager_instance, "send_progress"):
                await ws_manager_instance.send_progress(**kwargs)
                return

            run_id = kwargs.get("run_id") or kwargs.get("runId")
            if not run_id:
                return

            event = {
                "type": "progress",
                "runId": run_id,
                "timestamp": datetime.datetime.now().isoformat(),
                "data": kwargs,
            }
            await ws_manager_instance.broadcast(run_id, event)

        orchestrator_instance.register_progress_callback(progress_callback)

        # 5) 初始化智能编排器
        smart_orchestrator_instance = SmartTestOrchestrator(
            db=db_instance,
            http_client=orchestrator_instance.http_client,
            openai_api_key=settings.OPENAI_API_KEY,
            on_event_callback=progress_callback,
        )

        # 6) 初始化结果查询
        result_query_instance = ResultQuery(db_instance)

        # 7) 初始化节点配置服务
        node_config_service_instance = NodeConfigService(db_instance)
        scenario_service_instance = ScenarioService(db_instance)

        # 8) 注入全局实例到 API 模块
        multi_turn.smart_orchestrator = smart_orchestrator_instance
        routes.orchestrator = orchestrator_instance
        routes.ws_manager = ws_manager_instance
        routes.db = db_instance
        routes.storage = result_query_instance
        node_config_routes.node_config_service = node_config_service_instance
        routes.scenario_service = scenario_service_instance
        routes.node_config_service = node_config_service_instance

        logger.info("=" * 60)
        logger.info("Application started successfully")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Failed to start application: {e}", exc_info=True)
        raise

    yield

    logger.info("=" * 60)
    logger.info(f"Shutting down {settings.APP_NAME}...")
    logger.info("=" * 60)

    try:
        # AgentHTTPClient 当前是按请求创建 httpx.AsyncClient，无需显式 close
        if db_instance:
            await db_instance.close()

        logger.info("=" * 60)
        logger.info("Application shutdown complete")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )
    
    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 包含路由
    app.include_router(routes.router)
    app.include_router(multi_turn.router)
    app.include_router(node_config_routes.router)

    @app.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "version": settings.APP_VERSION,
            "database": "initialized" if db_instance else "not initialized",
        }

    @app.get("/")
    async def root():
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "health": "/health",
        }

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(exc),
                "type": type(exc).__name__,
            },
        )
    
    return app


# 创建应用实例
setup_logging()
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "agent_test_platform.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )