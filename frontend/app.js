const API_BASE = "https://tazzacode-ai.onrender.com";

let sessionId = null;
let currentState = {};

const chatWindow = document.getElementById("chatWindow");
const welcomeScreen = document.getElementById("welcomeScreen");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const fileInput = document.getElementById("fileInput");
const datasetCard = document.getElementById("datasetCard");
const downloadArea = document.getElementById("downloadArea");
const loadingOverlay = document.getElementById("loadingOverlay");

const cleanBtn = document.getElementById("cleanBtn");
const edaBtn = document.getElementById("edaBtn");
const sqlBtn = document.getElementById("sqlBtn");
const emailBtn = document.getElementById("emailBtn");

const ACTIONS_BY_TYPE = {
  missing_values: ["skip", "fill_mean", "fill_median", "fill_mode", "drop_rows"],
  duplicate_rows: ["skip", "drop_duplicates"],
  type_mismatch: ["skip", "convert_to_numeric", "convert_to_datetime"],
  invalid_values: ["skip", "drop_rows", "set_null", "clip_to_zero", "absolute_value", "fill_median"],
  categorical_inconsistency: ["skip", "normalize"],
};

// ---------- Helpers ----------
function showLoading(show) {
  loadingOverlay.classList.toggle("hidden", !show);
}

function addMessage(role, html) {
  welcomeScreen.style.display = "none";
  const msg = document.createElement("div");
  msg.className = `msg ${role}`;
  msg.innerHTML = `
    <div class="msg-avatar">${role === "user" ? "🧑" : "🤖"}</div>
    <div class="msg-bubble">${html}</div>
  `;
  chatWindow.appendChild(msg);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return msg.querySelector(".msg-bubble");
}

function mergeState(newState) {
  if (newState) currentState = { ...currentState, ...newState };
  updateSidebar();
}

function updateSidebar() {
  document.getElementById("progressClean").classList.toggle("done", !!currentState.cleaned_file_path);
  document.getElementById("progressEDA").classList.toggle("done", !!currentState.eda_results);
  document.getElementById("progressReport").classList.toggle("done", !!currentState.report_file_path);

  downloadArea.innerHTML = "";
  if (currentState.cleaned_file_path) {
    downloadArea.innerHTML += `<a href="${API_BASE}/download/${sessionId}/cleaned" download>Download cleaned CSV</a>`;
  }
  if (currentState.report_file_path) {
    downloadArea.innerHTML += `<a href="${API_BASE}/download/${sessionId}/report" download>Download report (.docx)</a>`;
  }
  if (!downloadArea.innerHTML) {
    downloadArea.innerHTML = `<p class="muted">Nothing available yet.</p>`;
  }
}

function enableAllActions() {
  chatInput.disabled = false;
  sendBtn.disabled = false;
  chatInput.placeholder = "Ask anything about your dataset...";
  cleanBtn.disabled = false;
  edaBtn.disabled = false;
  sqlBtn.disabled = false;
  emailBtn.disabled = false;
}

// ---------- API calls ----------
async function callUpload(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: formData });
  return res.json();
}

async function callClean() {
  const res = await fetch(`${API_BASE}/clean/${sessionId}`, { method: "POST" });
  return res.json();
}

async function callCleanReview(payload) {
  const res = await fetch(`${API_BASE}/clean/review/${sessionId}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  });
  return res.json();
}

async function callGenerateReport() {
  const res = await fetch(`${API_BASE}/generate-report/${sessionId}`, { method: "POST" });
  return res.json();
}

async function callChat(question) {
  const res = await fetch(`${API_BASE}/chat/${sessionId}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question })
  });
  return res.json();
}

