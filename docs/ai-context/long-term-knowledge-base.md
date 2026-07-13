# ETK 长期知识库

> 用途：作为后续 AI 协作、代码维护、问题定位和功能扩展的长期背景资料。内容以项目源码和现有文档为依据，保持可维护、可增量更新。

## 1. 项目定位

Emby ToolKit（ETK）是围绕 Emby 媒体服务器的增强管理平台。它不是 Emby 替代品，而是补齐个人媒体库长期维护中的自动化能力：

- 115 网盘文件识别、整理、转存、播放直链和 STRM 生成。
- Emby 元数据补全、中文化、演员/角色信息维护和图片回写。
- 智能追剧、缺季缺集补全、演员订阅和统一订阅。
- TMDb 合集、自建合集、虚拟库和反向代理展示。
- 共享资源中心、资源求共享、贡献点和影巢/中心端联动。
- 封面生成、媒体清理、自动标签、播放统计、用户管理和任务调度。

项目整体是“Web 管理后台 + 后台任务链 + 实时监控 + 外部服务集成 + 数据库持久化”的混合系统。

## 2. 技术栈

### 后端

- Python 3.12，生产镜像基于 `python:3.12-slim`。
- Flask 提供 Web API 和静态资源入口。
- gevent / gevent-websocket 提供异步网络与 WebSocket 支持。
- PostgreSQL 16 作为主要数据库，依赖 `psycopg2-binary`。
- APScheduler / croniter / pytz 负责定时任务。
- watchdog 负责目录实时监控。
- requests、BeautifulSoup、lxml 用于 HTTP 和网页解析。
- openai、zhipuai、google-genai 用于 AI 翻译/兼容接口。
- Pillow、numpy、PyYAML 用于封面生成。
- p115client 用于 115 网盘能力。
- telethon / python-socks 用于 Telegram 用户机器人/通知相关能力。

### 前端

- Vue 3 + Vite。
- vue-router 管理页面路由。
- Pinia 管理前端状态。
- Naive UI、Ant Design Vue、@vicons、ECharts 组成主要 UI/图表能力。
- `frontend/package.json` 版本当前为 `10.7.89`。

### 文档与部署

- 根目录 `package.json` 是 VitePress 文档站工程。
- Dockerfile 两阶段构建：先用 Node 20 Alpine 构建前端，再复制到 Python 运行镜像 `/app/static/`。
- `docker-compose.yml` 包含 `emby-toolkit` 和 `db` 两个服务，默认端口包括 5257、8096、5432。

## 3. 架构总览

### 主要组件

- Web 应用层：`web_app.py`
- 核心处理器：`core_processor.py` 中的 MediaProcessor 相关逻辑
- 任务系统：`task_manager.py` + `scheduler_manager.py` + `tasks/`
- 实时监控：`monitor_service.py`
- 反向代理/虚拟库：`reverse_proxy.py`
- 数据库层：`database/connection.py` 和各业务 DB 模块
- 外部服务层：`handler/`
- 前端 UI：`frontend/`

### 简化运行链路

1. 容器入口脚本生成运行配置并启动服务。
2. `web_app.py` 加载配置、数据库和处理器实例。
3. Web API、Webhook、前端操作或调度器触发任务。
4. 任务进入 `task_manager.py` 管理的执行体系。
5. 具体任务调用 `core_processor.py`、`watchlist_processor.py`、`actor_subscription_processor.py`、`handler/` 或 `services/` 完成业务。
6. 结果写入数据库、回写 Emby、刷新视图、更新状态或推送通知。
7. 前端通过 `/api/...` 查询状态和结果。

## 4. 顶层文件职责

