# Docker - "集装箱"

> ⏱ 阅读时间：1 分钟

## 是什么

把代码 + 运行环境**打包**成一个"镜像"，到任何机器上都能**一模一样地**跑。

## 类比

你搬家时把东西**装进集装箱**（Docker 镜像），到新家**拆箱就能用**。
- 不用担心新家没装某些软件
- 不用担心新家环境不同
- 集装箱**标准化**，卡车/火车/轮船都能运

## 解决了什么问题

**经典抱怨**：
> "我电脑能跑，你电脑跑不了啊！"
> "测试环境能跑，生产环境跑不了啊！"
> "新员工配环境配了 2 天还没好！"

**Docker 答案**：镜像里**啥都打包好了**，到哪都一样。

## 3 个核心概念

| 概念 | 类比 | 说明 |
|---|---|---|
| **镜像（Image）** | 集装箱的"模板" | 只读，比如 "Ubuntu + Python 3.10 + 你的代码" |
| **容器（Container）** | 跑起来的集装箱 | 镜像的运行实例 |
| **Dockerfile** | 集装箱"配方" | 几行命令告诉 Docker 怎么构建镜像 |

## 一个 Dockerfile 例子

```dockerfile
FROM python:3.10-slim       # 基础镜像（Ubuntu + Python）
WORKDIR /app
COPY . .                    # 复制你的代码
RUN pip install -r requirements.txt   # 装依赖
CMD ["uvicorn", "app:app", "--host", "0.0.0.0"]
```

## 常用命令

```bash
docker build -t my-app .        # 构建镜像
docker run -d -p 8000:8000 my-app  # 跑容器
docker ps                      # 看运行中的容器
docker stop <ID>               # 停
docker logs <ID>               # 看日志
```

## 关键点

- **环境一致性**：开发 = 测试 = 生产
- **快速启动**：几秒启动一个服务
- **资源隔离**：每个容器用自己的资源（CPU/内存）
- **CI/CD 标配**：推代码 → 自动构建镜像 → 自动部署

## 跟你的项目关系

- 你**现在不需要**（代码量小，直接跑就行）
- **生产部署时强烈建议**（用 Docker Compose 一键起后端+前端+数据库）
- **面试加分项**（懂 Docker = 入门级 DevOps）

## 缺了会怎样

- **不会缺**（你项目直接 `python run_api.py` 也能跑）
- 但**做大之后**：100 个微服务，靠 Docker 部署会方便 10 倍

## 怎么学

- **Docker Desktop**（本地装）：[docker.com](https://www.docker.com/products/docker-desktop)
- **Play with Docker**：在线免费玩
- **官方教程**：[docker.com/get-started](https://www.docker.com/get-started)

## 常见坑

- **镜像太大**（几 GB）：用 `alpine` 或 `slim` 基础镜像
- **数据丢失**：容器删了数据没了，**用 volume 持久化**
- **权限问题**：容器内 `root` 默认，**生产改非 root**
