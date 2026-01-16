
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class StepConfig:
    """单个步骤配置"""
    
    name: str
    method: str = "POST"
    endpoint: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    
    # 评估条件（决定是否继续）
    extraction: Optional[Dict[str, str]] = None  # 从响应中提取字段
    condition: Optional[str] = None  # 如 "response.task_id != null"
    should_continue: Optional[str] = None  # 如 "response.status == 'continue'"
    
    max_retries: int = 0
    timeout: float = 30.0


@dataclass
class ScenarioConfig:
    """测试场景配置"""
    
    name: str
    description: str = ""
    
    # 用户配置
    num_users: int = 1
    concurrency: int = 1
    ramp_up_time: int = 0  # 秒，用户启动间隔
    
    # Agent API 配置
    agent_endpoint: str = "/chat"
    
    # 步骤定义
    steps: List[StepConfig] = field(default_factory=list)
    
    # 成功条件
    success_condition: Optional[str] = None  # 如 "response.has_task_id"
    
    # 超时
    max_wait_time: int = 300  # 秒