- `web_app.py`：Web 服务入口，负责初始化、蓝图注册、静态资源和运行时装配。
- `core_processor.py`：项目最大核心文件，承载媒体元数据识别、处理、翻译、补全和回写等主流程。
- `watchlist_processor.py`：追剧状态、季集跟踪、缺失内容补全。
- `actor_subscription_processor.py`：演员订阅、演员作品追踪和订阅提交。
- `actor_utils.py`：演员相关工具函数。
- `ai_translator.py`：AI 翻译能力封装。
- `config_manager.py`：配置文件和配置项管理。
- `constants.py`：常量定义。
- `extensions.py`：共享扩展对象和运行时依赖注入点。
- `logger_setup.py`：日志配置。
- `monitor_service.py`：文件系统监控服务。
- `nfo_builder.py`：NFO 生成相关逻辑。
- `reverse_proxy.py`：反向代理服务与虚拟库输出。
- `scheduler_manager.py`：定时任务配置和调度。
- `task_manager.py`：任务队列、状态和互斥管理。
- `utils.py`：通用工具函数。

## 5. 目录职责

### `routes/`

按功能域拆分 Flask 蓝图。新增 API 时应优先放在对应业务路由文件中，不要把无关接口塞进大文件。

- `actions.py`：批量动作、复处理入口。
- `actor_subscriptions.py`：演员订阅 API。
- `cover_generator_config.py`：封面生成配置和预览。
- `custom_collections.py`：自建合集管理、规则、映射配置。
- `database_admin.py`：数据库统计、导入导出、维护动作、复核条目。
- `discover.py`：发现页、TMDb 搜索/筛选/推荐。
- `logs.py`：日志列表、查看、搜索、上下文。
- `media.py`：媒体查询、编辑、图片代理、订阅状态、自动标签、媒体信息编辑。
- `media_cleanup.py`：重复版本扫描、清理策略、删除/忽略。
- `p115.py`：115 登录、目录、播放、整理、命名、播放池、音乐、STRM 和系统目录等。
- `resubscribe.py`：补订阅规则和批量操作。
- `shared_resource.py`：共享资源中心、本地分享、中心资源、转存、求共享、贡献点、虚拟播放等。
- `subscription.py`：订阅相关接口。
- `system.py`：系统状态、配置、测试、任务控制等。
- `tasks.py`：任务触发和任务链控制。
- `tmdb_collections.py`：TMDb 合集处理。
- `unified_auth.py`：统一认证。
- `user_management.py`：用户同步、权限、邀请等管理能力。
- `user_portal.py`：普通用户门户。
- `watchlist.py`：智能追剧管理。
- `webhook.py`：Webhook 接入。

### `database/`

数据库层，按业务拆分 CRUD 和查询封装。`connection.py` 是连接、初始化、表结构和索引的重要入口。常见模块：

- `media_db.py`：媒体数据。
- `watchlist_db.py`：追剧数据。
- `actor_db.py`：演员订阅和演员数据。
- `custom_collection_db.py`：自建合集。
- `tmdb_collection_db.py`：TMDb 合集。
- `shared_share_db.py`、`shared_virtual_db.py`、`shared_credit_db.py`：共享资源中心相关数据。
- `resubscribe_db.py`：补订阅规则和状态。
- `request_db.py`：请求/求共享相关数据。
- `user_db.py`：用户、权限、邀请等。
- `cleanup_db.py`：媒体清理记录。
- `settings_db.py`：配置持久化。
- `log_db.py`：日志数据。
- `queries_db.py`：查询封装。
- `maintenance_db.py`：维护类操作。

### `handler/`

外部服务、数据源和复杂业务边界封装。常见模块：

- `emby.py`：Emby API。
- `tmdb.py`、`tmdb_collections.py`：TMDb API 和合集。
- `douban.py`：豆瓣数据。
- `moviepilot.py`：MoviePilot 集成。
- `telegram.py`、`tg_userbot.py`、`tg_media_candidate.py`、`tg_media_candidate_flow.py`：Telegram 通知/用户机器人/候选资源流程。
- `p115_service.py`：115 API 和整理主服务。
- `p115_media_recognition.py`、`p115_media_analyzer.py`、`p115_iso_analyzer.py`：115 媒体识别/分析。
- `p115_rename.py`：命名规则。
- `p115_play_pool.py`、`p115_play_pool_client.py`、`p115_copy_play.py`、`p115_temp_dir.py`：115 播放池、复制播放、临时目录。
- `shared_center_client.py`、`shared_subscription_service.py`、`shared_intro_service.py`：共享中心相关客户端和服务。
- `hdhive_client.py`：影巢相关客户端。
- `custom_collection.py`：自建合集业务处理。
- `poster_generator.py`：封面/海报相关封装。
- `github.py`：GitHub/更新相关能力。
- `maoyan_fetcher.py`：猫眼数据抓取。

