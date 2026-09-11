# MeetingFlow：AI 协作上下文

更新：2026-09-11。面向后续 Codex / AI 开发协作。开发设计、任务状态和验收标准见 `doc.md`，不要在这里维护第二份任务清单。

## 每次接续

1. 阅读本文件及 `doc.md` 的当前进度、决策和目标任务。
2. 检查实际目录、相关代码和已有修改；计划不代表功能已实现。
3. 根据用户当次授权选择任务，按依赖推进。用户只要求讨论或文档时，不开始应用开发。
4. 实现后执行对应验收，更新 `doc.md` 的状态、证据和下一步；重要设计变化同步到设计正文。

## 用户目标与协作方式

- 学校课设，目标是方向清楚、核心流程可演示的原型；完整生产落地以后再说。
- 用户希望积累学习和简历经验，能解释关键设计及真实效果。不虚构性能、准确率或已实现能力。
- 用户熟悉 Java / Spring Boot，微服务经验较少；项目后端明确要求 Python。必要时可用熟悉的后端概念解释设计。
- 按用户独立完成项目考虑，不安排六人分工，不主动调用子代理。
- 2026-09-07 用户表示距答辩约十天，但不要求赶工；核心主线优先，不承诺完成日期。
- 沟通简洁、问答式，每轮聚焦少量关键决策。压缩长描述，不重复已确认问题。
- 保持独立判断，解释可行性和取舍，不迎合、不堆技术名词。
- 2026-09-08 用户进一步授权先完成第一版，之后集中测试修改；沿用已确认设计自主推进，只有影响核心流程或外部接口的关键信息再问。不能把未回复当确认。
- 每完成一部分就更新 `doc.md`；阶段性更新本文件，重要约束改变时立即同步。现有工具足够时不添加额外 skill/MCP；确有收益或访问缺口时说明具体用途。
- 用户补充：技术栈需实际用到，但产品没有那么多硬性要求，先简单实现；目录按业务与职责组织，方便查找，不为原设计中的扩展对象提前搭完整框架。
- 用户要求账户 5 小时额度接近上限时自动找存档点。2026-09-08 补充不必始终在意或频繁汇报额度；适当阶段内部复查，默认约 85% 停止新增工作并保存文档。额度为账户共享，不能保证硬性封顶；不自动使用重置或购买额度。

## 已确认的约束

- 主线：会议输入 → 自动分析 → 自动生成任务 → 员工执行及反馈 → Boss 查看进度。
- 文本及上传录音；现场实时录音由用户另找工具，不纳入首版。
- Python 后端、本地 MySQL；DeepSeek 官方密钥已提供，ASR/Embedding 使用已批准的轻量本地 CPU 模型，使用 PyCharm 运行后端。
- 已确认 FastAPI + Vue 3 / TypeScript + Element Plus；必须实际使用 LangGraph。2026-09-08 用户授权基础用法难度不高就会议与助手两处都用，已决定 T10/T22 使用基础 StateGraph。节点、固定边与条件边即可，阶段结果继续保存在 MySQL，不引入额外检查点服务或 LangSmith。
- 2026-09-09 用户明确要求现在实现经理层，覆盖此前延后决定；用户确认经理即单部门部长；Boss 可按部门邀请或直接点名，部长安排自己部门参会人。具体规则已写入 doc.md 第 4 节。复杂组织树仍非当前目标。
- 默认自动处理，只有缺失、歧义、失败才介入；不设置每条任务都需要审核的步骤。
- 人员按姓名、部门、参会人匹配；允许人工纠错，不做复杂语音近音名算法。数据库内部仍使用 ID，用户不需要输入编号。
- 所有入口共用后端权限。模型解释指令，不能授权、越权读写或执行任意 SQL。
- 员工看自己参加的会议、自己负责或协作的任务；未参会的受派员工只能看到任务及相关摘录，不能看会议全文。
- 助手首版按已讨论方案提供受权限约束的查询问答；语音修改权限未获采用。

## 文档关系与实现纪律

- 用户最新明确决定优先；`doc.md` 是当前开发设计，原总纲和立项书保留为背景愿景。
- `doc.md` 中“实施默认”是为便于实施选择的方案，不冒充用户指定；调整时写明理由。
- 不按原总纲自动扩大范围，不一次性生成整个系统，部门负责人使用集中范围，不扩展通用权限平台。
- 原顺序先文本、再音频和助手；2026-09-08 用户无模型接口并授权先完成演示版，因此先做文本样例、授权查询及助手演示分支，音频和真实模型留待接口可用。恢复用持久化阶段结果起步，不默认微服务、Redis、消息队列或复杂检查点框架。
- 外部 API 尚未提供时可以用明确标识的测试适配器验证链路；不能称为真实 AI 验收通过。
- 各模块开发时核实依赖官方文档和兼容版本并锁定版本，不无故升级。项目使用根目录 `.venv`，PyCharm 也应选择该环境，避免和原 Miniconda 解释器混用。
- API 密钥、数据库密码只放本地环境配置，不进入文档、源码、日志或提交。
- 不把前端隐藏按钮当权限，不把模型声称“已完成”当实际执行结果。
- 每项任务只改必要内容，完成相关检查后再推进；保留用户已有修改。

## 当前会话结果

2026-09-11：课设首版 A/B 主线已完成，T01—T28 按本文课设范围验收。真实 DeepSeek 分析及只读问答、本地 CPU Whisper base 转写、BGE-small-zh-v1.5 语义检索均已接通。迁移 0009，16 张业务表及版本表；后端 168 项通过，前端类型/构建、真实浏览器闭环、独立空库迁移初始化及任务完成验证通过。

