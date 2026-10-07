/* SIPHON — front end */

const $ = (id) => document.getElementById(id);

const panels = {
  url:      $("panel-url"),
  preview:  $("panel-preview"),
  progress: $("panel-progress"),
  done:     $("panel-done"),
  error:    $("panel-error"),
};

let state = {
  url: "",
  quality: "best",
  info: null,
  jobId: null,
  poll: null,
  lastFile: "",
};

/* ── helpers ─────────────────────────────────────────── */

function show(...names) {
  Object.entries(panels).forEach(([k, el]) => el.classList.toggle("hidden", !names.includes(k)));
}

async function api(path, body) {
  const res = await fetch(path, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  } : undefined);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.error) throw new Error(data.error || "Request failed.");
  return data;
}

function hms(sec) {
  sec = Math.round(sec || 0);
  if (!sec) return "";
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const p = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(s)}` : `${m}:${p(s)}`;
}

function flash(cls) {
  document.body.classList.add(cls);
  setTimeout(() => document.body.classList.remove(cls), 700);
}

function fail(msg, help) {
  stopPolling();
  $("e-msg").textContent = msg;
  $("e-help").textContent = help || "Check the link, then try again. If the video plays in your browser, it should download.";
  show("error");
}

function stopPolling() {
  if (state.poll) { clearInterval(state.poll); state.poll = null; }
}

/* ── step 1: fetch info ──────────────────────────────── */

async function fetchInfo() {
  const url = $("url").value.trim();
  if (!url) { $("url").focus(); return; }

  state.url = url;
  const btn = $("btn-fetch");
  btn.disabled = true;
  btn.textContent = "READING";
  btn.classList.add("thinking");

  try {
    const info = await api("/api/info", { url });
    state.info = info;

    $("thumb").src = info.thumbnail || "";
    $("thumb").alt = info.title;
    $("v-title").textContent = info.title;
    $("v-uploader").textContent = info.uploader || "";
    $("v-duration").textContent = hms(info.duration);
    $("v-duration").classList.toggle("hidden", !info.duration);
    $("playlist-row").classList.toggle("hidden", !info.maybe_playlist);
    $("playlist").checked = false;

    show("preview");
  } catch (err) {
    fail(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "FETCH";
    btn.classList.remove("thinking");
  }
}

/* ── step 2: download ────────────────────────────────── */

async function startDownload() {
  $("p-title").textContent = state.info?.title || "Working";
  $("p-percent").textContent = "0%";
  $("p-bar").style.width = "0%";
  $("p-speed").textContent = "—";
  $("p-eta").textContent = "—";
  $("p-files").textContent = "0 files";
  $("p-stage").innerHTML = 'Starting up<span class="blink-cursor green">_</span>';
  show("progress");

  try {
    const { id } = await api("/api/download", {
      url: state.url,
      quality: state.quality,
      title: state.info?.title || "",
      playlist: $("playlist").checked,
    });
    state.jobId = id;
    state.poll = setInterval(tick, 400);
  } catch (err) {
    fail(err.message);
  }
}

async function tick() {
  let job;
  try {
    job = await api(`/api/progress/${state.jobId}`);
  } catch {
    return; // transient; keep polling
  }

  const pct = Math.max(0, Math.min(100, job.percent || 0));
  $("p-percent").textContent = `${pct.toFixed(0)}%`;
  $("p-bar").style.width = `${pct}%`;
  $("p-speed").textContent = job.speed || "—";
  $("p-eta").textContent = job.eta || "—";
  $("p-files").textContent = `${job.files || 0} file${job.files === 1 ? "" : "s"}`;
  $("p-stage").innerHTML =
    `${job.stage || "Working"}<span class="blink-cursor green">_</span>`;

  if (job.status === "done") {
    stopPolling();
    state.lastFile = job.file || "";
    $("d-title").textContent = job.title || state.info?.title || "Saved";
    $("d-path").textContent = job.file || "Saved to your Videos folder.";
    flash("flash-green");
    show("done");
  } else if (job.status === "error") {
    fail(job.error || "The download failed.");
  } else if (job.status === "cancelled") {
    stopPolling();
    reset();
  }
}

/* ── reset ───────────────────────────────────────────── */

function reset() {
  stopPolling();
  state.jobId = null;
  show("url");
  $("url").focus();
  $("url").select();
}

/* ── wiring ──────────────────────────────────────────── */

$("btn-fetch").addEventListener("click", fetchInfo);
$("url").addEventListener("keydown", (e) => { if (e.key === "Enter") fetchInfo(); });

$("quality").addEventListener("click", (e) => {
  const btn = e.target.closest(".q-btn");
  if (!btn) return;
  document.querySelectorAll(".q-btn").forEach((b) => b.classList.remove("selected"));
  btn.classList.add("selected");
  state.quality = btn.dataset.q;
});

$("btn-download").addEventListener("click", startDownload);
$("btn-back").addEventListener("click", reset);
$("btn-again").addEventListener("click", reset);
$("btn-retry").addEventListener("click", reset);

$("btn-cancel").addEventListener("click", async () => {
  if (state.jobId) await api(`/api/cancel/${state.jobId}`, {}).catch(() => {});
  reset();
});

$("btn-open").addEventListener("click", () => {
  api("/api/reveal", { path: state.lastFile }).catch(() => {});
});

/* ── health strip ────────────────────────────────────── */

(async function checkHealth() {
  try {
    const h = await api("/api/health");
    $("h-ytdlp").className  = "dot " + (h.ytdlp  ? "ok" : "bad");
    $("h-ffmpeg").className = "dot " + (h.ffmpeg ? "ok" : "bad");
    $("h-deno").className   = "dot " + (h.deno   ? "ok" : "bad");
  } catch {
    ["h-ytdlp", "h-ffmpeg", "h-deno"].forEach((i) => ($(i).className = "dot bad"));
  }
})();

$("url").focus();