### `tasks/`

任务系统按领域拆分，任务注册和任务链通常从 `tasks/core.py` 进入。

- `core.py`：任务注册和任务链定义。
- `media.py`：媒体处理任务。
- `watchlist.py`：追剧任务。
- `actors.py`：演员任务。
- `subscriptions.py`：订阅任务。
- `resubscribe.py`：补订阅任务。
- `custom_collections.py`：自建合集任务。
- `tmdb_collections.py`：TMDb 合集任务。
- `covers.py`：封面生成任务。
- `cleanup.py`：媒体清理任务。
- `discover.py`：发现/推荐任务。
- `hdhive.py`：影巢相关任务。
- `maintenance.py`：维护任务。
- `p115.py`、`p115_fingerprint_helpers.py`：115 任务和指纹辅助。
- `shared_resource_tasks.py`：共享资源任务。
- `users.py`：用户任务。
- `vector_tasks.py`：向量/检索相关任务。
- `system_update.py`：系统更新任务。
- `helpers.py`：任务辅助函数。

### `services/`

- `services/cover_generator/`：封面生成服务与样式，样式文件包括 `style_single_1.py`、`style_single_2.py`、`style_multi_1.py` 和 `badge_drawer.py`。
- `services/subscribe_assistant/`：订阅助手，包含 `config.py`、`engine.py`、`manager.py`、`store.py`。

### `frontend/`

- `frontend/src/router/index.js`：前端路由与登录守卫。
- `frontend/src/stores/auth.js`：认证状态。
- `frontend/src/stores/app.js`：应用状态。
- `frontend/src/components/`：主要页面组件。
- `frontend/src/components/settings/`：配置页组件。
- `frontend/src/components/modals/`：弹窗组件。
- `frontend/src/assets/`：样式、Logo、封面样式资源。
- `frontend/public/`：静态图标、默认图、PWA 图标等。

## 6. 主要前端路由

- `/login`：登录。
- `/setup`：首次配置。
- `/register/invite/:token`：邀请注册。
- `/DatabaseStats`：数据库统计首页，根路径 `/` 会重定向到这里。
- `/organize-records`：115 整理记录。
- `/review`：待复核。
- `/settings/scheduler`：调度设置。
- `/settings/general`：通用设置。
- `/auto-tagging`：自动标签。
- `/watchlist`：智能追剧。
- `/collections`：TMDb 合集。
- `/custom-collections`：自建合集。
- `/edit-media/:itemId`：媒体编辑。
- `/actor-subscriptions`：演员订阅。
- `/releases`：发布/版本相关页面。
- `/settings/cover-generator`：封面生成配置。
- `/resubscribe`：补订阅。
- `/shared-resources`：共享资源中心，要求管理员权限。
- `/media-cleanup`：媒体清理。
- `/user-management`：用户管理。
- `/unified-subscriptions`：统一订阅。
- `/user-center`：用户中心。
- `/stats`：Emby 统计，要求管理员权限。
- `/discover`：探索/发现。

## 7. 核心业务流

### 主动入库流

1. 实时监控识别新增 STRM 或实体媒体，并准备简版 NFO；实体文件同时准备媒体信息侧车。
2. ETK 主动通知 Emby 扫描，并按媒体路径轮询取得 Item ID。
3. Item ID 进入核心处理器，完成元数据补全、翻译、中文化、数据库写入和 Emby 回写。
4. 必要时刷新追剧、合集、封面、TMDb 合集订阅和 Telegram 通知。

### 任务链流

