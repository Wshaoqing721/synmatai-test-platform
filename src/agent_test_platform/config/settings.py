
import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置"""
    
    # 应用
    APP_NAME: str = "Agent Test Platform"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = os.getenv("DEBUG", "False") == "True"
    
    # 服务器
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # 数据库
    # SQLAlchemy async URL, e.g. postgresql+asyncpg://user:pass@host:5432/db
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://agent:agent@localhost:5432/agent_test_platform",
    )

    # 本地文件输出目录（测试结果 JSON 等），与数据库无关
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "./data/results")
    
    # Agent 后台接口
    AGENT_API_BASE_URL: str = os.getenv("AGENT_API_BASE_URL", "http://localhost:8080/api")
    AGENT_API_TIMEOUT: float = float(os.getenv("AGENT_API_TIMEOUT", "30.0"))
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # 测试配置
    DEFAULT_NUM_USERS: int = 5
    DEFAULT_CONCURRENCY: int = 2
    MAX_WAIT_TIME: int = 300  # 5 分钟超时
    STEP_POLL_INTERVAL: float = 1.0  # 步骤轮询间隔（秒）
    
    # WebSocket
    WEBSOCKET_HEARTBEAT_INTERVAL: float = 2.0
    
    # 日志
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "json"
    
    # 场景配置目录
    SCENARIOS_DIR: Path = Path(__file__).parent.parent / "scenarios" / "examples"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()