# ETK 短期对话上下文

> 用途：把这份内容粘到新对话开头，让助手快速接上当前项目。适合短期交接，不替代长期知识库。

## 当前项目

- 项目路径：`D:\work\emby-toolkit`
- 项目名称：Emby ToolKit / ETK
- 项目类型：面向 Emby 用户的媒体库增强工具，核心围绕 115 网盘整理、STRM 入库、元数据补全、追剧订阅、演员订阅、资源共享、合集维护、封面生成、清理和 Web 管理后台。
- 技术栈：Python 3.12 + Flask 后端，PostgreSQL 持久化，Vue 3 + Vite 前端，Docker 镜像包含 Nginx、ffmpeg、前端构建产物与后端服务。
- Emby 连接约定：首次配置或重新授权使用 Emby 管理员账号换取长期服务 Token，用户名和密码不落盘；内部沿用 `emby_api_key` 键保存 Token，并以 `emby_auth_mode=user_token` 标记授权完整。缺少标记时登录后强制授权，一键部署同时在前端和后端拒绝执行。
- 媒体信息约定：`p115_mediainfo_cache.mediainfo_json` 是格式化媒体流数据源，`media_metadata` 是媒体元数据持久化来源，通过独立的 [ETK MediaInfo Bridge](https://github.com/hbq0405/etk-mediainfo-bridge) 插件直接注入 Emby。ETK 不再生成或读取 NFO。整理阶段先写入除人物表外的完整元数据，并保存海报、背景、Logo、横版缩略图和季海报路径；这四个字段只作为元数据源路径，不再决定实际图片仓库内容。`metadata_ready` 表示首次刮削数据已就绪，`actors_ready` 表示翻译后人物表已完成，`metadata_schema_version` 表示当前字段集合是否已完整尝试回填。插件实现 Movie/Series/Season/Episode 元数据 Provider 和图片 Provider，STRM 首次扫描根据 pick code/SHA1、实体媒体首次扫描根据持久化路径返回确定的 TMDb 身份，最终刷新从数据库恢复完整元数据与图片；Season 响应只携带季号，Episode 响应才携带集号，插件也按项目类型分别写入 Emby 索引，禁止用集号覆盖季号。图片 Provider 和刷新收尾恢复把媒体项所属库的 `TypeOptions.ImageOptions` 提交给 `/api/emby/metadata/images/sync`；ETK 在 `media_image_policy_cache` 中按项目保存 Primary、Art、Backdrop、Banner、Logo、Thumb、Disc 的启用状态、数量、最小宽度和最终候选，相同策略直接复用，策略变化才重新查询 TMDb。开启“持久化元数据图片”后只把策略清单实际引用的图片写入现有 SHA256 内容仓库，关闭或缩减类型时清理不再引用的旧缓存；普通同步保留 Emby 手动选图，“替换现有图像”才强制重选。TMDb 没有独立 Art/Banner/Disc 分类，因此分别复用背景图、背景图和海报候选；Emby“搜索图像”仍实时查询 TMDb 全量候选且不改策略缓存。媒体流仍由插件从 `mediainfo_json` 注入；新 STRM 入库时插件从 Emby `ItemAdded/ItemUpdated` 事件取得 ItemID，注入前清空旧媒体流并删除抢占内嵌索引的外挂流，成功后调用 ETK `item-ready`；对于 Emby 删库重建等非 ETK 主动入库场景，`item-ready` 会按路径优先、pick code/SHA1 兜底轻量重绑 Movie/Episode 的新 ItemID，Episode 同时修正父 Series/Season，不运行 TMDb、翻译、图片或入库任务；若旧绑定已被同步任务清空，则仅在 STRM 指纹验证通过且 Emby 当前 TMDb ID 唯一命中同类型 ETK 记录时重建最小资产、SHA1 和 PickCode 数组。最终刷新重新识别外挂流，插件回补时将冲突外挂流移动到未占用索引。ETK 为 STRM 插件上报保留 8 秒优先窗口，超时才按路径轮询兜底；物理媒体仍直接轮询。剧集 ItemID 按 SeriesId 等待 3 秒聚合后一次提交，同一 ItemID 在插件回调与路径兜底之间只分派一次，待提交队列也会合并同剧分集。Emby 手动或任务刷新后，插件通过 `/api/p115/mediainfo/...` 自动回补媒体流；插件启动及神医片头提取任务完成后全库扫描片头，通知 ETK 将新增或变化的章节写回 `mediainfo_json.Chapters` 并上传共享中心，刷新清空章节时从本地快照恢复。首次入库和秒传预检会从中心合并已有片头；截图仍只在 ETK 临时目录生成并上传 Emby，不在媒体目录落地。Episode 无正式剧照时另用 `screenshot_hash` 持久化当前兜底截图；截图没有固定过期时间，只有同集正式剧照成功接管后才删除索引和物理文件，重截也只保留最新版。开启功能前已经存在于 Emby 缓存的旧截图，会在该 Episode 后续刷新时按 `emby_item_ids_json` 读取当前 Primary 并自动迁移进图片仓库。家庭视频因没有稳定 TMDb 分集身份暂不进入仓库；“补齐视频截图”任务会扫描 Emby 缺少主图的 Movie/Episode/Video STRM 并补图；“补齐媒体元数据”任务只重新处理结构版本落后的在库记录，并在批量补齐时保留既有人物表、跳过人物及角色翻译，插件也在 Emby 计划任务中提供同名触发入口；Emby 手动刷新单项时，Provider 检测到根 Movie/Series 的结构版本落后会异步补齐该根项目，完成后按现有流程刷新该 Item，不扫描全库；递归刷新 Series 后，ETK 收尾阶段会批量回补全部 Episode 实际版本。媒体信息维护只保留“重建媒体信息”任务：增量模式检查 Emby 并仅恢复缺失媒体流的实际版本，全量模式才处理全部在库版本。
- 元数据展示约定：插件响应在“关键词写入标签/工作室中文化”开关开启时，只输出命中对应映射表的中文标签，未映射原始值不写入 Emby；ETK 可保留中文分级分类，但 Emby `OfficialRating` 必须使用映射后的美国分级代码，不能写中文标签，否则家长控制不生效。
- TMDb 合集约定：ETK 不再提供独立“启用合集”开关，是否导入只读取电影所属 Emby 媒体库的 `ImportCollections`；`collections_info` 中电影所属合集元数据默认未激活，仅供插件按 `MinCollectionItems` 判断并创建 BoxSet，插件创建成功后主动通知 ETK 绑定 Emby ID 并激活，主入库流程不反查 Emby；ETK 页面和缺失订阅只读取激活记录。插件按 TMDb 合集 ID 创建或加入 BoxSet，并拦截 Emby 单项刷新 API，在刷新即使没有触发 `ItemUpdated` 时仍延迟回补合集关系。
- ItemID 自动重绑成功后会推进 `last_synced_at`，增量同步也会把桥接回调对应的 `last_updated_at` 作为兼容基线，避免 Emby 删库重建后把仅修改 ItemID 的项目重复判为待同步；路径、容器、大小或回调后的新变化仍会进入队列。
- TMDb 合集详情明确 404 时，ETK 只删除类型为 `BoxSet` 且 TMDb ID 完全匹配的 Emby 合集，同时清理 `collections_info`、图片策略和无引用图片缓存；电影、剧集详情 404 或合集图片接口失败不触发删除。
- 实体媒体插件化约定：实体文件识别后会在首次扫描前把路径和季集号占位写入 `asset_details_json`，插件通过 `/api/emby/metadata` 按路径取得 TMDb 身份、元数据和图片，媒体流仍由 Emby 原生探测。ETK 会通过 Emby API 自动注册并持久化插件所需的服务地址，因此纯实体媒体库也不要求预先存在 STRM。

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
- Webhook：`/webhook/emby` 只保留 MoviePilot 事件，不再兼容 Emby Webhook；ETK MediaInfo Bridge 通过 `/api/emby/events` 上报播放、用户数据、权限、合集和手动元数据/图片编辑事件，用户主动删除走独立的两阶段接口。元数据和图片都由对应的 Emby 手动保存 API 打短时标记后才上报，普通 `MetadataEdit`、刷新导入和 ETK 自身回填会被过滤；从 Emby 搜索图像手动下载 TMDb 图片时，插件同时上报图片类型与原始链接，ETK 只更新 `media_metadata` 对应的单个图片字段，不覆盖其他图片缓存；主动删除按 Movie/Episode/Season/Series 从 `media_metadata` 展开完整 PickCode。插件计划任务更新固定从已注册的 ETK 地址访问 `/api/emby/plugin-update`，由 ETK 使用全局网络代理流式转发官方 Release DLL，Emby 不再直连 GitHub。ETK 每次启动 30 秒后比较 Emby 已装插件和 GitHub Latest；仅版本落后时触发插件更新任务，且只有任务成功并确认 `HasPendingRestart=true` 才自动重启 Emby。
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