1. 调度器或前端调用 `/api/tasks/run` 触发任务。
2. `task_manager.py` 管理任务互斥、状态、进度和日志。
3. `tasks/core.py` 中注册的任务链按顺序执行具体任务。
4. 任务模块调用处理器、数据库和 handler 完成业务。

### 115 整理/播放流

1. 前端或任务触发 115 扫描、识别、整理。
2. `routes/p115.py` 接收 API 请求。
3. `handler/p115_service.py` 和识别/分析/命名模块处理目录、文件、媒体信息和规则。
4. 生成 STRM、记录整理结果，必要时提供 `/api/p115/play/...` 或虚拟播放接口。

### 共享资源流

1. 本地资源登记或从中心资源浏览。
2. 共享资源中心按 TMDb、SHA1、季集、标签和一致性规则聚合。
3. 用户可转存、秒传、求共享、贡献点消费或奖励。
4. 本地任务维护分享状态、资源可用性和中心端同步。

### 反向代理/虚拟库流

1. `reverse_proxy.py` 汇总原生库、自建合集和虚拟库项目。
2. 对虚拟项目做 ID、排序、分页和代理响应。
3. 通过 Nginx/代理入口把增强展示提供给 Emby 客户端。

## 8. 配置和运行数据

- 本地默认数据目录：`local_data/`。
- Docker/生产默认配置目录：`/config`，由 `APP_DATA_DIR=/config` 指定。
- 本地配置文件常见位置：`local_data/config.ini`。
- 不要把 `local_data/`、真实 `.env`、数据库、token/state、venv 或构建缓存写入长期文档或提交。

## 9. 本地开发与验证

### 后端

```powershell
pip install -r requirements.txt
python web_app.py
```

针对具体 Python 改动，优先编译检查改动文件：

```powershell
python -m py_compile path\to\changed_file.py
```

### 前端

```powershell
Push-Location frontend
npm install
npm run dev
npm run build
Pop-Location
```

### 文档站

```powershell
npm run docs:dev
npm run docs:build
```

## 10. Docker 与生产部署知识

### 镜像构建逻辑

- 第一阶段：`node:20-alpine` 构建 `frontend/dist`。
- 第二阶段：`python:3.12-slim` 安装系统依赖、Python 依赖、复制后端代码、复制前端静态文件到 `/app/static/`。
- 运行时入口：`/entrypoint.sh`。
- 健康检查：`http://localhost:5257/api/health`。

### Compose 服务

- 应用服务：`emby-toolkit`
- 数据库服务：`emby-toolkit-db` / Postgres 16 Alpine
- 应用端口：5257，Emby 代理相关端口在 compose 中映射 8096，Dockerfile 暴露 8097。
- 数据库端口：5432。

### 热更新原则

生产容器宿主机使用 SSH 别名 `unraid`，容器名固定 `emby-toolkit`。生产 `/app` 不是宿主机源码挂载，因此热更新必须：

1. 本地验证。
2. 打只包含本次改动文件和必要前端构建产物的临时包。
3. 上传到 `unraid:/tmp/`。
4. 备份容器内旧文件。
5. 用 `docker cp` 覆盖对应文件。
6. 修复 `/app/static` 权限。
7. 后端改动重启容器并检查健康状态。

详细命令见根目录 `AGENTS.md`，不要凭记忆改生产。

## 11. 外部服务和敏感信息

项目会接触 Emby、115、TMDb、MoviePilot、Telegram、共享中心、影巢中转服务器、SSH 生产宿主机等外部系统。连接参数和凭据类信息集中在 `AGENTS.md` 或本地配置中。

长期知识库只记录“去哪里找”和“如何使用”，不要复制明文密码、API Key、cookie、token 或真实 `.env` 内容。

## 12. 修改建议

### 新增后端 API

1. 找到对应业务域的 `routes/*.py`。
2. 复用已有配置、数据库和 handler，不新增跨域依赖。
3. 若需要后台处理，新增或复用 `tasks/` 任务。
4. 若需要持久化，优先在对应 `database/*_db.py` 中封装访问。
5. 做最小 py_compile 或接口级验证。

