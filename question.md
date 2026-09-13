# 问题清单与评估记录

> 2026-09-12 接续说明：以下原评估保留供追溯。用户随后授权仅作小范围 bug 修复，当前处理结果见第 7 节；原文中的“未改源码”“待确认”“仍在运行”等仅代表原评估当时状态，旧 PID 不作为当前停止进程的依据。

评估日期：2026-09-12。**本次评估未改动任何源码**，仅执行只读检查、测试与必要的真实调用。
问题按严重性排列；每条包含现象、证据、影响与建议。证据中的 ID 均来自本次实库运行。

## 0. 本次验证开销与遗留物

| 项目 | 内容 |
|---|---|
| 真实 DeepSeek 调用 | **2 次**（1 次独立分析验证 + 1 次完整闭环）。后续未再调用 |
| 创建的验证数据 | 会议 `1063`（AI-validation-0912）、作业 `669`、分析 `420`、任务 `781`（整理接口清单 / 张三） |
| 启动的进程 | 后端 PID `5608`（8000）、前端 PID `21476`（5173），**仍在运行** |
| 临时目录 | `work/pytest-tmp`（pytest 临时目录，已忽略） |
| 数据库写入 | 语义检索首次查询会按需生成并保存分片向量（设计如此） |

不需要这些时可以删除；删除方法与待确认事项见文末第 5 节。

## 1. 实测通过的部分

| 检查项 | 结果 |
|---|---|
| 完整后端回归 | **168 项全部通过**（真实 MySQL，事务回滚） |
| 模型与迁移一致性 | `alembic current` = 0009 (head)；`alembic check` = 无差异 |
| 前端类型检查 | `vue-tsc` 通过 |
| 浏览器只读冒烟 | PASS（登录错误、Boss/员工数据、导航、刷新、服务故障、退出/后退、会话撤销、移动端布局） |
| 本地 BGE 向量 | 512 维输出正常，标识 `bge-small-zh-v1.5:mean200:v1` |
| 本地 Whisper 转写 | 17 秒音频 2.3 秒出字 |
| 语义检索（真实数据） | 0.6 秒返回 4 个来源，`search_mode=semantic` |
| 真实模型输出可校验性 | 结构 100% 通过校验，**来源摘录 4/4 逐字命中原文** |
| 真实模型完整闭环 | 作业执行 `LOAD→ANALYZE→VALIDATE→PERSIST→PUBLISH→COMPLETE`，任务自动发布 |
| 日期解析 | "明天" → 2026-09-13 23:59（上海时区），符合设计 |
| 接口鉴权覆盖 | 32 条路径，除 `/api/health`、`/api/auth/login`、`/api/auth/logout` 外全部强制会话 |
| 仓库卫生 | `dist/`、`__pycache__/`、`storage/`、`work/`、`.env` 均未入库 |

## 2. 高严重性

### P1 缺负责人的事项被判为"讨论"，既不派发也不进待补充

- **现象**：真实模型把"需要有人整理测试用例，暂未确定负责人"判定为 `kind=DISCUSSION`，后端据此置为 `DISCUSSION` —— 不生成任务，**也不计入"待补充事项"**，Boss 首页待补充数为 0。
- **证据**：会议 1063 / 分析 420 的候选为 `0 PUBLISHED`（整理接口清单）、`1 DISCUSSION`（整理测试用例）、`2 DISCUSSION`（下次增加自动化测试）。而演示适配器 `app/ai/demo.py` 对同一句给出的是 `COMMITTED + owner=None`，会正确落入 `NEEDS_INFO` 待补充。
- **影响**：`doc.md` 3.2 承诺的"负责人缺失 → 留存候选、原因和来源，Boss 补充后转任务"在真实模型下**可能不生效**。这类事项只在纪要的"风险与讨论"里出现一句，Boss 很容易漏掉。本次模型确实把它写进了 `risks`，但没有可操作入口。
- **建议**（任选）：① 提示词中明确"有明确事项但未指定负责人"必须输出 `COMMITTED` 且 `owner=null`；② 或把 `DISCUSSION` 候选也纳入"待补充"列表供人工确认；③ 或接受现状并在文档中写明边界。
- **需要你决策**：这是提示词/产品取向问题，改哪一条由你定。

### P2 同一段文本两次调用结果不一致

- **现象**：同一段 `DEMO_TEXT`，两次真实调用给出了不同的候选数量与判定。
  - 第一次（独立调用）：4 个候选，含"核对字段 / 王五 / COMMITTED"、"整理测试用例"、"增加自动化测试"。
  - 第二次（完整流程）：3 个候选，**没有"核对字段"**，且后两个都判为 `DISCUSSION`。
