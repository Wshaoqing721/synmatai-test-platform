
from typing import Dict, Any
from enum import Enum
from sqlalchemy import Column, String, JSON, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.orm import relationship
from agent_test_platform.models.base import Base


class NodeExecutionMode(str, Enum):
    """节点执行模式"""
    SINGLE_CALL = "single_call"
    MULTI_TURN_DIALOG = "multi_turn_dialog"
    POLLING = "polling"
    CONDITIONAL = "conditional"


class NodeConfig(Base):
    """节点配置 - 存储到数据库"""
    __tablename__ = "node_configs"

    scenario_id = Column(String(36), nullable=False, index=True)  # 场景 ID
    node_id = Column(String(255), nullable=False, index=True)  # 节点 ID
    node_name = Column(String(255))  # 节点名称

    # 节点类型（与 DSL 的 type 对齐，例如 action / multi_turn_dialog）
    node_type = Column(String(50))

    # 执行模式
    execution_mode = Column(SQLEnum(NodeExecutionMode), nullable=False)

    # 出口条件（JSON 存储）
    exit_condition = Column(JSON, default=dict)  # {max_turns, timeout_seconds, task_keywords, ...}

    # 消息生成策略（JSON 存储）
    message_generation = Column(JSON, default=dict)  # {type, templates, ai_model, ...}

    # 任务检测策略（JSON 存储）
    task_detection = Column(JSON, default=dict)  # {type, keywords, regex_pattern, ...}

    # 完整配置备份
    full_config = Column(JSON, default=dict)  # 完整的配置对象

    # 节点依赖（与 DSL 的 depends_on 对齐），非必填
    dependencies = Column(JSON, default=list)

    # 单次调用节点的 HTTP 配置（与 DSL 的 config 对齐），非必填
    config = Column(JSON, default=dict)

    # 备注
    description = Column(Text)

    histories = relationship(
        "NodeConfigHistory",
        back_populates="node_config",
        cascade="all, delete-orphan",
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "scenario_id": self.scenario_id,
            "node_id": self.node_id,
            "node_name": self.node_name,
            "node_type": self.node_type,
            "execution_mode": self.execution_mode.value if self.execution_mode else None,
            "dependencies": self.dependencies or [],
            "exit_condition": self.exit_condition or {},
            "message_generation": self.message_generation or {},
            "task_detection": self.task_detection or {},
            "config": self.config or {},
            "full_config": self.full_config or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "description": self.description,
        }


class NodeConfigHistory(Base):
    """节点配置历史 - 记录配置变更"""
    __tablename__ = "node_config_history"

    node_config_id = Column(String(36), ForeignKey("node_configs.id"), nullable=False, index=True)

    # 变更内容
    config_before = Column(JSON)  # 变更前的配置
    config_after = Column(JSON)  # 变更后的配置

    # 变更信息
    change_type = Column(String(50), nullable=False)  # create, update, delete
    change_reason = Column(Text)
    changed_by = Column(String(255))

    node_config = relationship("NodeConfig", back_populates="histories")