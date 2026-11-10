# RQGM Harness 递归自进化实验程序说明

本程序在 `/workspace/redqueen` 中运行。它是低资源研究实验框架：从一个最小 Pi Harness 出发，让 Meta 修改自身与 Executor；让 Claude Code 驱动的 Challenger 修改 Skills、生成方法与判定程序；由不可变的外层控制器实施搜索、独立验证和安全隔离。

**真实入口是 `python3 -m rqgm_lab.experiment`。** `controller.py` 是保留的第一阶段 mock 闭环，不能用它运行真实实验。`live.py` 是单独的模型接口测试入口，不是进化实验。

软件闭环与“目标能力已经涌现”是两个不同结论。框架能够运行、记录并检验候选；是否发展出有效并发协作和统一的个体性，需要观察真实实验。不能根据一次通过、模型自述或合成测试得出结论。

## 1. 启动方法

### 1.1 环境检查

当前机器已经具备 Python 3.12、Git、Node、Claude Code 2.1.81，以及固定版本 Pi SDK 1.5.1。Python 侧只使用标准库，额外调用系统 `libseccomp.so.2`。无需数据库、微服务、Docker 或每轮安装依赖。

```bash
cd /workspace/redqueen
python3 -m rqgm_lab.experiment doctor
```

本机正式运行由 root 控制器启动，子进程自动降权至 UID/GID 65534，清空附加组及 capabilities。需保留宿主机的 CHOWN/SETUID/SETGID 权限；受限容器若无法降权，`doctor` 会拒绝正式运行。不要给 UID 65534 访问私有目录的权限。

`doctor` 不调用模型。它检查内存/磁盘、运行时、12 题回归数据、密钥权限，以及实际越界读取、隐藏文件 stat 拒绝、独立 UID、网络和 fork 拒绝。低于 768 MiB 可用内存或 500 MiB 空闲磁盘时拒绝启动。CLI 的真实 `run` 也会自动执行此检查。

密钥必须保存在项目根目录的 `apikey.bin`，内容为单行明文 key，权限 `600`。文件已加入 `.gitignore`。不要把它放进 Agent 的工作区、Skills、命令行或版本库。

### 1.2 建议的首次真实实验

```bash
python3 -m rqgm_lab.experiment run \
  --root runs/my-first-live \
  --budget 2 \
  --first-checkpoint 2 \
  --model glm-5.3-flash \
  --max-api-calls 60 \
  --max-reserved-tokens 600000 \
  --min-regression 10 \
  --parallel 2
```

这不是两个模型请求：`--budget 2` 指 **2 次选择评价**。初始隐藏回归、训练场景、自修改、候选隐藏回归、Challenger 修改与场景生成另外消耗模型调用，但全部受 `--max-api-calls` 和 `--max-reserved-tokens` 约束。首个边界在第 2 次评价后执行。初始化/修改失败时实际请求数不同，不承诺固定数量。

小实验验收后可扩大到累计 4 或 8 次评价，例如：

```bash
python3 -m rqgm_lab.experiment run \
  --root runs/my-first-live \
  --budget 4 \
  --first-checkpoint 2 \
  --model glm-5.3-flash \
  --max-api-calls 100 \
  --max-reserved-tokens 1000000 \
  --min-regression 10 \
  --parallel 2
```

恢复时必须保持模型、初始 checkpoint、回归下限、并发上下文上限等实验配置一致；可以提高累计评价/API/token 预算。预算数字是整个 run 的累计限制，不是每次重启重新获得一份。源码和依赖锁文件变化时拒绝无提示恢复，使用新目录或归档的原始源码。

模型调用始终串行。`--parallel 2` 开放两个独立任务上下文，允许 Python/工具执行重叠，以及独立多步任务的交错推进；两个模型请求排队执行。这保留研究并发协作的空间，同时避免在 2C4G 机器上同时启动多个重型模型 CLI。若设为 1，可作为关闭执行并发的对照，建议使用新的 run 目录。

### 1.3 状态、报告与重放

```bash
python3 -m rqgm_lab.experiment report --root runs/my-first-live
python3 -m rqgm_lab.experiment replay --root runs/my-first-live --record 0
git --git-dir=runs/my-first-live/objects.git log --all --graph --oneline
```

