
import httpx
import time
from typing import Dict, Any, Optional, Tuple
from agent_test_platform.config.logger import logger
from agent_test_platform.config.settings import settings


class AgentHTTPClient:
    """异步 HTTP 客户端，用于调用 Agent API"""
    
    def __init__(self):
        self.base_url = settings.AGENT_API_BASE_URL
        self.timeout = settings.AGENT_API_TIMEOUT
    
    async def call_agent(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str], float]:
        """
        调用 Agent API
        
        Returns:
            (成功标志, 响应体, 错误信息, 耗时ms)
        """
        start_time = time.time()
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers or {},
                )
            
            duration_ms = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                try:
                    response_json = response.json()
                    logger.info(
                        f"Agent API call success",
                        endpoint=endpoint,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                    )
                    return True, response_json, None, duration_ms
                except Exception as e:
                    logger.error(f"Failed to parse JSON: {e}")
                    return False, None, f"JSON parse error: {e}", duration_ms
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.warning(
                    f"Agent API call failed",
                    endpoint=endpoint,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
                return False, None, error_msg, duration_ms
        
        except httpx.TimeoutException as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Request timeout: {e}")
            return False, None, f"Timeout after {self.timeout}s", duration_ms
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Request error: {e}")
            return False, None, str(e), duration_ms
