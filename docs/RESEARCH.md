# 调研记录（2026-11-10）

论文均从当前目录 PDF 提取，文本位于 `research/*.txt`，未联网重新查询论文。

| 组件 | 核对来源 / 版本 | 复用方式 |
|---|---|---|
| RQGM | 本地 PDF §3, App B, F | Epoch、anchor-gated replacement、provenance erasure、geometric checkpoints |
| HGM | https://github.com/metauto-ai/HGM commit `013872d95da978483f5b540e531db063d23890da` | 对照 hgm.py TS_sample、tree.py，按标准库实现调度；不搬 Docker/SWE-bench 栈 |
| HyperAgents | https://github.com/facebookresearch/Hyperagents commit `59a68f672dfb92c74aeb7e61535d776fb36e172d` | 联合可变 Meta/Executor 思路，未复制实现；原许可证非普通 MIT，保留调研文本 |
| 第三方 RQGM | https://github.com/kingkillery/red-queen-godel-machine commit `2cea930b09e1df0e564efb0d6e77ac5154e52be7` | 原样 vendoring `beta.py`，MIT 许可证在 vendor/LICENSE；不称为作者官方实现 |
| Pi | https://github.com/earendil-works/pi （原 badlogic/pi-mono 重定向） | `@earendil-works/pi-coding-agent@1.5.1`，真实 createAgentSession、内存 SessionManager、DefaultResourceLoader；共享 runtime/package-lock.json |
| Claude Code | 本机 `claude --version` = 2.1.81；https://code.claude.com/docs/en/headless | `--bare -p --output-format json --no-session-persistence`；不改底层 Harness |
| MBPP+ | https://github.com/evalplus/mbppplus_release/releases/download/v0.2.0/MbppPlus.jsonl.gz | 固定 12 道简单任务，全部 base/plus 输入，控制器分离运行 reference 与 candidate；私有清单包含 SHA256 |

安装前：总内存约 3.5GiB，可用约 1.3GiB，无 swap；磁盘余量 33GiB。Pi 包本体解压约 24MB，实际共享依赖约 160MB；使用 `--ignore-scripts --omit=optional --no-audit --no-fund`，未编译或装容器。Python 无新增依赖。

上游查询元数据、固定版本源码与接口文档在 `research/upstream`。源码只下载必要文件；没有完整克隆大型仓库。Pi SDK 接口已经实际执行验证，而非只依据网页示例。

## 回归集注意

题目 ID、测试输入和参考实现仅在可信目录。临时 Executor 只取得清除样例 assert 的任务描述和函数入口；执行候选函数时取得本次输入参数，这是黑盒执行所必需，不提供期望值、测试程序或其他题目。任务执行环境在结束后销毁，所有回归轨迹只存可信日志；Meta/Challenger 不收到任何回归提示、分数或失败详情。

这不是 EvalPlus 官方完整评分栈：12 题特意选择普通 JSON 参数/结果且可用相等判定的任务，避免特殊序列化、集合、浮点容差和极端性能题。使用该子集的全部增强输入；不宣称得到官方全量 MBPP+ 成绩。校准单独标记，不计作 Seed 表现。
