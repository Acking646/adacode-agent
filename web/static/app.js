const $ = (id) => document.getElementById(id);

let cmMode = "rule";
let currentJob = null;
let currentWorkspace = $("workspace").value;
let currentTask = "";
let pollTimer = null;
let lastRenderKey = "";
let lastFilesKey = "";
let activeArtifact = "";
const artifacts = { patch: "", tests: "", context: "" };
const toolLabels = {
  list_files: "列出文件",
  read_file: "读取文件",
  write_file: "写入文件",
  edit_file: "修改文件",
  run_command: "执行命令",
  run_tests: "运行测试",
  finish: "结束任务",
};
const jobLabels = {
  queued: "已排队",
  running: "运行中",
  done: "已完成",
  failed: "运行失败",
};
const messageLabels = {
  Queued: "等待执行",
  "Preparing workspace": "准备工作区并运行初始测试",
  "Running agent": "调用模型并执行本地工具",
  Completed: "任务结束",
  "Tests still failing": "任务结束，但测试仍未通过",
};
const stateLabels = { idle: "就绪", running: "运行中", failed: "失败" };

function commandToList(text) {
  return text.match(/(?:[^\s"]+|"[^"]*")+/g)?.map((item) => item.replace(/^"|"$/g, "")) || [];
}

async function api(path, options = {}) {
  const { timeoutMs = 0, ...fetchOptions } = options;
  const controller = timeoutMs ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      signal: controller?.signal,
      ...fetchOptions,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || response.statusText);
    return payload;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("请求超时。若正在预览 Qwen，请检查 SSH 隧道和远程 GPU 服务。");
    }
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function setStatus(text, state = "idle") {
  $("status").innerHTML = `<span class="status-dot ${state}"></span>${escapeHtml(text)}`;
  const loopState = $("loopState");
  if (loopState) loopState.textContent = stateLabels[state] || state;
}

function reportUiError(error) {
  const message = error instanceof Error ? error.message : String(error);
  setStatus(`界面错误：${message}`, "failed");
  console.error(error);
}

function bindAsync(id, handler) {
  $(id).addEventListener("click", () => {
    Promise.resolve(handler()).catch(reportUiError);
  });
}

async function resetDemo() {
  $("resetDemo").disabled = true;
  try {
    const payload = await api("/api/demo/reset", { method: "POST", body: "{}", timeoutMs: 10000 });
    currentWorkspace = payload.workspace;
    currentTask = payload.task;
    $("workspace").value = payload.workspace;
    $("task").value = payload.task;
    lastFilesKey = "";
    renderFiles(payload.files || []);
    $("steps").textContent = "0";
    $("keepCount").textContent = "0";
    $("dropCount").textContent = "0";
    $("patchChars").textContent = "0 字符";
    $("jobId").textContent = "尚未运行";
    artifacts.patch = "";
    artifacts.tests = "";
    artifacts.context = "";
    updateArtifactBadges();
    closeArtifact();
    lastRenderKey = "";
    renderThread([]);
    setStatus("演示工作区已重置", "idle");
  } finally {
    $("resetDemo").disabled = false;
  }
}

async function runAgent() {
  $("runAgent").disabled = true;
  setPreviewDisabled(true);
  try {
    const submittedTask = $("task").value.trim();
    if (!submittedTask) throw new Error("请输入需要执行的编程任务。");
    currentTask = submittedTask;
    const budget = Math.max(800, Number($("tokenBudget").value) || 1600);
    $("tokenBudget").value = String(budget);
    setStatus("任务已提交", "running");
    lastRenderKey = "";
    renderThread([], currentTask);
    const payload = {
      workspace: $("workspace").value,
      task: currentTask,
      test_command: commandToList($("testCommand").value),
      model: $("model").value,
      base_url: $("baseUrl").value || null,
      cm_mode: cmMode,
      cm_base_url: $("cmBaseUrl").value,
      cm_model: $("cmModel").value,
      cm_api_key: "EMPTY",
      cm_timeout: 25,
      cm_retries: 1,
      cm_max_tokens: 768,
      max_steps: Number($("maxSteps").value),
      token_budget: budget,
      llm_timeout: 90,
      llm_retries: 1,
    };
    const started = await api("/api/run", { method: "POST", body: JSON.stringify(payload), timeoutMs: 10000 });
    currentJob = started.job_id;
    $("jobId").textContent = currentJob;
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(fetchJob, 3000);
    fetchJob();
  } catch (error) {
    setStatus(error.message, "failed");
    $("runAgent").disabled = false;
    setPreviewDisabled(false);
  }
}

async function previewContext(mode) {
  setPreviewDisabled(true);
  const name = mode === "qwen" ? "Qwen SFT" : "规则模型";
  try {
    const previewTask = $("task").value.trim() || currentTask;
    if (!previewTask) throw new Error("请先输入任务描述。");
    setStatus(`正在生成${name}压缩预览`, "running");
    const payload = {
      workspace: $("workspace").value,
      task: previewTask,
      cm_mode: mode,
      cm_base_url: $("cmBaseUrl").value,
      cm_model: $("cmModel").value,
      cm_api_key: "EMPTY",
      cm_timeout: 25,
      cm_retries: 1,
      cm_max_tokens: 768,
      token_budget: Number($("previewBudget").value),
    };
    const timeoutMs = mode === "qwen" ? 32000 : 8000;
    const result = await api("/api/context/preview", { method: "POST", body: JSON.stringify(payload), timeoutMs });
    renderContextPreview(result, previewTask);
    setStatus(`${result.manager}：保留 ${result.selected_tokens}/${result.full_tokens} tokens`, "idle");
  } catch (error) {
    setStatus(error.message, "failed");
    artifacts.context = `${name}预览失败\n${error.message}`;
    updateArtifactBadges();
    showArtifact("context");
  } finally {
    setPreviewDisabled(false);
  }
}

function setPreviewDisabled(value) {
  $("previewRule").disabled = value;
  $("previewQwen").disabled = value;
}

async function fetchJob() {
  if (!currentJob) return;
  try {
    const job = await api(`/api/job?id=${encodeURIComponent(currentJob)}`, { timeoutMs: 12000 });
    renderJob(job);
    if (job.status === "done" || job.status === "failed") {
      clearInterval(pollTimer);
      $("runAgent").disabled = false;
      setPreviewDisabled(false);
    }
  } catch (error) {
    setStatus(error.message, "failed");
    $("runAgent").disabled = false;
    setPreviewDisabled(false);
  }
}

function renderJob(job) {
  const trace = job.trace || { actions: [], steps: 0, selected: 0, dropped: 0 };
  const state = job.status === "failed" ? "failed" : job.status === "running" ? "running" : "idle";
  const statusText = jobLabels[job.status] || job.status;
  const messageText = messageLabels[job.message] || job.message || "";
  setStatus(`${statusText}${messageText ? `：${messageText}` : ""}`, state);
  $("steps").textContent = trace.steps || 0;
  $("keepCount").textContent = trace.selected || 0;
  $("dropCount").textContent = trace.dropped || 0;
  $("patchChars").textContent = `${job.patch_chars || 0} 字符`;

  artifacts.patch = job.patch || "";
  const before = job.before ? formatTest("修改前", job.before) : "";
  const after = job.after ? formatTest("修改后", job.after) : "";
  artifacts.tests = [before, after, job.summary ? `任务总结\n${job.summary}` : ""].filter(Boolean).join("\n\n");
  artifacts.context = renderContext(trace.actions || []);
  updateArtifactBadges(job);
  refreshOpenArtifact();

  const key = `${job.status}:${trace.steps}:${job.patch_chars || 0}:${job.message || ""}`;
  if (key !== lastRenderKey) {
    renderThread(trace.actions || [], currentTask, job);
    lastRenderKey = key;
  }
  renderFiles(job.files || []);
}

function updateArtifactBadges(job = null) {
  $("patchBadge").textContent = artifacts.patch ? `${artifacts.patch.length} 字符` : "暂无";
  if (job?.after) {
    $("testsBadge").textContent = job.after.ok ? "通过" : "失败";
  } else {
    $("testsBadge").textContent = artifacts.tests ? "可查看" : "等待";
  }
  $("contextBadge").textContent = artifacts.context ? "可查看" : "等待";
}

function showArtifact(kind) {
  activeArtifact = kind;
  const titles = {
    patch: "代码补丁",
    tests: "测试输出",
    context: "上下文选择",
  };
  $("artifactTitle").textContent = titles[kind] || "运行产物";
  $("artifactText").textContent = artifacts[kind] || "暂无数据。";
  $("artifactPanel").classList.remove("hidden");
  document.querySelectorAll(".artifact-chip").forEach((button) => {
    button.classList.toggle("active", button.dataset.artifact === kind);
  });
}

function refreshOpenArtifact() {
  if (!activeArtifact || $("artifactPanel").classList.contains("hidden")) return;
  $("artifactText").textContent = artifacts[activeArtifact] || "暂无数据。";
}

function closeArtifact() {
  activeArtifact = "";
  $("artifactPanel").classList.add("hidden");
  document.querySelectorAll(".artifact-chip").forEach((button) => button.classList.remove("active"));
}

function formatTest(title, payload) {
  const status = payload.ok ? "通过" : "失败";
  return `${title}：${status}（退出码=${payload.returncode}）\n${payload.output || ""}`;
}

function renderThread(actions, task = "", job = null) {
  const thread = $("thread");
  const previousTop = thread.scrollTop;
  const shouldFollow = !activeArtifact && thread.scrollHeight - thread.scrollTop - thread.clientHeight < 120;
  thread.innerHTML = "";
  thread.appendChild(threadHeading(job));
  thread.appendChild(message("assistant", "准备就绪", "我会读取本地文件、执行工具、修改代码、运行测试，并在每次模型调用前压缩上下文。"));
  if (task.trim()) {
    thread.appendChild(message("user", "编程任务", task.trim()));
  }

  if (!actions.length) {
    if (job?.status === "running") {
      thread.appendChild(message("assistant", "正在处理", "正在准备第一次本地工具调用。"));
    }
    restoreThreadScroll(thread, shouldFollow, previousTop);
    return;
  }

  for (const action of actions) {
    thread.appendChild(stepCard(action));
  }

  if (job?.status === "done") {
    const result = job.after?.ok ? "代码修改完成，测试已经通过。" : "任务已停止，请查看测试输出和执行时间线。";
    thread.appendChild(message("assistant", "运行结果", result));
  } else if (job?.status === "failed") {
    thread.appendChild(message("assistant", "异常停止", job.message || "运行过程中发生错误。"));
  }
  restoreThreadScroll(thread, shouldFollow, previousTop);
}

function restoreThreadScroll(thread, shouldFollow, previousTop) {
  if (shouldFollow) {
    thread.scrollTop = thread.scrollHeight;
  } else {
    thread.scrollTop = previousTop;
  }
}

function threadHeading(job = null) {
  const wrap = document.createElement("div");
  wrap.className = "thread-heading";
  const elapsed = job?.elapsed_seconds ? `${job.elapsed_seconds} 秒` : "等待";
  wrap.innerHTML = `
    <div>
      <span>执行时间线</span>
      <strong>智能体循环</strong>
    </div>
    <code id="loopState">${escapeHtml(elapsed)}</code>
  `;
  return wrap;
}

function stepCard(action) {
  const ok = action.ok ? "成功" : "失败";
  const args = JSON.stringify(action.args || {}, null, 2);
  const context = action.context || {};
  const compression = context.compression === undefined ? "-" : `${Math.round(context.compression * 100)}%`;
  const tokens = context.selected_tokens === undefined ? "-" : `${context.selected_tokens}/${context.full_tokens}`;
  const body = `
    <div class="step-grid">
      <div>
        <div class="mini-label">当前判断</div>
        <p>${escapeHtml(action.thought || "选择下一项本地工具操作。")}</p>
      </div>
      <div>
        <div class="mini-label">上下文</div>
        <div class="context-meter">
          <span>${escapeHtml(tokens)}</span>
          <strong>${escapeHtml(compression)}</strong>
        </div>
      </div>
    </div>
    <details open>
      <summary>工具参数</summary>
      <pre class="tool-args">${escapeHtml(args)}</pre>
    </details>
    <details>
      <summary>执行结果</summary>
      <pre class="tool-output">${escapeHtml(action.output || "")}</pre>
    </details>
    <div class="tool-meta">
      <span class="pill ${action.ok ? "ok" : "bad"}">${ok}</span>
      <span class="pill">保留 ${(action.keep || []).length}</span>
      <span class="pill">丢弃 ${(action.drop || []).length}</span>
      <span class="pill">${escapeHtml(localizeReason(action.reason || "已完成上下文选择"))}</span>
    </div>
  `;
  const label = toolLabels[action.name] || action.name;
  return message("assistant", `步骤 ${action.step}：${label}`, body, true);
}

function renderContextPreview(result, task) {
  const keep = result.keep || [];
  const drop = result.drop || [];
  $("keepCount").textContent = keep.length;
  $("dropCount").textContent = drop.length;
  artifacts.context = formatContextPreview(result);
  updateArtifactBadges();
  const body = `
    <div class="step-grid">
      <div>
        <div class="mini-label">管理器</div>
        <p>${escapeHtml(result.manager)}</p>
      </div>
      <div>
        <div class="mini-label">压缩率</div>
        <div class="context-meter">
          <span>${result.selected_tokens}/${result.full_tokens}</span>
          <strong>${Math.round(result.compression * 100)}%</strong>
        </div>
      </div>
    </div>
    <div class="tool-meta">
      <span class="pill ok">保留 ${keep.length}</span>
      <span class="pill">丢弃 ${drop.length}</span>
      <span class="pill">预算 ${result.token_budget}</span>
    </div>
  `;
  closeArtifact();
  renderThread([], task);
  $("thread").appendChild(message("assistant", `手动压缩预览：${result.manager}`, body, true));
  $("thread").scrollTop = $("thread").scrollHeight;
}

function formatContextPreview(result) {
  const keep = result.keep || [];
  const drop = result.drop || [];
  return [
    `${result.manager}`,
    `预算：${result.token_budget}`,
    `Token：${result.selected_tokens}/${result.full_tokens}`,
    `压缩率：${result.compression}`,
    `原因：${localizeReason(result.reason || "-")}`,
    "",
    "保留内容",
    ...keep.map(formatCandidate),
    "",
    "丢弃内容",
    ...drop.map(formatCandidate),
  ].join("\n");
}

function formatCandidate(item) {
  const path = item.metadata?.path ? ` ${item.metadata.path}` : "";
  return `- ${item.id} [${item.kind}]${path}（${item.tokens} tokens）\n${item.content}`;
}

function message(role, title, body, html = false) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "我" : "AC";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const titleEl = document.createElement("div");
  titleEl.className = "message-title";
  titleEl.innerHTML = `<span>${escapeHtml(title)}</span><code>${role === "user" ? "用户" : "智能体"}</code>`;
  const content = document.createElement("div");
  if (html) {
    content.innerHTML = body;
  } else {
    const paragraph = document.createElement("p");
    paragraph.textContent = body;
    content.appendChild(paragraph);
  }
  bubble.appendChild(titleEl);
  bubble.appendChild(content);
  article.appendChild(avatar);
  article.appendChild(bubble);
  return article;
}