打开 `runs/my-first-live/report.html` 查看双树、父节点、修改策略、原始/有效评价、预算与 Epoch 替换。文件是无外链的静态 HTML，不启动 Web 服务。

Seed 进化树以连线显示父子关系，包含有 Git commit 的拒绝候选；绿色是最新一次已完成运行的最终选择节点，灰色是其他节点。若之后有新的状态变更而尚无新的最终结果，不推断冠军。每个节点标注最近一次自动 MBPP+ 回归的通过数/总数，以及当前有效 Challenger 选择任务的通过数/总数；失效或无效任务另计，未测评不算失败。点击节点可跳转到逐题详情，人工复测和训练任务单独展示。

报告的“Per-node MBPP+ and Challenger results / 逐节点测评”列出每个 Seed（包括已归档但被拒绝的候选）的 MBPP+ 自动回归与人工复测：分别展示通过数、逐题结果、测试输入数量和执行错误；中断后的部分结果标为未完成，无记录标为未测评。Challenger 节点不执行 MBPP+，标为不适用。每个 Seed 的 Challenger 选择任务显示任务、能力方向、Epoch、Challenger commit、测试版本、通过情况及证据当前有效/已失效/无效排除状态；可归属节点的公开训练任务单列，不混入选择统计。历史训练事件若没有记录目标节点且无法可靠推断，不猜测归属。

这些内容从原始日志和 `manual-evaluations/` 读取，生成报告不重新调用模型、不改写评价。人工复测后重新执行 `report` 即可更新展示。报告含隐藏回归结果，只供操作者阅读，不得传给 Meta 或 Challenger。

`replay` 不调用模型：使用归档的同一 oracle，重新判定该次记录的原始 observation，核对结果是否一致。它不是对随机模型输出逐字复现的承诺。场景、程序、参数、观察轨迹和版本都保留，可用于新的独立重复实验。无有效 oracle 的记录不能被当作可复现成功。

### 1.4 中断与故障恢复

Ctrl-C 或 SIGTERM 后重新运行同一命令即可。退出码 130 表示用户中断，2 表示预算不足。网络/运行时异常保留失败事件并停止；修复后恢复同一个目录，不自动无限重试。

对于返回空文本的模型响应，运行时记录工具、模型、HTTP 状态、结束原因和服务报告的 token 用量，并最多重试一次。两次请求都计入原有预算；已耗尽的重试次数跨进程恢复保留。不会将推理内容当作最终答案，也不会把空响应计为能力失败。连续空响应仍会停止，需根据日志诊断。

仅针对此次空响应运行时修复，旧运行可显式执行 `python3 -m rqgm_lab.runtime_repair --root runs/<run>`，然后以原配置恢复。该迁移只允许 `live.py`、`engine.py`、Pi bridge 和迁移工具自身变更；其他源码变化会被拒绝。迁移追加新旧可信版本及变更记录，保留节点、历史评价、预算和待执行事务。由于运行时重试策略发生变化，跨版本结果需按各自控制器版本解释。通用的源码修改仍应新建实验。

- 每个动作开始前提交选中的父节点/任务/随机采样值。
- 每道隐藏回归完成后保存进度；重启不会从第一题重新付费。
- 每个完成的模型调用按 operation + 请求 + 模型参数保存结果，重启复用。
- 无效候选不会替换已归档节点；拒绝的候选 Git 对象仍保留。
- 原始日志有哈希链；断电导致尾行不完整时不会自动截断原件。

显式恢复损坏日志必须写到新目录：

```bash
python3 -m rqgm_lab.experiment recover \
  --root runs/my-first-live \
  --destination runs/my-first-live-recovered
```

恢复复制保留原目录和完整 `.original` 日志，只在新目录取合法前缀；若发现日志中段损坏，则拒绝自动处理。复制工作区仅用于这种操作者明确触发的恢复，正常进化不复制整套依赖。

远端模型请求与本地落盘不是分布式事务：如果远端已经完成，而本机在收到/保存响应前崩溃，恢复后可能重发该请求。预算预留在请求前持久化，避免因此绕过预算；不宣称 exactly-once 远端调用。

