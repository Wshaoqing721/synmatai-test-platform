
from fastapi import APIRouter, HTTPException, File, UploadFile, Path, Query
from typing import Dict, Any, List, Optional
from datetime import datetime
import yaml
import json
from agent_test_platform.config.logger import logger
from agent_test_platform.services.node_config_service import NodeConfigService
from agent_test_platform.models.node_config_model import NodeConfig

router = APIRouter(prefix="/api", tags=["node-config"])

# 全局实例（在 main.py 中初始化）
node_config_service: Optional[NodeConfigService] = None


# ============================================================
# 1. 节点配置 CRUD 操作
# ============================================================

@router.post("/scenarios/{scenario_id}/nodes")
async def create_node(scenario_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """创建新的节点配置（保存到数据库）"""
    
    if not node_config_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        node_id = config.get("id")
        if not node_id:
            raise HTTPException(status_code=400, detail="Missing node id")
        
        # 检查是否已存在
        existing = await node_config_service.get_node_config(scenario_id, node_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Node config already exists: {scenario_id}:{node_id}"
            )
        
        # 创建配置
        node_config = await node_config_service.create_node_config(
            scenario_id=scenario_id,
            node_id=node_id,
            config=config,
        )
        
        logger.info(f"Node created: {scenario_id}:{node_id}")
        
        return {
            "id": node_config.id,
            "node_id": node_config.node_id,
            "scenario_id": node_config.scenario_id,
            "status": "created",
            "message": "Node configuration saved successfully",
            "created_at": node_config.created_at.isoformat(),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create node: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/nodes/{node_id}")
async def get_node_config(scenario_id: str, node_id: str = Path(...)) -> Dict[str, Any]:
    """获取节点配置"""
    
    if not node_config_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        config = await node_config_service.get_node_config(scenario_id, node_id)
        
        if not config:
            raise HTTPException(status_code=404, detail="Node not found")
        
        return config.to_dict()
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get node config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/scenarios/{scenario_id}/nodes/{node_id}")
async def update_node_config(
    scenario_id: str,
    node_id: str = Path(...),
    config: Dict[str, Any] = None,
    change_reason: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """更新节点配置（无需重启应用）"""
    
    if not node_config_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        if not config:
            raise HTTPException(status_code=400, detail="Missing configuration")
        
        # 检查是否存在
        existing = await node_config_service.get_node_config(scenario_id, node_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Node not found")
        
        # 更新配置
        updated_config = await node_config_service.update_node_config(
            scenario_id=scenario_id,
            node_id=node_id,
            config=config,
            change_reason=change_reason,
        )
        
        logger.info(f"Node updated: {scenario_id}:{node_id}")
        
        return {
            "id": updated_config.id,
            "node_id": updated_config.node_id,
            "scenario_id": updated_config.scenario_id,
            "status": "updated",
            "message": "Node configuration updated successfully",
            "updated_at": updated_config.updated_at.isoformat(),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update node config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scenarios/{scenario_id}/nodes/{node_id}")
async def delete_node_config(
    scenario_id: str,
    node_id: str = Path(...),
    change_reason: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """删除节点配置"""
    
    if not node_config_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        # 删除配置
        success = await node_config_service.delete_node_config(
            scenario_id=scenario_id,
            node_id=node_id,
            change_reason=change_reason,
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Node not found")
        
        logger.info(f"Node deleted: {scenario_id}:{node_id}")
        
        return {
            "node_id": node_id,
            "scenario_id": scenario_id,
            "status": "deleted",
            "message": "Node configuration deleted successfully",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete node config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 2. 列表和查询操作
# ============================================================

@router.get("/scenarios/{scenario_id}/nodes")
async def list_nodes(
    scenario_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    """列表场景中的所有节点配置"""
    
    if not node_config_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        # 获取所有节点
        all_nodes = await node_config_service.list_scenario_nodes(scenario_id)
        
        # 分页
        total = len(all_nodes)
        nodes = all_nodes[skip:skip + limit]
        
        return {
            "scenario_id": scenario_id,
            "total": total,
            "skip": skip,
            "limit": limit,
            "nodes": [node.to_dict() for node in nodes],
        }
    
    except Exception as e:
        logger.error(f"Failed to list nodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nodes")
async def list_all_nodes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    """列表所有节点配置"""
    
    if not node_config_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        # 获取所有节点
        all_nodes = await node_config_service.get_all_node_configs()
        
        # 分页
        total = len(all_nodes)
        nodes = all_nodes[skip:skip + limit]
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "nodes": [node.to_dict() for node in nodes],
        }
    
    except Exception as e:
        logger.error(f"Failed to list all nodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 3. 导入导出操作
# ============================================================

@router.post("/scenarios/{scenario_id}/nodes/import")
async def import_nodes_yaml(
    scenario_id: str,
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """导入 YAML 格式的节点配置"""
    
    if not node_config_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        # 读取文件
        content = await file.read()
        config_dict = yaml.safe_load(content)
        
        if not isinstance(config_dict, dict):
            raise HTTPException(status_code=400, detail="Invalid YAML format")
        
        # 解析节点
        nodes_config = config_dict.get("nodes", [])
        if not isinstance(nodes_config, list):
            raise HTTPException(status_code=400, detail="'nodes' field must be a list")
        
        created_count = 0
        failed_nodes = []
        
        for node_config in nodes_config:
            try:
                node_id = node_config.get("id")
                if not node_id:
                    failed_nodes.append({
                        "config": node_config,
                        "error": "Missing 'id' field"
                    })
                    continue
                
                # 检查是否已存在
                existing = await node_config_service.get_node_config(scenario_id, node_id)
                if existing:
                    # 更新而不是创建
                    await node_config_service.update_node_config(
                        scenario_id=scenario_id,
                        node_id=node_id,
                        config=node_config,
                        change_reason="Imported from YAML",
                    )
                else:
                    # 创建新配置
                    await node_config_service.create_node_config(
                        scenario_id=scenario_id,
                        node_id=node_id,
                        config=node_config,
                    )
                
                created_count += 1
            
            except Exception as e:
                failed_nodes.append({
                    "config": node_config,
                    "error": str(e)
                })
        
        logger.info(f"Imported {created_count} nodes for scenario {scenario_id}")
        
        return {
            "scenario_id": scenario_id,
            "imported_count": created_count,
            "failed_count": len(failed_nodes),
            "failed_nodes": failed_nodes,
            "status": "success" if created_count > 0 else "partial_failure",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import nodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/nodes/export")
async def export_nodes_yaml(scenario_id: str) -> Dict[str, Any]:
    """导出场景的所有节点配置为 YAML 格式"""
    
    if not node_config_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        # 获取所有节点
        nodes = await node_config_service.list_scenario_nodes(scenario_id)
        
        # 构建 YAML 数据
        yaml_data = {
            "scenario_id": scenario_id,
            "exported_at": datetime.utcnow().isoformat(),
            "nodes": [node.full_config for node in nodes],
        }
        
        # 转换为 YAML 字符串
        yaml_str = yaml.dump(yaml_data, default_flow_style=False, allow_unicode=True)
        
        return {
            "scenario_id": scenario_id,
            "count": len(nodes),
            "yaml": yaml_str,
        }
    
    except Exception as e:
        logger.error(f"Failed to export nodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 4. 历史和版本管理
# ============================================================

@router.get("/scenarios/{scenario_id}/nodes/{node_id}/history")
async def get_node_config_history(
    scenario_id: str,
    node_id: str = Path(...),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    """获取节点配置变更历史"""
    
    if not node_config_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        # 获取节点配置
        config = await node_config_service.get_node_config(scenario_id, node_id)
        if not config:
            raise HTTPException(status_code=404, detail="Node not found")
        
        # 获取历史
        history = await node_config_service.get_node_config_history(config.id, limit)
        
        return {
            "node_id": node_id,
            "scenario_id": scenario_id,
            "total": len(history),
            "history": [
                {
                    "id": h.id,
                    "change_type": h.change_type,
                    "config_before": h.config_before,
                    "config_after": h.config_after,
                    "change_reason": h.change_reason,
                    "changed_by": h.changed_by,
                    "created_at": h.created_at.isoformat(),
                }
                for h in history
            ],
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get node config history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 5. 复制和克隆
# ============================================================

@router.post("/scenarios/{scenario_id}/nodes/{node_id}/copy")
async def copy_node_config(
    scenario_id: str,
    node_id: str = Path(...),
    target_scenario_id: str = Query(...),
    target_node_id: str = Query(...),
) -> Dict[str, Any]:
    """复制节点配置到另一个场景"""
    
    if not node_config_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        # 复制配置
        new_config = await node_config_service.copy_node_config(
            source_scenario_id=scenario_id,
            source_node_id=node_id,
            target_scenario_id=target_scenario_id,
            target_node_id=target_node_id,
        )
        
        if not new_config:
            raise HTTPException(status_code=404, detail="Source node not found")
        
        logger.info(f"Node copied: {scenario_id}:{node_id} -> {target_scenario_id}:{target_node_id}")
        
        return {
            "source_node_id": node_id,
            "source_scenario_id": scenario_id,
            "target_node_id": target_node_id,
            "target_scenario_id": target_scenario_id,
            "status": "copied",
            "new_config_id": new_config.id,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to copy node config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 6. 配置验证
# ============================================================

@router.post("/nodes/validate")
async def validate_node_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """验证节点配置的有效性"""
    
    try:
        # 检查必需字段
        required_fields = ["id", "name", "execution_mode"]
        missing_fields = [f for f in required_fields if f not in config]
        
        if missing_fields:
            return {
                "valid": False,
                "errors": [f"Missing required fields: {', '.join(missing_fields)}"],
            }
        
        # 检查执行模式
        valid_modes = ["single_call", "multi_turn_dialog", "polling", "conditional"]
        if config.get("execution_mode") not in valid_modes:
            return {
                "valid": False,
                "errors": [f"Invalid execution_mode: {config.get('execution_mode')}"],
            }
        
        # 验证子配置
        errors = []
        
        if "exit_condition" in config:
            exit_cond = config["exit_condition"]
            if not isinstance(exit_cond, dict):
                errors.append("exit_condition must be an object")
        
        if "message_generation" in config:
            msg_gen = config["message_generation"]
            if not isinstance(msg_gen, dict):
                errors.append("message_generation must be an object")
        
        if "task_detection" in config:
            task_det = config["task_detection"]
            if not isinstance(task_det, dict):
                errors.append("task_detection must be an object")
        
        if errors:
            return {
                "valid": False,
                "errors": errors,
            }
        
        return {
            "valid": True,
            "message": "Configuration is valid",
        }
    
    except Exception as e:
        logger.error(f"Failed to validate node config: {e}")
        raise HTTPException(status_code=500, detail=str(e))