function renderContext(actions) {
  if (!actions.length) return "";
  return actions
    .map((action) => {
      const context = action.context || {};
      const candidateById = new Map((context.candidates || []).map((item) => [item.id, item]));
      return [
        `步骤 ${action.step} / ${toolLabels[action.name] || action.name}`,
        `Token：${context.selected_tokens ?? "-"}/${context.full_tokens ?? "-"}，压缩率=${context.compression ?? "-"}`,
        `保留：${formatIds(action.keep || [], candidateById)}`,
        `丢弃：${formatIds(action.drop || [], candidateById)}`,
        `原因：${localizeReason(action.reason || "-")}`,
      ].join("\n");
    })
    .join("\n\n");
}

function formatIds(ids, candidateById) {
  if (!ids.length) return "-";
  return ids
    .map((id) => {
      const candidate = candidateById.get(id);
      if (!candidate) return id;
      const path = candidate.metadata?.path ? ` ${candidate.metadata.path}` : "";
      return `${id}[${candidate.kind}${path}, ${candidate.tokens}t]`;
    })
    .join(", ");
}

function localizeReason(reason) {
  return String(reason)
    .replace("Rule-based reward scoring selected compact context.", "规则奖励评分选择了紧凑上下文。")
    .replace("SFT manager selected context.", "SFT 模型完成了上下文选择。")
    .replace("Context manager failed", "上下文管理器失败")
    .replace("fell back to rule scoring", "已回退到规则评分");
}

