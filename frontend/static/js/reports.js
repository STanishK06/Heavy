(function () {
  const page = document.getElementById("reportsPage");
  if (!page || typeof Chart === "undefined") {
    return;
  }

  Chart.defaults.font.family = "Roboto";
  Chart.defaults.color = "#6B7280";

  const COLORS = {
    yellow: "#F59E0B",
    green: "#10B981",
    red: "#EF4444",
    blue: "#3B82F6",
    purple: "#8B5CF6",
    teal: "#14B8A6",
  };
  const charts = {};

  function destroyChart(id) {
    if (!charts[id]) {
      return;
    }
    charts[id].destroy();
    delete charts[id];
  }

  function formatCurrency(value) {
    return `Rs ${Number(value || 0).toLocaleString("en-IN")}`;
  }

  function formatChartMonth(value) {
    return /^\d{4}-\d{2}$/.test(value || "")
      ? new Date(`${value}-01T00:00:00`).toLocaleDateString("en-IN", { month: "short", year: "2-digit" })
      : (value || "");
  }

  function setDateRange(fromValue, toValue) {
    document.getElementById("dateFrom").value = fromValue;
    document.getElementById("dateTo").value = toValue;
  }

  function setPreset(preset) {
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth();
    const dateTo = today.toISOString().split("T")[0];
    const dateFrom = preset === "month"
      ? new Date(year, month, 1).toISOString().split("T")[0]
      : preset === "year"
        ? `${year}-01-01`
        : "2020-01-01";
    setDateRange(dateFrom, dateTo);
    loadReports();
  }

  function buildReportUrl() {
    const endpoint = page.dataset.endpoint;
    const from = document.getElementById("dateFrom").value || "";
    const to = document.getElementById("dateTo").value || "";
    return `${endpoint}?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
  }

  function updateSummary(summary) {
    document.getElementById("sTotal").textContent = summary.total || 0;
    document.getElementById("sConverted").textContent = summary.converted || 0;
    document.getElementById("sRevenue").textContent = formatCurrency(summary.revenue);
    document.getElementById("sPending").textContent = formatCurrency(summary.pending);
  }

  function renderTrendChart(rows) {
    destroyChart("trend");
    charts.trend = new Chart(document.getElementById("trendChart"), {
      type: "line",
      data: {
        labels: rows.map((row) => formatChartMonth(row.month)),
        datasets: [
          {
            label: "Inquiries",
            data: rows.map((row) => Number(row.inquiries || 0)),
            borderColor: COLORS.yellow,
            backgroundColor: COLORS.yellow,
            tension: 0.35,
            fill: false,
            pointRadius: 3,
            pointHoverRadius: 5,
            borderWidth: 2.5,
          },
          {
            label: "Admissions",
            data: rows.map((row) => Number(row.admissions || 0)),
            borderColor: COLORS.green,
            backgroundColor: COLORS.green,
            tension: 0.35,
            fill: false,
            pointRadius: 3,
            pointHoverRadius: 5,
            borderWidth: 2.5,
          },
        ],
      },
      options: {
        responsive: true,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "top", labels: { boxWidth: 12, padding: 14, font: { size: 12 } } },
        },
        scales: {
          y: { beginAtZero: true, grid: { color: "#F3F4F6" }, ticks: { stepSize: 1 } },
          x: { grid: { display: false } },
        },
      },
    });
  }

  function renderStatusChart(rows) {
    destroyChart("status");
    const statusColors = { Open: COLORS.yellow, Converted: COLORS.green, Closed: COLORS.red };
    charts.status = new Chart(document.getElementById("statusChart"), {
      type: "doughnut",
      data: {
        labels: rows.map((row) => row.status),
        datasets: [
          {
            data: rows.map((row) => Number(row.total || 0)),
            backgroundColor: rows.map((row) => statusColors[row.status] || COLORS.blue),
            hoverOffset: 8,
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        cutout: "65%",
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12, padding: 12, font: { size: 11 } } },
          tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${ctx.raw}` } },
        },
      },
    });
  }

  function renderLocationChart(rows) {
    destroyChart("location");
    charts.location = new Chart(document.getElementById("locationChart"), {
      type: "bar",
      data: {
        labels: rows.map((row) => row.location || "Unknown"),
        datasets: [
          {
            label: "Inquiries",
            data: rows.map((row) => Number(row.inquiries || 0)),
            backgroundColor: COLORS.yellow,
            borderRadius: 6,
            barPercentage: 0.6,
          },
          {
            label: "Admissions",
            data: rows.map((row) => Number(row.admissions || 0)),
            backgroundColor: COLORS.green,
            borderRadius: 6,
            barPercentage: 0.6,
          },
          {
            label: "Revenue",
            data: rows.map((row) => Number(row.revenue || 0)),
            backgroundColor: COLORS.blue,
            borderRadius: 6,
            barPercentage: 0.6,
            yAxisID: "y1",
          },
        ],
      },
      options: {
        responsive: true,
        interaction: { mode: "index" },
        plugins: {
          legend: { position: "top", labels: { boxWidth: 12, padding: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: (ctx) => ctx.dataset.label === "Revenue"
                ? `${ctx.dataset.label}: ${formatCurrency(ctx.raw)}`
                : `${ctx.dataset.label}: ${ctx.raw}`,
            },
          },
        },
        scales: {
          y: { beginAtZero: true, grid: { color: "#F3F4F6" } },
          y1: {
            beginAtZero: true,
            position: "right",
            grid: { drawOnChartArea: false },
            ticks: { callback: (value) => formatCurrency(value) },
          },
          x: { grid: { display: false } },
        },
      },
    });
  }

  function renderCourseChart(rows) {
    destroyChart("course");
    charts.course = new Chart(document.getElementById("courseChart"), {
      type: "bar",
      data: {
        labels: rows.map((row) => row.course || "Unknown"),
        datasets: [
          {
            label: "Inquiries",
            data: rows.map((row) => Number(row.inquiries || 0)),
            backgroundColor: COLORS.purple,
            borderRadius: 6,
          },
          {
            label: "Admissions",
            data: rows.map((row) => Number(row.admissions || 0)),
            backgroundColor: COLORS.teal,
            borderRadius: 6,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        plugins: {
          legend: { display: true, position: "top", labels: { boxWidth: 12, padding: 12, font: { size: 11 } } },
          tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.raw}` } },
        },
        scales: {
          x: { beginAtZero: true, grid: { color: "#F3F4F6" } },
          y: { grid: { display: false } },
        },
      },
    });
  }

  async function loadReports() {
    const response = await fetch(buildReportUrl());
    const data = await response.json();
    if (!response.ok || !data.ok) {
      alert(data.msg || "Unable to load report data.");
      return;
    }

    updateSummary(data.summary || {});
    renderTrendChart(data.trend || []);
    renderStatusChart(data.status || []);
    renderLocationChart(data.location || []);
    renderCourseChart(data.course || []);
  }

  document.getElementById("generateReportsBtn")?.addEventListener("click", loadReports);
  document.querySelectorAll("[data-report-preset]").forEach((button) => {
    button.addEventListener("click", () => {
      setPreset(button.dataset.reportPreset);
    });
  });

  const today = new Date();
  setDateRange(`${today.getFullYear()}-01-01`, today.toISOString().split("T")[0]);
  loadReports();
})();
