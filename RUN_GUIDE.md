# Remote Test Runner 运行指南

本文说明如何在 Windows 或 Linux 控制机上安装、启动和使用 Remote Test Runner。目标测试机需要开启 SSH，并允许控制机访问。

## 1. 环境要求

- Python 3.11 或更高版本
- 可访问的 Linux/FusionOS SSH 服务器
- Windows、Linux 或 macOS 控制机
- 用于证据截图的 Playwright Chromium，或 Windows 上已安装的 Microsoft Edge

## 2. 获取代码

```bash
git clone https://github.com/gaolyang/remote-test-runner.git
cd remote-test-runner
```

## 3. Windows 安装

在 PowerShell 中执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

如果 Chromium 下载较慢，可以跳过最后一条命令。程序会自动尝试使用 Windows 已安装的 Microsoft Edge；也可以明确指定：

```powershell
$env:RTR_BROWSER_CHANNEL = "msedge"
```

## 4. Linux 安装

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install --with-deps chromium
chmod +x run.sh
```

## 5. 启动服务

Windows：

```powershell
.\run.ps1
```

`run.ps1` 会自动优先使用项目 `.venv`，不强制要求提前激活虚拟环境。

Linux：

```bash
./run.sh
```

也可以直接启动：

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

浏览器访问：

```text
http://127.0.0.1:8000/
```

健康检查：

```text
http://127.0.0.1:8000/health
```

## 6. 页面执行测试

1. 在“测试案例”下拉框选择 YAML 案例。
2. 填写目标服务器 IP 和 SSH 端口，默认端口为 `22`。
3. 填写 SSH 用户名。
4. 使用密码时填写 SSH 密码，并将私钥路径留空。
5. 使用私钥时填写控制机上的私钥绝对路径，例如 `C:\Users\user\.ssh\id_ed25519`。
6. 点击 **Start Test**。
7. 页面将显示实时 SSH Terminal、当前 Step、规则判断和截图状态。

密码只存在于运行内存，认证结束后清除，不会写入 YAML、JSON、日志或截图元数据。

## 7. 自带测试案例

- `TC_DEMO_001`：FusionOS 系统版本、内核和 IP 检查。
- `TC_SYSTEM_002`：当前用户、主机名、系统时间和运行时长检查。
- `TC_RESOURCE_003`：文件系统、内存和块设备检查。
- `TC_NETWORK_004`：网络接口、路由和 TCP 监听端口检查。

测试非 FusionOS 主机时，`TC_DEMO_001` 的系统版本检查可能按预期返回 `FAIL`。这表示 YAML 规则判断生效，并不表示程序故障。

## 8. 新增 YAML 案例

在 `testcases/` 中创建 `.yaml` 文件：

```yaml
version: "1.0"

testcase:
  id: TC_EXAMPLE_001
  name: 示例测试
  description: 检查当前用户

target:
  connection:
    type: ssh

steps:
  - id: 1
    role: verify
    name: 查看当前用户
    action:
      type: shell
      command: whoami
    expected:
      exit_code: 0
      stdout_empty: false
    evidence:
      capture: true
      trigger: command_complete
```

保存后刷新首页，案例将自动出现在下拉框中。

## 9. 查看运行结果

结果保存在：

```text
results/YYYY-MM-DD/CASE_ID/
├── testcase.yaml
├── metadata.json
├── result.json
├── session.log
└── evidence/
```

- `result.json`：每个 Step 的命令、干净 stdout、退出码、状态和规则检查。
- `session.log`：适合人工阅读的完整执行记录。
- `evidence/*.png`：Playwright 截取的 Evidence Area。
- `metadata.json`：目标、用户、开始/结束时间和总状态，不包含密码。

## 10. 停止服务

在运行 Uvicorn 的终端按：

```text
Ctrl+C
```

## 11. 常见问题

### Authentication failed

目标 SSH 服务可访问，但用户名、密码或私钥认证未通过。先在控制机手工确认：

```bash
ssh username@server-ip
```

很多 Linux 系统默认禁止 root 密码登录，建议使用普通测试账户。

### Playwright 提示浏览器不存在

安装 Chromium：

```bash
python -m playwright install chromium
```

Windows 也可以使用系统 Edge：

```powershell
$env:RTR_BROWSER_CHANNEL = "msedge"
.\run.ps1
```

### 页面打开后找不到案例选择框

带 `?session_id=...` 的 URL 是会话详情页。重新访问不带参数的首页：

```text
http://127.0.0.1:8000/
```

## 12. 运行自动测试

```bash
python -m pytest -q
```

当前测试覆盖 YAML 模型、规则判断、Finish Marker、PTY 输出清理、危险命令检测和基础 API。
