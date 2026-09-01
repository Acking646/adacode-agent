const $ = (id) => document.getElementById(id);

let cmMode = "rule";
let currentJob = null;
let currentWorkspace = $("workspace").value;
let pollTimer = null;
let lastRenderKey = "";
let lastFilesKey = "";
let activeArtifact = "";
const artifacts = { patch: "", tests: "", context: "" };

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
      throw new Error("Request timed out. Qwen preview can be skipped if the tunnel or GPU is busy.");
    }
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function setStatus(text, state = "idle") {
  $("status").innerHTML = `<span class="status-dot ${state}"></span>${escapeHtml(text)}`;
  $("loopState").textContent = state;
}

async function resetDemo() {
  const payload = await api("/api/demo/reset", { method: "POST", body: "{}", timeoutMs: 10000 });
  currentWorkspace = payload.workspace;
  $("workspace").value = payload.workspace;
  $("task").value = payload.task;
  lastFilesKey = "";
  renderFiles(payload.files || []);
  $("steps").textContent = "0";
  $("keepCount").textContent = "0";
  $("dropCount").textContent = "0";
  $("patchChars").textContent = "0 chars";
  $("jobId").textContent = "no job";
  artifacts.patch = "";
  artifacts.tests = "";
  artifacts.context = "";
  updateArtifactBadges();
  closeArtifact();
  lastRenderKey = "";
  renderThread([]);
  setStatus("Demo reset", "idle");
}

