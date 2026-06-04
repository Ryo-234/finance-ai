# Render 部署 Step-by-Step - 1 小时把你的项目跑上线

> ⏱ 预计耗时：1-2 小时
> 成本：**¥0**（用免费版）
> 难度：⭐⭐（需要你会点鼠标 + 复制粘贴）

---

## 第 0 步：前提条件

确认你有这些：
- [x] **GitHub 账号**（用来登录 Render）
- [x] **代码已推 GitHub**（我们之前 commit 过 `5b1f6f8`）
- [x] **Render 账号**（下面教你注册）
- [ ] **阿里云 DashScope key**（你的 LLM 用的）
- [ ] **Tavily key**（金融搜索用的）
- [ ] **MiniMax key + model 名称**（我们已配在 .env）

> 没这些 key 部署后 LLM 功能跑不了，但能看 UI 和支付流程。

---

## 第 1 步：注册 Render（3 分钟）

1. 打开 https://render.com
2. 点 **"Get Started for Free"**
3. 选 **"Sign up with GitHub"**
4. 授权 Render 访问你的 GitHub 仓库

**完事**。

---

## 第 2 步：创建项目基础设施（5 分钟）

1. Render 控制台右上角点 **"New +"** → **"Blueprint"**
2. 选 **"Connect a repository"** → 选你的 `deer-flow-main` 仓库（或者 `research-agent-standalone` 分支，看你推的哪个）
3. Render 自动检测到 `render.yaml` 并显示预览
4. 看到 "research-agent-api" 和 "research-agent-db" 两个服务
5. 点 **"Apply"**

**Render 会自动**：
- 创建 PostgreSQL 数据库
- 拉代码并构建 Python 环境
- 启动后端服务
- 给后端一个 URL：`https://research-agent-api.onrender.com`

**等 3-5 分钟**。期间可以继续下面步骤。

---

## 第 3 步：填环境变量（10 分钟）

后端服务跑起来后，需要加 4 个敏感变量（**密钥文件**）。

### 3.1 进后端服务环境变量页

1. Render 控制台点 **"research-agent-api"** 服务
2. 左侧菜单点 **"Environment"**
3. 点 **"Add Environment Variable"**

### 3.2 加变量（4 个）

| Key | Value | 怎么填 |
|---|---|---|
| `ALIPAY_APP_PRIVATE_KEY` | 你的应用私钥 PEM 完整内容 | 见下方"读 PEM 内容" |
| `ALIPAY_PUBLIC_KEY` | 支付宝公钥 PEM 完整内容 | 同上 |
| `ALIPAY_NOTIFY_URL` | `https://research-agent-api.onrender.com/api/billing/callback/alipay` | **改 `onrender.com` 之前的名字为你后端实际 URL** |
| `ALIPAY_RETURN_URL` | `https://你的前端域名/billing/orders` | **先填后端的也行** |

#### 怎么读 PEM 内容

打开 PowerShell：

```powershell
# 读应用私钥
Get-Content "C:\Users\admin\Downloads\deer-flow-main\research_agent\data\alipay_app_private_key.pem" | Out-String

# 读支付宝公钥
Get-Content "C:\Users\admin\Downloads\deer-flow-main\research_agent\data\alipay_public_key.pem" | Out-String
```

把输出（含 `-----BEGIN ... -----` 头尾）**完整复制**到 Value 框。

> ⚠️ 多行字符串：Render 支持**多行 env var**。**直接把整段 PEM（含换行）粘进去**就行。

### 3.3 加 LLM API Keys

继续点 **"Add Environment Variable"**：

| Key | Value |
|---|---|
| `DASHSCOPE_API_KEY` | `sk-你的key` |
| `TAVILY_API_KEY` | `tvly-你的key` |
| `MINIMAX_API_KEY` | `sk-cp-你的key` |
| `ADMIN_EMAILS` | `你的邮箱@example.com`（用来访问管理员后台）|

点 **"Save Changes"**。Render 会**自动重启**服务。

---

## 第 4 步：验证后端（5 分钟）

1. 后端服务的页面有 **"Logs"** 标签 → 点进去
2. 应该看到：
   ```
   INFO:     Uvicorn running on http://0.0.0.0:10000
   INFO:     Application startup complete.
   INFO:     数据库已连接（PostgreSQL）
   INFO:     数据库表已就绪
   ```
3. 浏览器访问：`https://research-agent-api.onrender.com/api/health`
4. 应该看到：`{"status":"healthy","service":"research-agent-gateway","version":"1.0.0"}`

**成功后端 OK ✅**。

---

## 第 5 步：部署前端到 Vercel（10 分钟）

### 5.1 注册 Vercel