function renderFiles(files) {
  const list = $("fileList");
  const key = files.join("\n");
  if (key === lastFilesKey) return;
  lastFilesKey = key;
  list.innerHTML = "";
  if (!files.length) {
    const empty = document.createElement("span");
    empty.className = "muted-line";
    empty.textContent = "尚未载入文件";
    list.appendChild(empty);
    return;
  }
  for (const file of files.slice(0, 80)) {
    const button = document.createElement("button");
    button.textContent = file;
    button.title = file;
    button.addEventListener("click", () => openFile(file));
    list.appendChild(button);
  }
}

async function openFile(path) {
  const workspace = $("workspace").value || currentWorkspace;
  const payload = await api(`/api/file?workspace=${encodeURIComponent(workspace)}&path=${encodeURIComponent(path)}`, { timeoutMs: 8000 });
  artifacts.patch = payload.content;
  $("patchBadge").textContent = "文件";
  showArtifact("patch");
  $("artifactTitle").textContent = `文件：${path}`;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

document.querySelectorAll(".segmented button").forEach((button) => {
  button.addEventListener("click", () => {
    cmMode = button.dataset.mode;
    $("cmModeLabel").textContent = cmMode === "qwen" ? "Qwen SFT 上下文" : "规则上下文";
    document.querySelectorAll(".segmented button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
  });
});

document.querySelectorAll(".artifact-chip").forEach((button) => {
  button.addEventListener("click", () => {
    if (activeArtifact === button.dataset.artifact && !$("artifactPanel").classList.contains("hidden")) {
      closeArtifact();
    } else {
      showArtifact(button.dataset.artifact);
    }
  });
});

$("closeArtifact").addEventListener("click", closeArtifact);
bindAsync("resetDemo", resetDemo);
bindAsync("runAgent", runAgent);
bindAsync("previewRule", () => previewContext("rule"));
bindAsync("previewQwen", () => previewContext("qwen"));

window.addEventListener("error", (event) => reportUiError(event.error || event.message));
window.addEventListener("unhandledrejection", (event) => reportUiError(event.reason));

resetDemo().catch(reportUiError);