async function runAgent() {
  $("runAgent").disabled = true;
  setPreviewDisabled(true);
  const budget = Number($("tokenBudget").value);
  setStatus(budget < 800 ? "Queued with tight context" : "Queued", "running");
  lastRenderKey = "";
  renderThread([], $("task").value);
  const payload = {
    workspace: $("workspace").value,
    task: $("task").value,
    test_command: commandToList($("testCommand").value),
    model: $("model").value,
    base_url: $("baseUrl").value || null,
    cm_mode: cmMode,
    cm_base_url: $("cmBaseUrl").value,
    cm_model: $("cmModel").value,
    cm_api_key: "EMPTY",
    max_steps: Number($("maxSteps").value),
    token_budget: budget,
    llm_timeout: 300,
    llm_retries: 5,
  };
  try {
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
  const name = mode === "qwen" ? "Qwen SFT" : "Rule";
  setStatus(`${name} context preview`, "running");
  const payload = {
    workspace: $("workspace").value,
    task: $("task").value,
    cm_mode: mode,
    cm_base_url: $("cmBaseUrl").value,
    cm_model: $("cmModel").value,
    cm_api_key: "EMPTY",
    token_budget: Number($("tokenBudget").value),
  };
  try {
    const timeoutMs = mode === "qwen" ? 45000 : 8000;
    const result = await api("/api/context/preview", { method: "POST", body: JSON.stringify(payload), timeoutMs });
    renderContextPreview(result);
    showArtifact("context");
    setStatus(`${result.manager}: ${result.selected_tokens}/${result.full_tokens} tokens`, "idle");
  } catch (error) {
    setStatus(error.message, "failed");
    artifacts.context = `${name} preview failed\n${error.message}`;
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
  setStatus(`${job.status}: ${job.message || ""}`, state);
  $("steps").textContent = trace.steps || 0;
  $("keepCount").textContent = trace.selected || 0;
  $("dropCount").textContent = trace.dropped || 0;
  $("patchChars").textContent = `${job.patch_chars || 0} chars`;

  artifacts.patch = job.patch || "";
  const before = job.before ? formatTest("Before", job.before) : "";
  const after = job.after ? formatTest("After", job.after) : "";
  artifacts.tests = [before, after, job.summary ? `Summary\n${job.summary}` : ""].filter(Boolean).join("\n\n");
  artifacts.context = renderContext(trace.actions || []);
  updateArtifactBadges(job);
  refreshOpenArtifact();

  const key = `${job.status}:${trace.steps}:${job.patch_chars || 0}:${job.message || ""}`;
  if (key !== lastRenderKey) {
    renderThread(trace.actions || [], $("task").value, job);
    lastRenderKey = key;
  }
  renderFiles(job.files || []);
}

function updateArtifactBadges(job = null) {
  $("patchBadge").textContent = artifacts.patch ? `${artifacts.patch.length} chars` : "empty";
  if (job?.after) {
    $("testsBadge").textContent = job.after.ok ? "passed" : "failed";
  } else {
    $("testsBadge").textContent = artifacts.tests ? "ready" : "waiting";
  }
  $("contextBadge").textContent = artifacts.context ? "ready" : "waiting";
}

function showArtifact(kind) {
  activeArtifact = kind;
  const titles = {
    patch: "Patch",
    tests: "Test output",
    context: "Context selection",
  };
  $("artifactTitle").textContent = titles[kind] || "Artifact";
  $("artifactText").textContent = artifacts[kind] || "No data yet.";
  $("artifactPanel").classList.remove("hidden");
  document.querySelectorAll(".artifact-chip").forEach((button) => {
    button.classList.toggle("active", button.dataset.artifact === kind);
  });
}

function refreshOpenArtifact() {
  if (!activeArtifact || $("artifactPanel").classList.contains("hidden")) return;
  $("artifactText").textContent = artifacts[activeArtifact] || "No data yet.";
}

function closeArtifact() {
  activeArtifact = "";
  $("artifactPanel").classList.add("hidden");
  document.querySelectorAll(".artifact-chip").forEach((button) => button.classList.remove("active"));
}

function formatTest(title, payload) {
  const status = payload.ok ? "passed" : "failed";
  return `${title}: ${status} (returncode=${payload.returncode})\n${payload.output || ""}`;
}

function renderThread(actions, task = "", job = null) {
  const thread = $("thread");
  thread.innerHTML = "";
  thread.appendChild(threadHeading(job));
  thread.appendChild(message("assistant", "Ready", "I will inspect local files, execute tools, edit code, run tests, and compress context before each model call."));
  if (task.trim()) {
    thread.appendChild(message("user", "Task", task.trim()));
  }

  if (!actions.length) {
    if (job?.status === "running") {
      thread.appendChild(message("assistant", "Working", "Preparing the first local tool call."));
    }
    thread.scrollTop = thread.scrollHeight;
    return;
  }

  for (const action of actions) {
    thread.appendChild(stepCard(action));
  }

  if (job?.status === "done") {
    const result = job.after?.ok ? "Tests passed after the patch." : "Run finished; inspect the patch and test output.";
    thread.appendChild(message("assistant", "Result", result));
  } else if (job?.status === "failed") {
    thread.appendChild(message("assistant", "Stopped", job.message || "The run stopped with an error."));
  }
  thread.scrollTop = thread.scrollHeight;
}

function threadHeading(job = null) {
  const wrap = document.createElement("div");
  wrap.className = "thread-heading";
  const elapsed = job?.elapsed_seconds ? `${job.elapsed_seconds}s` : "waiting";
  wrap.innerHTML = `
    <div>
      <span>Timeline</span>
      <strong>agent loop</strong>
    </div>
    <code>${escapeHtml(elapsed)}</code>
  `;
  return wrap;
}

function stepCard(action) {
  const ok = action.ok ? "ok" : "failed";
  const args = JSON.stringify(action.args || {}, null, 2);
  const context = action.context || {};
  const compression = context.compression === undefined ? "-" : `${Math.round(context.compression * 100)}%`;
  const tokens = context.selected_tokens === undefined ? "-" : `${context.selected_tokens}/${context.full_tokens}`;
  const body = `
    <div class="step-grid">
      <div>
        <div class="mini-label">thought</div>
        <p>${escapeHtml(action.thought || "Choose the next local tool call.")}</p>
      </div>
      <div>
        <div class="mini-label">context</div>
        <div class="context-meter">
          <span>${escapeHtml(tokens)}</span>
          <strong>${escapeHtml(compression)}</strong>
        </div>
      </div>
    </div>
    <details open>
      <summary>tool call</summary>
      <pre class="tool-args">${escapeHtml(args)}</pre>
    </details>
    <details>
      <summary>observation</summary>
      <pre class="tool-output">${escapeHtml(action.output || "")}</pre>
    </details>
    <div class="tool-meta">
      <span class="pill ${action.ok ? "ok" : "bad"}">${ok}</span>
      <span class="pill">keep ${(action.keep || []).length}</span>
      <span class="pill">drop ${(action.drop || []).length}</span>
      <span class="pill">${escapeHtml(action.reason || "context selected")}</span>
    </div>
  `;
  return message("assistant", `Step ${action.step}: ${action.name}`, body, true);
}

function renderContextPreview(result) {
  const keep = result.keep || [];
  const drop = result.drop || [];
  $("keepCount").textContent = keep.length;
  $("dropCount").textContent = drop.length;
  artifacts.context = formatContextPreview(result);
  updateArtifactBadges();
  const body = `
    <div class="step-grid">
      <div>
        <div class="mini-label">manager</div>
        <p>${escapeHtml(result.manager)}</p>
      </div>
      <div>
        <div class="mini-label">compression</div>
        <div class="context-meter">
          <span>${result.selected_tokens}/${result.full_tokens}</span>
          <strong>${Math.round(result.compression * 100)}%</strong>
        </div>
      </div>
    </div>
    <div class="tool-meta">
      <span class="pill ok">keep ${keep.length}</span>
      <span class="pill">drop ${drop.length}</span>
      <span class="pill">budget ${result.token_budget}</span>
    </div>
  `;
  renderThread([], $("task").value);
  $("thread").appendChild(message("assistant", `Manual compression: ${result.manager}`, body, true));
  $("thread").scrollTop = $("thread").scrollHeight;
}

function formatContextPreview(result) {
  const keep = result.keep || [];
  const drop = result.drop || [];
  return [
    `${result.manager}`,
    `budget: ${result.token_budget}`,
    `tokens: ${result.selected_tokens}/${result.full_tokens}`,
    `compression: ${result.compression}`,
    `reason: ${result.reason || "-"}`,
    "",
    "KEEP",
    ...keep.map(formatCandidate),
    "",
    "DROP",
    ...drop.map(formatCandidate),
  ].join("\n");
}

function formatCandidate(item) {
  const path = item.metadata?.path ? ` ${item.metadata.path}` : "";
  return `- ${item.id} [${item.kind}]${path} (${item.tokens} tokens)\n${item.content}`;
}

function message(role, title, body, html = false) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "ME" : "AC";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const titleEl = document.createElement("div");
  titleEl.className = "message-title";
  titleEl.innerHTML = `<span>${escapeHtml(title)}</span><code>${role}</code>`;
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
        `Step ${action.step} / ${action.name}`,
        `tokens: ${context.selected_tokens ?? "-"}/${context.full_tokens ?? "-"} compression=${context.compression ?? "-"}`,
        `keep: ${formatIds(action.keep || [], candidateById)}`,
        `drop: ${formatIds(action.drop || [], candidateById)}`,
        `reason: ${action.reason || "-"}`,
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

function renderFiles(files) {
  const list = $("fileList");
  const key = files.join("\n");
  if (key === lastFilesKey) return;
  lastFilesKey = key;
  list.innerHTML = "";
  if (!files.length) {
    const empty = document.createElement("span");
    empty.className = "muted-line";
    empty.textContent = "No files loaded";
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
  $("patchBadge").textContent = "file";
  showArtifact("patch");
  $("artifactTitle").textContent = `File: ${path}`;
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
    $("cmModeLabel").textContent = cmMode === "qwen" ? "Qwen SFT CM" : "Rule CM";
    document.querySelectorAll(".segmented button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
  });
});

document.querySelectorAll(".artifact-chip").forEach((button) => {
  button.addEventListener("click", () => showArtifact(button.dataset.artifact));
});

$("closeArtifact").addEventListener("click", closeArtifact);
$("resetDemo").addEventListener("click", resetDemo);
$("runAgent").addEventListener("click", runAgent);
$("previewRule").addEventListener("click", () => previewContext("rule"));
$("previewQwen").addEventListener("click", () => previewContext("qwen"));

resetDemo();
