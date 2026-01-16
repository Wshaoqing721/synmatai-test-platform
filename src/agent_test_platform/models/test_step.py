
from sqlalchemy import Column, String, Integer, Float, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from agent_test_platform.models.base import Base
from enum import Enum


class TestStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TestStep(Base):
    """单个 HTTP 调用步骤"""
    
    __tablename__ = "test_step"
    
    virtual_user_id = Column(String(36), ForeignKey("virtual_user.id"), nullable=False)
    step_index = Column(Integer, nullable=False)
    
    # 步骤配置
    step_name = Column(String(255))
    http_method = Column(String(10), default="POST")
    endpoint = Column(String(500))
    
    status = Column(SQLEnum(TestStepStatus), default=TestStepStatus.PENDING)
    
    # HTTP 详情
    request_body = Column(JSON)
    response_status_code = Column(Integer)
    response_body = Column(JSON)
    
    # 耗时
    duration_ms = Column(Float, default=0)
    
    # 评估结果
    evaluation_result = Column(JSON)  # 步骤评估的结果，如 {'should_continue': True, 'reason': '...'}
    
    error_message = Column(String(2000))
    
    # 关系
    virtual_user = relationship("VirtualUser", back_populates="test_steps")