1. 打开 https://vercel.com
2. 点 **"Sign Up"** → **"Continue with GitHub"**

### 5.2 导入项目

1. Vercel 控制台点 **"Add New..."** → **"Project"**
2. 选同一个 GitHub 仓库
3. 填配置：
   - **Project Name**：`research-agent-web`
   - **Root Directory**：点 **"Edit"** → 输入 `frontend` → 保存
   - **Framework Preset**：Next.js（自动检测）
4. 展开 **"Environment Variables"**：
   ```
   NEXT_PUBLIC_API_BASE_URL=https://research-agent-api.onrender.com
   ```
   （**把 onrender.com 之前的名字改成你的实际后端 URL**）
5. 点 **"Deploy"**

### 5.3 等待 + 验证

- 等 2-3 分钟构建
- 看到 **"🎉 Congratulations!"** ✅
- 复制 Vercel 给你的 URL：`https://research-agent-web.vercel.app`

---

## 第 6 步：联调测试（5 分钟）

1. 浏览器打开 `https://research-agent-web.vercel.app`
2. 注册账号 → 登录
3. 访问 `/billing` → 看方案卡片
4. 点"专业版" → 跳支付页
5. 应该看到：
   - 二维码
   - 倒计时
   - "⚙️ 模拟支付（开发模式）" 按钮
6. 点 mock 支付 → 看到"支付成功"
7. 访问 `/billing/subscription` → 看到"专业版生效中"

**完事** 🎉

---

## 第 7 步：绑定你的域名（可选，30 分钟）

如果你有 `finance-ai.com` 域名：

### Vercel（前端）
1. Project Settings → Domains
2. 输 `finance-ai.com` → Add
3. Vercel 给你一条 CNAME 记录
4. 去你的域名注册商（阿里云/腾讯云/Cloudflare）配 DNS
5. 等 5 分钟生效

### Render（后端）
1. Service Settings → Custom Domain
2. 输 `api.finance-ai.com` → Add
3. 同样配 DNS
4. 重新生成 SSL 证书

---

## 第 8 步：生产安全收尾（重要！）

1. **关掉 mock-pay**：
   - Render 后端环境变量加 `ALIPAY_DEBUG=false`（但要先把密钥换成正式商户号的）
2. **限制 CORS**：Render 后端代码加 `ALLOWED_ORIGINS=https://finance-ai.com`
3. **开监控**：[UptimeRobot](https://uptimerobot.com)（免费）→ 监控 `/api/health`，挂掉发邮件
4. **数据库备份**：Render 控制台 → Database → Backups（每天自动）

---

## 故障排查（你可能遇到的）

### ❌ 后端启动失败："No module named 'xxx'"

**原因**：requirements.txt 没装全
**解决**：看 Logs 找具体哪个包，requirements.txt 加上

### ❌ 后端启动失败："could not translate host name"

**原因**：DATABASE_URL 没生效
**解决**：检查 Render Environment 里有没有 `DATABASE_URL`，且 `fromDatabase` 配置对了

### ❌ 浏览器报"Failed to fetch"

**原因**：后端 CORS 没开 / HTTPS mixed content
**解决**：
- 确认后端 URL 是 HTTPS
- 确认 `NEXT_PUBLIC_API_BASE_URL` 是 https:// 开头

### ❌ 支付二维码显示"支付暂不可用"

**原因**：ALIPAY_APP_PRIVATE_KEY 或 ALIPAY_PUBLIC_KEY 没填对
**解决**：看后端 Logs 找具体错误。常见：
- "RSA key format is not supported" → PEM 格式损坏，重新复制
- "Invalid PEM" → 含 BOM 头或换行符

### ❌ PostgreSQL "permission denied" / "schema does not exist"

**原因**：连接字符串里数据库名不存在
**解决**：Render 自动配的应该没问题。如果是手动配的，检查用户名/密码

### ❌ Render 服务 15 分钟后挂掉

**原因**：免费版**冷启动**（15 分钟无活动会休眠）
**解决**：
- 下次访问自动唤醒（**首次 30 秒**）
- 用户感知"卡了一下"
- 或升级到 ¥7/月一直在线

---

## 你现在要做的（按顺序）

1. [ ] 注册 Render 账号（GitHub 登录）
2. [ ] 在 Render 创建 Blueprint → 选你的仓库
3. [ ] 填 4 个 ALIPAY 变量（2 个 PEM + 2 个 URL）
4. [ ] 填 4 个 LLM/Admin 变量
5. [ ] 等后端启动完，访问 `/api/health` 验证
6. [ ] 注册 Vercel → 部署前端
7. [ ] 浏览器访问前端，注册测试
8. [ ] 联调通过，截图发给我看 🎉

**有卡住的地方随时问我，我盯着**。
