
from enum import Enum
from typing import Optional


class TestState(Enum):
    """测试状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UserState(Enum):
    """虚拟用户状态"""
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"  # 等待响应
    COMPLETED = "completed"
    FAILED = "failed"


class StateMachine:
    """简单的状态机，管理测试状态"""
    
    def __init__(self, initial_state: TestState = TestState.IDLE):
        self.state = initial_state
        self.transitions = {
            TestState.IDLE: {TestState.RUNNING, TestState.FAILED},
            TestState.RUNNING: {TestState.PAUSED, TestState.COMPLETED, TestState.FAILED, TestState.CANCELLED},
            TestState.PAUSED: {TestState.RUNNING, TestState.CANCELLED},
            TestState.COMPLETED: set(),
            TestState.FAILED: set(),
            TestState.CANCELLED: set(),
        }
    
    def can_transition(self, new_state: TestState) -> bool:
        """检查是否可以转移到新状态"""
        return new_state in self.transitions.get(self.state, set())
    
    def transition(self, new_state: TestState) -> bool:
        """尝试转移到新状态"""
        if self.can_transition(new_state):
            self.state = new_state
            return True
        return False
    
    def get_current_state(self) -> TestState:
        """获取当前状态"""
        return self.state