## 2. 目录与模块

```text
redqueen/
├── programmeDOC.md              本文：启动、结构、机制、边界
├── README.md                    快速入口
├── apikey.bin                   可信密钥；不入版本库，不交给 Agent
├── RQGM.pdf / HGM.pdf / HyperAgents.pdf
├── rqgm_lab/
│   ├── experiment.py            真实实验控制器、事务、CLI
│   ├── node_tools.py             操作者导出节点、指定 Seed 节点回归
│   ├── engine.py                可变 Harness 解释执行、原语、模型缓存、预算
│   ├── protocol.py              公开原语/场景契约和两个能力目标
│   ├── scenarios.py             场景生成、正负对照、oracle、执行观察
│   ├── anchors.py               控制器独占的固定判定锚点
│   ├── regression_live.py       独立的一次性真实 Executor 回归
│   ├── validation.py            MBPP+ 准备、隔离函数执行、早期 mock 验证
│   ├── search.py                CMP、TS、角色/任务均衡、best-belief
│   ├── store.py                 追加哈希日志、Git 内容存储
│   ├── artifacts.py             路径、类型、大小及 symlink 检查
│   ├── sandbox.py               Landlock、seccomp、capabilities 与资源上限
│   ├── bigmodel.py              可信凭据代理；固定上游、认证、请求限额
│   ├── live.py                  单运行时真实模型调用；使用代理
│   ├── providers.py             兼容早期 mock 与真实单次调用的接口
│   ├── report.py                本地静态实验报告
│   ├── recovery.py              保留原件的日志尾部恢复
│   ├── doctor.py                无 API 环境/隔离自检
│   ├── controller.py            第一阶段 mock 实验，单独保留
│   └── vendor/beta.py           复用的 MIT Beta 数值模块
├── seeds/
│   ├── live_seed/
│   │   ├── meta.py              可变的自修改入口
│   │   └── executor.py          可变的任务执行入口
│   ├── live_challenger/
│   │   ├── generate.py          可变测试生成方法
│   │   ├── improve.py           可变测试方法自修改入口
│   │   ├── judge.py             可变证据判定器
│   │   └── .claude/skills/challenge/SKILL.md
│   └── seed/、challenger/       旧 mock 种子，真实实验不使用
├── runtime/
│   ├── pi-bridge.mjs            固定 Pi SDK 接入；不可由候选修改
│   ├── package*.json            精确版本与依赖锁
│   └── node_modules/            共享依赖，只安装一次
├── private/                    控制器独占 MBPP+ 源文件、12题清单
├── research/                   本地论文文本、上游核对源码与版本清单
├── tests/                      框架测试，不是 Agent 实验题库
├── docs/                       调研、模型接口、历史方案与验收记录
└── runs/<run>/
    ├── events.jsonl            原始追加日志：事务、双树、轨迹、隐藏结果
    ├── calls.jsonl             每次 API 的保守预算预留与实际 usage
    ├── objects.git/            代码对象库：父子提交、可信源码快照
    ├── responses/              可信模型响应缓存；不挂载给 Agent
    ├── regression-progress/    回归恢复状态；不挂载给 Agent
    ├── report.html             操作者报告，不进入学习输入
    └── lock                    同一 run 独占锁
```

`runs/.execution.lock` 限制整个项目同一时间只有一个重型实验/接口调用。每个 run 另有自己的文件锁。Python 的线程只用于监控、短生命周期代理以及最多两个任务上下文，不引入分布式服务。

### 2.1 节点的保存、导出和人工复测

每个进化节点都在 `runs/<run>/objects.git` 的 `refs/heads/nodes/<commit>` 中，而不是可变的普通工作目录。Seed 节点含完整的 `executor.py` 和 `meta.py`；Challenger 节点含完整的 `generate.py`、`improve.py`、`judge.py` 与 `.claude/skills/challenge/SKILL.md`。根种子在 `seeds/live_*`，只用来创建第一个 commit；其后的历史版本只以 Git 对象保存，避免被下一轮覆盖。

列出已接纳节点：

```bash
python3 -m rqgm_lab.node_tools list --root runs/my-first-live
```

将一个节点导出到一个**不存在**的新目录，供人工检查或标准 Claude Code 项目会话使用：

