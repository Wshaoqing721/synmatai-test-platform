
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.future import select
from agent_test_platform.models.node_config_model import NodeConfig, NodeConfigHistory, NodeExecutionMode
from agent_test_platform.storage.database import Database
from agent_test_platform.config.logger import logger


class NodeConfigService:
    """节点配置服务 - 处理数据库操作"""
    
    def __init__(self, db: Database):
        self.db = db
    
    # ============================================================
    # 创建操作
    # ============================================================
    
    async def create_node_config(
        self,
        scenario_id: str,
        node_id: str,
        config: Dict[str, Any],
    ) -> NodeConfig:
        """创建节点配置"""
        
        try:
            # 验证配置
            if not self._validate_config(config):
                raise ValueError("Invalid node configuration")
            
            # 创建配置对象
            node_config = NodeConfig(
                scenario_id=scenario_id,
                node_id=node_id,
                node_name=config.get("name"),
                node_type=config.get("type") or config.get("node_type"),
                execution_mode=NodeExecutionMode(config.get("execution_mode")),
                dependencies=config.get("depends_on") or config.get("dependencies") or [],
                exit_condition=config.get("exit_condition", {}),
                message_generation=config.get("message_generation", {}),
                task_detection=config.get("task_detection", {}),
                config=config.get("config", {}) or {},
                full_config=config,
            )
            
            # 保存到数据库
            saved_config = await self.db.create(node_config)
            
            # 记录历史
            await self._record_history(
                node_config_id=saved_config.id,
                config_before=None,
                config_after=config,
                change_type="create",
                change_reason="Initial creation",
            )
            
            logger.info(f"Node config created: {scenario_id}:{node_id}")
            
            return saved_config
        
        except Exception as e:
            logger.error(f"Failed to create node config: {e}")
            raise
    
    # ============================================================
    # 读取操作
    # ============================================================
    
    async def get_node_config(
        self,
        scenario_id: str,
        node_id: str,
    ) -> Optional[NodeConfig]:
        """获取节点配置"""
        
        try:
            async with self.db.async_session() as session:
                stmt = select(NodeConfig).where(
                    (NodeConfig.scenario_id == scenario_id) &
                    (NodeConfig.node_id == node_id)
                )
                result = await session.execute(stmt)
                config = result.scalars().first()
                
                if not config:
                    logger.warning(f"Node config not found: {scenario_id}:{node_id}")
                    return None
                
                return config
        
        except Exception as e:
            logger.error(f"Failed to get node config: {e}")
            raise
    
    
    async def list_scenario_nodes(self, scenario_id: str) -> List[NodeConfig]:
        """列表场景的所有节点配置"""
        
        try:
            async with self.db.async_session() as session:
                stmt = select(NodeConfig).where(
                    NodeConfig.scenario_id == scenario_id
                ).order_by(NodeConfig.created_at.desc())
                
                result = await session.execute(stmt)
                configs = result.scalars().all()
                
                return configs if configs else []
        
        except Exception as e:
            logger.error(f"Failed to list scenario nodes: {e}")
            raise
    
    
    async def get_all_node_configs(self) -> List[NodeConfig]:
        """获取所有节点配置"""
        
        try:
            return await self.db.query_all(NodeConfig)
        except Exception as e:
            logger.error(f"Failed to get all node configs: {e}")
            raise
    
    # ============================================================
    # 更新操作
    # ============================================================
    
    async def update_node_config(
        self,
        scenario_id: str,
        node_id: str,
        config: Dict[str, Any],
        change_reason: str = None,
    ) -> Optional[NodeConfig]:
        """更新节点配置"""
        
        try:
            # 验证配置
            if not self._validate_config(config):
                raise ValueError("Invalid node configuration")
            
            # 获取现有配置
            existing_config = await self.get_node_config(scenario_id, node_id)
            
            if not existing_config:
                logger.warning(f"Node config not found: {scenario_id}:{node_id}")
                return None
            
            # 保存旧配置用于历史记录
            old_config = existing_config.full_config
            
            # 更新配置
            existing_config.node_name = config.get("name")
            existing_config.execution_mode = NodeExecutionMode(config.get("execution_mode"))
            existing_config.dependencies = config.get("depends_on") or config.get("dependencies") or []
            existing_config.exit_condition = config.get("exit_condition", {})
            existing_config.message_generation = config.get("message_generation", {})
            existing_config.task_detection = config.get("task_detection", {})
            existing_config.config = config.get("config", {}) or {}
            existing_config.full_config = config
            existing_config.updated_at = datetime.utcnow()
            
            # 保存到数据库
            updated_config = await self.db.update(existing_config)
            
            # 记录历史
            await self._record_history(
                node_config_id=existing_config.id,
                config_before=old_config,
                config_after=config,
                change_type="update",
                change_reason=change_reason or "Configuration update",
            )
            
            logger.info(f"Node config updated: {scenario_id}:{node_id}")
            
            return updated_config
        
        except Exception as e:
            logger.error(f"Failed to update node config: {e}")
            raise
    
    # ============================================================
    # 删除操作
    # ============================================================
    
    async def delete_node_config(
        self,
        scenario_id: str,
        node_id: str,
        change_reason: str = None,
    ) -> bool:
        """删除节点配置"""
        
        try:
            # 获取配置
            existing_config = await self.get_node_config(scenario_id, node_id)
            
            if not existing_config:
                logger.warning(f"Node config not found: {scenario_id}:{node_id}")
                return False
            
            # 保存配置用于历史记录
            old_config = existing_config.full_config
            
            # 记录历史
            await self._record_history(
                node_config_id=existing_config.id,
                config_before=old_config,
                config_after=None,
                change_type="delete",
                change_reason=change_reason or "Configuration deleted",
            )
            
            # 删除
            await self.db.delete(existing_config)
            
            logger.info(f"Node config deleted: {scenario_id}:{node_id}")
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to delete node config: {e}")
            raise
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """验证配置"""
        
        required_fields = ["id", "name", "execution_mode"]
        
        for field in required_fields:
            if field not in config:
                logger.warning(f"Missing required field: {field}")
                return False
        
        valid_modes = ["single_call", "multi_turn_dialog", "polling", "conditional"]
        if config.get("execution_mode") not in valid_modes:
            logger.warning(f"Invalid execution mode: {config.get('execution_mode')}")
            return False
        
        return True
    
    
    async def _record_history(
        self,
        node_config_id: str,
        config_before: Optional[Dict],
        config_after: Optional[Dict],
        change_type: str,
        change_reason: str,
    ):
        """记录配置变更历史"""
        
        try:
            history = NodeConfigHistory(
                node_config_id=node_config_id,
                config_before=config_before,
                config_after=config_after,
                change_type=change_type,
                change_reason=change_reason,
            )
            
            await self.db.create(history)
        
        except Exception as e:
            logger.error(f"Failed to record history: {e}")
    
    
    async def get_node_config_history(
        self,
        node_config_id: str,
        limit: int = 100,
    ) -> List[NodeConfigHistory]:
        """获取节点配置变更历史"""
        
        try:
            async with self.db.async_session() as session:
                stmt = select(NodeConfigHistory).where(
                    NodeConfigHistory.node_config_id == node_config_id
                ).order_by(
                    NodeConfigHistory.created_at.desc()
                ).limit(limit)
                
                result = await session.execute(stmt)
                histories = result.scalars().all()
                
                return histories if histories else []
        
        except Exception as e:
            logger.error(f"Failed to get node config history: {e}")
            raise
    
    
    async def copy_node_config(
        self,
        source_scenario_id: str,
        source_node_id: str,
        target_scenario_id: str,
        target_node_id: str,
    ) -> Optional[NodeConfig]:
        """复制节点配置"""
        
        try:
            # 获取源配置
            source_config = await self.get_node_config(source_scenario_id, source_node_id)
            
            if not source_config:
                logger.warning(f"Source config not found: {source_scenario_id}:{source_node_id}")
                return None
            
            # 创建新配置
            new_config_dict = source_config.full_config.copy()
            new_config_dict["id"] = target_node_id
            
            new_config = await self.create_node_config(
                target_scenario_id,
                target_node_id,
                new_config_dict,
            )
            
            logger.info(f"Node config copied: {source_scenario_id}:{source_node_id} -> {target_scenario_id}:{target_node_id}")
            
            return new_config
        
        except Exception as e:
            logger.error(f"Failed to copy node config: {e}")
            raise