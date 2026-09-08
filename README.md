# Remote Test Runner & Evidence Collector

远程测试自动执行与证据采集系统，用于将 Linux/FusionOS 的 SSH 手工测试流程自动化。MVP 会在一个持续存在的交互式 SSH Channel 中按 YAML 顺序执行命令，通过 WebSocket 将真实终端输出实时显示到 xterm.js，并按 Evidence Policy 保存截图、日志和结构化结果。

## 系统架构

```text
TestCase YAML → Execution Engine → Paramiko invoke_shell → Linux/FusionOS
                         │                         │
                         │                         └→ Terminal Output
                         │                                  │
                         └→ Evidence Engine          WebSocket ↔ xterm.js
                                  ▲                         │
                                  └── TERMINAL_RENDERED ────┘
                                            │
                                      Playwright 截图
```

关键模块：

- `backend/testcase`：Pydantic 数据模型、YAML 解析和 Runner 稳定入口。
- `backend/ssh`：Paramiko 连接及测试期间持续存在的 `invoke_shell()` 会话。
- `backend/execution`：Finish Marker、命令风险检测、步骤编排和渲染确认。
- `backend/evidence`：归档目录、Session Log 和 Playwright 截图。
- `backend/result`：由 YAML `expected` 驱动的确定性规则判断。
- `backend/api`：案例、会话、人工确认、手工截图和双向 WebSocket API。
- `frontend`：无框架 HTML/CSS/JavaScript 页面及 xterm.js 终端。

## 技术栈

Python 3.11+、FastAPI、WebSocket、Paramiko、PyYAML、Pydantic v2、Playwright、HTML/CSS/JavaScript、xterm.js。

## 安装

Windows PowerShell：

```powershell
cd D:\path\to\remote-test-runner
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Linux：

```bash
cd /path/to/remote-test-runner
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install --with-deps chromium
chmod +x run.sh
```

Playwright 的 Python 包和 Chromium 浏览器是两项独立安装。截图服务优先使用 Playwright Chromium；如果它尚未安装，会自动尝试 Windows 已安装的 Microsoft Edge。也可以设置 `RTR_BROWSER_CHANNEL=msedge` 或 `chrome` 明确选择浏览器。若都不可用，SSH 执行和日志仍可工作，但截图会在页面显示明确错误。

前端默认从 jsDelivr 加载 xterm.js 5.5.0 和 fit addon 0.10.0，首次打开需要能访问 CDN。隔离网络中可下载对应文件到 `frontend/vendor/`，并将 `index.html` 中的三个 CDN 地址改为 `/assets/vendor/...`。

## 启动

项目根目录执行：

```powershell
.\run.ps1
```

或跨平台直接启动：

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

访问 <http://127.0.0.1:8000>，健康检查为 <http://127.0.0.1:8000/health>。

如果用不同地址或端口启动，必须让截图浏览器知道可访问的服务地址：

```powershell
$env:RTR_PUBLIC_BASE_URL = "http://127.0.0.1:9000"
python -m uvicorn backend.main:app --port 9000
```

## 执行测试

1. 确认控制机能通过 SSH 访问目标 Linux/FusionOS。
2. 在网页选择 `TC_DEMO_001`，输入 IP、端口、用户名，以及密码或本机私钥路径。
3. 点击 **Start Test**。密码仅在认证前保存在当前 Python 进程内存中，认证后立即清除，永远不会写入 YAML、日志、JSON 或截图元数据。
4. xterm.js 会显示真实 Shell；自动步骤执行期间和结束前也支持键盘输入。
5. `verify` 步骤完成且前端确认终端渲染后，Playwright 截取 `#evidence-area`。
6. **Capture Evidence** 可随时补充 `stepNN_manual_XX.png`。
7. 检测到 `rm -rf`、`mkfs`、写磁盘的 `dd`、`shutdown`、`reboot`、`poweroff`、`fdisk` 或 `parted` 时会暂停；只有点击 **Confirm Risk & Run** 后才执行。

不要在自动命令仍在运行时手工输入命令；共享 PTY 会让两者输出交织。MVP 保留人工介入能力，但没有命令队列仲裁。

## TestCase YAML

案例放在 `testcases/*.yaml`：

```yaml
version: "1.0"
testcase:
  id: TC_EXAMPLE_001
  name: 示例检查
  description: 检查内核
target:
  connection:
    type: ssh
steps:
  - id: 1
    role: verify
    name: 查看内核
    action:
      type: shell
      command: uname -a
    expected:
      exit_code: 0
      stdout_contains:
        - Linux
    evidence:
      capture: true
      trigger: command_complete
```