```bash
python3 -m rqgm_lab.node_tools export \
  --root runs/my-first-live --role seed --node <commit前缀> \
  --destination /workspace/redqueen/exports/seed-<commit前缀>

python3 -m rqgm_lab.node_tools export \
  --root runs/my-first-live --role challenger --node <commit前缀> \
  --destination /workspace/redqueen/exports/challenger-<commit前缀>
```

手动让某个 Seed 节点完成控制器所选的 MBPP+ 子集，使用以下命令；这会真正调用 Pi，并按原有隔离方式运行临时 Executor。`--tasks` 是操作者侧筛选，省略时运行固定的 12 题集合。节点只会看到单道自然语言任务和入口函数名；参考实现、测试输入、期望值、累计分数和详细失败原因始终留在控制器侧。

```bash
python3 -m rqgm_lab.node_tools evaluate \
  --root runs/my-first-live --role seed --node <commit前缀> \
  --tasks 3,4 --max-api-calls 4 --max-reserved-tokens 40000
```

输出只给出通过数、总数、用量和一份 0600 控制器记录的位置；详细记录位于 `runs/<run>/manual-evaluations/`，不应复制到任何 Agent 工作区。该命令是一次独立复测，不改变进化树、选择统计或历史实验预算。

Challenger 的 Skill 在框架内不是依赖 Claude Code 自动扫描：每个节点的 `generate.py` 和 `improve.py` 会从同一节点的 `.claude/skills/challenge/SKILL.md` 明确读取内容，并作为本次 Claude 请求的 system prompt 一部分。因此控制器总是精确加载该节点版本的 Skill。导出后若要用常规 Claude Code 交互会话检查它，进入导出目录再启动 `claude` 即可；但该人工会话不属于受控实验，也不会写回进化树。

## 3. 一次真实实验的数据流

1. 环境与隔离自检；锁定可信源码、依赖和数据版本；建立 Seed / Challenger 根节点。
2. Claude Code 根据初始 Skill 和当前 Seed 源码生成场景构造程序。构造程序在沙箱中执行，产出场景、oracle 和正负对照。执行 oracle 两次验证控制样本。没有人为预置 Personal Agent 题库。
3. 固定初始 suite 与判定器版本。独立运行 12 题编码回归，记录初始编码能力。低于配置下限时停止，结果仅对操作者可见。
4. HGM 调度决定扩展 Seed 或执行选择评价。选择评价从当前固定 suite 中按角色/任务均衡抽取，不将结果直接放入修改提示。
5. 扩展前按需生成新的训练场景并执行；只有这些公开训练场景和轨迹提供给 Meta。Meta 用 Pi 产生 `build_patch()` 程序，沙箱执行后取得完整的新节点文件。
6. 新节点通过文件/语法边界检查并产生 Git 子提交；临时 Executor 执行完整独立编码回归。低于根节点基线或配置下限则拒绝；不把题目、测试或详情送回 Meta。
7. 到达 checkpoint，Challenger 基于公开训练轨迹通过 Claude Code 修改 Skill/生成/判定/自修改方法；生成新 suite 并验证正负对照。
8. 所有候选判定器在同一固定隐藏判定锚点上比较 best-belief。只有严格胜出者替换现任；平局保留现任。
9. 替换时推进 Epoch，使依赖旧验证者/生成器的评价失效。原始记录、任务、代码与树全部保留；下次抽到旧节点时才按新标准评价。
10. 预算结束时输出当前有效证据下的 best-belief 节点和报告。若恰好发生替换，尚无新标准证据，则返回 `winner: null`，不把一个未经新标准评价的节点宣称为冠军；上一 Epoch 的选择另行保留。

## 4. 可变 Harness 与并发接口

Seed 的 Meta 和 Executor 都是普通 Python 程序，用同一套 Pi SDK 模型技术底座；两者作为一个 Git 节点共同被修改、继承和验证。Challenger 通过自己的可变程序读取 Skill，将其作为 Claude Code 的系统上下文，不修改 Claude Code 本身。

每次入口读取：

```json
{"input": "当前请求", "state": "候选自己管理的状态", "observation": "上一个原语的结果"}
```

