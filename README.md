# MeetingFlow

会议分析与任务协同课设原型：会议文本或录音 → 自动分析 → 发布有效任务 → 员工协作与反馈 → 管理者查看进度。

2026-09-11：首版主线已完成，接入 DeepSeek 分析和只读问答、本地 Whisper 转写、本地中文向量检索。支持 Boss、部门负责人和员工，两个业务流程实际使用 LangGraph，数据保存于 MySQL。真实样例结果和限制见 [模型验收记录](docs/model-validation.md)，操作流程见 [试用指南](docs/demo-guide.md)。

## 本机直接运行

本机依赖、数据库迁移、演示账号和两个本地模型均已准备好，无需重复安装。

1. 在 Windows「服务」中确认 **MySQL80 正在运行**。
2. PyCharm 项目解释器选择 `D:\APyCharmProject\MeetingFlow\.venv\Scripts\python.exe`；运行脚本选 `D:\APyCharmProject\MeetingFlow\backend\run.py`，工作目录选 `D:\APyCharmProject\MeetingFlow\backend`。不要使用原来的 Miniconda Python 3.14 解释器。
3. 在项目终端执行以下命令启动前端，然后打开 [系统页面](http://127.0.0.1:5173/)。

```powershell
cd D:\APyCharmProject\MeetingFlow\frontend
npm.cmd run dev
```

**run.py 只启动后端，前端需要单独启动。** 如果页面已经能打开，不要重复启动占用相同端口的服务。停止时使用对应终端 Ctrl+C 或 PyCharm 停止按钮。只运行一个后端，分析和转写工作器随应用启动。

后端也可在项目根目录用终端启动：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

后端地址为 `http://127.0.0.1:8000`，接口文档为 [/docs](http://127.0.0.1:8000/docs)。前端通过 `/api` 代理后端。配置修改后需要重启后端。

## 登录与试用

演示密码在本机 `backend/.env.demo` 的 `DEMO_PASSWORD`，与 MySQL 密码不同，不写入源码或说明文档。

| 账号 | 身份 |
|---|---|
| boss | 王总，全部管理权限 |
| tech_manager / product_manager | 技术部 / 产品部负责人 |
| zhangsan / lisi / wangwu / zhaoliu | 张三 / 李四 / 王五 / 赵六，员工 |

账号由 Boss 在“人员管理”创建，没有开放注册、找回密码或员工自助改密码。会话默认 8 小时；停用、调岗或改变角色会撤销相关会话。部门负责人管理本部门任务；会议全文仍按参会权限开放。

建议先查看会议 **891“真实模型验收：接口与测试安排（合成语音）”**，其中任务 668 已由张三完成。要从零体验，请新建会议，选择参会人并提交短文本或清晰普通话录音。有效事项自动发布，缺负责人等事项由管理者补充。重新提交输入会保留旧任务，避免重复自动派发；可人工纠错和选择补建。

## 模型和费用开关

本机 `backend/.env` 已配置实际密钥及以下模式；密钥只保存在本地忽略文件。新安装用的 `.env.example` 默认是无收费的演示模式。

```dotenv
MEETINGFLOW_ANALYSIS_MODE=deepseek
MEETINGFLOW_DEEPSEEK_MODEL=deepseek-flash
MEETINGFLOW_ASR_MODE=local
MEETINGFLOW_EMBEDDING_MODE=local
```

- DeepSeek 官方接口负责会议分析和自由问答，密钥变量为 `MEETINGFLOW_DEEPSEEK_API_KEY`。新文本分析通常 1 次请求，结构错误最多额外修复 1 次；普通自由查询通常 1 次，会议内容问答最多 2 次。HTTP 不自动重试，人工重试可能再次计费。
- 固定查询按钮、`查找会议：接口清单`、`语义检索：接口资料由谁整理` 不调用收费模型。本地转写和向量计算也不收费，但下载模型需网络。
- Whisper base 多语言版以 CPU/int8 运行；BGE-small-zh-v1.5 生成本地 512 维向量。模型已存于 `backend/storage/models/`，运行时从本地加载。
- 关闭收费调用：将分析模式改为 `demo` 并重启后端，此时只接受页面固定分析样例。旧演示浏览器测试还要求 `MEETINGFLOW_ASR_MODE=unconfigured`，可将 Embedding 改为 `keyword` 使用纯关键词模式。

默认录音支持 mp3/wav/m4a，最多 50 MB、10 分钟；建议课设先用 1—3 分钟清晰普通话。分析文本最多 12000 字。录音仅经鉴权下载，不公开静态地址。转写完成后自动接入分析，失败可以重试；已保存转写会复用。转写期间出现新输入时不会覆盖新内容。

小模型可能识别错术语和姓名；可展开转写并“使用此文本纠错”。不含实时录音、说话人区分或多录音合并。检索只使用授权会议的最新版本，最多扫描最近 1000 个分片，返回至多 5 个来源；向量不可用会明确回退关键词模式。

## 新电脑首次安装 / 旧版本升级

已验证环境：Windows、Python 3.12.10、Node 24.8.0、npm 11.6.0、MySQL 8.0.45。本机约 16 GB 内存，未配置 GPU 推理。建议重建独立环境，不复制 `.venv`。

在项目根目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
# 仅在没有 .env 时复制，已有配置不要覆盖
Copy-Item backend\.env.example backend\.env
cd frontend
npm.cmd ci
cd ..\backend
..\.venv\Scripts\python.exe -m scripts.configure_database
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m scripts.seed_demo --random-password
..\.venv\Scripts\python.exe -m scripts.seed_managers
..\.venv\Scripts\python.exe -m scripts.download_models
```

建库工具隐藏输入数据库密码；发现目标库已有表会停止，不清空数据。下载工具只下载公开模型，不使用 DeepSeek 密钥。随后按需要填写真实密钥、开启模型模式并启动。Conda 替代配置和目录说明见 [项目指南](docs/project-guide.md)。

已有旧数据库只需停止后端，在 `backend` 执行迁移与分片回填，不重新建库：

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m scripts.index_meetings
```

当前迁移为 **0009**，16 张业务表及 Alembic 版本表。分片向量在首次语义查询时按需生成并保存；首次查询可能稍慢。

## 验证与常见问题

2026-09-11：后端 **168 项通过**（剩已有 AnyIO 弃用提示），前端类型检查和构建通过，依赖检查和迁移差异检查通过。独立临时空库已完成全部迁移、初始化、登录、演示分析及员工完成任务，随后移除临时库，未清空项目库。

```powershell
# backend 目录；测试强制模拟模式，不调用收费模型
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
..\.venv\Scripts\python.exe -m pip check
..\.venv\Scripts\python.exe -m alembic check
# frontend 目录
npm.cmd run build
npm.cmd run test:smoke
```

后端测试需 MySQL，使用事务回滚；不要与浏览器业务检查同时执行。`test:smoke` 只读，需要前后端和本机 Chrome。`test:business`、`test:admin-assistant`、`test:manager`、`test:knowledge-audio` 用于演示模式，会保留专用演示数据，已加真实模式阻止保护。真实验证脚本 `frontend/scripts/live-model-smoke.mjs` 是显式付费验证入口，依赖本机 `work/asr-spoken-validation.wav`，通常不必重复执行。

本轮真实验证共 3 次 DeepSeek 请求，输入 1188、输出 182 token。一个本地合成语音样例走通上传→转写→分析→任务→员工完成，以及语义检索和模型问答；它不是实际多人会议，不能由此声称识别率或生产性能。

| 现象 | 处理 |
|---|---|
| 登录提示数据库连接失败 | 先检查 MySQL80 服务及本地数据库配置 |
| 端口已占用 | 使用已经运行的服务，或停止原服务后再启动 |
| 缺少 Python 包 | 检查 PyCharm 是否选择根目录 `.venv` |
| 提示本地模型缺失 | 在 backend 运行 `python -m scripts.download_models`，使用项目解释器 |
| 模型认证、余额或限流错误 | 检查本地密钥及官方账户，或切回 demo 模式 |
| 旧录音显示待转写 | 开启本地 ASR 后在页面点击开始转写；静音校验附件不能用作识别演示 |
| 转写有错字或超长 | 使用文本纠错，或拆分为较短录音/文本 |

健康接口 `/api/health` 只表示后端进程存活，不代表数据库和模型可用。`frontend/dist` 为构建产物；当前按本机开发服务运行，没有配置线上部署。

## 代码与文档

- `backend/run.py`：启动入口；`backend/app/api/`、`services/`、`models/` 分别为接口、业务和数据。
- `backend/app/ai/`：模型适配、两个 LangGraph、分析与转写工作器；`backend/app/permissions.py`：集中权限。
- `frontend/src/`：页面与组件；`backend/migrations/`：数据库迁移；`backend/tests/`：测试。
- [doc.md](doc.md)：设计、任务完成情况和验证历史；[codex.md](codex.md)：后续协作上下文。
- [试用指南](docs/demo-guide.md)、[项目指南](docs/project-guide.md)、[模型验收记录](docs/model-validation.md)。

GitHub 私有仓库：[yhyym7/MeetingFlow](https://github.com/yhyym7/MeetingFlow)，主分支为 `main`，首版提交包含源码、测试、迁移和开发文档。`.env`、演示密码、数据库内容、录音、本地模型及 work 临时产物不随代码上传；在新电脑克隆后按首次安装步骤配置。仓库不替代本地业务数据备份。