`role` 支持 `setup`、`verify`、`cleanup`。未显式配置 evidence 时，`verify` 默认在 `command_complete` 截图，其他角色默认不截图。显式配置始终优先。

规则支持：

- `exit_code: <integer>`
- `stdout_contains: [text, ...]`
- `stdout_empty: true|false`

所有已配置规则都通过时 Step 才为 `PASS`。因此 `exit_code: 1` 与 `stdout_empty: true` 的组合可以是合法 PASS，不会把所有非零退出码强制判为失败。

新增案例时复制示例、修改唯一 Case ID 和步骤，然后刷新页面。YAML 无效时案例列表会标为无效，API 会返回具体校验错误。

## Finish Marker 与渲染确认

执行器为每一步生成随机 Marker，并在同一个 Shell 中把退出码输出为 `__RTR_FINISHED_<random>__:<code>`。Reader 持续读取 Channel，检测 Marker 后才认为命令完成；Marker 和 PTY 回显包装行不会进入业务 stdout。没有用固定 sleep 判断命令结束。

需要自动截图时，后端发送 `step_complete`；前端等待全部 xterm `write()` 回调和两帧浏览器渲染后返回 `terminal_rendered`。后端随后启动独立截图页，从会话 API 恢复终端快照并只截取 `#evidence-area`。渲染确认超时会记录警告并继续尝试截图，避免永久卡死。

## Evidence 保存位置

首次执行同一案例时：

```text
results/YYYY-MM-DD/TC_DEMO_001/
├── testcase.yaml
├── metadata.json
├── result.json
├── session.log
└── evidence/
    ├── step02_command_complete.png
    ├── step03_command_complete.png
    └── step04_command_complete.png
```

为避免覆盖，同一天重复运行会使用 `TC_DEMO_001_HHMMSS_<session>` 目录。`metadata.json` 不包含密码、Token 或私钥内容。

## 配置

| 环境变量 | 默认值 | 用途 |
|---|---:|---|
| `RTR_PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | Playwright 回访本服务的地址 |
| `RTR_TESTCASE_DIR` | `<project>/testcases` | 案例目录 |
| `RTR_RESULTS_DIR` | `<project>/results` | 结果目录 |
| `RTR_SSH_CONNECT_TIMEOUT` | `15` | SSH 连接超时（秒） |
| `RTR_COMMAND_TIMEOUT` | `300` | 单步命令超时（秒） |
| `RTR_RENDER_ACK_TIMEOUT` | `20` | 前端渲染确认超时（秒） |
| `RTR_BROWSER_CHANNEL` | 未设置 | 可选：`msedge`、`chrome` 等 Playwright 浏览器通道 |
| `RTR_SSH_PASSWORD` | 未设置 | 可选运行时 SSH 密码 |
| `RTR_SSH_AUTO_ADD_HOST_KEY` | `1` | `0` 时严格拒绝未知 host key |

MVP 为便于测试实验室首次连接，默认接受未知 SSH host key，并记录警告。安全要求高的环境应先维护控制机 `known_hosts`，再设置 `RTR_SSH_AUTO_ADD_HOST_KEY=0`。

## 测试与验证

```bash
python -m compileall backend tests
python -m pytest -q
```

完整端到端验收仍需要一台可访问的 SSH 服务器：执行示例案例后核对实时终端、三个自动 PNG、Session Log、metadata 和 result。

## 已知限制

- 单进程、内存会话；重启服务后不能恢复会话，不能使用多个 Uvicorn worker。
- 同一时间每个 Session 只运行一个自动命令；没有多服务器并行与任务调度。
- 交互式全屏程序、`sudo` 密码提示、重启恢复和自动输入密码尚未编排。
- Shell Marker 方案面向常规 POSIX Shell；改变终端行规程、主动关闭 Shell 或输出同一随机 Marker 的命令可能导致该步 ERROR。
- 截图服务为每次证据启动一个无头 Chromium，上量后应改为浏览器池。
- 没有用户系统、权限模型、数据库、自动脱敏、PDF 报告或 AI 判断。

## Roadmap

1. 本地化 xterm 静态资源、SSH host-key 首次确认 UI。
2. 浏览器池、交互步骤状态机、命令输入仲裁和断线重连。
3. `before_after` / `output_contains` Evidence Policy 与脱敏规则。
4. 多目标执行、数据库持久化、认证授权和 CI/Jenkins 接口。
5. 可选 AI Judge、案例辅助生成和 PDF/HTML 汇总报告。
