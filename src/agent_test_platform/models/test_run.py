
from sqlalchemy import Column, String, Integer, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from agent_test_platform.models.base import Base
from enum import Enum


class TestRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TestRun(Base):
    """一次完整的测试执行"""
    
    __tablename__ = "test_run"
    
    scenario_name = Column(String(255), nullable=False)
    status = Column(SQLEnum(TestRunStatus), default=TestRunStatus.PENDING)
    
    num_users = Column(Integer, nullable=False)
    concurrency = Column(Integer, nullable=False)
    
    # 进度统计
    completed_users = Column(Integer, default=0)
    failed_users = Column(Integer, default=0)
    
    # 时间统计
    total_duration_ms = Column(Integer, default=0)
    
    # 额外信息
    config = Column(JSON)  # 完整的测试配置
    error_message = Column(String(2000))
    
    # 关系
    virtual_users = relationship("VirtualUser", back_populates="test_run")
    test_results = relationship("TestResult", back_populates="test_run")