- **影响**：结果不可复现。演示时提交同一段文本，得到的任务数量可能不同；"协助性工作被拆成独立任务"（王五核对字段）与否也不稳定。
- **原因**：`temperature=0` 已设置，剩余波动来自服务端（MoE/批处理），后端无法完全消除。
- **建议**：提示词里把"抽取粒度"和"COMMITTED/DISCUSSION 边界"写死，能显著降低但不能归零波动；演示前先跑一次确认结果。

### P3 决策列表为空，页面会显示"没有记录明确决策"

- **现象**：`analysis 420` 的 `decisions` 是空数组，而 `summary` 里明确写了"张三将于明天整理接口清单"。
- **证据**：`DECISIONS: []`，`RISKS: ['测试用例整理暂无负责人，可能影响后续测试工作推进']`。
- **影响**：会议详情页"主要决策"区块显示空状态，是演示时很显眼的一处"看起来没生效"。
- **建议**：提示词要求 `decisions` 至少包含已确认的行动安排；或页面在 `decisions` 为空时回退展示已发布任务。

## 3. 中严重性

### P4 结构修复的超时边界（已修正此前判断）

- **现象**：`app/ai/analysis.py` 用 `asyncio.timeout(60)` 包住"最多 2 次模型调用"，单次 HTTP 超时为 55 秒（`app/ai/deepseek.py`）。
- **修正**：我先前判断"几乎必然超时"过重。实际只有**首次调用耗时超过约 40 秒**时，修复调用才会被 60 秒总时限切断，抛 `ANALYSIS_TIMEOUT`；而 DeepSeek 模式 `max_attempts=1` 不重试，作业直接失败。
- **状态**：本次真实调用一次通过（`repaired=False`），**未实测触发**，属静态推断。
- **建议**：把总超时改为按单次调用计时，或放宽到约 120 秒，让"结构错误修复 1 次"的设计真正落地。

### P5 转写错字会压低自动派发成功率

- **实测输出**：`今天的会议决定,张三明天整理接口清单,李四协助核对自段。此时用力还没有确定负责人。`（"字段"→"自段"、"此事项"→"此时用力"）
- **原因**：`app/ai/resolution.py` 中负责人用 `person.name == reference.name` 全等匹配，来源摘录用 `text.find(source_quote)` 逐字匹配。
- **影响**：这是**正确的保守设计**（不强猜），但叠加 ASR 错字后，真实录音场景下负责人解析失败、候选被 `REJECTED` 的比例会明显上升。
- **建议**：主线演示优先用**文本输入**；录音作为补充演示，并现场使用"使用此文本纠错"功能。

### P6 语义检索的冷启动规模风险

- **现象**：`app/services/semantic_search.py` 一次最多取 1000 个分片，对未缓存分片逐个生成向量（每片再按 200 字窗口、160 步长切分）后才计算相似度。
- **实测**：当前数据量下 **0.6 秒返回 4 个来源**，完全正常。
- **影响**：仅当演示数据增长到数百场会议时，首次语义查询才会明显变慢。前端助手已给 120 秒超时，可缓解。
- **建议**：当前规模无需处理；若要扩充数据，可考虑限制单次生成向量的分片数。

## 4. 低严重性

### P7 音频工作器数据库异常重试无退避

`app/ai/audio_worker.py` 遇到 `SQLAlchemyError` 后固定等待 2 秒重连；而分析工作器是 1/2/4…30 秒指数退避。数据库短暂不可用时会造成更密集的重连压力。课设规模影响很小。

### P8 登录无失败次数限制

`app/services/auth.py` 的 `login` 没有失败计数或速率限制。本地演示环境可接受，若对外开放则需补。

### P9 本机受限 shell 下 pytest 无法使用系统临时目录

