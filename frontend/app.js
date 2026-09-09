(function () {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const params = new URLSearchParams(window.location.search);
  const captureMode = params.get("capture") === "1";
  let sessionId = params.get("session_id");
  let socket = null;
  let currentState = null;
  let pendingRiskStep = null;
  let pendingInteractionStep = null;

  function expectedText(expected) {
    if (!expected) return "—";
    const parts = [];
    if (expected.exit_code !== null && expected.exit_code !== undefined) parts.push(`exit code = ${expected.exit_code}`);
    for (const text of expected.stdout_contains || []) parts.push(`stdout contains “${text}”`);
    if (expected.stdout_empty !== null && expected.stdout_empty !== undefined) parts.push(`stdout empty = ${expected.stdout_empty}`);
    return parts.join("; ") || "No rules (PASS when command completes)";
  }

  function setBadge(text, kind) {
    const badge = byId("connection-badge");
    badge.textContent = text;
    badge.dataset.kind = kind || "";
  }

  function renderState(state) {
    currentState = state;
    byId("case-summary").textContent = `${state.case_id} · ${state.case_name}`;
    byId("target-summary").textContent = `${state.username}@${state.target}`;
    byId("status-summary").textContent = state.status;
    const currentNumber = state.current_step_index >= 0 ? state.current_step_index + 1 : 0;
    byId("progress-summary").textContent = `${currentNumber} / ${state.total_steps}`;
    byId("status-message").textContent = state.message || "";
    byId("evidence-case-id").textContent = state.case_id;
    byId("evidence-case-name").textContent = state.case_name;
    byId("evidence-target").textContent = state.target;
    byId("evidence-time").textContent = new Date().toLocaleString("zh-CN", { hour12: false });

    const step = state.current_step;
    const latest = state.step_results && state.step_results.length ? state.step_results[state.step_results.length - 1] : null;
    byId("evidence-step").textContent = step ? `${step.id}: ${step.name}` : "—";
    byId("evidence-expected").textContent = step ? expectedText(step.expected) : "—";
    byId("evidence-result").textContent = latest ? latest.status : state.status;
    byId("evidence-result").dataset.status = latest ? latest.status : state.status;
    if (step && step.interaction && latest && latest.status === "WAITING_FOR_OPERATOR") {
      pendingInteractionStep = String(step.id);
      byId("interaction-message").textContent = step.interaction.instructions;
      byId("interaction-bar").classList.remove("hidden");
      byId("interaction-button").disabled = false;
    }

    const list = byId("step-list");
    list.replaceChildren();
    for (const item of state.steps || []) {
      const li = document.createElement("li");
      li.dataset.status = item.status;
      li.textContent = `Step ${item.id} · ${item.name}`;
      list.appendChild(li);
    }
  }

  async function api(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try { message = (await response.json()).detail || message; } catch (_) { /* no JSON */ }
      throw new Error(message);
    }
    return response.json();
  }

  async function loadCases() {
    const cases = await api("/api/cases", { cache: "no-store" });
    const select = byId("testcase");
    select.replaceChildren();
    for (const item of cases) {
      const option = document.createElement("option");
      option.value = item.filename;
      option.disabled = !item.valid;
      option.textContent = item.valid ? `${item.id} — ${item.name} (${item.step_count} steps)` : `${item.filename} — YAML 无效`;
      select.appendChild(option);
    }
    if (!cases.some((item) => item.valid)) byId("form-error").textContent = "testcases 目录中没有有效案例。";
  }

  async function importCases() {
    const input = byId("case-file");
    const file = input.files && input.files[0];
    if (!file) {
      byId("import-message").textContent = "请先选择 .xlsx、.xlsm 或 .csv 文件。";
      return;
    }
    const button = byId("import-button");
    const form = new FormData();
    form.append("file", file);
    form.append("overwrite", byId("overwrite-cases").checked ? "true" : "false");
    button.disabled = true;
    byId("import-message").dataset.kind = "working";
    byId("import-message").textContent = "正在解析并生成 YAML…";
    try {
      const result = await api("/api/cases/import", { method: "POST", body: form });
      const stepCount = result.cases.reduce((sum, item) => sum + item.step_count, 0);
      const updateText = result.updated ? `，更新 ${result.updated} 个（原文件已备份）` : "";
      byId("import-message").dataset.kind = "success";
      byId("import-message").textContent = `导入成功：${result.imported} 个用例、${stepCount} 个步骤${updateText}。`;
      await loadCases();
      const first = result.cases[0];
      if (first) byId("testcase").value = first.filename;
      input.value = "";
    } catch (error) {
      byId("import-message").dataset.kind = "error";
      byId("import-message").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  function connectWebSocket() {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${location.host}/ws/terminal/${sessionId}`);
    setBadge("连接中", "working");
    socket.addEventListener("open", () => {
      setBadge("已连接", "ok");
      window.RTRTerminal.focus();
    });
    socket.addEventListener("close", () => setBadge("连接已关闭", "closed"));
    socket.addEventListener("error", () => setBadge("连接错误", "error"));
    socket.addEventListener("message", async (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "terminal_output") {
        await window.RTRTerminal.write(message.data);
      } else if (message.type === "snapshot") {
        renderState(message.state);
        if (message.state.transcript) await window.RTRTerminal.write(message.state.transcript);
      } else if (message.state) {
        renderState(message.state);
      }
      if (message.type === "manual_confirm_required") {
        pendingRiskStep = message.step_id;
        byId("confirm-button").disabled = false;
        byId("action-message").textContent = `高危命令：${message.risks.join(", ")}。请人工确认。`;
      }
      if (message.type === "interaction_required") {
        pendingInteractionStep = message.step_id;
        byId("interaction-message").textContent = message.instructions || "请在终端中完成交互。";
        byId("interaction-bar").classList.remove("hidden");
        byId("interaction-button").disabled = false;
        window.RTRTerminal.focus();
      }
      if (message.type === "interaction_completed") {
        pendingInteractionStep = null;
        byId("interaction-bar").classList.add("hidden");
      }
      if (message.type === "step_complete" && message.capture_requested) {
        await window.RTRTerminal.rendered();
        socket.send(JSON.stringify({ type: "terminal_rendered", event_id: message.event_id }));
      }
      if (message.type === "evidence_captured") byId("action-message").textContent = `Evidence: ${message.path}`;
      if (message.type === "evidence_error" || message.type === "error") byId("action-message").textContent = message.message;
    });
  }

  async function start(event) {
    event.preventDefault();
    byId("form-error").textContent = "";
    byId("start-button").disabled = true;
    const body = {
      testcase: byId("testcase").value,
      host: byId("host").value,
      port: Number(byId("port").value),
      username: byId("username").value,
      password: byId("password").value || null,
      key_filename: byId("key-filename").value || null
    };
    try {
      const result = await api("/api/sessions", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
      });
      sessionId = result.session_id;
      byId("password").value = "";
      history.replaceState({}, "", `/?session_id=${encodeURIComponent(sessionId)}`);
      byId("start-panel").classList.add("hidden");
      byId("runner-panel").classList.remove("hidden");
      window.RTRTerminal.fit();
      connectWebSocket();
    } catch (error) {
      byId("form-error").textContent = error.message;
      byId("start-button").disabled = false;
    }
  }

  async function prepareCapturePage() {
    byId("start-panel").classList.add("hidden");
    byId("runner-panel").classList.remove("hidden");
    byId("controls").classList.add("hidden");
    byId("connection-badge").classList.add("hidden");
    document.body.classList.add("capture-mode");
    const state = await api(`/api/sessions/${encodeURIComponent(sessionId)}`);
    renderState(state);
    await window.RTRTerminal.write(state.transcript || "");
    await window.RTRTerminal.rendered();
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    document.body.dataset.evidenceReady = "true";
  }

  window.RTRTerminal.init(
    (data) => socket && socket.readyState === WebSocket.OPEN && socket.send(JSON.stringify({ type: "input", data })),
    (columns, rows) => socket && socket.readyState === WebSocket.OPEN && socket.send(JSON.stringify({ type: "resize", columns, rows }))
  );

  byId("start-form").addEventListener("submit", start);
  byId("import-button").addEventListener("click", importCases);
  byId("capture-button").addEventListener("click", async () => {
    try {
      byId("action-message").textContent = "正在截图…";
      const result = await api(`/api/sessions/${sessionId}/capture`, { method: "POST" });
      byId("action-message").textContent = `Evidence: ${result.path}`;
    } catch (error) { byId("action-message").textContent = error.message; }
  });
  byId("confirm-button").addEventListener("click", async () => {
    if (!pendingRiskStep) return;
    try {
      await api(`/api/sessions/${sessionId}/confirm/${encodeURIComponent(pendingRiskStep)}`, { method: "POST" });
      pendingRiskStep = null;
      byId("confirm-button").disabled = true;
      byId("action-message").textContent = "已确认，继续执行。";
    } catch (error) { byId("action-message").textContent = error.message; }
  });
  byId("interaction-button").addEventListener("click", async () => {
    if (!pendingInteractionStep) return;
    const stepId = pendingInteractionStep;
    byId("interaction-button").disabled = true;
    try {
      await api(`/api/sessions/${sessionId}/interaction/${encodeURIComponent(stepId)}/complete`, { method: "POST" });
      pendingInteractionStep = null;
      byId("interaction-bar").classList.add("hidden");
      byId("action-message").textContent = "交互已确认，继续执行。";
    } catch (error) {
      byId("interaction-button").disabled = false;
      byId("action-message").textContent = error.message;
    }
  });
  byId("abort-button").addEventListener("click", async () => {
    if (!window.confirm("确定终止当前测试？")) return;
    try { await api(`/api/sessions/${sessionId}/abort`, { method: "POST" }); }
    catch (error) { byId("action-message").textContent = error.message; }
  });

  if (captureMode && sessionId) {
    prepareCapturePage().catch((error) => {
      byId("action-message").textContent = error.message;
      document.body.dataset.evidenceReady = "error";
    });
  } else if (sessionId) {
    byId("start-panel").classList.add("hidden");
    byId("runner-panel").classList.remove("hidden");
    connectWebSocket();
  } else {
    loadCases().catch((error) => { byId("form-error").textContent = error.message; });
  }
})();
