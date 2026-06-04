# PaaS 免费部署路径 - "零基础 1 小时上线"

> ⏱ 阅读时间：5 分钟
> 目标：用最少的成本把项目跑上线
> 适合：想"先看看上线是啥样"的同学

---

## TL;DR

| | 自建 VPS | **PaaS 平台（推荐）** |
|---|---|---|
| 成本 | ¥100+/月 + 域名 ¥30-60/年 | **¥0（用免费版）** |
| 学习 | 3-7 天（学 Linux + Nginx + HTTPS）| **1-2 小时**（绑 GitHub + 点几下）|
| 维护 | 自己（监控、备份、扩容）| **平台自动** |
| 风险 | 容易配错 | 平台帮你兜底 |
| 控制力 | 高 | 中（受限于平台）|

**新手友好度**：PaaS 完胜。

---

## 推荐平台组合

| 组件 | 平台 | 理由 |
|---|---|---|
| **前端** | Vercel | Next.js 亲妈，免费，自动 HTTPS |
| **后端** | Render | Python 友好，免费，自动 HTTPS |
| **数据库** | Render PostgreSQL | 一键启动，90 天免费 |

**总成本：¥0**（用免费版）

---

## 部署前准备（你要有）

| 准备 | 是否必须 | 备注 |
|---|---|---|
| **GitHub 账号** | ✅ 必须 | 用来存代码 |
| **代码已推到 GitHub** | ✅ 必须 | 推过 commit 就行 |
| **Render 账号** | ✅ 必须 | 用 GitHub 登录 |
| **Vercel 账号** | ✅ 必须 | 用 GitHub 登录 |
| **域名** | ❌ 可选 | 免费子域名 `xxx.onrender.com` 先用着 |
| **信用卡** | ❌ 不用 | 免费版不用绑卡 |

---

## 部署步骤（约 1-2 小时）

### 第 1 步：注册 Render（5 分钟）

1. 打开 https://render.com
2. 点 **"Get Started for Free"**
3. 选 **"Sign up with GitHub"**
4. 授权 Render 访问你的 GitHub 仓库

### 第 2 步：部署后端（10 分钟）

1. Render 控制台点 **"New +"** → **"Web Service"**
2. 选你的 GitHub 仓库（比如 `research-agent-standalone`）
3. 填配置：
   - **Name**：`research-agent-api`
   - **Root Directory**：`research_agent`（重要！）
   - **Runtime**：Python 3
   - **Build Command**：`pip install -r requirements.txt`
   - **Start Command**：`python run_api.py --host 0.0.0.0 --port $PORT`
4. 选 **"Free"** 实例
5. 点 **"Advanced"** 加环境变量：
   ```
   DASHSCOPE_API_KEY=你的key
   MODEL_PROVIDER=minimax
   ALIPAY_APPID=9021000164641571
   ALIPAY_DEBUG=true
   ALIPAY_PRIVATE_KEY_PATH=/opt/render/project/src/data/alipay_app_private_key.pem
   ALIPAY_PUBLIC_KEY_PATH=/opt/render/project/src/data/alipay_public_key.pem
   ALIPAY_NOTIFY_URL=https://你的域名/api/billing/callback/alipay
   ALIPAY_RETURN_URL=https://你的域名/billing/orders
   ```
6. 点 **"Create Web Service"**
7. 等 3-5 分钟构建完成
8. 看到 **"Your service is live"** ✅
9. 复制 URL（`https://research-agent-api.onrender.com`）

**密钥文件怎么办？**

Render 不让你直接上传文件，但环境变量可以存文件内容：

```python
# 在代码里把环境变量写回文件
import os
with open("/tmp/key.pem", "w") as f:
    f.write(os.environ["ALIPAY_PRIVATE_KEY_PEM_CONTENT"])
```

### 第 3 步：部署前端（10 分钟）

1. 打开 https://vercel.com
2. 用 GitHub 登录
3. 点 **"Add New..."** → **"Project"**
4. 选同一个 GitHub 仓库
5. 填配置：
   - **Project Name**：`research-agent-web`
   - **Root Directory**：`frontend`（点 Edit 改）
   - **Framework Preset**：Next.js（自动检测）
6. 展开 **"Environment Variables"**：
   ```
   NEXT_PUBLIC_API_BASE_URL=https://research-agent-api.onrender.com
   ```
7. 点 **"Deploy"**
8. 等 2-3 分钟
9. 看到 **"🎉 Congratulations!"** ✅
10. 复制 URL（`https://research-agent-web.vercel.app`）

### 第 4 步：联调（10 分钟）

1. 浏览器打开 `https://research-agent-web.vercel.app`
2. 注册账号 → 登录
3. 访问 `/billing` 看方案卡片
4. 点"专业版" → 跳支付页
5. 看到二维码 + 倒计时 = **完美！**
6. 点"⚙️ 模拟支付（开发模式）"按钮
7. 看到"支付成功"提示 = **联调通过！**

