
from enum import Enum
from sqlalchemy import Column, String, Integer, Float, DateTime, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from agent_test_platform.models.base import Base


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class NodeType(str, Enum):
    START = "start"
    ACTION = "action"
    ASSERTION = "assertion"
    CONDITION = "condition"
    END = "end"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ScenarioStatus(str, Enum):
    """场景状态"""
    ACTIVE = "active"           # 活跃
    INACTIVE = "inactive"       # 非活跃
    ARCHIVED = "archived"       # 已归档
    
class Scenario(Base):
    """测试场景（包含节点 DAG）"""
    __tablename__ = "scenarios"

    name = Column(String(255), nullable=False)
    description = Column(String(1000))
    status = Column(SQLEnum(ScenarioStatus), default=ScenarioStatus.ACTIVE, nullable=False)  # 场景状态
   
    def __init__(self, **kwargs):
        if "status" not in kwargs:
            kwargs["status"] = ScenarioStatus.ACTIVE
        super().__init__(**kwargs)

    def to_dict(self):
        status = self.status
        status_value = status.value if hasattr(status, "value") else (str(status) if status is not None else None)
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": status_value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

# ============================================================
# TestRun 测试执行
# ============================================================

class TestRun(Base):
    """一次完整的测试执行"""
    __tablename__ = "test_runs"

    name = Column(String(255))
    scenario_id = Column(String(36), ForeignKey("scenarios.id"), nullable=False)
    scenario_name = Column(String(255))
    status = Column(SQLEnum(RunStatus), default=RunStatus.PENDING)
    progress = Column(Integer, default=0)  # 0-100
    total_users = Column(Integer, default=0)
    current_users = Column(Integer, default=0)  # 当前完成的用户数
    start_time = Column(DateTime)
    end_time = Column(DateTime)

    # 统计信息
    success_users = Column(Integer, default=0)
    failed_users = Column(Integer, default=0)

    user_executions = relationship("UserExecution", cascade="all, delete-orphan")


# ============================================================
# VirtualUser 虚拟用户执行
# ============================================================

class UserExecution(Base):
    """单个虚拟用户的执行记录"""
    __tablename__ = "user_executions"

    test_run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)
    user_index = Column(Integer, nullable=False)
    status = Column(SQLEnum(NodeStatus), default=NodeStatus.PENDING)  # pending, running, success, failed
    current_node_id = Column(String(36))
    start_time = Column(DateTime)
    end_time = Column(DateTime)

    context = Column(JSON)  # 用户上下文（token, session 等）
    conversation_history = Column(JSON)  # 对话历史

    node_executions = relationship("NodeExecution", cascade="all, delete-orphan")


# ============================================================
# NodeExecution 节点执行状态
# ============================================================

class NodeExecution(Base):
    """单个节点的执行状态"""
    __tablename__ = "node_executions"

    user_execution_id = Column(String(36), ForeignKey("user_executions.id"), nullable=False)
    node_id = Column(String(36), nullable=False)
    node_name = Column(String(255))
    status = Column(SQLEnum(NodeStatus), default=NodeStatus.PENDING)

    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration = Column(Float)  # 毫秒

    # 请求/响应详情
    request_body = Column(JSON)
    request_headers = Column(JSON)

    response_status = Column(Integer)
    response_headers = Column(JSON)
    response_body = Column(JSON)

    error_message = Column(String(1000))


# ============================================================
# TestSummary 测试结果汇总
# ============================================================

class TestSummary(Base):
    """测试结果统计"""
    __tablename__ = "test_summaries"

    test_run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)

    # 用户统计
    total_users = Column(Integer, default=0)
    success_users = Column(Integer, default=0)
    failed_users = Column(Integer, default=0)
    success_rate = Column(Float, default=0)  # 0-100

    # 响应时间统计（毫秒）
    avg_response_time = Column(Float)
    min_response_time = Column(Float)
    max_response_time = Column(Float)
    p50_response_time = Column(Float)
    p95_response_time = Column(Float)
    p99_response_time = Column(Float)

    # 节点统计
    failed_nodes = Column(JSON)  # List[FailedNodeStat]
    node_stats = Column(JSON)    # List[NodeStat]