
import asyncio
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from agent_test_platform.config.logger import logger
from agent_test_platform.http_client.client import AgentHTTPClient
from agent_test_platform.core.conversation_executor import ConversationExecutor
from agent_test_platform.config.node_strategy import NodeStrategy
from agent_test_platform.config.user_config import UserConfigTemplate
from agent_test_platform.storage.database import Database
from agent_test_platform.integrations.openai_client import OpenAIClient
from agent_test_platform.models.node_based import TestRun, RunStatus
from agent_test_platform.models.conversation_model import VirtualUserProfile


class SmartTestOrchestrator:
    """智能测试编排器"""
    
    def __init__(
        self,
        db: Database,
        http_client: AgentHTTPClient,
        openai_api_key: Optional[str] = None,
        on_event_callback=None,
    ):
        self.db = db
        self.http_client = http_client
        self.ai_client = OpenAIClient(openai_api_key) if openai_api_key else None
        self.on_event_callback = on_event_callback
        
        # 节点配置缓存
        self.node_strategies: Dict[str, NodeStrategy] = {}
    
    async def run_multi_turn_test(
        self,
        test_run_id: str,
        scenario_name: str,
        node_configs: Dict[str, Dict[str, Any]],
        num_users: int = 5,
        concurrency: int = 2,
    ) -> bool:
        """运行多轮对话测试"""
        
        logger.info(
            f"Starting multi-turn test",
            test_run_id=test_run_id,
            scenario=scenario_name,
            num_users=num_users,
        )
        
        try:
            # 1. 加载节点策略
            for node_id, config in node_configs.items():
                self.node_strategies[node_id] = NodeStrategy(node_id, config)
            
            # 2. 创建虚拟用户配置
            user_configs = [
                UserConfigTemplate.get_user_config(i, scenario_name)
                for i in range(num_users)
            ]
            
            # 3. 并发执行用户
            semaphore = asyncio.Semaphore(concurrency)
            
            async def run_user_test(user_index: int):
                async with semaphore:
                    return await self._execute_single_user(
                        test_run_id=test_run_id,
                        user_index=user_index,
                        user_config=user_configs[user_index],
                        node_configs=node_configs,
                    )
            
            tasks = [
                asyncio.create_task(run_user_test(i))
                for i in range(num_users)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 4. 汇总结果
            successful = sum(1 for r in results if r is True)
            failed = sum(1 for r in results if r is False)
            
            logger.info(
                f"Test completed",
                test_run_id=test_run_id,
                successful=successful,
                failed=failed,
            )
            
            # 5. 更新测试状态
            test_run = await self.db.get(TestRun, test_run_id)
            if test_run:
                test_run.status = RunStatus.DONE
                test_run.completed_users = successful
                test_run.failed_users = failed
                test_run.progress = 100
                await self.db.update(test_run)
            
            return True
        
        except Exception as e:
            logger.error(f"Test failed: {e}")
            
            # 更新测试状态为失败
            test_run = await self.db.get(TestRun, test_run_id)
            if test_run:
                test_run.status = RunStatus.FAILED
                await self.db.update(test_run)
            
            return False
    
    async def _execute_single_user(
        self,
        test_run_id: str,
        user_index: int,
        user_config: Dict[str, Any],
        node_configs: Dict[str, Dict[str, Any]],
    ) -> bool:
        """执行单个用户的测试"""
        
        logger.info(
            f"User {user_index} test starting",
            run_id=test_run_id,
            username=user_config.get("username"),
        )
        
        user_start_time = time.time()
        
        try:
            # 1. 创建虚拟用户配置记录
            user_profile = VirtualUserProfile(
                user_execution_id=f"user-{user_index}",  # 实际应该是真实的 user_execution_id
                username=user_config.get("username"),
                user_role=user_config.get("role"),
                preferences=user_config,
                dialog_personality=user_config.get("dialog_personality"),
                initial_message=user_config.get("initial_message"),
                task_description=user_config.get("task_description"),
                target_task_keywords=user_config.get("target_task_keywords", []),
            )
            
            user_profile = await self.db.create(user_profile)
            
            # 2. 执行每个节点
            for node_id, node_config in node_configs.items():
                node_strategy = self.node_strategies.get(node_id)
                if not node_strategy:
                    logger.warning(f"Node strategy not found: {node_id}")
                    continue
                
                # 创建对话执行器
                executor = ConversationExecutor(
                    node_strategy=node_strategy,
                    user_profile=user_config,
                    user_execution_id=user_profile.id,
                    node_id=node_id,
                    node_name=node_config.get("name"),
                    test_run_id=test_run_id,
                    db=self.db,
                    http_client=self.http_client,
                    ai_client=self.ai_client,
                    on_event_callback=self.on_event_callback,
                )
                
                # 执行对话
                success = await executor.execute()
                
                if not success:
                    logger.warning(f"Node {node_id} failed for user {user_index}")
                    # 失败但继续（或根据需要中止）
            
            logger.info(
                f"User {user_index} test completed",
                run_id=test_run_id,
                duration_ms=int((time.time() - user_start_time) * 1000),
            )
            
            return True
        
        except Exception as e:
            logger.error(f"User {user_index} test failed: {e}")
            return False