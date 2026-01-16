
import asyncio
from typing import Optional, List, Dict, Any
import aiohttp
from agent_test_platform.config.logger import logger


class OpenAIClient:
    """OpenAI 客户端"""
    
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def init(self):
        """初始化 session"""
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """关闭 session"""
        if self.session:
            await self.session.close()
    
    async def generate_message(
        self,
        prompt: str,
        conversation_history: List[Dict[str, str]] = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> Optional[str]:
        """生成消息"""
        
        try:
            await self.init()
            
            # 构建消息列表
            messages = [{"role": "system", "content": "你是一个智能测试助手，帮助用户完成任务。"}]
            
            # 添加对话历史
            if conversation_history:
                messages.extend(conversation_history[-5:])  # 最多最近 5 轮
            
            # 添加当前提示
            messages.append({"role": "user", "content": prompt})
            
            # 调用 OpenAI API
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            async with self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.error(f"OpenAI API error: {resp.status}")
                    return None
                
                data = await resp.json()
                message = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                return message.strip() if message else None
        
        except Exception as e:
            logger.error(f"Failed to generate message with OpenAI: {e}")
            return None
    
    async def check_task_generated(
        self,
        response_text: str,
        task_description: str,
    ) -> bool:
        """使用 AI 检查是否生成了任务"""
        
        try:
            prompt = f"""
            检查以下 Agent 响应是否表示任务已生成。
            
            任务描述: {task_description}
            Agent 响应: {response_text}
            
            请回答 "是" 或 "否"。
            """
            
            result = await self.generate_message(prompt, max_tokens=10)
            
            if result and "是" in result:
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Failed to check task generation with AI: {e}")
            return False
