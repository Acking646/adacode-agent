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
  $("status").textContent = "Demo reset";
  $("steps").textContent = "0";
  $("keepCount").textContent = "0";
  $("dropCount").textContent = "0";
  $("patchChars").textContent = "0 chars";
  $("patch").textContent = "";
  $("tests").textContent = "";
  $("context").textContent = "";
  $("jobId").textContent = "no job";
  renderThread([]);
}

async function runAgent() {
  $("runAgent").disabled = true;
  $("status").textContent = "Queued";
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
    token_budget: Number($("tokenBudget").value),
    llm_timeout: 300,
    llm_retries: 5,
  };
  const started = await api("/api/run", { method: "POST", body: JSON.stringify(payload) });
  currentJob = started.job_id;
  $("jobId").textContent = currentJob;
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(fetchJob, 1200);
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
  renderThread(trace.actions || [], $("task").value, job);
  renderFiles(job.files || []);
}

function formatTest(title, payload) {
  const status = payload.ok ? "passed" : "failed";
  return `${title}: ${status} (returncode=${payload.returncode})\n${payload.output || ""}`;
}

function renderThread(actions, task = "", job = null) {
  const thread = $("thread");
  thread.innerHTML = "";
  thread.appendChild(message("assistant", "Ready", "I will inspect files, run local commands, edit code, and keep the prompt compact through the context manager."));
  if (task.trim()) {
    thread.appendChild(message("user", "Task", task.trim()));
  }
  if (!actions.length) {
    if (job?.status === "running") {
      thread.appendChild(message("assistant", "Working", "Preparing the next local tool call..."));
    }
    thread.scrollTop = thread.scrollHeight;
    return;
  }

  for (const action of actions) {
    const ok = action.ok ? "ok" : "failed";
    const args = JSON.stringify(action.args || {}, null, 2);
    const body = `
      <div class="tool-args">${escapeHtml(args)}</div>
      <div class="tool-output">${escapeHtml(action.output || "")}</div>
      <div class="tool-meta">
        <span class="pill ${action.ok ? "ok" : "bad"}">${ok}</span>
        <span class="pill">keep ${(action.keep || []).length}</span>
        <span class="pill">drop ${(action.drop || []).length}</span>
      </div>
    `;
    thread.appendChild(message("assistant", `Step ${action.step}: ${action.name}`, body, true));
  }

  if (job?.status === "done") {
    const result = job.after?.ok ? "Tests passed after the patch." : "Run finished; inspect the patch and test output.";
    thread.appendChild(message("assistant", "Result", result));
  } else if (job?.status === "failed") {
    thread.appendChild(message("assistant", "Stopped", job.message || "The run stopped with an error."));
  }
  thread.scrollTop = thread.scrollHeight;
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
  const payload = await api(`/api/file?workspace=${encodeURIComponent(workspace)}&path=${encodeURIComponent(path)}`);
  $("patch").textContent = payload.content;
  activateTab("patch");
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
    $("cmModeLabel").textContent = cmMode === "qwen" ? "Qwen SFT CM" : "Rule CM";
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
