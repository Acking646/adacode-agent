const $ = (id) => document.getElementById(id);

let cmMode = "rule";
let currentJob = null;
let currentWorkspace = $("workspace").value;
let pollTimer = null;

function commandToList(text) {
  return text.match(/(?:[^\s"]+|"[^"]*")+/g)?.map((item) => item.replace(/^"|"$/g, "")) || [];
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

async function resetDemo() {
  const payload = await api("/api/demo/reset", { method: "POST", body: "{}" });
  currentWorkspace = payload.workspace;
  $("workspace").value = payload.workspace;
  $("task").value = payload.task;
  renderFiles(payload.files || []);
  $("status").textContent = "示例已重置";
  $("patch").textContent = "";
  $("tests").textContent = "";
  $("context").textContent = "";
  $("timeline").className = "timeline-list empty";
  $("timeline").textContent = "等待运行";
  drawActivity([]);
}

async function runAgent() {
  $("runAgent").disabled = true;
  $("status").textContent = "排队中";
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
    token_budget: Number($("tokenBudget").value),
    llm_timeout: 300,
    llm_retries: 5,
  };
  const started = await api("/api/run", { method: "POST", body: JSON.stringify(payload) });
  currentJob = started.job_id;
  $("jobId").textContent = currentJob;
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(fetchJob, 1500);
  fetchJob();
}

async function fetchJob() {
  if (!currentJob) return;
  try {
    const job = await api(`/api/job?id=${encodeURIComponent(currentJob)}`);
    renderJob(job);
    if (job.status === "done" || job.status === "failed") {
      clearInterval(pollTimer);
      $("runAgent").disabled = false;
    }
  } catch (error) {
    $("status").textContent = error.message;
    $("runAgent").disabled = false;
  }
}

function renderJob(job) {
  const trace = job.trace || { actions: [], steps: 0, selected: 0, dropped: 0 };
  $("status").textContent = `${job.status}: ${job.message || ""}`;
  $("steps").textContent = trace.steps || 0;
  $("keepCount").textContent = trace.selected || 0;
  $("dropCount").textContent = trace.dropped || 0;
  $("patchChars").textContent = `${job.patch_chars || 0} chars`;
  $("patch").textContent = job.patch || "";

  const before = job.before ? formatTest("Before", job.before) : "";
  const after = job.after ? formatTest("After", job.after) : "";
  $("tests").textContent = [before, after, job.summary ? `Summary\n${job.summary}` : ""].filter(Boolean).join("\n\n");
  $("context").textContent = renderContext(trace.actions || []);
  renderTimeline(trace.actions || []);
  renderFiles(job.files || []);
  drawActivity(trace.actions || []);
}

function formatTest(title, payload) {
  const status = payload.ok ? "passed" : "failed";
  return `${title}: ${status} (returncode=${payload.returncode})\n${payload.output || ""}`;
}

function renderTimeline(actions) {
  const box = $("timeline");
  if (!actions.length) {
    box.className = "timeline-list empty";
    box.textContent = "等待工具调用";
    return;
  }
  box.className = "timeline-list";
  box.innerHTML = "";
  for (const action of actions) {
    const item = document.createElement("div");
    item.className = `step ${action.ok ? "" : "bad"}`;
    const args = JSON.stringify(action.args || {}, null, 2);
    item.innerHTML = `
      <div class="step-index">${action.step}</div>
      <div>
        <div class="step-title">
          <span>${escapeHtml(action.name || "unknown")}</span>
          <code>${action.ok ? "ok" : "failed"}</code>
        </div>
        <div class="step-output">${escapeHtml(args)}\n\n${escapeHtml(action.output || "")}</div>
      </div>
    `;
    box.appendChild(item);
  }
}

function renderContext(actions) {
  if (!actions.length) return "";
  return actions
    .map((action) => {
      return [
        `Step ${action.step} / ${action.name}`,
        `keep: ${(action.keep || []).join(", ") || "-"}`,
        `drop: ${(action.drop || []).join(", ") || "-"}`,
        `reason: ${action.reason || "-"}`,
      ].join("\n");
    })
    .join("\n\n");
}

function renderFiles(files) {
  const list = $("fileList");
  list.innerHTML = "";
  for (const file of files.slice(0, 48)) {
    const button = document.createElement("button");
    button.textContent = file;
    button.title = file;
    button.addEventListener("click", () => openFile(file));
    list.appendChild(button);
  }
}

async function openFile(path) {
  const workspace = $("workspace").value || currentWorkspace;
  const payload = await api(`/api/file?workspace=${encodeURIComponent(workspace)}&path=${encodeURIComponent(path)}`);
  $("patch").textContent = payload.content;
  activateTab("patch");
}

function drawActivity(actions) {
  const canvas = $("activityCanvas");
  const context = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  context.clearRect(0, 0, w, h);
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, w, h);
  context.strokeStyle = "#d7dee8";
  context.beginPath();
  context.moveTo(0, h - 28);
  context.lineTo(w, h - 28);
  context.stroke();

  const count = Math.max(actions.length, 1);
  const barWidth = Math.max(12, Math.floor((w - 48) / count) - 8);
  actions.forEach((action, index) => {
    const keep = action.keep?.length || 0;
    const drop = action.drop?.length || 0;
    const height = Math.min(64, 18 + keep * 5 + drop * 2);
    const x = 24 + index * (barWidth + 8);
    const y = h - 28 - height;
    context.fillStyle = action.ok ? "#1f7a8c" : "#b24b4b";
    context.fillRect(x, y, barWidth, height);
    context.fillStyle = "#637083";
    context.fillText(String(index + 1), x + 2, h - 10);
  });
}

function activateTab(name) {
  document.querySelectorAll(".tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === name);
  });
  document.querySelectorAll(".tab-body").forEach((body) => {
    body.classList.toggle("hidden", body.id !== name);
  });
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
    document.querySelectorAll(".segmented button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
  });
});

document.querySelectorAll(".tabs button").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});

$("resetDemo").addEventListener("click", resetDemo);
$("runAgent").addEventListener("click", runAgent);

resetDemo();