入口输出一个动作：

| 动作 | 作用 | 信任与隔离 |
|---|---|---|
| `model` | 用当前角色的 Pi / Claude 编码运行时请求模型 | 只返文本和 usage；真实凭据不进入候选 |
| `python` | 在当前任务工作区执行 Python | 独立受限进程、无网络和系统权限 |
| `parallel` | 最多两个作业，独立临时目录/上下文 | 不自动共享记忆或工作文件；结果按提交顺序返回 |
| `context` | 作为 parallel 的作业，运行完整的子 Harness | 子任务可自主多步调用模型/执行代码；禁止递归扩散并发 |
| `finish` | 返回本次任务结果 | 输出仍由外层验证 |

这是一组受限执行能力，不是 Router/Worker 架构。初始 Executor 只调用一次模型，然后返回答案；没有预先写好路由、共享记忆、身份同步或协作算法。候选可以修改控制流、构造上下文、管理状态、添加 Python 模块、执行代码、创建自己的持久文件，并决定如何使用独立上下文。

同一个场景的多个 turn 共享该场景工作区；不同场景与独立回归实例重新建立工作区，防止评价之间泄漏。这允许研究跨 turn / 跨执行单元的记忆一致性，但不是已经实现的生产级长期记忆服务。长期效果需要更长的独立研究设计，不能从三次 turn 自动推断。

`build_suite()` 与 `build_patch()` 是初始方法使用的代码产物协议：由模型编写构造程序，在沙箱执行后得到结构化数据。采用它是为了避免大段 Python 源码嵌入 JSON 时的转义错误；程序本身也属于可修改 Harness 的方法。失败可在限定预算内依据公开执行错误修正。

## 5. 场景与可靠判定

每个冻结 suite 含两个由 Challenger 自主设计的场景，分别针对两个固定能力目标。每场景包含 1–3 个任务 turn、初始文件、Python `check(observation)` oracle、解释、难度说明、正例与 1–3 个反例。场景数量是资源预算，不是预置题目或规定进化路线。

Executor 只看到任务 turn 和初始文件，不看到 oracle/正负对照。oracle 在另一个隔离工作区运行，只取得控制器收集的答案、导出文件和事件。并发事件的上下文 ID、开始/结束时间由控制器记录，候选返回的“我并发了”不会自动成为调度事实。

验证要求：

- 正例通过、全部反例失败，重复运行结果一致。
- 目录/文件不能覆盖初始 Agent 源文件；禁 symlink 导出、路径穿越和无限大产物。
- oracle 必须返回真正的 bool，而非字符串、隐式真值或伪造分数。
- 若真实观察导致 oracle 异常或不一致，该评价记为 `usable: false`，保留日志但不进入成功/失败后验，不能冤枉 Seed 或算作成功。调度次数仍平衡，避免只反复抽同一个无效场景。
- 在固定的公开证据格式上，Challenger 的 judge 仍可自修改；外层拒绝把执行失败或实际 oracle 失败包装成成功。

**判定正确不等于测量完备。** 正负对照能发现恒真 oracle、明显矛盾和不可执行测试，不能自动证明场景充分覆盖“个体性”或排除全部 reward hacking。场景解释和实际轨迹保存在报告/日志中，需研究者审查构念效度。这不是一个预先保证晋升或必然成功的测试体系。

## 6. 两类独立验证与绝密边界

### 6.1 MBPP+ 编码回归

数据来自公开 EvalPlus MBPP+ v0.2.0，但选取的 12 题清单、增强输入、参考实现和所有详细回归结果仅保存在可信目录及操作者记录中。使用这些题的全部 base/plus 输入，并在独立进程中运行参考和候选实现。

临时 Executor 只取得本题任务说明和函数入口，样例 assert 已从提示中移除；不知道数据集名、测试用途、其他题目、期望输出或回归成绩。执行候选函数时自然需要传入本次参数，但验证程序和期望值不在同一进程里。每题结束销毁工作区，不把任何回归状态传回训练。

这 12 题特意避开复杂序列化/集合/容差判定，采用普通 JSON 输入与结果比较；不声称复现 EvalPlus 全量官方成绩。此前参考实现校准的 12/12 也不等于 Seed 的成绩。

