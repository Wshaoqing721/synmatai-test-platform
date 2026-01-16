
import asyncio
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from agent_test_platform.config.logger import logger
from agent_test_platform.http_client.client import AgentHTTPClient
from agent_test_platform.models.node_based import (
    Scenario, NodeStatus, NodeExecution, UserExecution
)
from agent_test_platform.models.node_config_model import NodeConfig
from agent_test_platform.storage.database import Database


class NodeDAGExecutor:
    """基于节点 DAG 的测试执行器"""
    
    def __init__(
        self,
        user_index: int,
        user_id: str,
        scenario: Scenario,
        nodes: List[NodeConfig],
        test_run_id: str,
        db: Database,
        http_client: AgentHTTPClient,
        on_event_callback=None,
    ):
        self.user_index = user_index
        self.user_id = user_id
        self.scenario = scenario
        self.nodes = nodes
        self.test_run_id = test_run_id
        self.db = db
        self.http_client = http_client
        self.on_event_callback = on_event_callback
        
        # 用户上下文
        self.user_context: Dict[str, Any] = {
            'token': None,
            'session_id': str(user_id),
            'conversation_history': [],
        }
        
        # 节点执行状态追踪
        self.node_states: Dict[str, NodeStatus] = {}
        self.node_executions: Dict[str, NodeExecution] = {}
        
        self.start_time = None
        self.end_time = None
        self.user_execution: Optional[UserExecution] = None

    def _node_id(self, node: NodeConfig) -> str:
        return node.node_id or node.id

    def _node_ids(self) -> List[str]:
        return [self._node_id(n) for n in self.nodes]

    def _get_node(self, node_id: str) -> Optional[NodeConfig]:
        return next((n for n in self.nodes if self._node_id(n) == node_id), None)
    
    async def run(self) -> bool:
        """运行完整的用户测试"""
        
        logger.info(f"User {self.user_index} starting", run_id=self.test_run_id)
        self.start_time = time.time()
        
        try:
            # 1. 创建用户执行记录
            self.user_execution = await self._create_user_execution()
            if not self.user_execution:
                return False
            
            # 2. 初始化节点状态
            for node_id in self._node_ids():
                self.node_states[node_id] = NodeStatus.PENDING
            
            # 3. 构建依赖图并拓扑排序
            execution_order = self._topological_sort()
            if not execution_order:
                logger.error("Failed to sort nodes topologically")
                return False
            
            # 4. 执行节点
            for node_id in execution_order:
                node = self._get_node(node_id)
                if not node:
                    continue
                
                # 检查依赖是否都已完成
                if not self._check_dependencies(node_id):
                    logger.warning(f"Skipping node {node_id} due to failed dependency")
                    self.node_states[node_id] = NodeStatus.SKIPPED
                    continue
                
                # 推送节点启动事件
                await self._send_event(
                    "node_started",
                    {
                        "userId": self.user_id,
                        "nodeId": node_id,
                        "nodeName": node.node_name,
                    },
                )
                
                # 执行节点
                success = await self._execute_node(node)
                
                if not success:
                    logger.warning(f"Node {node_id} failed")
                    # 失败但继续执行其他节点（可根据需要修改）
            
            # 5. 更新用户状态
            await self._finalize_user(success=True)
            
            logger.info(
                f"User {self.user_index} completed",
                duration_ms=int((time.time() - self.start_time) * 1000),
            )
            return True
        
        except Exception as e:
            logger.error(f"User {self.user_index} failed: {e}")
            await self._finalize_user(success=False)
            return False
        
        finally:
            self.end_time = time.time()
    
    # ============================================================
    # 拓扑排序与依赖检查
    # ============================================================
    
    def _topological_sort(self) -> List[str]:
        """使用 Kahn 算法进行拓扑排序"""
        
        # 构建入度表
        node_ids = self._node_ids()
        in_degree = {node_id: 0 for node_id in node_ids}
        adjacency = {node_id: [] for node_id in node_ids}

        for node in self.nodes:
            node_id = self._node_id(node)
            for dep_id in (node.dependencies or []):
                if dep_id in adjacency:
                    adjacency[dep_id].append(node_id)
                    in_degree[node_id] += 1
        
        # Kahn 算法
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            node_id = queue.pop(0)
            result.append(node_id)
            
            for neighbor in adjacency[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # 检查是否有环
        if len(result) != len(node_ids):
            logger.error("Cyclic dependency detected in scenario")
            return []
        
        return result
    
    def _check_dependencies(self, node_id: str) -> bool:
        """检查节点的所有依赖是否都已成功完成"""
        
        node = self._get_node(node_id)
        if not node or not node.dependencies:
            return True
        
        for dep_id in node.dependencies:
            dep_status = self.node_states.get(dep_id, NodeStatus.PENDING)
            # 如果依赖失败或被跳过，则此节点无法执行
            if dep_status in (NodeStatus.FAILED, NodeStatus.SKIPPED):
                return False
        
        return True
    
    # ============================================================
    # 节点执行
    # ============================================================
    
    async def _execute_node(self, node) -> bool:
        """执行单个节点"""
        
        # 根据节点类型处理
        node_type = (node.node_type or "").lower()
        if not node_type:
            node_type = "action"

        if node_type == "start":
            return await self._execute_start_node(node)
        elif node_type == "end":
            return await self._execute_end_node(node)
        elif node_type == "action":
            return await self._execute_action_node(node)
        elif node_type == "assertion":
            return await self._execute_assertion_node(node)
        elif node_type == "condition":
            return await self._execute_condition_node(node)
        else:
            logger.warning(f"Unknown node type: {node.node_type}")
            return False
    
    async def _execute_start_node(self, node) -> bool:
        """执行开始节点"""
        node_id = self._node_id(node)
        self.node_states[node_id] = NodeStatus.SUCCESS
        
        node_exec = NodeExecution(
            node_id=node_id,
            node_name=node.node_name,
            status=NodeStatus.SUCCESS,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            duration=0,
        )
        self.node_executions[node_id] = node_exec
        
        await self._send_event(
            "node_completed",
            {
                "userId": self.user_id,
                "nodeId": node_id,
                "nodeName": node.node_name,
                "duration": 0,
            },
        )
        
        return True
    
    async def _execute_end_node(self, node) -> bool:
        """执行结束节点"""
        node_id = self._node_id(node)
        self.node_states[node_id] = NodeStatus.SUCCESS
        
        node_exec = NodeExecution(
            node_id=node_id,
            node_name=node.node_name,
            status=NodeStatus.SUCCESS,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            duration=0,
        )
        self.node_executions[node_id] = node_exec
        
        return True
    
    async def _execute_action_node(self, node) -> bool:
        """执行动作节点（HTTP 调用）"""

        node_id = self._node_id(node)
        self.node_states[node_id] = NodeStatus.RUNNING
        
        node_exec = NodeExecution(
            node_id=node_id,
            node_name=node.node_name,
            status=NodeStatus.RUNNING,
            start_time=datetime.utcnow(),
        )
        
        node_start_time = time.time()
        
        try:
            # 从节点配置获取 HTTP 信息
            config = node.config or {}
            if (not config) and isinstance(getattr(node, "full_config", None), dict):
                config = node.full_config.get("config", {}) or {}
            endpoint = config.get("endpoint", "/chat")
            method = config.get("method", "POST")
            payload_template = config.get("payload", {})
            
            # 构建请求体
            payload = self._build_payload(payload_template)
            
            logger.info(
                "Executing action node",
                node_id=node_id,
                node_name=node.node_name,
                endpoint=endpoint,
            )
            
            # 调用 HTTP API
            success, response_json, error_msg, duration_ms = await self.http_client.call_agent(
                endpoint=endpoint,
                payload=payload,
                headers=self._build_headers(),
            )
            
            duration = time.time() - node_start_time
            
            if success and response_json:
                self.node_states[node_id] = NodeStatus.SUCCESS
                node_exec.status = NodeStatus.SUCCESS
                node_exec.response_status = 200
                node_exec.response_body = response_json
                
                # 提取字段
                extraction = config.get("extraction", {})
                extracted = self._extract_fields(response_json, extraction)
                self.user_context.update(extracted)
                
                logger.info(
                    "Action node success",
                    node_id=node_id,
                    duration=duration,
                )
                
                # 推送完成事件
                await self._send_event(
                    "node_completed",
                    {
                        "userId": self.user_id,
                        "nodeId": node_id,
                        "nodeName": node.node_name,
                        "duration": int(duration * 1000),
                        "request": {
                            "method": method,
                            "url": endpoint,
                            "headers": self._build_headers(),
                            "body": payload,
                        },
                        "response": {
                            "status": 200,
                            "statusText": "OK",
                            "headers": {},
                            "body": response_json,
                            "duration": int(duration * 1000),
                        },
                    },
                )
            else:
                self.node_states[node_id] = NodeStatus.FAILED
                node_exec.status = NodeStatus.FAILED
                node_exec.error_message = error_msg
                
                logger.warning(
                    "Action node failed",
                    node_id=node_id,
                    error=error_msg,
                )
                
                # 推送失败事件
                await self._send_event(
                    "node_failed",
                    {
                        "userId": self.user_id,
                        "nodeId": node_id,
                        "nodeName": node.node_name,
                        "error": error_msg,
                    },
                )
            
            node_exec.duration = duration
            node_exec.end_time = datetime.utcnow()
            self.node_executions[node_id] = node_exec
            
            return success
        
        except Exception as e:
            logger.error(f"Exception in action node: {e}")
            self.node_states[node_id] = NodeStatus.FAILED
            node_exec.status = NodeStatus.FAILED
            node_exec.error_message = str(e)
            node_exec.duration = time.time() - node_start_time
            node_exec.end_time = datetime.utcnow()
            self.node_executions[node_id] = node_exec
            
            await self._send_event(
                "node_failed",
                {
                    "userId": self.user_id,
                    "nodeId": node_id,
                    "nodeName": node.node_name,
                    "error": str(e),
                },
            )
            
            return False
    
    async def _execute_assertion_node(self, node) -> bool:
        """执行断言节点"""

        node_id = self._node_id(node)
        self.node_states[node_id] = NodeStatus.RUNNING
        
        node_exec = NodeExecution(
            node_id=node_id,
            node_name=node.node_name,
            status=NodeStatus.RUNNING,
            start_time=datetime.utcnow(),
        )
        
        node_start_time = time.time()
        
        try:
            # 从配置获取断言条件
            config = node.config or {}
            condition = config.get("condition", "True")
            
            # 评估条件
            success = self._evaluate_condition(condition)
            
            duration = time.time() - node_start_time
            
            if success:
                self.node_states[node_id] = NodeStatus.SUCCESS
                node_exec.status = NodeStatus.SUCCESS
                logger.info(f"Assertion node success: {node.node_name}")
                
                await self._send_event(
                    "node_completed",
                    {
                        "userId": self.user_id,
                        "nodeId": node_id,
                        "nodeName": node.node_name,
                        "duration": int(duration * 1000),
                    },
                )
            else:
                self.node_states[node_id] = NodeStatus.FAILED
                node_exec.status = NodeStatus.FAILED
                node_exec.error_message = f"Assertion failed: {condition}"
                logger.warning(f"Assertion node failed: {node.node_name}")
                
                await self._send_event(
                    "node_failed",
                    {
                        "userId": self.user_id,
                        "nodeId": node_id,
                        "nodeName": node.node_name,
                        "error": f"Assertion failed: {condition}",
                    },
                )
            
            node_exec.duration = duration
            node_exec.end_time = datetime.utcnow()
            self.node_executions[node_id] = node_exec
            
            return success
        
        except Exception as e:
            logger.error(f"Exception in assertion node: {e}")
            self.node_states[node_id] = NodeStatus.FAILED
            node_exec.status = NodeStatus.FAILED
            node_exec.error_message = str(e)
            node_exec.duration = time.time() - node_start_time
            node_exec.end_time = datetime.utcnow()
            self.node_executions[node_id] = node_exec
            
            return False
    
    async def _execute_condition_node(self, node) -> bool:
        """执行条件节点"""
        
        # 与断言节点类似，但可能有不同的处理逻辑
        return await self._execute_assertion_node(node)
    
    # ============================================================
    # 数据库操作
    # ============================================================
    
    async def _create_user_execution(self) -> Optional[UserExecution]:
        """创建用户执行记录"""
        try:
            user_exec = UserExecution(
                test_run_id=self.test_run_id,
                user_index=self.user_index,
                status=NodeStatus.RUNNING,
                current_node_id=None,
                start_time=datetime.utcnow(),
                context=self.user_context,
                conversation_history=[],
            )
            return await self.db.create(user_exec)
        except Exception as e:
            logger.error(f"Failed to create user execution: {e}")
            return None
    
    async def _finalize_user(self, success: bool):
        """完成用户执行"""
        try:
            if self.user_execution:
                self.user_execution.status = NodeStatus.SUCCESS if success else NodeStatus.FAILED
                self.user_execution.end_time = datetime.utcnow()
                
                # 保存所有节点执行记录
                for node_exec in self.node_executions.values():
                    node_exec.user_execution_id = self.user_execution.id
                    await self.db.create(node_exec)
                
                await self.db.update(self.user_execution)
                
                # 推送用户完成事件
                duration = (self.end_time - self.start_time) * 1000
                await self._send_event(
                    "user_completed",
                    {
                        "userId": self.user_id,
                        "status": "success" if success else "failed",
                        "duration": int(duration),
                    },
                )
        except Exception as e:
            logger.error(f"Failed to finalize user: {e}")
    
    # ============================================================
    # 工具方法
    # ============================================================
    
    def _build_payload(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """构建请求体（模板替换）"""
        import copy
        import re
        
        payload = copy.deepcopy(template)
        
        def replace_context(obj):
            if isinstance(obj, str):
                pattern = r'\{(?:context\.)?(\w+)\}'
                def replacer(match):
                    key = match.group(1)
                    return str(self.user_context.get(key, ''))
                return re.sub(pattern, replacer, obj)
            elif isinstance(obj, dict):
                return {k: replace_context(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_context(item) for item in obj]
            return obj
        
        return replace_context(payload)
    
    def _build_headers(self) -> Dict[str, str]:
        """构建请求头"""
        headers = {}
        if self.user_context.get('token'):
            headers['Authorization'] = f"Bearer {self.user_context['token']}"
        return headers
    
    def _extract_fields(self, response: Dict[str, Any], extraction: Dict[str, str]) -> Dict[str, Any]:
        """从响应提取字段"""
        if not extraction:
            return {}
        
        extracted = {}
        for key, path in extraction.items():
            try:
                value = response
                for part in path.split('.'):
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        value = None
                        break
                
                if value is not None:
                    extracted[key] = value
            except Exception:
                pass
        
        return extracted
    
    def _evaluate_condition(self, condition: str) -> bool:
        """评估条件"""
        try:
            context = {
                'context': self.user_context,
                'True': True,
                'False': False,
                'None': None,
            }
            result = eval(condition, {"__builtins__": {}}, context)
            return bool(result)
        except Exception as e:
            logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return True
    
    async def _send_event(self, event_type: str, data: Dict[str, Any]):
        """推送事件"""
        if self.on_event_callback:
            try:
                if asyncio.iscoroutinefunction(self.on_event_callback):
                    await self.on_event_callback(
                        event_type=event_type,
                        run_id=self.test_run_id,
                        data=data,
                    )
                else:
                    self.on_event_callback(
                        event_type=event_type,
                        run_id=self.test_run_id,
                        data=data,
                    )
            except Exception as e:
                logger.error(f"Failed to send event: {e}")