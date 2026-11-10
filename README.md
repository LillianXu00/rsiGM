# RQGM Harness 递归自进化实验

完整结构、算法适配、隔离边界及启动说明见 [programmeDOC.md](programmeDOC.md)。调研与上游版本见 [docs/RESEARCH.md](docs/RESEARCH.md)。

在当前服务器以 root 控制器启动；不可信子进程自动降权，并受 Landlock / seccomp 约束。使用已有 `apikey.bin`，不需要重新安装依赖。

```bash
cd /workspace/redqueen
python3 -m rqgm_lab.experiment doctor
python3 -m rqgm_lab.experiment run --root runs/my-first-live --budget 2 --max-api-calls 60 --max-reserved-tokens 600000
python3 -m rqgm_lab.experiment report --root runs/my-first-live
```

同一源码和配置下重复命令可恢复；将 `--budget` 增至 4 可继续评价，同时按需提高累计 API/token 上限。不要把旧源码运行目录用于新版本实验。报告位于对应目录的 `report.html`，原始日志、隐藏评测及报告只供操作者查看。

已通过 29 项本地测试及 Pi / Claude Code 真实 API 测试。真实闭环完成两次能力评价、Seed 自修改和 Challenger 更新检查，但候选均未被接纳，尚未观察到目标能力涌现。结果与限制见 [验收摘要](docs/acceptance.json) 和 [真实实验报告](runs/live-acceptance-v3/report.html)。

```bash
python3 -m unittest discover -s tests -v
```

测试使用本地 HTTP 服务，需允许回环端口；无需付费 API。原有 `rqgm_lab.controller` 是历史 mock 对照入口，正式实验使用 `rqgm_lab.experiment`。
