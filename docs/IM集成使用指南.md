# 企业微信 / 飞书 / QQ / 微信 集成使用指南

## 概述

本系统现在支持 AI 员工通过以下即时通讯平台发送通知和消息：

- **企业微信**：通过 webhook 机器人
- **飞书**：通过 webhook 机器人
- **QQ**：通过 go-cqhttp 或类似机器人框架
- **微信**：通过第三方机器人框架（如 WeChat Hook）

## 快速开始

### 1. 配置集成账号

1. 进入 AI 员工的管理界面
2. 找到「外部集成」或「工具配置」页面
3. 选择对应的平台，添加集成：

#### 企业微信配置示例

```json
{
  "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
}
```

#### 飞书配置示例

```json
{
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_HOOK_KEY"
}
```

#### QQ 配置示例

```json
{
  "api_endpoint": "http://localhost:8080",
  "access_token": "YOUR_TOKEN_IF_NEEDED"
}
```

#### 微信配置示例

```json
{
  "api_endpoint": "http://localhost:3000"
}
```

### 2. 配置完成后即可使用

配置好后，AI 员工就能自动使用该平台发送消息了！

## 使用示例

### 示例 1：企业微信通知

你说：“向企业微信群发送今天下午 3 点开会的通知”

AI 会自动调用 `wechat_work_send` 工具，发送会议通知。

### 示例 2：飞书通知

你说：“在飞书群里发一下本周周报的提交提醒，@所有人”

AI 会调用 `feishu_send` 工具，发送带 @所有人 的提醒。

### 示例 3：QQ/微信消息

你说：“给 QQ 群 123456 发送一条系统维护通知”

AI 会调用 `qq_send` 工具发送消息。

## 工具说明

| 工具名 | 平台 | 说明 |
|--------|------|------|
| `wechat_work_send` | 企业微信 | 发送消息到企业微信群 |
| `feishu_send` | 飞书 | 发送消息到飞书群 |
| `qq_send` | QQ | 发送消息到 QQ 群或好友 |
| `wechat_send` | 微信 | 发送消息到微信群或好友 |

## 详细配置指南

### 企业微信配置

1. 在企业微信中创建一个群聊
2. 群设置 → 添加群机器人 → 新建
3. 复制机器人的 webhook 地址
4. 把 webhook 地址填入集成配置中的 `webhook_url` 字段

### 飞书配置

1. 在飞书中创建一个群聊
2. 群设置 → 群机器人 → 添加机器人
3. 复制 webhook 地址
4. 填入集成配置中的 `webhook_url` 字段

### QQ 配置（使用 go-cqhttp）

1. 下载并配置 [go-cqhttp](https://github.com/Mrs4s/go-cqhttp)
2. 启动 go-cqhttp 并保持运行
3. 把 `api_endpoint` 设置为 go-cqhttp 的 HTTP 监听地址（默认 http://localhost:8080）
4. 如果配置了 access_token，也一起填入

### 微信配置

微信机器人需要使用第三方框架，具体配置请参考所选框架的文档。

## 常见问题

### Q：配置好了还是发送失败？

A：请检查：
1. webhook/API 地址是否正确
2. 机器人是否已被正确添加到群里
3. 网络连接是否正常

### Q：如何 @ 所有人？

A：企业微信和飞书支持在 `mentioned_list` 中使用 `["@all"]`，AI 会自动处理。

### Q：是否支持发送图片、文件？

A：当前版本主要支持文本消息，后续会扩展支持富媒体消息。
