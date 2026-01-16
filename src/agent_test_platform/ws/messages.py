
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
from datetime import datetime
import json


@dataclass
class ProgressMessage:
    """进度消息"""
    
    run_id: str
    user_id: str
    step_index: int
    step_name: str
    status: str  # pending, running, success, failed, timeout
    duration_ms: float = 0
    response_status_code: Optional[int] = None
    error_message: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
    
    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        data = asdict(self)
        return json.dumps(data)


@dataclass
class AggregateProgressMessage:
    """聚合进度消息（整体测试进度）"""
    
    run_id: str
    total_users: int
    completed_users: int
    failed_users: int
    current_step: int  # 平均的当前步骤
    total_steps: int
    elapsed_time_s: float
    status: str  # running, completed, failed
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
    
    def to_json(self) -> str:
        data = asdict(self)
        return json.dumps(data)