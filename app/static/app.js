const summaryLabels = {
  sources: "Sources",
  endpoints_catalogued: "Endpoints",
  safe_runtime_endpoints: "Safe routes",
  candidate_records_loaded: "Candidate rows",
  production_approved_sources: "Approved sources",
  complete_runs: "Completed runs",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function number(value) {
  return new Intl.NumberFormat("th-TH").format(value || 0);
}

function badge(value) {
  const css = value === "api_first" ? "api" : value === "snapshot_only" ? "snapshot" : "blocked";
  return '<span class="badge ' + css + '">' + escapeHtml(value) + "</span>";
}

async function loadSummary() {
  const response = await fetch("/api/summary");
  const data = await response.json();
  const root = document.querySelector("#summary");
  root.innerHTML = Object.entries(summaryLabels)
    .map(function ([key, label]) {
      return (
        '<article class="stat"><span>' +
        escapeHtml(label) +
        "</span><strong>" +
        number(data[key]) +
        "</strong></article>"
      );
    })
    .join("");
}

async function loadSources() {
  const response = await fetch("/api/sources");
  const sources = await response.json();
  document.querySelector("#sourceRows").innerHTML = sources
    .map(function (source) {
      return (
        "<tr>" +
        "<td>" + number(source.ordinal) + "</td>" +
        '<td><a href="' + escapeHtml(source.url) + '" target="_blank" rel="noreferrer">' +
        escapeHtml(source.name_th) + "</a><small>" + escapeHtml(source.source_id) + "</small></td>" +
        "<td>" + badge(source.acquisition_mode) + "</td>" +
        "<td><span class=\"policy\">" + escapeHtml(source.cloud_policy) + "</span></td>" +
        "<td>" + number(source.expected_record_count) + "</td>" +
        "<td>" + number(source.loaded_records) + "</td>" +
        '<td><button class="ghost-button endpoint-button" data-source="' +
        escapeHtml(source.source_id) + '">ดู</button></td>' +
        "</tr>"
      );
    })
    .join("");
  document.querySelectorAll(".endpoint-button").forEach(function (button) {
    button.addEventListener("click", function () {
      openEndpoints(button.dataset.source);
    });
  });
}

async function loadRuns() {
  const response = await fetch("/api/runs?limit=12");
  const runs = await response.json();
  const root = document.querySelector("#runs");
  if (!runs.length) {
    root.innerHTML = '<p class="empty">ยังไม่มี ingestion run — เริ่มด้วย python -m app.cli ingest</p>';
    return;
  }
  root.innerHTML = runs
    .map(function (run) {
      return (
        '<article class="run"><span class="run-status ' + escapeHtml(run.status) + '"></span>' +
        "<div><strong>" + escapeHtml(run.source_id) + "</strong><small>" +
        escapeHtml(run.run_id) + " · " + escapeHtml(run.strategy) + "</small></div>" +
        "<b>" + number(run.records_loaded) + " rows</b></article>"
      );
    })
    .join("");
}

async function openEndpoints(sourceId) {
  const response = await fetch("/api/sources/" + encodeURIComponent(sourceId) + "/endpoints");
  const endpoints = await response.json();
  document.querySelector("#endpointTitle").textContent = sourceId + " · " + endpoints.length + " endpoints";
  document.querySelector("#endpointList").innerHTML = endpoints
    .map(function (endpoint) {
      const state = endpoint.restricted ? "blocked" : endpoint.runtime_enabled ? "safe" : "review";
      return (
        '<article class="endpoint"><span class="method">' + escapeHtml(endpoint.method) + "</span>" +
        '<div><code>' + escapeHtml(endpoint.url) + "</code><small>" +
        escapeHtml(endpoint.kind || endpoint.access) + "</small></div>" +
        '<span class="endpoint-state ' + state + '">' + state + "</span></article>"
      );
    })
    .join("");
  document.querySelector("#endpointDialog").showModal();
}

document.querySelector("#closeDialog").addEventListener("click", function () {
  document.querySelector("#endpointDialog").close();
});

Promise.all([loadSummary(), loadSources(), loadRuns()]).catch(function (error) {
  document.body.insertAdjacentHTML(
    "beforeend",
    '<div class="toast">โหลด dashboard ไม่สำเร็จ: ' + escapeHtml(error.message) + "</div>",
  );
});
