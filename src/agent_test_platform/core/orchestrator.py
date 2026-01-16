
import asyncio
import uuid
from typing import Optional, List
from datetime import datetime
from agent_test_platform.config.logger import logger
from agent_test_platform.scenarios.loader import ScenarioLoader
from agent_test_platform.models.test_run import TestRun, TestRunStatus
from agent_test_platform.models.node_based import (
    Scenario as NodeScenario,
    TestRun as NodeTestRun,
    RunStatus as NodeRunStatus,
)
from agent_test_platform.storage.database import Database
from agent_test_platform.http_client.client import AgentHTTPClient
from agent_test_platform.config.settings import settings
from agent_test_platform.core.state_machine import StateMachine, TestState
from agent_test_platform.core.executor import VirtualUserExecutor
from agent_test_platform.core.node_executor import NodeDAGExecutor
from agent_test_platform.models.node_config_model import NodeConfig


class TestOrchestrator:
    """测试编排器 - 管理整个测试执行过程"""
    
    def __init__(self, db: Database):
        self.db = db
        self.http_client = AgentHTTPClient()
        self.scenario_loader = ScenarioLoader(settings.SCENARIOS_DIR)
        
        # 运行时状态
        self.test_run: Optional[TestRun] = None
        self.state_machine = StateMachine(TestState.IDLE)
        self.user_tasks: List[asyncio.Task] = []
        self.progress_callbacks = []
    
    def register_progress_callback(self, callback):
        """注册进度回调"""
        self.progress_callbacks.append(callback)
    
    async def start_test(
        self,
        scenario_name: str,
        num_users: Optional[int] = None,
        concurrency: Optional[int] = None,
    ) -> Optional[str]:
        """
        启动测试
        
        Returns:
            test_run_id
        """
        
        # 1. 加载场景
        scenario = self.scenario_loader.load(scenario_name)
        if not scenario:
            logger.error(f"Failed to load scenario: {scenario_name}")
            return None
        
        # 覆盖配置
        if num_users:
            scenario.num_users = num_users
        if concurrency:
            scenario.concurrency = concurrency
        
        # 2. 创建 TestRun 记录
        test_run_id = str(uuid.uuid4())
        self.test_run = TestRun(
            id=test_run_id,
            scenario_name=scenario_name,
            status=TestRunStatus.PENDING,
            num_users=scenario.num_users,
            concurrency=scenario.concurrency,
            config={
                'scenario': scenario_name,
                'num_users': scenario.num_users,
                'concurrency': scenario.concurrency,
                'steps': len(scenario.steps),
            },
        )
        
        self.test_run = await self.db.create(self.test_run)
        
        logger.info(
            "Test started",
            test_run_id=test_run_id,
            scenario=scenario_name,
            num_users=scenario.num_users,
        )
        
        # 3. 状态转移
        self.state_machine.transition(TestState.RUNNING)
        self.test_run.status = TestRunStatus.RUNNING
        await self.db.update(self.test_run)
        
        # 4. 启动虚拟用户
        asyncio.create_task(self._run_users(test_run_id, scenario))
        
        return test_run_id
    
    async def _run_users(self, test_run_id: str, scenario):
        """启动并管理虚拟用户"""

        # API v2 会传 scenario_id（str），而 YAML 模式会传 ScenarioConfig
        # 这里做兼容：优先把 str 当成 node-based scenario_id 去 DB 取
        node_scenario: Optional[NodeScenario] = None
        yaml_scenario = None
        try:
            if isinstance(scenario, str):
                node_scenario = await self.db.get(
                    NodeScenario,
                    scenario,
                )
                if node_scenario is None:
                    yaml_scenario = self.scenario_loader.load(scenario)
            else:
                yaml_scenario = scenario

            if node_scenario is not None:
                await self._run_users_node_based(test_run_id, node_scenario)
                return

            if yaml_scenario is None:
                raise ValueError("Scenario not found")

            # YAML 模式：使用 VirtualUserExecutor
            user_semaphore = asyncio.Semaphore(yaml_scenario.concurrency)
            
            async def run_user_with_semaphore(user_index: int):
                async with user_semaphore:
                    user_id = str(uuid.uuid4())
                    
                    executor = VirtualUserExecutor(
                        user_id=user_id,
                        user_index=user_index,
                        scenario=yaml_scenario,
                        test_run_id=test_run_id,
                        db=self.db,
                        http_client=self.http_client,
                        on_progress_callback=self._on_user_progress,
                    )
                    
                    return await executor.run()
            
            # 创建所有用户任务
            tasks = [asyncio.create_task(run_user_with_semaphore(i)) for i in range(yaml_scenario.num_users)]
            
            # 等待所有任务完成（带超时）
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=yaml_scenario.max_wait_time,
            )
            
            # 统计结果
            successful = sum(1 for r in results if r is True)
            failed = sum(1 for r in results if r is False)
            
            logger.info(
                "All users completed",
                test_run_id=test_run_id,
                successful=successful,
                failed=failed,
            )
            
            # 更新 TestRun
            if self.test_run is not None:
                self.test_run.completed_users = successful
                self.test_run.failed_users = failed
                self.test_run.status = TestRunStatus.DONE if failed == 0 else TestRunStatus.DONE
                self.test_run.total_duration_ms = int(
                    (datetime.utcnow() - self.test_run.created_at).total_seconds() * 1000
                )
                await self.db.update(self.test_run)
            
            # 状态转移
            self.state_machine.transition(TestState.COMPLETED)
            
            logger.info(f"Test completed: {test_run_id}")
        
        except asyncio.TimeoutError:
            logger.error(f"Test timeout: {test_run_id}")
            if self.test_run is not None:
                self.test_run.status = TestRunStatus.FAILED
                self.test_run.error_message = "Test execution timeout"
                await self.db.update(self.test_run)
            self.state_machine.transition(TestState.FAILED)
        
        except Exception as e:
            logger.error(f"Error during test execution: {e}")
            if self.test_run is not None:
                self.test_run.status = TestRunStatus.FAILED
                self.test_run.error_message = str(e)
                await self.db.update(self.test_run)
            self.state_machine.transition(TestState.FAILED)

    async def _run_users_node_based(self, run_id: str, scenario: NodeScenario) -> None:
        """API v2(node_based) 模式：基于 Scenario DAG 执行并更新 node_based.TestRun"""

        test_run = await self.db.get(NodeTestRun, run_id)
        if not test_run:
            raise ValueError(f"Test run not found: {run_id}")

        total_users = int(test_run.total_users or 0)
        if total_users <= 0:
            raise ValueError("total_users must be > 0")

        # node_based 的场景模型里目前没有 concurrency 字段，先用全局默认并做上限保护
        concurrency = max(1, min(total_users, settings.DEFAULT_CONCURRENCY))
        user_semaphore = asyncio.Semaphore(concurrency)

        # 读取该场景关联的所有节点配置（替代 ScenarioNode）
        scenario_nodes = await self.db.query_by_field(NodeConfig, "scenario_id", scenario.id)

        async def run_user_with_semaphore(user_index: int):
            async with user_semaphore:
                user_id = f"user-{user_index:03d}"
                executor = NodeDAGExecutor(
                    user_index=user_index,
                    user_id=user_id,
                    scenario=scenario,
                    nodes=scenario_nodes,
                    test_run_id=run_id,
                    db=self.db,
                    http_client=self.http_client,
                    on_event_callback=None,
                )
                return await executor.run()

        tasks = [asyncio.create_task(run_user_with_semaphore(i)) for i in range(total_users)]

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()

        successful = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if r is False or isinstance(r, Exception))

        test_run.success_users = successful
        test_run.failed_users = failed
        test_run.current_users = successful + failed
        test_run.progress = int((test_run.current_users / total_users) * 100) if total_users else 0
        test_run.end_time = datetime.utcnow()
        test_run.status = NodeRunStatus.DONE if failed == 0 else NodeRunStatus.FAILED
        await self.db.update(test_run)
    
    async def _on_user_progress(
        self,
        run_id: str,
        user_id: str,
        step_index: int,
        step_name: str,
        status: str,
        duration_ms: float,
        response_status: Optional[int] = None,
        error: Optional[str] = None,
    ):
        """用户进度回调"""
        
        # 调用所有注册的进度回调
        for callback in self.progress_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(
                        run_id=run_id,
                        user_id=user_id,
                        step_index=step_index,
                        step_name=step_name,
                        status=status,
                        duration_ms=duration_ms,
                        response_status=response_status,
                        error=error,
                    )
                else:
                    callback(
                        run_id=run_id,
                        user_id=user_id,
                        step_index=step_index,
                        step_name=step_name,
                        status=status,
                        duration_ms=duration_ms,
                        response_status=response_status,
                        error=error,
                    )
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")
    
    async def get_test_status(self, test_run_id: str) -> Optional[dict]:
        """获取测试状态"""
        test_run = await self.db.get(TestRun, test_run_id)
        if not test_run:
            return None
        
        return {
            'id': test_run.id,
            'scenario_name': test_run.scenario_name,
            'status': test_run.status.value,
            'num_users': test_run.num_users,
            'completed_users': test_run.completed_users,
            'failed_users': test_run.failed_users,
            'total_duration_ms': test_run.total_duration_ms,
            'created_at': test_run.created_at.isoformat(),
        }
    
    async def cancel_test(self, test_run_id: str) -> bool:
        """取消测试"""
        test_run = await self.db.get(TestRun, test_run_id)
        if not test_run:
            return False
        
        test_run.status = TestRunStatus.CANCELLED
        await self.db.update(test_run)
        
        logger.info(f"Test cancelled: {test_run_id}")
        return True