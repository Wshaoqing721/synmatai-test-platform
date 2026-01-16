
import asyncio
import time
from typing import Dict, Any, Optional
from datetime import datetime
from agent_test_platform.config.logger import logger
from agent_test_platform.http_client.client import AgentHTTPClient
from agent_test_platform.models.conversation_model import (
    Conversation, DialogTurn, ConversationStatus, NodeExecutionMode, VirtualUserProfile
)
from agent_test_platform.config.node_strategy import NodeStrategy
from agent_test_platform.storage.database import Database


class ConversationExecutor:
    """多轮对话执行器"""
    
    def __init__(
        self,
        node_strategy: NodeStrategy,
        user_profile: Dict[str, Any],
        user_execution_id: str,
        node_id: str,
        node_name: str,
        test_run_id: str,
        db: Database,
        http_client: AgentHTTPClient,
        ai_client=None,  # OpenAI 客户端
        on_event_callback=None,
    ):
        self.node_strategy = node_strategy
        self.user_profile = user_profile
        self.user_execution_id = user_execution_id
        self.node_id = node_id
        self.node_name = node_name
        self.test_run_id = test_run_id
        self.db = db
        self.http_client = http_client
        self.ai_client = ai_client
        self.on_event_callback = on_event_callback
        
        # 对话状态
        self.conversation: Optional[Conversation] = None
        self.turn_count = 0
        self.start_time = None
        self.dialog_history = []  # 对话历史
    
    async def execute(self) -> bool:
        """执行多轮对话"""
        
        logger.info(
            f"Starting conversation execution",
            node_id=self.node_id,
            user=self.user_profile.get("username"),
        )
        
        self.start_time = time.time()
        
        try:
            # 1. 创建对话记录
            self.conversation = await self._create_conversation()
            
            # 2. 发送初始消息
            initial_message = self.user_profile.get("initial_message", "你好")
            await self._send_turn(initial_message, is_initial=True)
            
            # 3. 多轮对话循环
            while True:
                # 检查是否应该继续
                elapsed = time.time() - self.start_time
                
                if not self.node_strategy.should_continue_dialog(
                    self.turn_count,
                    elapsed,
                    self.dialog_history[-1] if self.dialog_history else {},
                ):
                    break
                
                # 生成下一条消息
                next_message = self.node_strategy.get_next_message(
                    self.user_profile,
                    self.dialog_history,
                )
                
                # 发送消息
                await self._send_turn(next_message)
            
            # 4. 完成对话
            await self._finalize_conversation(success=True)
            
            return True
        
        except Exception as e:
            logger.error(f"Conversation execution failed: {e}")
            await self._finalize_conversation(success=False, error=str(e))
            return False
    
    async def _send_turn(self, user_message: str, is_initial: bool = False) -> Dict[str, Any]:
        """发送单轮对话"""
        
        self.turn_count += 1
        logger.info(
            f"Turn {self.turn_count}",
            node_id=self.node_id,
            message=user_message,
        )
        
        turn_start = time.time()
        
        try:
            # 1. 构建上下文消息
            context_message = self._build_context_message(user_message)
            
            # 2. 调用 Agent API
            success, response, error, duration = await self.http_client.call_agent(
                endpoint="/chat",
                payload={"message": context_message},
                headers=self._build_headers(),
            )
            
            # 3. 检查响应
            if not success:
                logger.warning(f"Agent API failed: {error}")
                return {}
            
            agent_response = response or {}
            
            # 4. 保存对话轮次
            turn = DialogTurn(
                conversation_id=self.conversation.id,
                turn_number=self.turn_count,
                user_message=user_message,
                agent_response=agent_response,
                agent_response_raw=str(response),
                duration_ms=duration,
            )
            
            # 5. 检查是否生成任务
            task_detected = self.node_strategy._check_task_generated(agent_response)
            if task_detected:
                turn.task_detected = True
                turn.task_id = agent_response.get("task_id")
                turn.task_data = agent_response.get("task", {})
                turn.completion_criteria_met = True
                turn.should_continue = False
                
                logger.info(
                    f"Task generated",
                    task_id=turn.task_id,
                    turn=self.turn_count,
                )
            
            # 6. 保存到数据库
            turn = await self.db.create(turn)
            
            # 7. 更新对话历史
            self.dialog_history.append({
                "turn": self.turn_count,
                "user_message": user_message,
                "agent_response": agent_response,
                "task_detected": task_detected,
            })
            
            # 8. 推送事件
            if self.on_event_callback:
                await self.on_event_callback(
                    event_type="turn_completed",
                    node_id=self.node_id,
                    turn_number=self.turn_count,
                    task_detected=task_detected,
                    duration_ms=int(duration),
                )
            
            return agent_response
        
        except Exception as e:
            logger.error(f"Turn execution failed: {e}")
            raise
    
    async def _create_conversation(self) -> Conversation:
        """创建对话记录"""
        
        conversation = Conversation(
            user_execution_id=self.user_execution_id,
            node_id=self.node_id,
            node_name=self.node_name,
            status=ConversationStatus.ONGOING,
            execution_mode=self.node_strategy.execution_mode,
            config=self.node_strategy.config,
        )
        
        return await self.db.create(conversation)
    
    async def _finalize_conversation(self, success: bool, error: str = None):
        """完成对话"""
        
        try:
            elapsed = time.time() - self.start_time
            
            self.conversation.status = ConversationStatus.COMPLETED if success else ConversationStatus.FAILED
            self.conversation.total_turns = self.turn_count
            self.conversation.duration_ms = int(elapsed * 1000)
            self.conversation.completed_at = datetime.utcnow()
            
            # 检查是否生成了任务
            for turn in self.conversation.turns:
                if turn.task_detected:
                    self.conversation.task_generated = True
                    self.conversation.task_id = turn.task_id
                    self.conversation.task_data = turn.task_data
                    break
            
            await self.db.update(self.conversation)
            
            logger.info(
                f"Conversation completed",
                node_id=self.node_id,
                turns=self.turn_count,
                task_generated=self.conversation.task_generated,
                duration_ms=self.conversation.duration_ms,
            )
        
        except Exception as e:
            logger.error(f"Failed to finalize conversation: {e}")
    
    def _build_context_message(self, user_message: str) -> str:
        """构建包含上下文的消息"""
        
        # 简单的上下文构建
        # 可以更复杂地处理对话历史
        context_parts = [
            f"用户身份: {self.user_profile.get('role', '普通用户')}",
            f"任务描述: {self.user_profile.get('task_description', '')}",
            f"消息: {user_message}",
        ]
        
        return "\n".join(context_parts)
    
    def _build_headers(self) -> Dict[str, str]:
        """构建请求头"""
        return {
            "User-Agent": f"VirtualUser-{self.user_profile.get('username')}",
        }