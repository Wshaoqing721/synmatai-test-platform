
from typing import List, Dict, Any
import json


class UserConfigTemplate:
    """虚拟用户配置模板"""
    
    # 预定义的用户角色
    ROLES = {
        "normal_user": {
            "role": "普通用户",
            "dialog_personality": "简洁友好",
            "initial_message": "你好，我需要创建一个任务",
            "target_task_keywords": ["任务", "创建", "已生成"],
        },
        "tech_user": {
            "role": "技术人员",
            "dialog_personality": "技术性强",
            "initial_message": "我需要创建一个自动化测试任务，请帮我配置参数",
            "target_task_keywords": ["task_id", "configured", "ready"],
        },
        "admin": {
            "role": "管理员",
            "dialog_personality": "详细询问",
            "initial_message": "我需要创建一个新的系统任务，需要详细的权限配置",
            "target_task_keywords": ["权限", "任务ID", "已授权"],
        },
    }
    
    # 不同场景的用户配置
    SCENARIO_CONFIGS = {
        "simple_chat": {
            "num_users": 5,
            "concurrency": 2,
            "users": [
                {
                    "index": 0,
                    "role": "normal_user",
                    "task_description": "创建一个简单的测试任务",
                },
                {
                    "index": 1,
                    "role": "normal_user",
                    "task_description": "创建一个简单的测试任务",
                },
                # ... 更多用户
            ],
        },
        "multi_user_stress": {
            "num_users": 50,
            "concurrency": 10,
            "users": [
                {
                    "index": i,
                    "role": "normal_user" if i % 3 == 0 else ("tech_user" if i % 3 == 1 else "admin"),
                    "task_description": f"用户 {i} 的任务",
                }
                for i in range(50)
            ],
        },
    }
    
    @staticmethod
    def get_user_config(user_index: int, scenario: str) -> Dict[str, Any]:
        """获取用户配置"""
        scenario_config = UserConfigTemplate.SCENARIO_CONFIGS.get(scenario, {})
        users = scenario_config.get("users", [])
        
        if user_index < len(users):
            user_spec = users[user_index]
        else:
            # 循环使用配置
            user_spec = users[user_index % len(users)]
        
        # 获取角色模板
        role = user_spec.get("role", "normal_user")
        role_template = UserConfigTemplate.ROLES.get(role, UserConfigTemplate.ROLES["normal_user"])
        
        # 合并配置
        config = {
            "index": user_index,
            "username": f"user_{user_index:03d}",
            "role": role_template["role"],
            "dialog_personality": role_template["dialog_personality"],
            "initial_message": role_template["initial_message"],
            "target_task_keywords": role_template["target_task_keywords"],
            "task_description": user_spec.get("task_description", ""),
        }
        
        return config
    
    @staticmethod
    def create_custom_config(
        num_users: int,
        roles: List[str],
        task_descriptions: List[str],
    ) -> Dict[str, Any]:
        """创建自定义用户配置"""
        return {
            "num_users": num_users,
            "concurrency": min(num_users, 10),
            "users": [
                {
                    "index": i,
                    "role": roles[i % len(roles)],
                    "task_description": task_descriptions[i % len(task_descriptions)],
                }
                for i in range(num_users)
            ],
        }
