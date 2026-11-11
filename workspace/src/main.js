import "./style.css";
import { initAiChat } from "./floating-ai/ai-panel.js";

// Workspace components
const workspaceTools = document.querySelector(
  "#workspace-tools"
);

const launcher = document.querySelector(
  "#workspace-launcher"
);

const workspaceMenu = document.querySelector(
  "#workspace-menu"
);

// Menu actions
const menuAI = document.querySelector("#menu-ai");
const menuReport = document.querySelector("#menu-report");

// Panels
const aiPanel = document.querySelector("#ai-panel");
const reportPanel = document.querySelector("#report-panel");

const aiClose = document.querySelector("#ai-close");
const reportClose = document.querySelector("#report-close");

// Report fields
const reportPeriod = document.querySelector("#report-period");
const customRange = document.querySelector("#custom-range");

// ================================
// MENU CONTROLS
// ================================

function setMenuOpen(isOpen) {
  workspaceMenu.classList.toggle("hidden", !isOpen);
  launcher.setAttribute("aria-expanded", String(isOpen));
}

launcher.addEventListener("click", () => {
  const isOpen = launcher.getAttribute("aria-expanded") === "true";
  setMenuOpen(!isOpen);
});

// Close menu when clicking outside
document.addEventListener("click", (event) => {
  if (!workspaceTools.contains(event.target)) {
    setMenuOpen(false);
  }
});

// ================================
// PANEL MANAGEMENT
// ================================

function openPanel(panelName) {
  aiPanel.classList.toggle(
    "hidden",
    panelName !== "ai"
  );

  reportPanel.classList.toggle(
    "hidden",
    panelName !== "report"
  );

  // Hide main Tools launcher when panel is open
  workspaceTools.classList.toggle(
    "hidden",
    panelName !== null
  );

  setMenuOpen(false);
}

// Open AI
menuAI.addEventListener("click", () => {
  openPanel("ai");
});

// Open Report
menuReport.addEventListener("click", () => {
  openPanel("report");
});

// Close panels
aiClose.addEventListener("click", () => {
  openPanel(null);
});

reportClose.addEventListener("click", () => {
  openPanel(null);
});

// Escape keyboard support
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    const isPanelOpen =
      !aiPanel.classList.contains("hidden") ||
      !reportPanel.classList.contains("hidden");

    if (isPanelOpen) {
      openPanel(null);
    } else {
      setMenuOpen(false);
    }
  }
});

// ================================
// REPORT TIME RANGE
// ================================

reportPeriod.addEventListener("change", () => {
  const isCustom = reportPeriod.value === "custom";

  customRange.classList.toggle(
    "hidden",
    !isCustom
  );
});

// Jalankan event handler chat AI
initAiChat();

/* =========================================
   MANUAL MONITORING REPORT - PHASE 9.4
========================================= */

