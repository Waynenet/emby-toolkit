# ETK 短期对话上下文

> 用途：把这份内容粘到新对话开头，让助手快速接上当前项目。适合短期交接，不替代长期知识库。

## 当前项目

- 项目路径：`D:\work\emby-toolkit`
- 项目名称：Emby ToolKit / ETK
- 项目类型：面向 Emby 用户的媒体库增强工具，核心围绕 115 网盘整理、STRM 入库、元数据补全、追剧订阅、演员订阅、资源共享、合集维护、封面生成、清理和 Web 管理后台。
- 技术栈：Python 3.12 + Flask 后端，PostgreSQL 持久化，Vue 3 + Vite 前端，Docker 镜像包含 Nginx、ffmpeg、前端构建产物与后端服务。
- 媒体信息约定：`p115_mediainfo_cache.mediainfo_json` 是格式化媒体流数据源，`media_metadata` 是媒体元数据持久化来源，通过独立的 [ETK MediaInfo Bridge](https://github.com/hbq0405/etk-mediainfo-bridge) 插件直接注入 Emby。ETK STRM 不再生成简版或完整 NFO；实体媒体仍保留 NFO 兜底。整理阶段先写入除人物表外的完整元数据，并保存海报、背景、Logo、横版缩略图和季海报路径；`metadata_ready` 表示首次刮削数据已就绪，`actors_ready` 表示翻译后人物表已完成。插件实现 Movie/Series/Season/Episode 元数据 Provider 和图片 Provider，首次扫描根据 STRM pick code/SHA1 返回确定的 TMDb 身份，最终刷新从数据库恢复完整元数据与图片。媒体流仍由插件从 `mediainfo_json` 注入；新 STRM 入库时插件从 Emby `ItemAdded/ItemUpdated` 事件取得 ItemID，注入前清空旧媒体流并删除抢占内嵌索引的外挂流，成功后调用 ETK `item-ready`；最终刷新重新识别外挂流，插件回补时将冲突外挂流移动到未占用索引。ETK 为插件保留 8 秒优先窗口，超时才按路径轮询兜底；物理媒体仍直接轮询。剧集 ItemID 按 SeriesId 等待 3 秒聚合后一次提交，同一 ItemID 在插件回调和路径兜底之间只分派一次，待提交队列也会合并同剧分集。Emby 手动或任务刷新后，插件通过 `/api/p115/mediainfo/...` 自动回补媒体流；插件启动及神医片头提取任务完成后全库扫描片头，通知 ETK 将新增或变化的章节写回 `mediainfo_json.Chapters` 并上传共享中心，刷新清空章节时从本地快照恢复。首次入库和秒传预检会从中心合并已有片头；智能追剧的缺图分集只在 ETK 临时目录截图并上传 Emby `Primary` 缓存，临时图随即删除，TMDb 后续出图时先更新数据库再替换 Emby 缓存；递归刷新 Series 后，ETK 收尾阶段会批量回补全部 Episode 实际版本。媒体信息维护只保留“重建媒体信息”任务：增量模式检查 Emby 并仅恢复缺失媒体流的实际版本，全量模式才处理全部在库版本。

## 本项目协作规则

- 先确认目标再改代码；关键需求不清楚时必须先问。
- 改动要简单、外科手术式，只覆盖用户要求的范围。
- 修改后必须用测试、构建、运行命令或明确检查验证结果。
- 不要无关重构，不要顺手清理无关文件。
- 新文档不要重复写入明文账号、密码、API Key 等敏感信息；需要时引用 `AGENTS.md` 中的运维备查。

## 关键入口

- `web_app.py`：Flask Web 服务入口，初始化配置、数据库、处理器、任务系统和蓝图。
- `core_processor.py`：核心媒体处理器，负责元数据处理、翻译、补全和回写。
- `watchlist_processor.py`：智能追剧处理。
- `actor_subscription_processor.py`：演员订阅处理。
- `task_manager.py`：任务队列与任务状态。
- `scheduler_manager.py`：定时任务调度。
- `monitor_service.py`：媒体目录实时监控。
- `reverse_proxy.py`：虚拟库/自建合集反向代理，单独 Flask `proxy_app`。
- `config_manager.py`：配置读取、保存和默认值管理。
- `extensions.py`：全局扩展/共享对象。
- `constants.py`：项目常量。

## 目录速览

- `routes/`：API 蓝图，按功能域拆分。
- `database/`：数据库连接、初始化、表结构和 CRUD 封装。
- `handler/`：外部系统和数据源封装，如 Emby、TMDb、豆瓣、MoviePilot、Telegram、115、影巢/共享中心。
- `tasks/`：任务链和具体任务实现。
- `services/cover_generator/`：封面生成服务与样式。
- `services/subscribe_assistant/`：订阅助手配置、引擎、存储和管理器。
- `frontend/`：Vue 3 前端工程。
- `docs/`：VitePress 文档站。
- `docker/entrypoint.sh`：容器启动逻辑。
- `local_data/`：本地运行数据与配置，通常不要纳入文档或提交。

## 后端功能域

- 系统配置与状态：`routes/system.py`
- 登录/注册/统一认证：`routes/unified_auth.py`
- 用户管理和用户门户：`routes/user_management.py`、`routes/user_portal.py`
- 媒体查询、编辑、图片代理、自动标签：`routes/media.py`
- 日志查看和搜索：`routes/logs.py`
- 任务触发和动作入口：`routes/tasks.py`、`routes/actions.py`
- Webhook：`routes/webhook.py`，核心入口包括 Emby Webhook。
- 115 网盘：`routes/p115.py`，包括扫码、cookie、目录、播放直链、整理规则、命名规则、播放池、音乐同步、STRM 替换等。
- 追剧：`routes/watchlist.py`
- 演员订阅：`routes/actor_subscriptions.py`
- TMDb 合集：`routes/tmdb_collections.py`
- 自建合集：`routes/custom_collections.py`
- 补订阅/统一订阅：`routes/resubscribe.py`、`routes/subscription.py`
- 共享资源中心：`routes/shared_resource.py`
- 媒体清理：`routes/media_cleanup.py`
- 数据库维护：`routes/database_admin.py`
- 封面生成配置：`routes/cover_generator_config.py`
- 发现页/TMDb 探索：`routes/discover.py`

## 前端页面入口

前端路由在 `frontend/src/router/index.js`。主要页面包括：

- `/login`、`/setup`、`/register/invite/:token`
- `/DatabaseStats` 数据库概览
- `/organize-records` 115 整理记录
- `/review` 待复核条目
- `/settings/scheduler` 调度配置
- `/settings/general` 通用配置
- `/auto-tagging` 自动标签
- `/watchlist` 智能追剧
- `/collections` TMDb 合集
- `/custom-collections` 自建合集
- `/edit-media/:itemId` 媒体编辑
- `/actor-subscriptions` 演员订阅
- `/releases` 版本/发布相关页面
- `/settings/cover-generator` 封面生成配置
- `/resubscribe` 补订阅
- `/shared-resources` 共享资源中心，管理员页面
- `/media-cleanup` 媒体清理
- `/user-management` 用户管理
- `/unified-subscriptions` 统一订阅
- `/user-center` 用户中心
- `/stats` Emby 播放统计，管理员页面
- `/discover` 探索页

## 本地验证常用命令

```powershell
python -m py_compile routes\media.py services\subscribe_assistant\manager.py
Push-Location frontend
npm run build
Pop-Location
```

通用后端检查可按改动文件替换 `py_compile` 参数。前端改动优先跑 `frontend` 下的 `npm run build`。

## 生产热更新注意

生产容器宿主机使用 SSH 别名 `unraid`，容器名固定为 `emby-toolkit`，容器内应用目录 `/app`，静态目录 `/app/static`。生产 `/app` 不是宿主机源码挂载，热更新要用 `docker cp` 覆盖容器内文件。详细流程和回退命令见项目根目录 `AGENTS.md` 的“生产容器热更新备查”。

## 外部连接备查

- Emby、SSH、MoviePilot MCP、影巢中转服务器等连接细节在 `AGENTS.md`。
- 新增文档时不要复制明文密码、API Key 或私钥路径以外的敏感值；需要使用时回到 `AGENTS.md` 查阅。

## 当前生成的长期资料

- 长期知识库：`docs/ai-context/long-term-knowledge-base.md`
- 短期上下文：`docs/ai-context/short-term-context.md`
