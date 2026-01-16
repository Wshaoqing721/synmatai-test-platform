
from fastapi import APIRouter, HTTPException, WebSocket, Path, Query
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import selectinload
from agent_test_platform.api.schemas import *
from agent_test_platform.models.node_based import Scenario, TestRun, UserExecution, TestSummary, RunStatus
from agent_test_platform.config.logger import logger
import asyncio

from agent_test_platform.services.node_config_service import NodeConfigService
from agent_test_platform.services.scenario_service import ScenarioService


router = APIRouter(prefix="/api", tags=["v2"])

# 全局实例（在 main.py 中初始化）
orchestrator = None
ws_manager = None
db = None
# 全局实例（在 main.py 中初始化）
scenario_service: Optional[ScenarioService] = None
node_config_service: Optional[NodeConfigService] = None

# ============================================================
# 1. 测试运行 API
# ============================================================

@router.get("/runs")
async def list_test_runs() -> List[Dict]:
    """获取所有测试运行"""
    try:
        # 从数据库查询
        test_runs = await db.query_all(TestRun)
        return [
            {
                "id": run.id,
                "name": run.name,
                "scenarioId": run.scenario_id,
                "scenarioName": run.scenario_name,
                "status": run.status.value,
                "progress": run.progress,
                "totalUsers": run.total_users,
                "currentUsers": run.current_users,
                "startTime": run.start_time ,
                "endTime": run.end_time  if run.end_time else None,
                "createdAt": run.created_at ,
            }
            for run in test_runs
        ]
    except Exception as e:
        logger.error(f"Failed to list test runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{runId}")