function generateReportText(report) {
  const formatTime = (value) => {
    if (!value) return "Tidak tersedia";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "Tidak tersedia";
    return d.toLocaleString("id-ID", {
      timeZone: "Asia/Jakarta",
      dateStyle: "medium",
      timeStyle: "medium",
    });
  };

  const formatNumber = (value) => {
    return Number(value ?? 0).toLocaleString("id-ID");
  };

  const classes = report.status_classes || {};
  const errors = report.errors || {};
  const categories = report.error_categories || {};
  const paths = report.top_error_endpoints || [];
  const slow = report.slow_request_samples || [];

  let out = "";
  out += "=================================================================\n";
  out += "                    MONITORING REPORT\n";
  out += "=================================================================\n\n";
  out += `Status       : ${report.report_status || "READY"}\n`;
  out += `Index        : ${report.index}\n`;
  out += `Periode      : ${formatTime(report.period?.start)} — ${formatTime(report.period?.end)} (WIB)\n`;
  out += `Generated At : ${formatTime(report.generated_at)} (WIB)\n\n`;

  out += "-----------------------------------------------------------------\n";
  out += "TRAFFIC & ERROR SUMMARY\n";
  out += "-----------------------------------------------------------------\n";
  out += `Total Requests   : ${formatNumber(report.total_requests)}\n`;
  out += `HTTP 2xx         : ${formatNumber(classes["2xx"])}\n`;
  out += `HTTP 3xx         : ${formatNumber(classes["3xx"])}\n`;
  out += `HTTP 4xx         : ${formatNumber(classes["4xx"])}\n`;
  out += `HTTP 5xx         : ${formatNumber(classes["5xx"])}\n`;
  out += `HTTP Error Rate  : ${errors.error_rate_percent ?? 0}%\n`;
  out += `Client Error Rate: ${errors.client_error_rate_percent ?? 0}% (4xx)\n`;
  out += `Server Error Rate: ${errors.server_error_rate_percent ?? 0}% (5xx)\n`;

  if (categories.technical_4xx || categories.business_4xx) {
    if (categories.technical_4xx) {
      out += `  - Technical 4xx: ${formatNumber(categories.technical_4xx.count)} (${categories.technical_4xx.rate_percent}%)\n`;
    }
    if (categories.business_4xx) {
      out += `  - Business 4xx : ${formatNumber(categories.business_4xx.count)} (${categories.business_4xx.rate_percent}%)\n`;
    }
  }
  out += "\n";

  out += "-----------------------------------------------------------------\n";
  out += "TOP ERROR ENDPOINTS\n";
  out += "-----------------------------------------------------------------\n";
  if (paths.length === 0) {
    out += "Tidak ada error endpoint terdeteksi pada periode ini.\n";
  } else {
    paths.forEach((item, idx) => {
      out += `${idx + 1}. ${item.path.padEnd(35)} : ${formatNumber(item.error_count)} error\n`;
    });
  }
  out += "\n";

  out += "-----------------------------------------------------------------\n";
  out += "SLOW REQUEST SAMPLES (LATENCY)\n";
  out += "-----------------------------------------------------------------\n";
  if (slow.length === 0) {
    out += "Semua request responsif (< threshold).\n";
  } else {
    slow.forEach((item, idx) => {
      const status = item.status_code ? ` (HTTP ${item.status_code})` : "";
      out += `${idx + 1}. ${item.path.padEnd(35)} : ${formatNumber(item.response_time_ms)} ms${status}\n`;
    });
  }
  out += "\n";

  out += "-----------------------------------------------------------------\n";
  out += "DATA FRESHNESS\n";
  out += "-----------------------------------------------------------------\n";
  out += `Latest Event in Index : ${formatTime(report.latest_event_in_index)} (WIB)\n`;

  if (report.warnings?.length) {
    out += "\n-----------------------------------------------------------------\n";
    out += "WARNINGS / CATATAN LAPORAN\n";
    out += "-----------------------------------------------------------------\n";
    report.warnings.forEach(w => {
      out += `- ${w}\n`;
    });
  }

  out += "=================================================================\n";
  out += "End of Report\n";
  return out;
}

