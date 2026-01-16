
from sqlalchemy import Column, String, Integer, Float, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from agent_test_platform.models.base import Base
from enum import Enum


class TestResultStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class TestResult(Base):
    """测试结果汇总"""
    
    __tablename__ = "test_result"
    
    test_run_id = Column(String(36), ForeignKey("test_run.id"), nullable=False)
    
    # 整体状态
    status = Column(SQLEnum(TestResultStatus))
    
    # 统计数据
    total_users = Column(Integer)
    successful_users = Column(Integer)
    failed_users = Column(Integer)
    
    total_requests = Column(Integer)
    successful_requests = Column(Integer)
    failed_requests = Column(Integer)
    
    # 性能数据
    avg_response_time_ms = Column(Float)
    max_response_time_ms = Column(Float)
    min_response_time_ms = Column(Float)
    
    total_duration_ms = Column(Integer)
    
    # 汇总信息
    summary = Column(JSON)  # 详细的汇总信息
    
    # 关系
    test_run = relationship("agent_test_platform.models.test_run.TestRun", back_populates="test_results")
