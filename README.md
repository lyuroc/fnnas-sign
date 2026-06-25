# 飞牛论坛打卡 (fnnas-sign)

> 飞牛OS (FNOS) 原生应用，每天自动打卡飞牛论坛 (club.fnnas.com)，签到结果通过微信 / QQ / 邮件推送。

![版本](https://img.shields.io/badge/版本-1.0.0-blue)
![平台](https://img.shields.io/badge/平台-飞牛OS-brightgreen)
![依赖](https://img.shields.io/badge/依赖-零外部依赖-success)
![许可证](https://img.shields.io/badge/许可证-MIT-yellow)

---

## ✨ 功能

| 功能 | 说明 |
|------|------|
| 🤖 每日自动打卡 | 在设定的时间范围内随机选择时间点自动签到 |
| 🎲 随机打卡时间 | 每天不同，模拟真人操作 |
| 🔄 已打卡自动续期 | 今天已打卡则自动生成明天的随机时间 |
| 📢 多通道推送 | 微信、QQ、邮件三渠道通知签到结果 |
| 🍃 动森风格 UI | 浏览器直接管理配置、手动打卡、查看日志 |
| 🔐 零外部依赖 | 纯 Python 标准库实现，无需安装任何第三方包 |

---

## 🚀 安装

### 方式一：通过 FPK 安装（推荐）

1. 下载 [fnnas-sign.fpk](https://github.com/lyuroc/fnnas-sign/releases/download/v1.0.0/fnnas-sign.fpk)（v1.0.0）
2. 打开飞牛OS → 应用中心 → 手动安装 → 选择 FPK 文件
3. 安装完成后访问 http://你的NASIP:7654 打开管理界面

### 方式二：源码运行（开发调试）

```bash
git clone https://github.com/lyuroc/fnnas-sign.git
cd fnnas-sign

# 零外部依赖！Python 标准库开箱即用
python3 app/server/app.py
```

访问 http://127.0.0.1:7654 打开管理界面。

---

## ⚙️ 配置说明

### 1. 论坛 Cookie

浏览器登录 club.fnnas.com → F12 → Application → Cookies → 找到：

| 参数 | 说明 | 获取位置 |
|------|------|----------|
| pvRK_2132_auth | 登录认证凭据 | Cookie 中的 pvRK_2132_auth 字段值 |
| pvRK_2132_saltkey | 安全密钥 | Cookie 中的 pvRK_2132_saltkey 字段值 |

### 2. 签到参数

程序自动从签到页面提取 sign 和 formhash，无需手动配置。

> 如果自动签到一直失败，请检查 Cookie 是否过期，重新登录获取。

### 3. Webhook 密钥（微信/QQ推送）

```bash
# SSH 到 Hermes 容器，查看 webhook 订阅密钥
cat /home/hermeswebui/.hermes/webhook_subscriptions.json | python3 -c "import json,sys;d=json.load(sys.stdin);print('微信:',d['fnnas-sign-wechat']['secret']);print('QQ:',d['fnnas-sign-qq']['secret'])"
```

### 4. 推送地址

| 通道 | 默认地址 |
|------|----------|
| 微信 | http://127.0.0.1:8644/webhooks/fnnas-sign-wechat |
| QQ | http://127.0.0.1:8644/webhooks/fnnas-sign-qq |

### 5. 邮箱推送（SMTP）

推荐使用 QQ 邮箱授权码（非登录密码）：

1. 登录 QQ 邮箱 → 设置 → 账户 → 开启 POP3/SMTP 服务
2. 生成授权码
3. 管理界面填入：SMTP 服务器 smtp.qq.com，端口 465（SSL）

---

## 🕐 打卡时段

默认打卡时段为 00:00 - 06:00（凌晨时段）。可在管理界面调整，系统在该时段内随机选择时间点执行。

---

## 🏗️ 技术架构

前端采用 [animal-island-ui](https://github.com/lyuroc/animal-island-ui)（动物森友会风格 UI 组件库），基于 Vue 3 + Vite 构建。


```
fnnas-sign/
├── app/
│   ├── server/              # Python 后端（纯标准库）
│   │   ├── app.py                  # HTTP 服务（http.server）
│   │   ├── signer.py               # 论坛签到（零外部依赖）
│   │   ├── soup_mini.py            # 自研 HTML 解析器
│   │   └── stdlib_http.py          # 自研 HTTP 会话工具
│   ├── www/                 # Web 前端（Vue 3）
│   └── ui/                  # 桌面图标
├── cmd/                     # FNOS 生命周期脚本
├── manifest                 # 应用清单
└── fnnas-sign.fpk           # 打包文件
```


---

## 📝 更新日志

### v1.0.0 (2026-06-25)

- 初始版本发布
- 每日自动打卡 + 随机时间签到
- 微信/QQ/邮件三通道推送
- 零外部依赖重构

---

## 🙏 致谢

- [animal-island-ui](https://github.com/lyuroc/animal-island-ui) — 动物森友会风格 UI 组件库
- [飞牛OS (FNOS)](https://www.fnnas.com/) — 应用运行平台
- [Hermes Gateway](https://hermes-agent.nousresearch.com) — 消息推送通道

---

## 📄 许可证

MIT License © 2026 [中秋满月](https://github.com/lyuroc)