async function callEmail(recipient) {
  const res = await fetch(`${API_BASE}/email/${sessionId}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email_id: recipient })
  });
  return res.json();
}

// ---------- Renderers ----------
function renderInitialChoice() {
  const bubble = addMessage("assistant", `
    <div class="card">
      <p>Your file is uploaded. What would you like to do?</p>
      <div class="btn-row">
        <button class="btn-outline" data-choice="clean">🧹 Clean Dataset</button>
        <button class="btn-outline" data-choice="skip">⏩ Skip Cleaning & Generate EDA</button>
        <button class="btn-outline" data-choice="ask">💬 Ask Questions Directly</button>
      </div>
      <p class="muted">Tip: cleaning first usually gives more accurate answers, but you can always ask questions right away.</p>
    </div>
  `);

  bubble.querySelectorAll("button").forEach(btn => {
    btn.onclick = async () => {
      const choice = btn.dataset.choice;
      addMessage("user", btn.textContent.trim());
      if (choice === "clean") {
        startCleaning();
      } else if (choice === "skip") {
        showLoading(true);
        const result = await callGenerateReport();
        showLoading(false);
        mergeState(result);
        const summary = result.report_sections ? result.report_sections.plain_summary : "Your EDA report is ready.";
        addMessage("assistant", summary);
      } else {
        chatInput.focus();
      }
    };
  });
}

async function startCleaning() {
  showLoading(true);
  const data = await callClean();
  showLoading(false);
  const interrupt = data.interrupt ? data.interrupt[0] : null;
  if (interrupt && interrupt.type === "approval") {
    renderApproval(interrupt);
  }
}

function renderApproval(interrupt) {
  const issues = interrupt.cleaning_issues;
  const rowsHtml = issues.map(issue => {
    const opts = ACTIONS_BY_TYPE[issue.issue_type] || ["skip"];
    const optionsHtml = opts.map(o =>
      `<option value="${o}" ${o === issue.suggested_action ? "selected" : ""}>${o}</option>`
    ).join("");
    return `
      <div class="issue-row" data-id="${issue.id}">
        <span><b>${issue.column || "Dataset"}</b> — ${issue.description}</span>
        <select>${optionsHtml}</select>
      </div>
    `;
  }).join("");

  const bubble = addMessage("assistant", `
    <div class="card">
      <p>Here's what I found. Choose an action for each issue:</p>
      ${rowsHtml}
      <div class="btn-row"><button class="btn-outline" id="submitCleaning">Submit</button></div>
    </div>
  `);

  bubble.querySelector("#submitCleaning").onclick = async () => {
    const decisions = {};
    bubble.querySelectorAll(".issue-row").forEach(row => {
      const val = row.querySelector("select").value;
      if (val !== "skip") decisions[row.dataset.id] = val;
    });
    addMessage("user", `Applied ${Object.keys(decisions).length} cleaning action(s)`);
    showLoading(true);
    const data = await callCleanReview({ decisions });
    showLoading(false);
    mergeState(data.state);
    addMessage("assistant", "Cleaning applied. You can now generate an EDA report or ask questions.");
  };
}

function renderTable(supportingData) {
  if (!supportingData) return "";

  // Direct mode: {success, result: [...]}
  if (supportingData.result && Array.isArray(supportingData.result) && supportingData.result.length) {
    const cols = Object.keys(supportingData.result[0]);
    return `<table class="result-table"><tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr>` +
      supportingData.result.map(row => `<tr>${cols.map(c => `<td>${row[c]}</td>`).join("")}</tr>`).join("") +
      `</table>`;
  }

  // Investigative mode: array of {purpose, sql, result}
  if (Array.isArray(supportingData)) {
    return supportingData.map(sub => {
      const r = sub.result;
      if (!r || !r.result || !r.result.length) return "";
      const cols = Object.keys(r.result[0]);
      return `<p class="muted" style="margin-top:8px;"><b>${sub.purpose}</b></p>` +
        `<table class="result-table"><tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr>` +
        r.result.map(row => `<tr>${cols.map(c => `<td>${row[c]}</td>`).join("")}</tr>`).join("") +
        `</table>`;
    }).join("");
  }

  return "";
}

function renderEmailForm() {
  const bubble = addMessage("assistant", `
    <div class="card">
      <p>Enter an email address to send your report:</p>
      <input type="text" id="emailInput" placeholder="you@example.com"
             style="padding:8px;border-radius:6px;border:1px solid #d1d5db;">
      <div class="btn-row"><button class="btn-outline" id="sendEmailBtn">Send</button></div>
      <span class="muted" id="emailStatus"></span>
    </div>
  `);
  bubble.querySelector("#sendEmailBtn").onclick = async () => {
    const email = bubble.querySelector("#emailInput").value.trim();
    if (!email) return;
    const status = bubble.querySelector("#emailStatus");
    status.textContent = "Sending...";
    const result = await callEmail(email);
    status.textContent = result.success ? "Sent!" : `Failed: ${result.error}`;
  };
}

// ---------- Events ----------
fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (!file) return;

  showLoading(true);
  const data = await callUpload(file);
  showLoading(false);

  sessionId = data.session_id;
  datasetCard.innerHTML = `<b>${file.name}</b><br>${(file.size / 1024).toFixed(1)} KB`;
  enableAllActions();
  addMessage("user", `Uploaded ${file.name}`);
  renderInitialChoice();
});

cleanBtn.addEventListener("click", () => {
  addMessage("user", "Clean Data");
  startCleaning();
});

edaBtn.addEventListener("click", async () => {
  addMessage("user", "Generate EDA Report");
  showLoading(true);
  const result = await callGenerateReport();
  showLoading(false);
  mergeState(result);
  const summary = result.report_sections ? result.report_sections.plain_summary : "Your EDA report is ready.";
  addMessage("assistant", summary);
});

sqlBtn.addEventListener("click", () => chatInput.focus());

emailBtn.addEventListener("click", () => renderEmailForm());

async function sendQuestion() {
  const question = chatInput.value.trim();
  if (!question || !sessionId) return;
  addMessage("user", question);
  chatInput.value = "";

  const bubble = addMessage("assistant", `<span class="muted">Analyzing...</span>`);
  const result = await callChat(question);
  mergeState(result);

  const display = result.display_output;
  if (display) {
    bubble.innerHTML = `<p>${display.answer}</p>${renderTable(display.supporting_data)}`;
  } else {
    bubble.innerHTML = `<p>Sorry, I couldn't process that question.</p>`;
  }
}

sendBtn.addEventListener("click", sendQuestion);
chatInput.addEventListener("keypress", e => { if (e.key === "Enter") sendQuestion(); });

document.getElementById("newChatBtn").addEventListener("click", () => location.reload());