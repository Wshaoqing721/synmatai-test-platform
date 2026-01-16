
import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from agent_test_platform.config.logger import logger
from agent_test_platform.http_client.client import AgentHTTPClient
from agent_test_platform.scenarios.model import ScenarioConfig, StepConfig
from agent_test_platform.models.virtual_user import VirtualUser, VirtualUserStatus
from agent_test_platform.models.test_step import TestStep, TestStepStatus
from agent_test_platform.storage.database import Database


class VirtualUserExecutor:
    """虚拟用户执行器 - 异步执行单个用户的测试"""
    
    def __init__(
        self,
        user_id: str,
        user_index: int,
        scenario: ScenarioConfig,
        test_run_id: str,
        db: Database,
        http_client: AgentHTTPClient,
        on_progress_callback=None,
    ):
        self.user_id = user_id
        self.user_index = user_index
        self.scenario = scenario
        self.test_run_id = test_run_id
        self.db = db
        self.http_client = http_client
        self.on_progress_callback = on_progress_callback
        
        # 用户上下文
        self.user_context: Dict[str, Any] = {
            'token': None,
            'session_id': str(user_id),
            'conversation_history': [],
        }
        
        self.start_time = None
        self.end_time = None
        self.current_step_index = 0
    
    async def run(self) -> bool:
        """运行虚拟用户的完整测试"""
        
        logger.info(f"Virtual user {self.user_index} starting", run_id=self.test_run_id)
        self.start_time = time.time()
        
        try:
            # 1. 创建虚拟用户记录
            user = await self._create_user_record()
            if not user:
                logger.error(f"Failed to create user record")
                return False
            
            # 2. 按照场景步骤执行
            step_index = 0
            while step_index < len(self.scenario.steps):
                step_config = self.scenario.steps[step_index]
                
                # 更新用户状态
                await self._update_user_status(user, step_index)
                
                # 执行步骤
                success, should_continue = await self._execute_step(
                    user, step_index, step_config
                )
                
                if not success:
                    logger.warning(
                        f"Step {step_index} failed",
                        user_id=self.user_id,
                        step_name=step_config.name,
                    )
                    # 失败不中止，继续下一步（或根据需要修改）
                
                # 判断是否继续
                if not should_continue:
                    logger.info(
                        f"User {self.user_index} completed (condition met)",
                        run_id=self.test_run_id,
                    )
                    break
                
                step_index += 1
            
            # 3. 更新用户为完成状态
            await self._finalize_user(user, success=True)
            
            logger.info(
                f"Virtual user {self.user_index} completed",
                run_id=self.test_run_id,
                duration_ms=int((time.time() - self.start_time) * 1000),
            )
            return True
        
        except Exception as e:
            logger.error(
                f"Virtual user {self.user_index} failed",
                error=str(e),
                run_id=self.test_run_id,
            )
            return False
        
        finally:
            self.end_time = time.time()
    
    async def _create_user_record(self) -> Optional[VirtualUser]:
        """创建虚拟用户数据库记录"""
        try:
            user = VirtualUser(
                test_run_id=self.test_run_id,
                user_index=self.user_index,
                status=VirtualUserStatus.IDLE,
                total_steps=len(self.scenario.steps),
                context=self.user_context,
            )
            return await self.db.create(user)
        except Exception as e:
            logger.error(f"Failed to create user record: {e}")
            return None
    
    async def _update_user_status(self, user: VirtualUser, step_index: int):
        """更新用户状态"""
        try:
            user.status = VirtualUserStatus.RUNNING
            user.current_step = step_index
            await self.db.update(user)
        except Exception as e:
            logger.error(f"Failed to update user status: {e}")
    
    async def _execute_step(
        self,
        user: VirtualUser,
        step_index: int,
        step_config: StepConfig,
    ) -> tuple[bool, bool]:
        """
        执行单个步骤
        
        Returns:
            (步骤是否成功, 是否继续)
        """
        
        # 创建 TestStep 记录
        test_step = TestStep(
            virtual_user_id=user.id,
            step_index=step_index,
            step_name=step_config.name,
            http_method=step_config.method,
            endpoint=step_config.endpoint,
            request_body=step_config.payload,
            status=TestStepStatus.RUNNING,
        )
        test_step = await self.db.create(test_step)
        
        step_start = time.time()
        
        try:
            # 1. 准备请求体（支持从上下文替换）
            payload = self._build_payload(step_config.payload)
            
            logger.info(
                f"Executing step {step_index}",
                user_id=self.user_id,
                step_name=step_config.name,
                endpoint=step_config.endpoint,
            )
            
            # 2. 调用 Agent API
            success, response_json, error_msg, duration_ms = await self.http_client.call_agent(
                endpoint=step_config.endpoint,
                payload=payload,
                headers=self._build_headers(),
            )
            
            duration_ms = (time.time() - step_start) * 1000
            
            # 3. 更新 TestStep 记录
            test_step.duration_ms = duration_ms
            test_step.response_body = response_json if response_json else {}
            test_step.error_message = error_msg
            
            if success and response_json:
                test_step.status = TestStepStatus.SUCCESS
                test_step.response_status_code = 200
                
                # 4. 从响应中提取字段
                extracted = self._extract_fields(response_json, step_config.extraction)
                self.user_context.update(extracted)
                
                # 5. 评估是否继续
                should_continue = self._evaluate_condition(
                    response_json,
                    step_config.should_continue,
                )
                
                test_step.evaluation_result = {
                    'extracted_fields': extracted,
                    'should_continue': should_continue,
                }
                
                logger.info(
                    f"Step {step_index} success",
                    user_id=self.user_id,
                    should_continue=should_continue,
                    duration_ms=duration_ms,
                )
            else:
                test_step.status = TestStepStatus.FAILED
                test_step.response_status_code = 500
                should_continue = False
                
                logger.warning(
                    f"Step {step_index} failed",
                    user_id=self.user_id,
                    error=error_msg,
                )
            
            await self.db.update(test_step)
            
            # 6. 调用进度回调
            if self.on_progress_callback:
                await self.on_progress_callback(
                    run_id=self.test_run_id,
                    user_id=self.user_id,
                    step_index=step_index,
                    step_name=step_config.name,
                    status=test_step.status.value,
                    duration_ms=duration_ms,
                    response_status=test_step.response_status_code,
                    error=error_msg,
                )
            
            return success, should_continue
        
        except Exception as e:
            logger.error(f"Exception during step execution: {e}")
            
            test_step.status = TestStepStatus.FAILED
            test_step.error_message = str(e)
            test_step.duration_ms = (time.time() - step_start) * 1000
            await self.db.update(test_step)
            
            return False, False
    
    async def _finalize_user(self, user: VirtualUser, success: bool):
        """最终化用户记录"""
        try:
            duration_ms = int((self.end_time - self.start_time) * 1000)
            
            user.status = VirtualUserStatus.COMPLETED if success else VirtualUserStatus.FAILED
            user.total_duration_ms = duration_ms
            
            # 计算统计数据
            steps = await self.db.query_steps(user.id)
            user.num_requests = len(steps)
            user.num_errors = sum(1 for s in steps if s.status == TestStepStatus.FAILED)
            
            await self.db.update(user)
        except Exception as e:
            logger.error(f"Failed to finalize user: {e}")
    
    def _build_payload(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """根据模板和上下文构建请求体"""
        import copy
        import re
        
        payload = copy.deepcopy(template)
        
        # 简单的模板替换：{context.field_name} -> context['field_name']
        def replace_context(obj):
            if isinstance(obj, str):
                # 匹配 {context.xxx} 或 {xxx}
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
        """构建请求头（包括 token 等）"""
        headers = {}
        if self.user_context.get('token'):
            headers['Authorization'] = f"Bearer {self.user_context['token']}"
        return headers
    
    def _extract_fields(
        self,
        response: Dict[str, Any],
        extraction: Optional[Dict[str, str]],
    ) -> Dict[str, Any]:
        """从响应中提取字段"""
        if not extraction:
            return {}
        
        extracted = {}
        for key, path in extraction.items():
            # 简单的 JSON 路径提取：response.data.task_id
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
    
    def _evaluate_condition(
        self,
        response: Dict[str, Any],
        condition: Optional[str],
    ) -> bool:
        """
        评估是否继续
        
        简单的表达式评估，如：
        - "response.status == 'continue'" -> 继续
        - "response.task_id" -> 有 task_id 则继续
        """
        if not condition:
            return True  # 默认继续
        
        try:
            # 创建安全的评估上下文
            context = {
                'response': response,
                'True': True,
                'False': False,
                'None': None,
            }
            
            # 简单的安全评估（仅支持比较和布尔运算）
            result = eval(condition, {"__builtins__": {}}, context)
            return bool(result)
        
        except Exception as e:
            logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return True  # 失败时默认继续