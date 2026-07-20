# Agent 工作要求

## 1. Think Before Coding

先想清楚，再动手写。

- 需求不确定时，先停下来询问，不要擅自假设。
- 存在多种理解时，先把可能理解列出来，再确认方向。
- 不要闷头猜测，也不要在关键信息缺失时直接实现。

核心原则：一句话，不准瞎假设。

## 2. Simplicity First

能简单，绝不复杂。

- 只写解决当前问题所需的最少代码。
- 50 行能解决的，不要写成 200 行。
- 避免过度抽象、过度封装和无必要的复杂设计。

核心原则：代码越少、路径越短，越容易验证和维护。

## 3. Surgical Changes

外科手术式改动。

- 用户要求改哪里，就只改哪里。
- 不要顺手优化、重构或清理无关代码。
- 修改范围要可控，避免引入额外风险。

核心原则：让它改哪，它就只改哪。

## 4. Goal-Driven Execution

先定目标，再让代码自己验证。

- 开始前明确本次任务的目标和完成标准。
- 修 Bug 时，优先写出能复现问题的测试或验证步骤。
- 修改后必须通过测试、运行结果或明确检查来证明目标已达成。

核心原则：先定目标，再验证结果。

## 临时测试文件约定

- `tests/` 仅用于本地验证和生产热更新前测试，属于临时目录。
- 测试通过后，必须在提交、推送前删除 `tests/` 及其生成物。
- 禁止将 `tests/` 中的临时测试文件纳入 Git 跟踪或提交。

## 执行检查清单

每次开始编码前，先检查：

- 我是否已经理解用户真正要解决的问题？
- 是否存在需要确认的关键假设？
- 是否可以用更少、更简单的代码完成？
- 修改范围是否只覆盖本次任务需要的部分？
- 完成后是否有测试、命令或步骤可以验证结果？

## AI 上下文文档自动读取

每次处理本项目任务前，应先读取 `docs/ai-context/short-term-context.md`，用于快速接手项目当前约定、关键入口和常用验证方式。

涉及架构判断、模块边界、部署热更新、长期维护、跨模块修改或新功能设计时，还应读取 `docs/ai-context/long-term-knowledge-base.md`，并以其中的项目结构、业务流和维护规则作为背景参考。

读取这些文档不代表可以跳过需求确认；如果用户目标或关键假设仍不清楚，仍需先暂停并澄清。

## Emby 服务器连接备查（别名）

敏感连接值不写入本文件；恢复 Git 跟踪前应确保这里只保留别名和用途。

- 服务别名：`emby-main`
- 用途：本项目默认 Emby 服务器。
- 私密信息：地址、账号、密码保存在本机私密备查或密码管理器中，不提交到仓库。
- 使用方式：需要连接 Emby 时，先解析 `emby-main` 对应的本机私密配置。

## SSH 远程连接
SSH 连接必须使用本机 SSH config 中的别名，不在本文件记录公网 IP、端口、用户名、私钥路径等敏感值。

- 中心服务器别名：`center`
- 生产容器宿主机别名：`unraid`
- 影巢中转服务器别名：`hdhive-relay`
- 连接方式：从本机 Windows 通过 `ssh <alias>` 连接。
- 中心端代码：没有 GitHub 仓库，本地源码备份路径使用别名 `center-source-backup` 管理。
- 影巢中转服务器源码备份路径使用别名 `hdhive-relay-source-backup` 管理。该备份只保存 `app.py`、`hdhive-auth.service`、`requirements.txt` 和脱敏 `.env.example`，不保存 SQLite 数据库、token/state、venv 或真实 `.env`。

如果以上任一项不清楚，应先暂停并澄清，而不是直接编码。

## 生产容器热更新备查

生产容器宿主机走 SSH 别名 `unraid`，容器名固定为 `emby-toolkit`。容器内应用目录是 `/app`，前端静态文件目录是 `/app/static`。生产容器的 `/app` 不是宿主机源码挂载，热更新要用 `docker cp` 覆盖容器内文件。

标准流程：

1. 本地先完成验证。

```powershell
python -m py_compile routes\media.py services\subscribe_assistant\manager.py
Push-Location frontend
npm run build
Pop-Location
```

2. 在本机打热更新临时包。只放本次要更新的后端文件和 `frontend/dist`。

```powershell
$hotfix = Join-Path $env:TEMP 'etk-hotfix'
if ($hotfix -notlike "$env:TEMP*") { throw 'unexpected temp path' }
Remove-Item -LiteralPath $hotfix -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path (Join-Path $hotfix 'routes') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $hotfix 'services\subscribe_assistant') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $hotfix 'static') -Force | Out-Null

Copy-Item -LiteralPath 'routes\media.py' -Destination (Join-Path $hotfix 'routes\media.py')
Copy-Item -LiteralPath 'services\subscribe_assistant\manager.py' -Destination (Join-Path $hotfix 'services\subscribe_assistant\manager.py')
Copy-Item -Path 'frontend\dist\*' -Destination (Join-Path $hotfix 'static') -Recurse -Force
```

