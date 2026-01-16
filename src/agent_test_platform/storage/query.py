
from typing import Optional, Dict, Any, List
from agent_test_platform.config.logger import logger
from agent_test_platform.models.test_run import TestRun
from agent_test_platform.models.virtual_user import VirtualUser
from agent_test_platform.models.test_step import TestStep
from agent_test_platform.storage.database import Database
from agent_test_platform.storage.json_writer import JSONResultWriter


class ResultQuery:
    """测试结果查询接口"""
    
    def __init__(self, db: Database):
        self.db = db
        self.json_writer = JSONResultWriter()
    
    async def get_test_result(self, test_run_id: str) -> Optional[Dict[str, Any]]:
        """获取完整测试结果"""
        
        try:
            # 获取 TestRun
            test_run = await self.db.get(TestRun, test_run_id)
            if not test_run:
                return None
            
            # 构建摘要
            summary = self._build_summary(test_run)
            
            # 构建详情
            detail = await self._build_detail(test_run)
            
            # 写入 JSON 文件
            await self.json_writer.write_results(test_run_id, summary, detail)
            
            return {
                'summary': summary,
                'detail': detail,
            }
        
        except Exception as e:
            logger.error(f"Failed to get test result: {e}")
            return None
    
    def _build_summary(self, test_run: TestRun) -> Dict[str, Any]:
        """构建测试摘要"""
        
        return {
            'run_id': test_run.id,
            'scenario_name': test_run.scenario_name,
            'status': test_run.status.value,
            'start_time': test_run.created_at.isoformat(),
            'end_time': test_run.updated_at.isoformat(),
            'total_duration_ms': test_run.total_duration_ms,
            'statistics': {
                'total_users': test_run.num_users,
                'completed_users': test_run.completed_users,
                'failed_users': test_run.failed_users,
            },
        }
    
    async def _build_detail(self, test_run: TestRun) -> Dict[str, Any]:
        """构建测试详情"""
        
        # 获取所有虚拟用户
        virtual_users_data = []
        
        # 这里需要从数据库查询虚拟用户，伪代码示例
        # 实际实现需要在 Database 类中添加相应的查询方法
        
        return {
            'test_run_id': test_run.id,
            'virtual_users': virtual_users_data,
        }