### 6.2 验证者晋升锚点

`anchors.py` 定义固定的隐藏证据样例及其独立标签，包括正常成功、实际失败、执行错误、缺字段、重复证据 ID、伪 bool 等。它检验 judge 是否遵守固定的证据判定语义。锚点与 MBPP+ 完全分离，候选没有得到这些样例或分数。

这套锚点是验证者证据可靠性的基准，**不是 Personal Agent 能力题库，也不是场景难度评分**。因此提升生成策略的候选若在锚点上没有严格胜出，也不会被强行晋升；这正是 anchor-gated replacement 的限制。达到相同完美分数后可能长期不替换，这应当被如实记录，而不是为制造进化曲线而破坏规则。

### 6.3 实际权限

Linux Landlock ABI>=4 控制文件读写与网络端口；seccomp 拒绝 fork、非线程 clone、进程窥探、挂载、io_uring 绕过、任意 socket 等；执行前设置 no_new_privs，并清零 effective/permitted/inheritable capabilities。沙箱不支持则失败关闭。

不可信 Python 只能读运行库和自己的临时工作区。Pi 运行时额外只读共享依赖。控制器、Ground Truth、原日志、其他工作区、宿主凭据和 `/proc` 均不可见。父进程关闭继承 FD，环境白名单重建。密钥代理只对真实模型运行时开放短期令牌，候选 Python 没有令牌/端口/凭据。

可信计算基包括 Linux 内核、系统运行库、控制器代码、固定 Pi bridge 与安装的运行时。此边界不防御宿主管理员修改内核/控制器，日志也不是对 root 防篡改的 WORM 设备；对不可信 Agent 的保护由内核实际执行。

## 7. RQGM / HGM 机制

本地原论文与源码调研见 `docs/RESEARCH.md` 和 `research/manifest.json`。

- 每个节点有 own 成功/失败计数；CMP 聚合包含自身的完整后代子树计数。
- 扩展父节点按 `Beta(1+S_clade, 1+F_clade)` Thompson Sampling；评价目标按 own counts 抽样。
- `N^0.5 >= |T|` 使用 UCB-Air 扩展门。每个 N 最多尝试一次扩展，失败后继续评价，防止同一失败节点造成无限扩展循环。失败尝试和原因保留。
- 选择目标后，按最少评价的能力角色与场景平衡采样。无效 oracle 尝试只用于负载平衡，不用于 utility。
- 最终 best-belief 使用 Beta 后验的 5% 分位数；固定 `tau=1`，遵循 RQGM 的简化固定温度设置，不声称复现 HGM 的全部温度调度实验。
- checkpoint 默认 `2,4,8,16,...`；可调整首个 checkpoint，但中途不改。
- 每次边界产生至多一个 Challenger 候选；父节点按该树独立锚点证据的 CMP/TS 选择。
- 隐藏锚点对所有候选用同一完整集合评分，重复评测不伪装成新增独立样本；最大 best-belief 严格胜出才晋升，平局保留现任。
- 每条 utility 记录带生成/判定依赖的 slot 版本。suite 与 judge 一起冻结、更换；更换只使关联记录失效，独立锚点计数、代码与历史保留。
- 旧节点惰性重评，不在边界全量刷评。

双树是本研究对原论文单 archive 多角色形式的工程适配；不把它称为原论文已经证明的双树收敛结论。上游模型服务自身更新也可能破坏理论上的完全平稳性，记录固定模型 ID 并不等于拥有模型权重快照。

## 8. 资源、调用与日志预算

| 项目 | 默认/限制 |
|---|---|
| 外层实验 | 单进程主控、全局执行锁 |
| 重型模型会话 | 始终串行 |
| 独立任务上下文 | 1 或 2；不允许递归并发扩散 |
| 单 Harness | 最多 8 步；普通上下文最多 3 次模型调用，生成/修改最多 2 次 |
| 单次输出 | 任务 2048、回归 1024、生成/修改 4096 token |
| 单次上游请求 | 90s 网络超时，运行时墙钟 120s，broker 最多 1 请求 |
| Python | 地址空间 256MiB；CPU 20s；普通原语墙钟 12s，oracle 8s |
| Node/Claude | Node heap 192MiB；RSS 512MiB 监测上限 |
| 子进程输出/工作目录 | 单输出文件 1MiB；目录 8MiB/256 条目，100ms 监测 |
| 可导出的候选 | 64 个文本文件、合计 256KiB，禁 symlink/设备/FIFO |
| suite | 2 场景；总结构不超过 64KiB；每个 oracle 8KiB |
| 初始 suite 修正 | 最多 3 次 generation attempt，错误留档 |
| 总预算 | 默认 80 API 请求、600000 保守预留 token；CLI 可设置 |