### 新增前端页面/功能

1. 找对应页面组件或设置页组件。
2. 复用现有 Naive UI/Ant Design Vue 风格。
3. API 请求通过现有 axios 用法。
4. 路由放在 `frontend/src/router/index.js`。
5. 跑 `npm run build` 验证。

### 修复业务 Bug

1. 先定位入口：前端页面、API 路由、任务、handler、数据库。
2. 尽量写出复现命令、日志定位或最小验证步骤。
3. 改动只触及根因文件。
4. 验证不要只看无报错，最好检查目标行为或返回值。

## 13. 已知注意事项

- 部分旧 Markdown 或源码注释存在中文乱码显示，实际业务逻辑仍需以代码和上下文为准。
- `core_processor.py`、`watchlist_processor.py`、`shared_resource.py`、`p115.py`、`reverse_proxy.py` 等文件较大，修改前必须先局部搜索相关函数和调用点。
- 前端路由守卫依赖 `authStore.checkAuthStatus()`，首次配置会使用 `SETUP_REQUIRED` 跳转到 `/setup`。
- 共享资源、115 播放、虚拟库、反向代理都是高耦合功能，改动时需要同时检查路由、handler、database、tasks 和前端调用。
- 静态资源热更新后若浏览器报 JS MIME type 为 `text/html`，优先检查 `/app/static/assets` 权限。

## 14. 文档维护规则

- 短期上下文只放“快速接手需要知道什么”。
- 长期知识库放稳定事实、架构、流程和维护约定。
- 如果后续新增重要模块、路由、任务链或部署流程，应同步更新本文件。
- 凭据和实时状态不进知识库，统一引用安全位置。

## 15. 对话沉淀与长期记忆

本节记录从项目协作对话中沉淀下来的长期有效规则。它不是聊天流水账，只保留后续任务会反复用到的结论、约定和维护方式。

### 本轮已形成的长期约定

- 项目 AI 上下文统一放在 `docs/ai-context/`。
- 短期交接文档是 `docs/ai-context/short-term-context.md`，用于每次任务开始时快速恢复项目背景。
- 长期知识库是 `docs/ai-context/long-term-knowledge-base.md`，用于记录稳定架构、模块边界、业务流程、部署方式和协作规则。
- `AGENTS.md` 已加入自动读取规则：每次处理本项目任务前先读短期上下文；涉及架构、跨模块、部署、长期维护或新功能设计时再读长期知识库。
- 自动读取知识库不等于跳过需求确认；目标、边界或关键假设不清楚时仍必须先问。
- 长期知识库不保存明文密码、API Key、cookie、token、真实 `.env`、数据库内容或其他敏感运行状态。
- 需要使用外部连接、生产热更新、SSH、MoviePilot MCP、Emby 等细节时，回到 `AGENTS.md` 或本地配置查阅，不在知识库中重复敏感值。

### 对话整理原则

- 只沉淀“以后还会用”的信息：项目结构、稳定规则、排障路径、部署流程、模块职责、已确认的协作偏好。
- 不沉淀一次性状态：临时命令输出、当前未提交状态、某次扫描结果、一次性调试日志。
- 不沉淀敏感明文：账号密码、API Key、token、cookie、内网服务密钥、真实 `.env`。
- 不把用户的一次性表达改写成永久需求；只有明确可复用、可验证、对后续任务有帮助的内容才进入长期知识库。
- 如果对话中产生了代码改动、部署经验或排障结论，优先写成“触发条件 + 处理方式 + 验证命令/检查点”的形式。

### 推荐更新流程

1. 开始任务前读取短期上下文；必要时读取长期知识库。
2. 完成任务后判断是否产生可复用经验。
3. 若只是一次性执行结果，不写入长期知识库。
4. 若是稳定规则、模块认知、部署流程或排障经验，追加到本文件对应章节。
5. 更新后检查是否误写敏感明文。
6. 用 `git status --short` 确认只修改了预期文件。
