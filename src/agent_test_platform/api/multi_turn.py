
from fastapi import APIRouter, HTTPException
from typing import Dict, List, Any
import asyncio
from agent_test_platform.config.logger import logger
from agent_test_platform.config.node_strategy import NodeStrategy
import time

router = APIRouter(prefix="/api", tags=["multi-turn"])

smart_orchestrator = None  # 在 main.py 中初始化


@router.post("/tests/multi-turn/run")
async def start_multi_turn_test(payload: Dict[str, Any]) -> Dict[str, Any]:
    """启动多轮对话测试"""
    
    try:
        test_run_id = f"test-{int(time.time())}"
        scenario_name = payload.get("scenario_name")
        node_configs = payload.get("node_configs", {})
        num_users = payload.get("num_users", 1)
        concurrency = payload.get("concurrency", 1)
        
        if not scenario_name:
            raise HTTPException(status_code=400, detail="scenario_name is required")
        
        if not node_configs:
            raise HTTPException(status_code=400, detail="node_configs is required")
        
        # 异步启动测试
        asyncio.create_task(
            smart_orchestrator.run_multi_turn_test(
                test_run_id=test_run_id,
                scenario_name=scenario_name,
                node_configs=node_configs,
                num_users=num_users,
                concurrency=concurrency,
            )
        )
        
        return {
            "test_run_id": test_run_id,
            "scenario_name": scenario_name,
            "num_users": num_users,
            "status": "started",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start multi-turn test: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tests/multi-turn/node-config")
async def update_node_config(
    node_id: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """更新节点配置（动态，无需重启）"""
    
    try:
        # 验证配置
        strategy = NodeStrategy(node_id, config)
        
        # 缓存策略
        smart_orchestrator.node_strategies[node_id] = strategy
        
        return {
            "node_id": node_id,
            "status": "updated",
            "message": "Node configuration updated successfully",
        }
    
    except Exception as e:
        logger.error(f"Failed to update node config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

