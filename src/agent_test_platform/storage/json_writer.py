
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from agent_test_platform.config.logger import logger
from agent_test_platform.config.settings import settings


class JSONResultWriter:
    """JSON 结果导出"""
    
    def __init__(self):
        self.output_dir = Path(settings.DATABASE_PATH)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def write_results(self, test_run_id: str, summary: Dict[str, Any], detail: Dict[str, Any]):
        """将测试结果写入 JSON 文件"""
        
        try:
            # 写入摘要
            summary_file = self.output_dir / f"{test_run_id}_summary.json"
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"Summary written: {summary_file}")
            
            # 写入详情
            detail_file = self.output_dir / f"{test_run_id}_detail.json"
            with open(detail_file, 'w', encoding='utf-8') as f:
                json.dump(detail, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"Detail written: {detail_file}")
        
        except Exception as e:
            logger.error(f"Failed to write JSON results: {e}")