- **现象**：直接运行 `pytest` 时，14 个用例报 `PermissionError: [WinError 5]`（无法写当前用户的系统临时目录 `%LOCALAPPDATA%\Temp`，个人目录名已省略）。
- **性质**：**环境问题，不是代码缺陷**。改用 `--basetemp` 指向项目内目录后 168 项全部通过。
- **建议**：把 `--basetemp=work\pytest-tmp` 写进 README 的测试命令，避免以后重复踩坑。
- 实际可用命令：

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=..\work\pytest-tmp
```

### P10 前端下载链接硬编码 `/api` 前缀

`frontend/src/components/MeetingRecording.vue` 中下载链接写为 `/api/meetings/.../download`。与当前 Vite 代理匹配，课设无影响；仅将来部署到子路径时需要调整。

## 5. 需要你确认或提供的事项

1. **P1 / P3 是否要修**：这两个是提示词层面的问题，改提示词属于改代码，等你明确批准我再动手。你倾向"改提示词强调未指定负责人也算待办"，还是"把讨论项也纳入待补充列表"？
2. **验证数据去留**：会议 `1063`、任务 `781` 是我建的，要保留作为新的演示样例，还是由我删除？
3. **我启动的进程**：后端 PID `5608`、前端 PID `21476` 仍在运行。要我停掉，还是你接着用？停止命令：

```powershell
Stop-Process -Id 5608,21476
```

4. **DeepSeek 余额**：本次已用 2 次请求。请告诉我余额或次数上是否还有限制，后续我按你的上限控制调用。
5. **是否继续验证助手真实问答**：`T22` 的真实问答链路在 2026-09-11 已验证过，本次为省费用未重复。需要我再验证一次吗（约 1—2 次调用）？
6. **是否还有其他你想让我重点测的场景**（例如经理层的部门邀请链路、录音上传转写全链路）。

---

## 6. 测试流程记录（供后续 AI 复现）

本次全部操作在 PowerShell 中执行，工作目录为项目根 `D:\APyCharmProject\MeetingFlow`，Python 使用根目录 `.venv\Scripts\python.exe`。除注明"真实调用"外，均不产生费用。

### 6.1 前置条件

- MySQL80 必须处于 Running。**AI 无法自行启动**：非管理员权限执行 `Start-Service MySQL80` 会被拒绝，需用户在 Windows「服务」中手动启动。
- 确认端口与数据库：`Get-Service MySQL80`、`netstat -ano | Select-String ":8000|:5173|:3306"`。

### 6.2 不需要数据库的检查

```powershell
# 前端类型检查（0 错误）
cd frontend; npm.cmd run typecheck

# 纯规则与密码安全测试（24 项，不连库）
cd backend; ..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_resolution.py tests/test_security.py

# 依赖一致性
..\.venv\Scripts\python.exe -m pip check

# 接口清单（32 条路径）
..\.venv\Scripts\python.exe -c "from app.main import create_app; a=create_app(start_worker=False); s=a.openapi(); print('paths', len(s['paths'])); [print(p, sorted(m.upper() for m in v)) for p,v in s['paths'].items()]"

# 本地向量模型（应输出 rows/dims=512 与标识）
..\.venv\Scripts\python.exe -c "from app.ai.local_models import embed_texts, EMBEDDING_ID; v=embed_texts(['hello meeting action item','zhang san owns the api docs']); print('rows', len(v), 'dims', len(v[0])); print('id', EMBEDDING_ID)"

# 本地转写（实测 2.3 秒，输出含错字属已知现象）
..\.venv\Scripts\python.exe -c "import time; from app.ai.local_models import transcribe; s=time.time(); t=transcribe(r'D:\APyCharmProject\MeetingFlow\work\asr-spoken-validation.wav'); print('seconds', round(time.time()-s,1)); print('chars', len(t)); print(t.encode('unicode_escape').decode())"
```

迁移链完整性：在 `backend/migrations/versions` 中 grep `^(revision|down_revision)`，应得到 0001→0009 单链、无分叉。

### 6.3 需要数据库的检查

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic current        # 期望 0009 (head)
..\.venv\Scripts\python.exe -m alembic check          # 期望 No new upgrade operations detected

# 完整回归：168 项通过。必须加 --basetemp，否则 14 个用例因系统临时目录不可写而 error
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=D:\APyCharmProject\MeetingFlow\work\pytest-tmp
```

不要与浏览器业务脚本同时跑（都用真实库，会互相等锁）。

### 6.4 端到端流程

```powershell
# 启动后端（8000），日志重定向到 work/
Start-Process -FilePath "D:\APyCharmProject\MeetingFlow\.venv\Scripts\python.exe" -ArgumentList "run.py" `
  -WorkingDirectory "D:\APyCharmProject\MeetingFlow\backend" `
  -RedirectStandardOutput "...\work\backend-0912.log" -RedirectStandardError "...\work\backend-0912.err.log" -WindowStyle Hidden

# 启动前端（5173）
Start-Process -FilePath "npm.cmd" -ArgumentList "run","dev" -WorkingDirectory "D:\APyCharmProject\MeetingFlow\frontend" `
  -RedirectStandardOutput "...\work\frontend-0912.log" -RedirectStandardError "...\work\frontend-0912.err.log" -WindowStyle Hidden

curl.exe -s http://127.0.0.1:8000/api/health          # 期望 {"status":"ok",...}
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:5173/api/health   # 期望 200