本次共 3 次付费请求（输入 1188、输出 182 token），后续不为重复验证继续调用。会议 891 和任务 668 保留实际结果；语音为本机合成短样例，出现“字段”“测试用例”识别错误，可在页面纠正转写。完整证据及边界见 docs/model-validation.md，不宣称真实会议准确率或生产性能。

本机 .env 已启用 deepseek/local/local，密钥只存该本地忽略文件，不再询问用户提供。两个模型已下载到 backend/storage/models，运行时使用 CPU，本机 RTX 4060 Laptop 8GB 未启用 GPU 推理。测试 fixture 强制 demo/unconfigured/keyword，避免收费；旧演示浏览器脚本已加模式保护。

入口 http://127.0.0.1:5173/；MySQL80 已启动。账号密码仅在 backend/.env.demo。前后端日志 work/backend-0911.*.log、work/frontend-0911.*.log，操作进程前核验 PID。README 已说明 PyCharm 运行 backend/run.py、前端单独启动、迁移、模型开关和排错。旧会议 271、456、457、787 保留；787 的静音附件仅用于上传测试。

下一步是用户试用、短真实录音验证和反馈修正，按需要少量使用收费接口；没有待提供的 ASR/Embedding 密钥或必须新增的 skill/MCP。2026-09-11 用户已授权建立 GitHub 仓库并推送首版，覆盖此前延后 Git 的约定；仓库为 https://github.com/yhyym7/MeetingFlow，私有、main 分支。注册按 Boss 创建账号的既定方案，没有开放注册、密码找回或自助改密码；复杂组织、实时录音、部署等不扩入当前课设。

## 工程入口与已知环境事项

- 后端：根目录 `.venv\Scripts\python.exe backend\run.py`；健康接口 `/api/health` 仅表示进程存活，不能表示数据库/AI 可用。配置从 `backend/.env` 读取，与启动目录无关。
- 前端：在 `frontend` 中运行 `npm.cmd run dev`；构建与类型检查用 `npm.cmd run build`。默认前端 5173、后端 8000，前端通过 `/api` 代理请求。
- 安装依赖使用后端 `requirements.txt` 和前端 `npm.cmd ci`。`frontend/.npmrc` 将缓存放在 `work/npm-cache`。若受限运行出现项目内 `node_modules` 写入 EPERM，本轮通过工具审批后正常运行，不需要让用户重装 Node。
- 启动与验证步骤见 README。GitHub 私有仓库 yhyym7/MeetingFlow，origin 使用 HTTPS，凭据由 Windows Git Credential Manager 管理，不输出令牌。源码上传不包括数据库、密钥、录音和模型；后续操作先检查 git status。
- 环境已通过外部分析和本地轻量转写/向量验证。继续使用已验证 `.venv`；老师偏好 Conda 时可按根目录 `environment.yml` 重建并切换解释器，两者不叠加。Conda 配置语法已校验，未实际安装项目 Conda 环境。详细区别与目录索引见 `docs/project-guide.md`。
- 数据库配置位于本地 `backend/.env`，演示随机密码位于本地 `backend/.env.demo`；不读取并打印这些文件全文，不把密钥复制进文档。演示账号：boss、zhangsan、lisi、wangwu、zhaoliu。
- 数据模型位于 `app/models/`，HTTP 位于 `app/api/`，请求响应模型位于 `app/schemas/`，业务操作位于 `app/services/`，权限统一在 `app/permissions.py`。后续会议/任务接口必须复用 SQL 范围和授权详情取数，不能仅靠前端隐藏按钮。
- 数据库变更用 Alembic；测试在 `backend` 中运行 `..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`，真实 MySQL 测试用外层事务回滚，不清库。LangGraph 1.2.11 已安装并锁定，带入 httpx2 后当前剩 1 项 AnyIO 弃用提示，不需主动做无关升级。
- `app/ai/`：contracts/adapters/analysis/prompts 为输出与模型适配，resolution 为确定性规则，workflow 为真实 StateGraph 和单并发工作器。结果存 MySQL；不使用外部 LangSmith 追踪或额外检查点服务。测试 app 显式 `start_worker=False`，避免改动真实演示库的后台作业。

- 前端：api 为请求与类型，stores/session 为会话状态，router.ts 为路由，views 为页面，components 为复用列表，utils 为日期格式。现有导航守卫用于体验；真正权限始终由后端验证。
- 页面验证：frontend 中 npm.cmd run test:smoke，需前后端/MySQL已启动和有效的 backend/.env.demo 密码；只读取业务，不创建演示业务记录。依赖 playwright-core 1.63.0，复用本机 Chrome。
- 业务复验 npm.cmd run test:business 会建立/复用会议 271 并添加动态；npm.cmd run test:admin-assistant 会建立/复用并停用 demo_validation。不要与后端事务测试并行运行，避免演示用户行锁互相等待。代码入口索引已补在 docs/project-guide.md。

- 经理与部门参会：services/meeting_attendance.py、permissions.py、前端 DepartmentAttendance.vue；初始化 scripts/seed_managers.py，复验 npm.cmd run test:manager，会保留命名明确的演示会议。

- 2026-09-10 新入口：services/knowledge.py 与 models/knowledge.py 为持久化分片；scripts/index_meetings.py 为幂等历史回填。services/audio.py、api/audio.py 为私有录音上传和下载；前端 MeetingRecording.vue、MeetingSource.vue。真实转写已接入；待转写附件仍不当作已分析输入。

- 2026-09-11 入口：ai/deepseek.py、local_models.py、audio_worker.py、assistant_live.py；services/transcription.py、semantic_search.py。模型下载 scripts/download_models.py，独立空库验证 scripts/verify_clean_database.py；后者仅操作自身生成的临时库且需要建库权限，通常无需重复运行。真实验证脚本 frontend/scripts/live-model-smoke.mjs 可能计费，不自动重复。