async def get_test_run(runId: str = Path(...)) -> Dict:
    """获取单个测试运行"""
    try:
        test_run = await db.get(TestRun, runId)
        if not test_run:
            raise HTTPException(status_code=404, detail="Test run not found")
        
        return {
            "id": test_run.id,
            "name": test_run.name,
            "scenarioId": test_run.scenario_id,
            "scenarioName": test_run.scenario_name,
            "status": test_run.status.value,
            "progress": test_run.progress,
            "totalUsers": test_run.total_users,
            "currentUsers": test_run.current_users,
            "startTime": test_run.start_time ,
            "endTime": test_run.end_time  if test_run.end_time else None,
            "createdAt": test_run.created_at ,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get test run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs")
async def create_test_run(payload: Dict) -> Dict:
    """创建新的测试运行"""
    try:
        scenario_id = payload.get("scenarioId")
        name = payload.get("name")
        user_count = payload.get("userCount")
        
        # 获取场景
        scenario = await db.get(Scenario, scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        # 创建测试运行
        test_run = TestRun(
            name=name,
            scenario_id=scenario_id,
            scenario_name=scenario.name,
            status=RunStatus.PENDING,
            progress=0,
            total_users=user_count,
            current_users=0,
            start_time=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        
        test_run = await db.create(test_run)
        
        return {
            "id": test_run.id,
            "name": test_run.name,
            "scenarioId": test_run.scenario_id,
            "status": test_run.status.value,
            "progress": 0,
            "totalUsers": user_count,
            "currentUsers": 0,
            "createdAt": test_run.created_at ,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create test run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{runId}/start")
async def start_test_run(runId: str = Path(...)) -> Dict:
    """启动测试"""
    try:
        test_run = await db.get(TestRun, runId)
        if not test_run:
            raise HTTPException(status_code=404, detail="Test run not found")
        
        # 更新状态
        test_run.status = RunStatus.RUNNING
        test_run.start_time = datetime.utcnow()
        await db.update(test_run)
        
        # 启动编排器
        asyncio.create_task(orchestrator._run_users(runId, test_run.scenario_id))
        
        return {"status": "started"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start test run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{runId}/stop")
async def stop_test_run(runId: str = Path(...)) -> Dict:
    """停止测试"""
    try:
        test_run = await db.get(TestRun, runId)
        if not test_run:
            raise HTTPException(status_code=404, detail="Test run not found")
        
        test_run.status = RunStatus.FAILED
        test_run.end_time = datetime.utcnow()
        await db.update(test_run)
        
        return {"status": "stopped"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop test run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 2. 场景 API
# ============================================================


@router.post("/scenarios")
async def create_scenario(
    name: str = Query(..., min_length=1, max_length=255),
    description: Optional[str] = Query(None, max_length=1000),
) -> Dict[str, Any]:
    """
    创建新的测试场景
    
    Args:
        name: 场景名称（必需）
        description: 场景描述（可选）
    
    Returns:
        新创建的场景信息
    """
    
    if not scenario_service:
        raise HTTPException(status_code=500, detail="ScenarioService not initialized")
    
    try:
        scenario = await scenario_service.create_scenario(
            name=name,
            description=description or "",
        )
        
        logger.info(f"Scenario created: {scenario.id}")
        
        return {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "status": scenario.status.value if hasattr(scenario.status, "value") else str(scenario.status),
            "nodes": [],
            "created_at": scenario.created_at ,
            "message": "Scenario created successfully",
        }
    
    except Exception as e:
        logger.error(f"Failed to create scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 2. 获取场景
# ============================================================

@router.get("/scenarios")
async def list_scenarios(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    列表所有测试场景（包含关联的节点配置）
    
    Args:
        skip: 跳过的记录数
        limit: 返回的最大记录数
        status: 按状态筛选（active, inactive, archived）
    
    Returns:
        场景列表（包含每个场景的节点）
    """
    
    if not scenario_service:
        raise HTTPException(status_code=500, detail="ScenarioService not initialized")
    
    try:
        all_scenarios = await scenario_service.list_scenarios()
        
        # 按状态筛选
        if status:
            all_scenarios = [s for s in all_scenarios if s.status.value == status]
        
        total = len(all_scenarios)
        scenarios = all_scenarios[skip:skip + limit]
        
        result_scenarios = []
        for scenario in scenarios:
            # 获取该场景下的所有节点配置
            nodes = await node_config_service.list_scenario_nodes(scenario.id)

            scenario_status = scenario.status
            scenario_status_value = (
                scenario_status.value
                if hasattr(scenario_status, "value")
                else (str(scenario_status) if scenario_status is not None else None)
            )
            
            result_scenarios.append({
                "id": scenario.id,
                "name": scenario.name,
                "description": scenario.description,
                "status": scenario_status_value,
                "node_count": len(nodes),
                "nodes": [
                    {
                        "id": node.id,
                        "node_id": node.node_id,
                        "name": node.node_name,
                        "execution_mode": node.execution_mode.value,
                    }
                    for node in nodes
                ],
                "created_at": scenario.created_at ,
                "updated_at": scenario.updated_at ,
            })
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "scenarios": result_scenarios,
        }
    
    except Exception as e:
        logger.error(f"Failed to list scenarios: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str = Path(...)) -> Dict[str, Any]:
    """
    获取单个场景及其关联的所有节点配置
    
    Args:
        scenario_id: 场景 ID
    
    Returns:
        场景详情及其所有节点
    """
    
    if not scenario_service or not node_config_service:
        raise HTTPException(status_code=500, detail="Services not initialized")
    
    try:
        scenario = await scenario_service.get_scenario(scenario_id)
        
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        # 获取该场景下的所有节点
        nodes = await node_config_service.list_scenario_nodes(scenario_id)
        
        return {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "status": scenario.status.value if hasattr(scenario.status, "value") else str(scenario.status),
            "node_count": len(nodes),
            "nodes": [
                {
                    "id": node.id,
                    "node_id": node.node_id,
                    "name": node.node_name,
                    "execution_mode": node.execution_mode.value,
                    "exit_condition": node.exit_condition,
                    "message_generation": node.message_generation,
                    "task_detection": node.task_detection,
                    "created_at": node.created_at ,
                    "updated_at": node.updated_at ,
                }
                for node in nodes
            ],
            "created_at": scenario.created_at ,
            "updated_at": scenario.updated_at ,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 3. 更新场景
# ============================================================

@router.put("/scenarios/{scenario_id}")
async def update_scenario(
    scenario_id: str = Path(...),
    name: Optional[str] = Query(None, min_length=1, max_length=255),
    description: Optional[str] = Query(None, max_length=1000),
    status: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    更新场景信息
    
    Args:
        scenario_id: 场景 ID
        name: 新的场景名称（可选）
        description: 新的场景描述（可选）
        status: 新的状态（active, inactive, archived）
    
    Returns:
        更新后的场景信息
    """
    
    if not scenario_service:
        raise HTTPException(status_code=500, detail="ScenarioService not initialized")
    
    try:
        scenario = await scenario_service.update_scenario(
            scenario_id=scenario_id,
            name=name,
            description=description,
            status=status,
        )
        
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        logger.info(f"Scenario updated: {scenario_id}")
        
        return {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "status": scenario.status.value if hasattr(scenario.status, "value") else str(scenario.status),
            "updated_at": scenario.updated_at ,
            "message": "Scenario updated successfully",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 4. 删除场景
# ============================================================

@router.delete("/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: str = Path(...)) -> Dict[str, Any]:
    """
    删除场景（关联的节点配置也会被删除）
    
    Args:
        scenario_id: 场景 ID
    
    Returns:
        删除结果
    """
    
    if not scenario_service or not node_config_service:
        raise HTTPException(status_code=500, detail="Services not initialized")
    
    try:
        # 先删除该场景下的所有节点配置
        nodes = await node_config_service.list_scenario_nodes(scenario_id)
        for node in nodes:
            await node_config_service.delete_node_config(
                scenario_id=scenario_id,
                node_id=node.node_id,
                change_reason="Scenario deleted",
            )
        
        # 再删除场景
        success = await scenario_service.delete_scenario(scenario_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        logger.info(f"Scenario deleted: {scenario_id}")
        
        return {
            "scenario_id": scenario_id,
            "status": "deleted",
            "message": "Scenario deleted successfully",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 5. 场景统计
# ============================================================

@router.get("/scenarios/{scenario_id}/stats")
async def get_scenario_stats(scenario_id: str = Path(...)) -> Dict[str, Any]:
    """
    获取场景的统计信息
    
    Args:
        scenario_id: 场景 ID
    
    Returns:
        场景统计信息（节点数量、各类型节点数等）
    """
    
    if not scenario_service or not node_config_service:
        raise HTTPException(status_code=500, detail="Services not initialized")
    
    try:
        scenario = await scenario_service.get_scenario(scenario_id)
        
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        # 获取节点
        nodes = await node_config_service.list_scenario_nodes(scenario_id)
        
        # 统计各执行模式的节点数
        mode_stats = {}
        detection_stats = {}
        
        for node in nodes:
            # 执行模式统计
            mode = node.execution_mode.value
            mode_stats[mode] = mode_stats.get(mode, 0) + 1
            
            # 检测策略统计
            detection_type = node.task_detection.get("type", "unknown")
            detection_stats[detection_type] = detection_stats.get(detection_type, 0) + 1
        
        return {
            "scenario_id": scenario_id,
            "scenario_name": scenario.name,
            "total_nodes": len(nodes),
            "execution_mode_stats": mode_stats,
            "detection_strategy_stats": detection_stats,
            "created_at": scenario.created_at ,
            "updated_at": scenario.updated_at ,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scenario stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 6. 场景和节点批量操作
# ============================================================

@router.post("/scenarios/{scenario_id}/clone")
async def clone_scenario(
    scenario_id: str = Path(...),
    new_name: str = Query(...),
) -> Dict[str, Any]:
    """
    克隆场景（包括所有关联的节点配置）
    
    Args:
        scenario_id: 源场景 ID
        new_name: 新场景的名称
    
    Returns:
        新创建的场景信息
    """
    
    if not scenario_service or not node_config_service:
        raise HTTPException(status_code=500, detail="Services not initialized")
    
    try:
        # 获取源场景
        source_scenario = await scenario_service.get_scenario(scenario_id)
        if not source_scenario:
            raise HTTPException(status_code=404, detail="Source scenario not found")
        
        # 创建新场景
        new_scenario = await scenario_service.create_scenario(
            name=new_name,
            description=f"Clone of {source_scenario.name}",
        )
        
        # 复制所有节点配置
        source_nodes = await node_config_service.list_scenario_nodes(scenario_id)
        for source_node in source_nodes:
            await node_config_service.copy_node_config(
                source_scenario_id=scenario_id,
                source_node_id=source_node.node_id,
                target_scenario_id=new_scenario.id,
                target_node_id=source_node.node_id,
            )
        
        logger.info(f"Scenario cloned: {scenario_id} -> {new_scenario.id}")
        
        return {
            "source_scenario_id": scenario_id,
            "new_scenario_id": new_scenario.id,
            "new_scenario_name": new_scenario.name,
            "cloned_nodes": len(source_nodes),
            "message": "Scenario cloned successfully",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clone scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# 3. 用户执行 API
# ============================================================

@router.get("/runs/{runId}/users")
async def list_user_executions(runId: str = Path(...)) -> List[Dict]:
    """获取测试中所有虚拟用户的执行状态"""
    try:
        test_run = await db.get(TestRun, runId)
        if not test_run:
            raise HTTPException(status_code=404, detail="Test run not found")
        
        user_executions = await db.query_by_field(
            UserExecution,
            "test_run_id",
            runId,
            options=[selectinload(UserExecution.node_executions)],
        )
        
        return [
            {
                "userId": f"user-{exec.user_index:03d}",
                "userName": f"虚拟用户 {exec.user_index + 1}",
                "status": exec.status.value,
                "currentNodeId": exec.current_node_id,
                "nodeStates": {
                    node_exec.node_id: {
                        "nodeId": node_exec.node_id,
                        "status": node_exec.status.value,
                        "duration": node_exec.duration,
                        "startTime": node_exec.start_time  if node_exec.start_time else None,
                        "endTime": node_exec.end_time  if node_exec.end_time else None,
                        "error": node_exec.error_message,
                        "request": {
                            "method": "POST",  # TODO: 从配置获取
                            "url": "/api/chat",  # TODO: 从配置获取
                            "headers": node_exec.request_headers or {},
                            "body": node_exec.request_body,
                        } if node_exec.request_body else None,
                        "response": {
                            "status": node_exec.response_status or 0,
                            "statusText": "OK" if node_exec.response_status == 200 else "Error",
                            "headers": node_exec.response_headers or {},
                            "body": node_exec.response_body,
                            "duration": node_exec.duration or 0,
                        } if node_exec.response_body else None,
                    }
                    for node_exec in exec.node_executions
                },
                "startTime": exec.start_time ,
                "endTime": exec.end_time  if exec.end_time else None,
            }
            for exec in user_executions
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list user executions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{runId}/users/{userId}")
async def get_user_execution(
    runId: str = Path(...),
    userId: str = Path(...),
) -> Dict:
    """获取单个虚拟用户的执行状态"""
    try:
        test_run = await db.get(TestRun, runId)
        if not test_run:
            raise HTTPException(status_code=404, detail="Test run not found")
        
        # 从 userId 解析 user_index
        user_index = int(userId.split("-")[-1]) - 1 if userId.startswith("user-") else 0
        
        user_executions = await db.query_by_field(
            UserExecution,
            "test_run_id",
            runId,
            options=[selectinload(UserExecution.node_executions)],
        )
        user_exec = next((u for u in user_executions if u.user_index == user_index), None)
        
        if not user_exec:
            raise HTTPException(status_code=404, detail="User execution not found")
        
        return {
            "userId": userId,
            "userName": f"虚拟用户 {user_index + 1}",
            "status": user_exec.status.value,
            "currentNodeId": user_exec.current_node_id,
            "nodeStates": {
                node_exec.node_id: {
                    "nodeId": node_exec.node_id,
                    "status": node_exec.status.value,
                    "duration": node_exec.duration,
                    "startTime": node_exec.start_time  if node_exec.start_time else None,
                    "endTime": node_exec.end_time  if node_exec.end_time else None,
                    "error": node_exec.error_message,
                }
                for node_exec in user_exec.node_executions
            },
            "startTime": user_exec.start_time ,
            "endTime": user_exec.end_time  if user_exec.end_time else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 4. 测试结果 API
# ============================================================

@router.get("/runs/{runId}/summary")
async def get_test_summary(runId: str = Path(...)) -> Dict:
    """获取测试结果摘要"""
    try:
        test_run = await db.get(TestRun, runId)
        if not test_run:
            raise HTTPException(status_code=404, detail="Test run not found")
        
        # 查询汇总数据
        summaries = await db.query_by_field(TestSummary, "test_run_id", runId)
        summary = summaries[0] if summaries else None
        
        if not summary:
            raise HTTPException(status_code=404, detail="Summary not found")
        
        return {
            "runId": runId,
            "totalUsers": summary.total_users,
            "successUsers": summary.success_users,
            "failedUsers": summary.failed_users,
            "successRate": summary.success_rate,
            "avgResponseTime": summary.avg_response_time,
            "minResponseTime": summary.min_response_time,
            "maxResponseTime": summary.max_response_time,
            "p50ResponseTime": summary.p50_response_time,
            "p95ResponseTime": summary.p95_response_time,
            "p99ResponseTime": summary.p99_response_time,
            "failedNodes": summary.failed_nodes or [],
            "nodeStats": summary.node_stats or [],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get test summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 5. WebSocket 实时进度推送
# ============================================================

@router.websocket("/runs/{runId}/ws")
async def websocket_progress(
    websocket: WebSocket,
    runId: str = Path(...),
):
    """WebSocket 实时进度推送"""
    
    if not ws_manager:
        await websocket.close(code=1000, reason="Manager not initialized")
        return
    
    await ws_manager.connect(websocket, runId)
    
    try:
        while True:
            # 保持连接活跃
                _ = await websocket.receive_text()
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    
    finally:
        ws_manager.disconnect(runId)