3. 上传到生产宿主机。

```powershell
scp -r "$env:TEMP\etk-hotfix" unraid:/tmp/
```

4. 远端备份容器内旧文件，再覆盖新文件。按实际改动增减 `docker cp` 的文件列表；不要无脑覆盖无关目录。

```powershell
ssh unraid 'set -e; ts=$(date +%Y%m%d-%H%M%S); backup=/tmp/etk-hotfix-backup/$ts; mkdir -p "$backup/routes" "$backup/services/subscribe_assistant" "$backup/static"; docker cp emby-toolkit:/app/routes/media.py "$backup/routes/media.py"; docker cp emby-toolkit:/app/services/subscribe_assistant/manager.py "$backup/services/subscribe_assistant/manager.py"; docker cp emby-toolkit:/app/static/. "$backup/static/"; docker cp /tmp/etk-hotfix/routes/media.py emby-toolkit:/app/routes/media.py; docker cp /tmp/etk-hotfix/services/subscribe_assistant/manager.py emby-toolkit:/app/services/subscribe_assistant/manager.py; docker cp /tmp/etk-hotfix/static/. emby-toolkit:/app/static/; echo "$backup"'
```

`docker cp` 可能把新拷入的目录权限置成 `700 root:root`，导致 `/assets/*.js` 被服务端回退成 `index.html`，浏览器报 `Expected a JavaScript-or-Wasm module script but the server responded with a MIME type of "text/html"`。覆盖静态文件后必须修权限：

```powershell
ssh unraid "docker exec emby-toolkit find /app/static -type d -exec chmod 755 {} +"
ssh unraid "docker exec emby-toolkit find /app/static -type f -exec chmod 644 {} +"
```

5. 后端 Python 改动必须重启容器才会生效。前端静态文件覆盖后通常立即可用，但统一重启更稳。

```powershell
ssh unraid "docker restart emby-toolkit"
ssh unraid "docker ps --filter name=emby-toolkit --format '{{.Names}} {{.Status}}'"
ssh unraid "docker exec emby-toolkit curl -fsS http://localhost:5257/api/health"
ssh unraid "docker exec emby-toolkit curl -sI http://localhost:5257/assets/index-BhODbAkL.js"
```

注意事项：

- PowerShell 会抢先解析 `$()`、管道和引号。复杂远端命令优先用外层双引号配合简单命令，或外层单引号把 Bash 片段完整交给远端。
- 不要在容器里执行未确认变量的 `rm -rf /app/static/*`。如果需要清空静态目录，先单独确认命令在远端 Bash 中展开正确。
- `docker cp /tmp/etk-hotfix/static/. emby-toolkit:/app/static/` 会覆盖当前入口引用的静态文件，旧 hash 文件残留通常不影响验证。
- 静态资源验证时，`/assets/index-*.js` 必须返回 `Content-Type: text/javascript`。如果返回 `text/html`，优先检查 `/app/static/assets` 目录权限。
- 如需回退，使用第 4 步输出的 `/tmp/etk-hotfix-backup/<timestamp>` 目录，把备份文件 `docker cp` 回容器后重启。

## MP-MCP 连接备查

MoviePilot 内置 Streamable HTTP MCP，可直接通过 HTTP JSON-RPC 调用。

- 服务别名：`moviepilot-main`
- MCP 端点别名：`moviepilot-main-mcp`
- 工具列表端点别名：`moviepilot-main-mcp-tools`
- 认证 Header：`X-API-KEY: <MOVIEPILOT_API_KEY>`
- 推荐 Header：`Accept: application/json, text/event-stream`
- 私密信息：实际地址和 API Key 保存在本机私密备查或环境变量中，不提交到仓库。

最小验证命令：

```powershell
$mpMcpEndpoint = $env:MOVIEPILOT_MCP_ENDPOINT
$mpApiKey = $env:MOVIEPILOT_API_KEY
if (-not $mpMcpEndpoint -or -not $mpApiKey) { throw 'Missing MOVIEPILOT_MCP_ENDPOINT or MOVIEPILOT_API_KEY' }

$headers = @{
  "X-API-KEY" = $mpApiKey
  "Content-Type" = "application/json"
  "Accept" = "application/json, text/event-stream"
}

$body = @{
  jsonrpc = "2.0"
  id = 1
  method = "tools/list"
  params = @{}
} | ConvertTo-Json -Depth 5 -Compress

Invoke-RestMethod `
  -Uri $mpMcpEndpoint `
  -Headers $headers `
  -Method POST `
  -Body $body
```

调用工具使用 `tools/call`：

```powershell
$body = @{
  jsonrpc = "2.0"
  id = 2
  method = "tools/call"
  params = @{
    name = "query_subscribes"
    arguments = @{}
  }
} | ConvertTo-Json -Depth 10 -Compress
```
