
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable, List
import json


@dataclass
class ExitCondition:
    """退出条件"""
    
    max_turns: int = 10                      # 最多对话轮次
    timeout_seconds: int = 300              # 总超时时间
    
    # 任务检测条件
    task_keywords: List[str] = None         # 任务关键字
    task_regex_pattern: str = None          # 正则匹配任务
    
    # 自定义判断函数（灵活性）
    custom_check_func: Optional[str] = None # Python 代码字符串


@dataclass
class MessageGenerationStrategy:
    """消息生成策略"""
    
    strategy_type: str = "template"         # template, ai_generated, random
    
    # Template 策略
    message_templates: List[str] = None     # 预定义消息模板
    
    # AI 生成策略
    ai_model: str = "gpt-3.5-turbo"        # 使用哪个 AI 模型
    ai_prompt_template: str = ""            # 提示词模板
    ai_temperature: float = 0.7             # 温度参数
    
    # 随机策略
    random_messages: List[str] = None       # 随机选择的消息


@dataclass
class TaskDetectionStrategy:
    """任务检测策略"""
    
    detection_type: str = "keyword"         # keyword, regex, ai, custom
    
    # Keyword 检测
    keywords: List[str] = None              # 关键字列表
    
    # Regex 检测
    regex_pattern: str = None               # 正则表达式
    
    # AI 检测
    ai_model: str = "gpt-3.5-turbo"
    ai_prompt: str = "检查以下文本是否表示任务已生成"
    
    # 自定义检测函数
    custom_check_code: Optional[str] = None # Python 代码字符串


class NodeStrategy:
    """节点执行策略（完整的 DSL 定义）"""
    
    def __init__(self, node_id: str, config: Dict[str, Any]):
        self.node_id = node_id
        self.config = config
        
        # 解析执行模式
        self.execution_mode = config.get("execution_mode", "multi_turn_dialog")
        
        # 出口条件
        exit_config = config.get("exit_condition", {})
        self.exit_condition = ExitCondition(
            max_turns=exit_config.get("max_turns", 10),
            timeout_seconds=exit_config.get("timeout_seconds", 300),
            task_keywords=exit_config.get("task_keywords", []),
            task_regex_pattern=exit_config.get("task_regex_pattern"),
            custom_check_func=exit_config.get("custom_check_func"),
        )
        
        # 消息生成策略
        msg_config = config.get("message_generation", {})
        self.message_strategy = MessageGenerationStrategy(
            strategy_type=msg_config.get("type", "template"),
            message_templates=msg_config.get("templates", []),
            ai_model=msg_config.get("ai_model", "gpt-3.5-turbo"),
            ai_prompt_template=msg_config.get("ai_prompt", ""),
            ai_temperature=msg_config.get("temperature", 0.7),
            random_messages=msg_config.get("random_messages", []),
        )
        
        # 任务检测策略
        task_config = config.get("task_detection", {})
        self.task_detection = TaskDetectionStrategy(
            detection_type=task_config.get("type", "keyword"),
            keywords=task_config.get("keywords", []),
            regex_pattern=task_config.get("regex_pattern"),
            ai_model=task_config.get("ai_model", "gpt-3.5-turbo"),
            ai_prompt=task_config.get("ai_prompt", "检查是否生成了任务"),
            custom_check_code=task_config.get("custom_check_code"),
        )
    
    def should_continue_dialog(self, turns: int, elapsed_time: float, last_response: Dict) -> bool:
        """判断是否继续对话"""
        
        # 检查最大轮次
        if turns >= self.exit_condition.max_turns:
            return False
        
        # 检查超时
        if elapsed_time > self.exit_condition.timeout_seconds:
            return False
        
        # 检查任务生成（如果已生成，结束对话）
        if self._check_task_generated(last_response):
            return False
        
        # 自定义检查函数
        if self.exit_condition.custom_check_func:
            try:
                result = eval(self.exit_condition.custom_check_func, {
                    "response": last_response,
                    "turns": turns,
                    "elapsed_time": elapsed_time,
                })
                return bool(result)
            except Exception as e:
                print(f"Error evaluating custom check: {e}")
                return True
        
        return True
    
    def _check_task_generated(self, response: Dict[str, Any]) -> bool:
        """检查是否生成了任务"""
        
        if self.task_detection.detection_type == "keyword":
            return self._check_by_keyword(response)
        elif self.task_detection.detection_type == "regex":
            return self._check_by_regex(response)
        elif self.task_detection.detection_type == "custom":
            return self._check_by_custom(response)
        else:
            return False
    
    def _check_by_keyword(self, response: Dict[str, Any]) -> bool:
        """通过关键字检查"""
        response_text = str(response)
        for keyword in self.task_detection.keywords:
            if keyword.lower() in response_text.lower():
                return True
        return False
    
    def _check_by_regex(self, response: Dict[str, Any]) -> bool:
        """通过正则表达式检查"""
        import re
        response_text = str(response)
        try:
            return bool(re.search(self.task_detection.regex_pattern, response_text))
        except Exception:
            return False
    
    def _check_by_custom(self, response: Dict[str, Any]) -> bool:
        """通过自定义代码检查"""
        if not self.task_detection.custom_check_code:
            return False
        
        try:
            result = eval(self.task_detection.custom_check_code, {
                "response": response,
            })
            return bool(result)
        except Exception as e:
            print(f"Error in custom check: {e}")
            return False
    
    def get_next_message(self, user_profile: Dict, conversation_history: List[str]) -> str:
        """获取下一条消息"""
        
        if self.message_strategy.strategy_type == "template":
            return self._generate_from_template(user_profile, conversation_history)
        elif self.message_strategy.strategy_type == "ai_generated":
            return self._generate_from_ai(user_profile, conversation_history)
        elif self.message_strategy.strategy_type == "random":
            return self._generate_random(user_profile, conversation_history)
        else:
            return "继续"
    
    def _generate_from_template(self, user_profile: Dict, history: List[str]) -> str:
        """从模板生成消息"""
        templates = self.message_strategy.message_templates or ["继续", "请继续"]
        
        # 简单轮转
        round_num = len(history) % len(templates)
        return templates[round_num]
    
    def _generate_from_ai(self, user_profile: Dict, history: List[str]) -> str:
        """从 AI 生成消息"""
        # 这里集成 OpenAI API
        # 实现见后面
        pass
    
    def _generate_random(self, user_profile: Dict, history: List[str]) -> str:
        """随机生成消息"""
        import random
        messages = self.message_strategy.random_messages or ["继续", "再试一次", "请继续"]
        return random.choice(messages)
