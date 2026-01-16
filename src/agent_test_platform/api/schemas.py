
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime


class TestRunRequest(BaseModel):
    """启动测试请求"""
    scenario_name: str
    num_users: Optional[int] = None
    concurrency: Optional[int] = None


class TestRunResponse(BaseModel):
    """启动测试响应"""
    test_run_id: str
    status: str


class TestStatusResponse(BaseModel):
    """测试状态响应"""
    id: str
    scenario_name: str
    status: str
    num_users: int
    completed_users: int
    failed_users: int
    total_duration_ms: int
    created_at: str


class TestStepDetail(BaseModel):
    """步骤详情"""
    step_index: int
    step_name: str
    status: str
    duration_ms: float
    request_body: Optional[Dict[str, Any]]
    response_body: Optional[Dict[str, Any]]
    evaluation_result: Optional[Dict[str, Any]]


class VirtualUserDetail(BaseModel):
    """虚拟用户详情"""
    user_id: str
    user_index: int
    status: str
    total_duration_ms: int
    num_requests: int
    num_errors: int
    test_steps: List[TestStepDetail]


class TestResultResponse(BaseModel):
    """测试结果响应"""
    summary: Dict[str, Any]
    detail: Dict[str, Any]


class CancelTestResponse(BaseModel):
    """取消测试响应"""
    success: bool
    message: str