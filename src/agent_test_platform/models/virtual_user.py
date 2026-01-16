
from sqlalchemy import Column, String, Integer, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from agent_test_platform.models.base import Base
from enum import Enum


class VirtualUserStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class VirtualUser(Base):
    """虚拟用户"""
    
    __tablename__ = "virtual_user"
    
    test_run_id = Column(String(36), ForeignKey("test_run.id"), nullable=False)
    user_index = Column(Integer, nullable=False)  # 用户编号，如 0, 1, 2...
    
    status = Column(SQLEnum(VirtualUserStatus), default=VirtualUserStatus.IDLE)
    
    # 当前执行进度
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, default=0)
    
    # 用户级统计
    num_requests = Column(Integer, default=0)
    num_errors = Column(Integer, default=0)
    total_duration_ms = Column(Integer, default=0)
    
    # 用户上下文（如 token, session_id）
    context = Column(JSON, default=dict)
    
    # 对话历史
    conversation_history = Column(JSON, default=list)
    
    error_message = Column(String(2000))
    
    # 关系
    test_run = relationship("agent_test_platform.models.test_run.TestRun", back_populates="virtual_users")
    test_steps = relationship("TestStep", back_populates="virtual_user")