### 第 5 步：绑定你的域名（可选，30 分钟）

如果你有 `finance-ai.com` 域名：

1. **Vercel** → Project Settings → Domains → 加 `finance-ai.com`
2. Vercel 给你两条 DNS 记录（CNAME）
3. 去你的域名注册商（阿里云/腾讯云/Cloudflare）改 DNS
4. 等 10 分钟生效
5. Vercel 自动签发 HTTPS 证书 ✅

---

## 部署后运维（持续）

| 任务 | 频率 | 工具 |
|---|---|---|
| **看监控** | 每天 | Render 控制台 |
| **看错误日志** | 出问题时 | Render Logs |
| **数据库备份** | 每天自动 | Render 自动 |
| **更新代码** | 每次 push | 自动部署（零操作）|
| **续费** | 用免费版不用 | - |

---

## 故障排查（常见 3 个坑）

### 1. 前端 fetch 不到后端

**症状**：浏览器 console 报 "Failed to fetch"
**原因**：跨域（CORS） / HTTPS mixed content
**解决**：
- 检查后端 `ALLOWED_ORIGINS` 配置
- 前端 `NEXT_PUBLIC_API_BASE_URL` 必须用 HTTPS

### 2. 后端启动失败

**症状**：Render 控制台显示 "Build failed" / "Deploy failed"
**解决**：
- 看 Logs 找具体错误
- 通常是依赖装不上（Python 版本不对 / 包名拼错）
- 在 Render 设置里改 Python 版本到 3.10+

### 3. 数据库连不上

**症状**：API 返回 "数据库连接超时"
**解决**：
- Render 的 PostgreSQL 免费版会自动休眠（15 分钟无连接就睡）
- 下次访问会自动唤醒（**但首次唤醒要 30 秒**）
- 解决：用户首次访问等几秒；或升级到 ¥7/月一直在线

---

## 免费额度 vs 付费

| 平台 | 免费额度 | 限制 |
|---|---|---|
| **Render Web** | 750 小时/月 | 15 分钟无活动会睡（冷启动 30 秒）|
| **Render PostgreSQL** | 90 天 | 到期数据丢失（要导出或付费）|
| **Vercel** | 100 GB 流量/月 | 超出 $0.15/GB |
| **Cloudflare** | 无限 | - |

**早期 MVP 够用**。到用户 1000+ 再说付费。

---

## 等你需要"正式上线"时

免费版撑不住时（用户 100+、收入稳定）：

1. **买 VPS**：阿里云/腾讯云 2 核 4G，¥100/月
2. **买域名**：`.com` 60 元/年
3. **申请备案**：7-20 天（国内服务器必备）
4. **申请商户号**：用营业执照办（你的项目已经写好代码了）
5. **写 Dockerfile**：把后端打包成镜像
6. **写 docker-compose.yml**：一键起后端 + 前端 + 数据库
7. **配 Nginx + HTTPS + 进程守护 + 监控 + 备份**（按 [learn 笔记](../README.md) 一项项来）

---

## 上线 Checklist（30 项）

### 部署前
- [ ] 代码已推 GitHub
- [ ] requirements.txt 完整
- [ ] .env.example 存在（不含真实密钥）
- [ ] .gitignore 排除 .env / .pem / __pycache__
- [ ] 关键代码有日志
- [ ] 错误处理完善（不裸奔崩）

### 部署时
- [ ] 平台账号注册完
- [ ] 环境变量填好（不填密钥路径）
- [ ] 密钥用环境变量 / Volume 方式挂载
- [ ] 数据库连接字符串改了（不用 SQLite）
- [ ] Build / Start 命令对
- [ ] 端口用 `$PORT`（平台会注入）

### 部署后
- [ ] 域名能访问
- [ ] HTTPS 生效（绿色锁）
- [ ] 注册 / 登录 / 主要功能跑通
- [ ] 错误日志能看到
- [ ] 监控告警接好（UptimeRobot）
- [ ] 数据库备份策略定好
- [ ] 监控指标：响应时间、错误率、内存

---

## 写在最后

**PaaS 平台让你"跳过" 80% 的部署知识**：
- 不用学 Linux 命令
- 不用配 Nginx
- 不用管 HTTPS 证书
- 不用做进程守护
- 不用装数据库

**省下的 20% 知识**（数据库设计、API 设计、缓存、安全）才是**真正考验你能力**的。

所以：
- 部署**先会用**（PaaS，1 小时）
- 再**理解原理**（[learn 笔记](../README.md)，慢慢学）
- 最后**真上生产**（VPS + Docker，1-2 周）

**别让部署挡住你做产品**。
