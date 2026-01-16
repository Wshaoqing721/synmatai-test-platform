
## PostgreSQL (docker-compose)

在项目根目录启动 PostgreSQL：

`docker compose up -d`

默认会启动一个数据库：

- host: `localhost`
- port: `5432`
- user: `agent`
- password: `agent`
- db: `agent_test_platform`

应用使用 `DATABASE_URL` 连接数据库（SQLAlchemy async URL）：

`postgresql+asyncpg://agent:agent@localhost:5432/agent_test_platform`

可以复制 `.env.example` 为 `.env` 并按需修改。

