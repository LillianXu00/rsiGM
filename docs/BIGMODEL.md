> 阶段性记录：最终实现、启动入口和当前限制以 [programmeDOC.md](../programmeDOC.md) 为准。

# 智谱 Coding Plan 接入

已通过真实 Pi SDK 和本机 Claude Code CLI 验证。没有安装新依赖、改全局 Claude 设置、把真实 key 传给 Agent，或启用后台实验。

## 使用

项目根目录 `apikey.bin` 为单行明文 API key（允许结尾换行）；权限已设为 600，并加入 `.gitignore`。只由可信 Python broker 读取。

```bash
# 默认串行测试 Pi 与 Claude Code，各一次小型代码生成
python3 -m rqgm_lab.live --tool both
# 指定单个运行时与任务；参数不包含 key
python3 -m rqgm_lab.live --tool pi --max-tokens 1024 --prompt 'Write a Python binary search function.'
python3 -m rqgm_lab.live --tool claude --max-tokens 1024 --prompt 'Review this Python expression: sum(range(10)).'
```

Python 调用：`providers.pi({'prompt': '...'})` 或 `providers.claude({'prompt': '...'})`。省略第二个 response 参数表示真实调用；传入 response 仍走原 mock。也可以使用 `live.invoke(tool, request, model=..., max_tokens=...)`。

默认模型 `glm-5.3-flash`；可显式指定 `--model glm-5.3`。默认输出上限 512 token，允许 1–4096；每次会话最多 2 次上游请求，没有自动切换到按量收费的标准 API。请求和进程按既有全局锁串行执行。网络超时 90s，运行时墙钟上限 120s。

## 边界

- Pi → 本机临时 broker → `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`。
- Claude Code → 同类临时 broker → `https://open.bigmodel.cn/api/anthropic/v1/messages`。
- broker 仅允许固定路由、固定域名，禁重定向；鉴权用随机会话令牌，真实 key 只在发往智谱的请求头中注入。
- 沙箱继续拒绝密钥文件、控制器、隐藏数据与原始日志访问；不可信候选没有 broker 的会话令牌。模型运行时只允许连接指定临时 TCP 端口。Landlock 按端口过滤，不声称是按 IP 的完整网络防火墙。
- 上游 HTTP 错误脱敏后返回；不记录请求体、认证头或 key。正常结果包含真实 usage；金额未知，以智谱套餐账单为准，不把 Pi 的占位单价 0 当作实际费用。
- 原 `controller run` 仍是显式 mock，包含合成测试/合成修改；本次接入不把它伪装为真实自进化实验。正式循环的多轮自主执行、并发子会话及测量设计仍按 PLAN.md 后续完善。
- 当前 CLI 使用隔离的临时会话且 tools 为空，适用于模型接口与文本/代码生成验证；不在项目根目录启动拥有工具权限的 Claude，以防它读取密钥或可信数据。

## 已核对的官方说明

- https://docs.bigmodel.cn/cn/coding-plan/quick-start
- https://docs.bigmodel.cn/cn/coding-plan/tool/others （列出 Pi、Claude Code，确认编程专用端点）
- https://docs.bigmodel.cn/cn/coding-plan/tool/claude （Anthropic 兼容设置；保留本机 2.1.81，经实测无需升级）
- https://docs.bigmodel.cn/cn/coding-plan/latest-model （默认 GLM-5.3-Flash；关闭思考对应低 effort）
- https://docs.bigmodel.cn/cn/coding-plan/usage-notes （串行使用以控制资源与套餐并发）

首次真实验收：两个运行时各 1 请求、均 HTTP 200、输出正确 `add(a,b)`；Pi 58 输入/18 输出 token，Claude Code 160 输入/18 输出 token。没有发送隐藏回归材料。