# 只读浏览器冒烟（需要前后端与本机 Chrome，读取 .env.demo 密码）
cd frontend; npm.cmd run test:smoke
```

语义检索实测（本地推理，不收费；首次查询会写入向量缓存）：

```powershell
..\.venv\Scripts\python.exe -c "import time;from app.database import get_engine;from sqlalchemy import select;from sqlalchemy.orm import Session;from app.models import User;from app.services.semantic_search import search_semantic;db=Session(get_engine());u=db.scalar(select(User).where(User.username=='boss'));s=time.time();r=search_semantic(db,u,'\u63a5\u53e3\u6e05\u5355');print('elapsed',round(time.time()-s,1));print('mode',r.search_mode);print('sources',len(r.sources))"
```

真实模型闭环（**会产生费用，仅在用户授权时执行**）：用 `create_meeting` + `submit_text_input` 建会议并提交原文，后端工作器会自动认领作业；等待约 45 秒后查 `ProcessingJob.status`、`ActionItem.status` 与 `Task`。本次结果：作业 SUCCEEDED，1 个任务自动发布。

### 6.5 踩坑记录

| 坑 | 表现 | 处理 |
|---|---|---|
| 系统临时目录不可写 | `PermissionError`，14 个用例 error，个人目录名已省略 | 加 `--basetemp` 指向 `work\` |
| PowerShell 传中文给 `python -c` | 字符串被破坏，报 `SyntaxError: invalid character` | 用 `\uXXXX` 转义，或从模块导入常量（如 `DEMO_TEXT`） |
| PowerShell 引号嵌套 | 单引号包裹时内部双引号会被吃掉 | 外层用双引号、Python 内部用单引号 |
| `app.routes` 不展平 | 直接遍历只能得到 2 条路由 | 用 `app.openapi()['paths']` |
| 服务启动类型 Automatic 但仍 Stopped | `Start-Service` 报"无法打开服务" | 需用户在「服务」中手动启动 |

### 6.6 本次结论一句话

核心链路（迁移、回归、鉴权、分析、发布、转写、检索、页面）全部可用且相互一致；真实模型的主要风险不在工程实现，而在**模型输出语义不稳定**（候选数量与 `kind` 判定波动、决策列表为空、缺负责人事项被归入讨论），详见第 2 节。

## 7. 用户授权后的复核与处置（2026-09-12）

只按课设展示需要做小修，不扩大到性能、安全平台或额外体验功能。

| 项目 | 最终处置 |
|---|---|
| P1 缺负责人归讨论 | 提示词明确“已确定要做、负责人未定”输出 COMMITTED + owner=null；保留真正讨论的原规则。实际讨论项会显示在会议详情，并非完全隐藏，只是没有生成按钮。不强制把所有讨论转成任务。 |
| P2 数量波动 | 提示词明确同一行动的协助安排不要重复拆任务。第二次保存的结果仍含王五协作，不能仅因少一项独立任务判定漏掉安排；两次调用也不足以证明具体服务端原因。 |
| P3 空决策 | 保持现状，不强制生成决策，也不用任务伪装成决策。 |
| P4 超时 | 初次与最多一次修复各自限时 60 秒。旧“约 40 秒”不是固定边界，原问题取决于两次调用总时长。 |
| 补充发现：非法 JSON 绕过修复 | 已修复。客户端把受限原始内容交给分析校验，非法 JSON/非对象/缺顶层字段现在能进入一次修复；仍失败就结束。助手仍不增加修复调用。 |
| P5—P10 | 不改业务代码。ASR 错字、检索规模、重连间隔、登录限速、部署路径均按原型边界说明。测试目录权限仅写入 README 的可选排错步骤。 |

复核确认会议 1063 的原文等于 DEMO_TEXT，作业成功、任务 781 已生成，两项候选为 DISCUSSION，3 项来源与原文对应。P5 的来源匹配对照的是保存的转写文本，不是语音原稿；人员匹配失败通常进入 NEEDS_INFO，而非 REJECTED。原“4/4、100%”仅代表独立样本，不是广泛准确率。

流程修正：前端与后端命令应各自在自己的目录执行，从 frontend 返回 backend 使用 `cd ..\backend`；日志路径中的省略号是占位符；`--basetemp` 仅针对受限环境，普通机器不必强加。列出 OpenAPI 路径不等于已对所有权限完成逐条测试。保留验证数据，不按照旧 PID 直接清理进程。

本轮验证命令（backend 目录）：

```powershell
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_analysis.py tests/test_resolution.py tests/test_live_models.py::test_provider_errors_have_no_retry_or_secret
```

结果：36 项通过，剩已有 AnyIO 弃用提示；没有调用真实模型、没有修改业务数据、没有再次跑全量测试。原全量 168 项成绩保留为此前证据，不冒充本轮全量回归。答辩流程与常见现象说明已加入 docs/demo-guide.md。