重型运行时的 RSS 和目录监控不是 cgroup 硬配额，可能有短时超额；单 Harness 的 420s 检查在步骤边界执行，长原语仍由自身超时限制。2C4G 主机上建议保留现有默认值，不随意扩大并发或模型上下文。

token 预算采用“请求 JSON UTF-8 字节数 + 最大输出 + 余量”的保守预留，先写入日志再发请求；不是将 token 精确预测成字节。响应另记实际 input/output/cache usage。金额未知，必须看智谱账单，不能把占位单价 0 解释为免费。

正常运行只物化很小的候选文件；依赖共享、Git 对象去重、报告按需生成。原始记录不能被候选删除；保留策略和长期备份由操作者负责。

## 9. 测试与验收

```bash
python3 -m unittest discover -s tests -v
```

框架测试覆盖内核隔离、真实密钥路径不可读、capabilities 清零、预算与凭据代理、路径/symlink、独立上下文重叠、本地模块导入、候选回滚、源码恢复约束、CMP/后验、角色均衡、Epoch 替换/失效、无效 oracle 排除、日志快照/哈希/损坏尾恢复等。

测试中的合成模型和固定用例只验证框架控制流，不参与真实 Challenger 题库。涉及本机 HTTP broker 的测试需要允许 loopback bind；不需要访问真实 API。

实际模型连通性可单独检查：

```bash
python3 -m rqgm_lab.live --tool both --max-tokens 512
```

最终本地测试：29/29 通过；UID 降权后的 Pi 与 Claude Code 真实请求各一次，均 HTTP 200。真实闭环 `runs/live-acceptance-v3` 使用 34 次请求，报告输入/输出 token 为 23,823 / 17,452；初始回归 11/12，两项能力评测均未通过，自修改 Seed 候选因回归下降被拒绝，Challenger 候选因正负对照失败被拒绝，Epoch 保持 0。这验证了实际调用、候选生成和拒绝路径，不证明能力涌现。Epoch 晋升、选择性失效和恢复路径已用离线可控模型验证。

该真实闭环运行后进一步加固了 UID 隔离；最终源码已通过全量离线测试和真实运行时冒烟测试，没有再重复完整付费闭环。旧运行绑定旧源码，不能用最终源码直接续跑；新实验使用新目录。完整验收摘要见 `docs/acceptance.json`。开发过程中发现的失败实验目录也保留，不删除或改写成成功。

## 10. 复用组件与维护

- Pi：复用 `@earendil-works/pi-coding-agent@1.5.1` 的 session、资源加载、模型适配；Meta 与 Executor 共用。
- Claude Code：复用已安装 CLI；Skill/提示和生成/修改程序位于可变 Challenger，底层 CLI 不改。
- HGM：核对官方 CMP/TS/UCB-Air 实现，以标准库保留核心搜索，避免搬入大型 SWE-bench/Docker 栈。
- HyperAgents：复用共同自修改的节点边界思路；Meta 不被固定为只修改 Executor。
- RQGM：保留 Epoch、锚点晋升、选择性失效；复用锁定第三方 MIT `beta.py` 数值模块，许可证随代码保留。
- MBPP+：复用官方公开数据的固定小子集，外层私有评测。

重新安装共享依赖前先检查资源：

```bash
free -m
df -h .
npm ci --prefix runtime --ignore-scripts --omit=optional --no-audit --no-fund
```

不要在进化节点里运行安装或修改模型配置。若要修改可信控制器、公开协议、验证者锚点、回归集合或基础模型，创建新的实验版本/目录，保留旧版本，以免把不同条件下的结果混在一条进化曲线上。
