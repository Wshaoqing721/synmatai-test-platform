from datetime import datetime
from typing import Optional
from enum import Enum
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    JSON,
    ForeignKey,
    Enum as SQLEnum,
    Boolean,
    Text,
)
from sqlalchemy.orm import relationship

from agent_test_platform.models.base import Base


class ConversationStatus(str, Enum):
    """对话状态"""
    PENDING = "pending"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    FAILED = "failed"


class NodeExecutionMode(str, Enum):
    """节点执行模式"""
    SINGLE_CALL = "single_call"
    MULTI_TURN_DIALOG = "multi_turn_dialog"
    POLLING = "polling"
    CONDITIONAL = "conditional"


class DialogTurn(Base):
    """单轮对话记录"""
    __tablename__ = "dialog_turns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_number = Column(Integer, nullable=False)

    # 用户消息
    user_message = Column(Text)

    # Agent 响应
    agent_response = Column(JSON)
    agent_response_raw = Column(Text)

    # AI 生成的回复
    ai_generated_reply = Column(Text)

    # 判断结果
    task_detected = Column(Boolean, default=False)
    task_id = Column(String(255))
    task_data = Column(JSON)

    completion_criteria_met = Column(Boolean, default=False)
    should_continue = Column(Boolean, default=True)

    # 执行信息
    duration_ms = Column(Float)
    error_message = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="turns")


class Conversation(Base):
    """完整的多轮对话"""
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_execution_id = Column(
        String(36),
        ForeignKey("user_executions.id"),
        nullable=False,
    )
    node_id = Column(String(36), nullable=False)
    node_name = Column(String(255))

    status = Column(SQLEnum(ConversationStatus), default=ConversationStatus.PENDING)
    execution_mode = Column(SQLEnum(NodeExecutionMode))

    # 对话配置
    config = Column(JSON)

    # 对话历史
    turns = relationship(
        "DialogTurn",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="DialogTurn.turn_number",
    )

    # 最终结果
    task_generated = Column(Boolean, default=False)
    task_id = Column(String(255))
    task_data = Column(JSON)

    total_turns = Column(Integer, default=0)
    duration_ms = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


class VirtualUserProfile(Base):
    """虚拟用户配置文件"""
    __tablename__ = "virtual_user_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_execution_id = Column(
        String(36),
        ForeignKey("user_executions.id"),
        nullable=False,
    )

    # 用户身份信息
    username = Column(String(255))
    user_role = Column(String(255))
    email = Column(String(255))

    # 用户偏好
    preferences = Column(JSON)

    # 对话模式
    dialog_personality = Column(String(255))
    initial_message = Column(Text)

    # 目标和约束
    task_description = Column(Text)
    target_task_keywords = Column(JSON)

    # 统计
    total_conversations = Column(Integer, default=0)
    successful_conversations = Column(Integer, default=0)
    average_turns_per_conversation = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)
