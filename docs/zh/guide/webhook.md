# Webhook 接入

Webhook 用于接收 MoviePilot 事件。Emby 事件由 ETK MediaInfo Bridge 插件直接上报，无需安装或配置 Emby Webhook 插件。

## 配置地址

```
http://ETK-IP:5257/webhook/emby
请求内容类型：application/json
```

MoviePilot Webhook 使用这个地址，ETK 根据 payload 里的 `type` 字段识别 MP 事件。该地址不再接收 Emby Webhook；Emby 中已有的 Webhook 配置可以直接删除。

## 推荐事件

### Emby（桥接插件自动上报）

- 播放：开始、停止
- 用户：添加到收藏、移出收藏、标记已播放、标记未播放、用户政策已更新
- 用户主动删除：删除前收集电影多版本、整季或整剧的完整 115 PickCode，删除成功后联动清理
- 手动编辑：元数据保存、图片上传/删除/排序/手动远程选图

### MoviePilot

- MP安装webhook插件，请求方式：POST，URL：http://ETK-IP:5257/webhook/emby

## 行为说明

- 桥接插件不依赖 `item.add`、`library.new` Webhook；新媒体 Item ID 由插件直接取得并提交给 ETK。
- 用户事件：实时同步用户权限、播放记录。
- 元数据/图像更新：只处理用户手动修改；媒体库刷新、Provider 导入和 ETK 自身回填不会触发，避免刷新回旋。
- MoviePilot 订阅事件：订阅助手实时接管新增、修改、删除、完成事件，维护下载状态和完成快照。
- MoviePilot 下载事件：记录下载 hash、站点、集数等信息，供订阅助手下载巡检使用。
- MoviePilot 整理完成事件：进入 ETK 入库整理、追剧刷新、共享登记等后续流程。

## 速率控制

元数据更新等高频事件内置去抖逻辑，可减少对 Emby 的压力。