function triggerDownload(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function renderMonitoringReport(report, container) {
  container.replaceChildren();

  const formatTime = (value) => {
    if (!value) return "Tidak tersedia";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "Tidak tersedia";
    return d.toLocaleString("id-ID", {
      timeZone: "Asia/Jakarta",
      dateStyle: "medium",
      timeStyle: "medium",
    });
  };

  const formatNumber = (value) => {
    return Number(value ?? 0).toLocaleString("id-ID");
  };

  const errors = report.errors || {};
  const errorRate = Number(errors.error_rate_percent ?? 0);
  const classes = report.status_classes || {};
  const categories = report.error_categories || {};
  const paths = report.top_error_endpoints || [];
  const slow = report.slow_request_samples || [];

  const wrapper = document.createElement("div");
  wrapper.className = "report-card";

  // Header Banner - Clean text without READY badge or oval pills
  const header = document.createElement("div");
  header.className = "report-header";
  header.innerHTML = `
    <div class="report-title-row">
      <h4 class="report-main-title">Monitoring Report</h4>
    </div>
    <div class="report-meta-text">
      Index: <strong>${report.index}</strong> • Periode: ${formatTime(report.period?.start)} — ${formatTime(report.period?.end)} (WIB)
    </div>
  `;
  wrapper.appendChild(header);

  // Download Actions Bar
  const downloadBar = document.createElement("div");
  downloadBar.className = "report-download-bar";
  downloadBar.innerHTML = `
    <button type="button" class="btn-download" id="btn-download-txt">
      ⬇️ Download Document (.txt)
    </button>
    <button type="button" class="btn-download-secondary" id="btn-download-json">
      Download JSON
    </button>
  `;
  wrapper.appendChild(downloadBar);

  // Hook download button listeners
  const nowStr = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  downloadBar.querySelector("#btn-download-txt").addEventListener("click", () => {
    const textData = generateReportText(report);
    triggerDownload(textData, `monitoring-report-${report.index}-${nowStr}.txt`, "text/plain;charset=utf-8");
  });

  downloadBar.querySelector("#btn-download-json").addEventListener("click", () => {
    const jsonData = JSON.stringify(report, null, 2);
    triggerDownload(jsonData, `monitoring-report-${report.index}-${nowStr}.json`, "application/json;charset=utf-8");
  });

  // KPI Metrics (Clean monochrome text boxes)
  const kpiGrid = document.createElement("div");
  kpiGrid.className = "report-kpi-grid";
  kpiGrid.innerHTML = `
    <div class="kpi-card">
      <span class="kpi-label">Total Traffic</span>
      <span class="kpi-value">${formatNumber(report.total_requests)}</span>
      <span class="kpi-sub">Total log requests</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">HTTP Error Rate</span>
      <span class="kpi-value">${errorRate.toFixed(2)}%</span>
      <span class="kpi-sub">4xx: ${errors.client_error_rate_percent ?? 0}% • 5xx: ${errors.server_error_rate_percent ?? 0}%</span>
    </div>
  `;
  wrapper.appendChild(kpiGrid);

  // Status Distribution (Clean simple rows without colored pills)
  const statusSection = document.createElement("div");
  statusSection.className = "report-section";
  statusSection.innerHTML = `
    <div class="report-section-title">Distribusi Status HTTP</div>
    <div class="report-plain-grid">
      <div class="plain-row">
        <span>HTTP 2xx</span>
        <strong>${formatNumber(classes["2xx"])}</strong>
      </div>
      <div class="plain-row">
        <span>HTTP 3xx</span>
        <strong>${formatNumber(classes["3xx"])}</strong>
      </div>
      <div class="plain-row">
        <span>HTTP 4xx</span>
        <strong>${formatNumber(classes["4xx"])}</strong>
      </div>
      <div class="plain-row">
        <span>HTTP 5xx</span>
        <strong>${formatNumber(classes["5xx"])}</strong>
      </div>
    </div>
  `;
  wrapper.appendChild(statusSection);

  // 4xx Category Breakdown
  if (categories.technical_4xx || categories.business_4xx) {
    const catBox = document.createElement("div");
    catBox.className = "report-category-box";
    catBox.innerHTML = `
      <span class="cat-label">Detail 4xx:</span>
      ${categories.technical_4xx ? `<span>Technical: <strong>${formatNumber(categories.technical_4xx.count)}</strong> (${categories.technical_4xx.rate_percent}%)</span>` : ''}
      ${categories.business_4xx ? `<span>Business: <strong>${formatNumber(categories.business_4xx.count)}</strong> (${categories.business_4xx.rate_percent}%)</span>` : ''}
    `;
    wrapper.appendChild(catBox);
  }

  // Top Error Endpoints (Direct text, no oval shapes)
  const errSection = document.createElement("div");
  errSection.className = "report-section";
  let errItemsHtml = "";
  if (paths.length === 0) {
    errItemsHtml = `<div class="report-empty-text">Tidak ada error endpoint pada periode ini.</div>`;
  } else {
    errItemsHtml = paths.map(item => `
      <div class="report-plain-item">
        <span class="item-path">${item.path}</span>
        <span class="item-value">${formatNumber(item.error_count)} error</span>
      </div>
    `).join("");
  }
  errSection.innerHTML = `
    <div class="report-section-title">Top Error Endpoints</div>
    <div class="report-plain-list">${errItemsHtml}</div>
  `;
  wrapper.appendChild(errSection);

  // Slow Requests (Direct text: "300 ms", no oval shape, clean text)
  const slowSection = document.createElement("div");
  slowSection.className = "report-section";
  let slowItemsHtml = "";
  if (slow.length === 0) {
    slowItemsHtml = `<div class="report-empty-text">Semua request responsif (&lt; threshold).</div>`;
  } else {
    slowItemsHtml = slow.map(item => `
      <div class="report-plain-item">
        <span class="item-path">${item.path}</span>
        <span class="item-value">${formatNumber(item.response_time_ms)} ms</span>
      </div>
    `).join("");
  }
  slowSection.innerHTML = `
    <div class="report-section-title">Slow Requests (Latency)</div>
    <div class="report-plain-list">${slowItemsHtml}</div>
  `;
  wrapper.appendChild(slowSection);

  // Data Freshness & Kibana Screenshot
  const footerSection = document.createElement("div");
  footerSection.className = "report-meta-footer";
  footerSection.innerHTML = `
    <div class="meta-row">
      <span>Data Freshness:</span>
      <strong>${formatTime(report.latest_event_in_index)}</strong>
    </div>
    <div class="meta-row">
      <span>Kibana Screenshot:</span>
      <span>Phase 9.6 (Scheduled Worker)</span>
    </div>
  `;
  wrapper.appendChild(footerSection);

  // Warnings if any
  if (report.warnings?.length) {
    const warnBox = document.createElement("div");
    warnBox.className = "report-warning-box";
    warnBox.innerHTML = `
      <h6>Catatan Laporan:</h6>
      <ul>${report.warnings.map(w => `<li>${w}</li>`).join("")}</ul>
    `;
    wrapper.appendChild(warnBox);
  }

  container.appendChild(wrapper);
}


function setupManualReport() {
  const button = document.getElementById("generate-report");
  const indexInput = document.getElementById("report-index");
  const periodInput = document.getElementById("report-period");
  const startInput = document.getElementById("report-start");
  const endInput = document.getElementById("report-end");
  const resultBox = document.getElementById("report-result");

  if (!button || !indexInput || !periodInput || !resultBox) {
    console.warn("Manual Report: elemen UI belum lengkap.");
    return;
  }

  button.disabled = false;

  button.addEventListener("click", async () => {
    const index = indexInput.value.trim();
    const period = periodInput.value;

    if (!index) {
      alert("Elasticsearch Index wajib diisi.");
      return;
    }

    const payload = { index };

    // Custom date range
    if (period === "custom") {
      if (!startInput?.value || !endInput?.value) {
        alert("Isi waktu mulai dan waktu akhir.");
        return;
      }

      const start = new Date(startInput.value);
      const end = new Date(endInput.value);

      if (
        Number.isNaN(start.getTime()) ||
        Number.isNaN(end.getTime()) ||
        start >= end
      ) {
        alert("Rentang waktu tidak valid.");
        return;
      }

      payload.period_minutes = null;
      payload.start = start.toISOString();
      payload.end = end.toISOString();
    } else {
      const minutes = Number(period);

      if (![15, 60, 1440].includes(minutes)) {
        alert("Periode laporan tidak dikenali.");
        return;
      }

      payload.period_minutes = minutes;
    }

    // Loading state
    button.disabled = true;
    button.innerHTML = '<span class="button-spinner"></span> Menganalisis Log...';

    resultBox.hidden = false;
    resultBox.replaceChildren();

    const progress = document.createElement("div");
    progress.className = "report-loading-state";
    progress.innerHTML = `
      <div class="loading-spinner-large"></div>
      <p>Mengambil data monitoring dari Elasticsearch...</p>
    `;

    resultBox.appendChild(progress);
    resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });

    try {
      const response = await fetch("/api/reports/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Gagal membuat Monitoring Report."
        );
      }

      renderMonitoringReport(data, resultBox);
      resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });

    } catch (error) {
      resultBox.replaceChildren();

      const messageBox = document.createElement("div");
      messageBox.className = "report-error-box";
      messageBox.innerHTML = `
        <strong>Gagal Membuat Report:</strong>
        <p>${error.message}</p>
      `;
      resultBox.appendChild(messageBox);

    } finally {
      button.disabled = false;
      button.innerHTML = "⚡ Generate Report";
    }
  });
}

// Jalankan setelah elemen HTML panel tersedia.
setupManualReport();
