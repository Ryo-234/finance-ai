# SSH - "远程控制服务器"

> ⏱ 阅读时间：1 分钟

## 是什么

远程登录 Linux 服务器的命令行工具。**所有服务器管理都靠它**。

## 类比

TeamViewer / 远程桌面（但只控制命令行，没有图形界面）。

## 怎么用

```bash
ssh 用户名@服务器IP
# 例：ssh root@123.45.67.89
# 输入密码（每次输） 或 用密钥（推荐）
```

## 关键点

- **默认端口 22**（可以改，但不建议）
- **生产环境必须用密钥**（不要用密码，密码会被暴力破解）
- **root 用户慎用**（创建普通用户 + sudo）

## 密钥 vs 密码

| | 密码 | SSH 密钥 |
|---|---|---|
| 安全 | 弱（8 位密码秒破）| 强（2048 位数学难题）|
| 方便 | 输入简单 | 第一次配麻烦 |
| 推荐 | ❌ 不用 | ✅ 强烈推荐 |

## 怎么生成 SSH 密钥

```bash
# 1. 在你电脑生成
ssh-keygen -t rsa -b 4096

# 2. 公钥 (~/.ssh/id_rsa.pub) 复制到服务器
ssh-copy-id root@123.45.67.89

# 3. 之后登录免密
ssh root@123.45.67.89
```

## 跟你的项目关系

- 部署时需要 SSH 到服务器拉代码、装依赖
- 用 GitHub Actions 自动部署时也用 SSH
- 平时开发可以**完全不用 SSH**（PaaS 平台有 Web 控制台）

## 高级用法

```bash
# 端口转发（调试用）
ssh -L 8000:localhost:8000 user@server
# 把服务器的 8000 转到你电脑的 8000

# 文件复制
scp file.txt user@server:/path/

# 配置文件 ~/.ssh/config 简化登录
Host myserver
    HostName 123.45.67.89
    User root
    Port 22
    IdentityFile ~/.ssh/id_rsa

# 之后只要：ssh myserver
```

## 缺了会怎样

- **没法管理服务器**（除非有云平台 Web 终端）
- **没法部署代码**（除非全自动 CI/CD）

## 怎么用免费

- 你电脑：自带（macOS/Linux 都有；Windows 用 Git Bash 或 PowerShell）
- 服务器：默认开启
- 客户端推荐：Windows 用 **Windows Terminal** 或 **MobaXterm**

## 常见坑

- **权限太大**：`chmod 700 ~/.ssh; chmod 600 ~/.ssh/id_rsa`（必须）
- **忘记私钥密码**：找不回来（重新生成）
- **公钥没复制对**：连不上
- **服务器改 SSH 端口**：要 `ssh -p 新端口`
