> 阶段性记录：最终实现、启动入口和当前限制以 [programmeDOC.md](../programmeDOC.md) 为准。

# 技术方案与研究边界

先读本地 RQGM.pdf、HGM.pdf、HyperAgents.pdf，再核对上游代码；本方案已在开始编码前向用户说明。

目标只有两项：独立上下文的自主并发任务处理，以及跨执行单元的一致身份、记忆、用户目标和行为原则。不得把 Router/Worker、共享记忆或固定验证路线作为进化答案。

模块：

- `search.py`：CMP 子树成功/失败聚合、节点/子树 Thompson Sampling、UCB-Air、角色/任务均衡。
- `controller.py`：可信 Epoch 调度、冻结版本、隐藏锚点替换、选择性失效、失败恢复。
- `store.py`：追加 JSONL 和 Git 对象库；无数据库、工作区完整拷贝或每节点安装。
- `sandbox.py`：Landlock 文件访问控制 + seccomp 系统调用过滤；临时工作区与资源限额。
- `providers.py` / `runtime/pi-bridge.mjs`：真实 Pi SDK / Claude Code CLI 的 mock 模型适配。
- `seeds/`：可变 Meta、Executor、Challenger Skills/生成器/判定器。
- `validation.py` / `private/`：控制器持有的独立验证，不进入任何修改上下文。

实施顺序：资源检查 → 论文与源码映射 → 隔离与日志 → mock 两运行时 → 静态回归校准 → 双树/替换/失效 → 恢复与报告 → 用户提供 API 后实现可信模型代理与开放执行协议。

## 算法映射与不能混淆的事项

1. RQGM 本地论文 §3、附录 B.2/B.3、算法 1：用 `N**0.5 >= |T|` 扩展，扩展父节点用 clade counts，评价目标用 own counts。Beta(1+S,1+F)；最终选择 5% 下分位 best-belief。
2. HGM §3：保留 CMP/TS。代码支持 tau 参数；本次采用 RQGM 的固定 tau=1，未声称复现 HGM 的全部温度调度或论文指标。
3. Epoch 边界 N=4,8,16,...；验证者、测试生成程序和判定程序共同按 Git commit 冻结。边界才允许替换，平局保留现任。生成/评分依赖均记入 slot provenance；更换后重算 active 视图，原记录和 Git 对象不删除。只在再次抽到节点时重评。
4. 双树是本实验对单 archive 多角色形式的适配：Seed 是 Meta+Executor 原子节点；Challenger 独立树，边界每次一个候选，父节点用其固定锚点 evidence 的 CMP/TS。不是论文原样复现的双树定理。
5. 隐藏 MBPP+ **只做 Seed 回归门**；不用于 Challenger 学习、困难度评价或晋升。不能用它代替验证者准确性的独立 anchor。
6. 当前 anchor 是隐藏的、固定的合成判定正确/错误样本，只检验 mock equality oracle。不能证明真实 Personal Agent 测试质量。正式实验需要针对可执行证据协议建立独立、固定的判定锚点；这属于测量设计，不得偷换成规定 Agent 实现架构。
7. 训练输入与选择证据分开。全量锚点重复评估不能当作新的独立样本累计。
8. 当前 mock 的任务分布和修改为脚本合成，不能推断递归自改进、共同进化学习或目标能力已经涌现。

## 真实实验仍需完成的接入

已通过独立 live 入口接入智谱 Coding Plan，凭据只存在可信代理内，Pi/Claude 使用短期令牌；见 BIGMODEL.md。进化控制器仍保留 mock，不把真实密钥交给可变 Python/工具进程。还需把一次提示词构造接口扩展为通用、多轮工具/子会话能力，受全局并发<=2与预算约束；具体调度、记忆和协作结构由候选自行决定。当前为安全 mock 禁止候选 fork，**还不是可用于研究并发能力涌现的正式 Harness**。

不能仅把 mock_response 替换为网络请求就宣称满足正式实验要求。实际 API 兼容性、token 计费、可信调用代理、多轮自主测试生成、独立判定锚点和两目标的测量有效性需要下一阶段集成验证。
