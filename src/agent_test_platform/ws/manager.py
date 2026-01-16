
import json
import datetime
from typing import Dict, Set
from fastapi import WebSocket
from agent_test_platform.config.logger import logger


class WSConnectionManager:
    """WebSocket 连接管理器（前端适配版）"""
    
    def __init__(self):
        # runId -> set of websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, run_id: str):
        """连接 WebSocket"""
        await websocket.accept()
        
        if run_id not in self.active_connections:
            self.active_connections[run_id] = set()
        
        self.active_connections[run_id].add(websocket)
        
        logger.info("WebSocket connected", run_id=run_id)
    
    def disconnect(self, run_id: str):
        """断开连接"""
        if run_id in self.active_connections:
            self.active_connections[run_id].clear()
            del self.active_connections[run_id]
        
        logger.info("WebSocket disconnected", run_id=run_id)
    
    async def broadcast(self, run_id: str, event: dict):
        """广播事件"""
        if run_id not in self.active_connections:
            return
        
        dead_connections = set()
        
        for websocket in self.active_connections[run_id]:
            try:
                await websocket.send_json(event)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")
                dead_connections.add(websocket)
        
        for conn in dead_connections:
            self.active_connections[run_id].discard(conn)
    
    # ============================================================
    # 前端事件推送方法（与 WSEvent 对应）
    # ============================================================
    
    async def send_run_started(self, run_id: str, scenario_id: str, scenario_name: str, total_users: int):
        """推送测试启动事件"""
        event = {
            "type": "run_started",
            "runId": run_id,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "scenarioId": scenario_id,
                "scenarioName": scenario_name,
                "totalUsers": total_users,
            },
        }
        await self.broadcast(run_id, event)
    
    async def send_run_progress(self, run_id: str, progress: int, current_users: int):
        """推送测试进度"""
        event = {
            "type": "run_progress",
            "runId": run_id,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "progress": progress,
                "currentUsers": current_users,
            },
        }
        await self.broadcast(run_id, event)
    
    async def send_user_started(self, run_id: str, user_id: str, user_name: str):
        """推送用户启动事件"""
        event = {
            "type": "user_started",
            "runId": run_id,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "userId": user_id,
                "userName": user_name,
            },
        }
        await self.broadcast(run_id, event)
    
    async def send_user_completed(self, run_id: str, user_id: str, status: str, duration: float):
        """推送用户完成事件"""
        event = {
            "type": "user_completed",
            "runId": run_id,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "userId": user_id,
                "status": status,  # "success" 或 "failed"
                "duration": int(duration),
            },
        }
        await self.broadcast(run_id, event)
    
    async def send_node_started(self, run_id: str, user_id: str, node_id: str, node_name: str):
        """推送节点启动事件"""
        event = {
            "type": "node_started",
            "runId": run_id,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "userId": user_id,
                "nodeId": node_id,
                "nodeName": node_name,
            },
        }
        await self.broadcast(run_id, event)
    
    async def send_node_completed(
        self,
        run_id: str,
        user_id: str,
        node_id: str,
        node_name: str,
        duration: float,
        request: Dict = None,
        response: Dict = None,
    ):
        """推送节点完成事件"""
        event = {
            "type": "node_completed",
            "runId": run_id,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "userId": user_id,
                "nodeId": node_id,
                "nodeName": node_name,
                "duration": int(duration),
                "request": request,
                "response": response,
            },
        }
        await self.broadcast(run_id, event)
    
    async def send_node_failed(
        self,
        run_id: str,
        user_id: str,
        node_id: str,
        node_name: str,
        error: str,
        request: Dict = None,
        response: Dict = None,
    ):
        """推送节点失败事件"""
        event = {
            "type": "node_failed",
            "runId": run_id,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "userId": user_id,
                "nodeId": node_id,
                "nodeName": node_name,
                "error": error,
                "request": request,
                "response": response,
            },
        }
        await self.broadcast(run_id, event)