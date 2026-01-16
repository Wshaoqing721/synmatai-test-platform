
from typing import Dict, Any, List, Optional
from datetime import datetime

from sqlalchemy.future import select

from agent_test_platform.storage.database import Database
from agent_test_platform.config.logger import logger
from agent_test_platform.models.node_based import Scenario, ScenarioStatus


class ScenarioService:
    """场景管理服务"""

    def __init__(self, db: Database):
        self.db = db

    # ---------- 创建 ----------

    async def create_scenario(
        self,
        name: str,
        description: str = "",
    ) -> Scenario:
        """创建场景"""

        scenario = Scenario(
            name=name,
            description=description,
            status=ScenarioStatus.ACTIVE,
        )

        scenario = await self.db.create(scenario)

        logger.info(f"Scenario created: {scenario.id} - {name}")

        return scenario

    # ---------- 查询 ----------

    async def get_scenario(self, scenario_id: str) -> Optional[Scenario]:
        """获取单个场景"""

        async with self.db.async_session() as session:
            stmt = select(Scenario).where(Scenario.id == scenario_id)
            res = await session.execute(stmt)
            return res.scalars().first()

    async def list_scenarios(self) -> List[Scenario]:
        """列表所有场景"""

        async with self.db.async_session() as session:
            stmt = select(Scenario).order_by(Scenario.created_at.desc())
            res = await session.execute(stmt)
            return list(res.scalars().all())

    async def get_all_scenarios(self) -> List[Scenario]:
        """获取所有场景"""

        return await self.db.query_all(Scenario)

    # ---------- 更新 ----------

    async def update_scenario(
        self,
        scenario_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Scenario]:
        """更新场景"""

        scenario = await self.get_scenario(scenario_id)
        if not scenario:
            return None

        if name:
            scenario.name = name
        if description is not None:
            scenario.description = description
        if status:
            scenario.status = ScenarioStatus(status)

        scenario.updated_at = datetime.utcnow()

        updated = await self.db.update(scenario)

        logger.info(f"Scenario updated: {scenario_id}")

        return updated

    # ---------- 删除 ----------

    async def delete_scenario(self, scenario_id: str) -> bool:
        """删除场景"""

        scenario = await self.get_scenario(scenario_id)
        if not scenario:
            return False

        await self.db.delete(scenario)

        logger.info(f"Scenario deleted: {scenario_id}")

        return True

    # ---------- 统计 ----------

    async def get_scenario_count(self) -> int:
        """获取场景总数"""

        scenarios = await self.list_scenarios()
        return len(scenarios)

    async def get_scenarios_by_status(self, status: str) -> List[Scenario]:
        """按状态获取场景"""

        async with self.db.async_session() as session:
            stmt = (
                select(Scenario)
                .where(Scenario.status == ScenarioStatus(status))
                .order_by(Scenario.created_at.desc())
            )
            res = await session.execute(stmt)
            return list(res.scalars().all())