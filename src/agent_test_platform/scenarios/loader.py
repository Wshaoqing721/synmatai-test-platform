
import yaml
from pathlib import Path
from typing import Optional
from agent_test_platform.scenarios.model import ScenarioConfig, StepConfig
from agent_test_platform.config.logger import logger


class ScenarioLoader:
    """YAML 场景加载器"""
    
    def __init__(self, scenarios_dir: Path):
        self.scenarios_dir = scenarios_dir
    
    def load(self, scenario_name: str) -> Optional[ScenarioConfig]:
        """加载场景配置"""
        try:
            file_path = self.scenarios_dir / f"{scenario_name}.yaml"
            
            if not file_path.exists():
                logger.error(f"Scenario file not found: {file_path}")
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # 转换为 ScenarioConfig
            config = self._parse_config(data)
            logger.info(f"Loaded scenario: {scenario_name}")
            return config
        
        except Exception as e:
            logger.error(f"Failed to load scenario {scenario_name}: {e}")
            return None
    
    def _parse_config(self, data: dict) -> ScenarioConfig:
        """解析 YAML 数据为 ScenarioConfig"""
        
        steps = [
            StepConfig(
                name=step.get('name', f'step_{i}'),
                method=step.get('method', 'POST'),
                endpoint=step.get('endpoint', ''),
                payload=step.get('payload', {}),
                extraction=step.get('extraction'),
                condition=step.get('condition'),
                should_continue=step.get('should_continue'),
                max_retries=step.get('max_retries', 0),
                timeout=step.get('timeout', 30.0),
            )
            for i, step in enumerate(data.get('steps', []))
        ]
        
        return ScenarioConfig(
            name=data.get('name'),
            description=data.get('description', ''),
            num_users=data.get('num_users', 1),
            concurrency=data.get('concurrency', 1),
            ramp_up_time=data.get('ramp_up_time', 0),
            agent_endpoint=data.get('agent_endpoint', '/chat'),
            steps=steps,
            success_condition=data.get('success_condition'),
            max_wait_time=data.get('max_wait_time', 300),
        )