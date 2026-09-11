let timelineChart, breakdownChart, page = 1;

const fmtEUR = (v) => (v >= 0 ? "+" : "") + v.toLocaleString("de-DE", {style: "currency", currency: "EUR"});
const $ = (id) => document.getElementById(id);

function showError(msg) {
  const b = document.getElementById("error-banner");
  b.textContent = msg;
  b.classList.remove("hidden");
  setTimeout(() => b.classList.add("hidden"), 5000);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail || r.statusText;
    throw new Error(detail);
  }
  return r.json();
}

async function loadKpis() {
  const k = await api("/api/kpis");
  document.getElementById("kpi-balance").textContent = fmtEUR(k.total_balance);
  document.getElementById("kpi-income").textContent = fmtEUR(k.income_month);
  document.getElementById("kpi-expenses").textContent = fmtEUR(k.expenses_month);
  document.getElementById("kpi-net").textContent = fmtEUR(k.net_cashflow);
}

async function loadTimeline(granularity = "monthly") {
  const data = await api(`/api/timeline?granularity=${granularity}`);
  const labels = data.map(d => d.period);
  const income = data.map(d => d.income);
  const expenses = data.map(d => Math.abs(d.expenses));
  if (timelineChart) {
    timelineChart.data.labels = labels;
    timelineChart.data.datasets[0].data = income;
    timelineChart.data.datasets[1].data = expenses;
    timelineChart.update();
    return;
  }
  timelineChart = new Chart(document.getElementById("timeline-chart"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        {label: "Einnahmen", data: income, backgroundColor: "#16a34a"},
        {label: "Ausgaben", data: expenses, backgroundColor: "#dc2626"},
      ],
    },
    options: {scales: {x: {stacked: true}, y: {stacked: true}}},
  });
}

async function loadBreakdown() {
  const data = await api("/api/categories/breakdown");
  const total = data.reduce((s, d) => s + d.total, 0);
  if (timelineChart && !breakdownChart) {
    breakdownChart = new Chart(document.getElementById("breakdown-chart"), {
      type: "doughnut",
      data: {
        labels: data.map(d => d.category),
        datasets: [{data: data.map(d => d.total), backgroundColor: palette(data.length)}],
      },
      options: {plugins: {tooltip: {callbacks: {label: (c) =>
        `${c.label}: ${fmtEUR(c.parsed)} (${Math.round(c.parsed / total * 100)}%)`}}}},
    });
  } else if (breakdownChart) {
    breakdownChart.data.labels = data.map(d => d.category);
    breakdownChart.data.datasets[0].data = data.map(d => d.total);
    breakdownChart.update();
  }
}

function palette(n) {
  const colors = ["#2563eb", "#16a34a", "#dc2626", "#d97706", "#7c3aed", "#0d9488", "#db2777", "#65a30d", "#57534e"];
  return Array.from({length: n}, (_, i) => colors[i % colors.length]);
}

async function loadTransactions() {
  const params = new URLSearchParams({
    search: document.getElementById("f-search").value,
    page,
  });
  const cat = document.getElementById("f-category").value;
  const acct = document.getElementById("f-account").value;
  if (cat) params.set("category_id", cat);
  if (acct) params.set("account_id", acct);
  const from = document.getElementById("f-from").value;
  const to = document.getElementById("f-to").value;
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);

  const data = await api(`/api/transactions?${params}`);
  const body = document.getElementById("tx-body");
  body.innerHTML = "";
  for (const t of data.items) {
    const tr = document.createElement("tr");
    tr.className = "border-b hover:bg-slate-50";
    tr.innerHTML = `
      <td class="py-2">${t.buchungsdatum}</td>
      <td>${t.partner_name ?? ""}</td>
      <td class="text-slate-500">${(t.verwendungszweck ?? "").slice(0, 40)}</td>
      <td class="text-right font-mono ${t.betrag < 0 ? "text-red-600" : "text-green-600"}">${fmtEUR(t.betrag)}</td>
      <td class="text-slate-500 text-xs">${t.account_bank}</td>
      <td><select class="cat-select border rounded text-xs px-1 py-1" data-tx="${t.id}">
        <option value="">Unassigned</option>
        ${categories.map(c => `<option value="${c.id}" ${c.id === t.category_id ? "selected" : ""}>${c.name}</option>`).join("")}
      </select></td>`;
    body.appendChild(tr);
  }
  document.getElementById("tx-count").textContent = `${data.total} Transaktionen`;
  body.querySelectorAll(".cat-select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      try {
        const res = await api(`/api/transactions/${sel.dataset.tx}/category`, {
          method: "PATCH",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({category_id: +sel.value}),
        });
        if (res.rule_created) toast(`Regel gelernt: ${res.category}`);
        loadBreakdown();
        loadRules();
      } catch (e) { showError(e.message); }
    });
  });
}

let categories = [];

async function loadCategories() {
  categories = await api("/api/categories");
  const sel = document.getElementById("f-category");
  sel.innerHTML = '<option value="">Alle Kategorien</option>' +
    categories.map(c => `<option value="${c.id}">${c.name}</option>`).join("");
  const ul = document.getElementById("cat-list");
  ul.innerHTML = categories.map(c =>
    `<li class="flex justify-between py-1"><span>${c.name} <span class="text-slate-400 text-xs">${c.type}</span></span>
     <button data-id="${c.id}" class="del-cat text-red-500 text-xs">✕</button></li>`).join("");
  ul.querySelectorAll(".del-cat").forEach(b => b.addEventListener("click", async () => {
    try { await api(`/api/categories/${b.dataset.id}`, {method: "DELETE"}); loadCategories(); loadTransactions(); }
    catch (e) { showError(e.message); }
  }));
  const ruleCat = document.getElementById("new-rule-cat");
  ruleCat.innerHTML = categories.map(c => `<option value="${c.id}">${c.name}</option>`).join("");
}

async function loadRules() {
  const rules = await api("/api/rules");
  const ul = document.getElementById("rule-list");
  ul.innerHTML = rules.map(r =>
    `<li class="flex justify-between py-1 items-center">
      <span class="font-mono text-xs">${r.pattern} → <b>${r.category}</b>
      ${r.created_from_manual_override ? '<span class="text-purple-500 text-[10px]">(gelernt)</span>' : ""}</span>
      <button data-id="${r.id}" data-learned="${r.created_from_manual_override}" class="del-rule text-red-500 text-xs">✕</button>
     </li>`).join("");
  ul.querySelectorAll(".del-rule").forEach(b => b.addEventListener("click", async () => {
    try {
      const force = b.dataset.learned === "true" ? "?force=true" : "";
      await api(`/api/rules/${b.dataset.id}${force}`, {method: "DELETE"});
      loadRules();
    } catch (e) { showError(e.message); }
  }));
}

function toast(msg) {
  const b = document.getElementById("error-banner");
  b.textContent = msg;
  b.classList.remove("hidden", "bg-red-600");
  b.classList.add("bg-green-600");
  setTimeout(() => { b.classList.add("hidden"); b.classList.add("bg-red-600"); }, 3000);
}

document.getElementById("sync-btn").addEventListener("click", async () => {
  const btn = document.getElementById("sync-btn");
  const status = document.getElementById("sync-status");
  btn.disabled = true;
  status.textContent = "Sync läuft…";
  try {
    const {job_id} = await api("/api/sync", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({}),
    });
    const poll = setInterval(async () => {
      const s = await api(`/api/sync/status/${job_id}`);
      if (s.status !== "running") {
        clearInterval(poll);
        btn.disabled = false;
        if (s.status === "done") {
          status.textContent = `Sync OK (${Object.keys(s.result.results).length} Banken)`;
          refreshAll();
        } else if (s.status === "tan_required") {
          status.textContent = "TAN nötig";
          showError(s.hint);
        } else {
          status.textContent = "Fehler";
          showError(s.error || "Sync fehlgeschlagen");
        }
      }
    }, 1500);
  } catch (e) {
    btn.disabled = false;
    status.textContent = "";
    showError(e.message);
  }
});

document.querySelectorAll(".gran-btn").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll(".gran-btn").forEach(x =>
    x.className = "gran-btn px-3 py-1 text-sm rounded bg-slate-200 text-slate-700");
  b.className = "gran-btn px-3 py-1 text-sm rounded bg-blue-600 text-white";
  loadTimeline(b.dataset.gran);
}));

document.getElementById("f-apply").addEventListener("click", () => { page = 1; loadTransactions(); });
document.getElementById("prev-page").addEventListener("click", () => { if (page > 1) { page--; loadTransactions(); } });
document.getElementById("next-page").addEventListener("click", () => { page++; loadTransactions(); });
document.getElementById("add-cat").addEventListener("click", async () => {
  const name = document.getElementById("new-cat-name").value;
  const type = document.getElementById("new-cat-type").value;
  try {
    await api("/api/categories", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name, type})});
    document.getElementById("new-cat-name").value = "";
    loadCategories();
  } catch (e) { showError(e.message); }
});
document.getElementById("add-rule").addEventListener("click", async () => {
  const pattern = document.getElementById("new-rule-pattern").value;
  const category_id = +document.getElementById("new-rule-cat").value;
  try {
    await api("/api/rules", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({pattern, category_id, match_field: "partner_name"})});
    document.getElementById("new-rule-pattern").value = "";
    loadRules();
  } catch (e) { showError(e.message); }
});

function refreshAll() {
  loadKpis();
  loadTimeline(document.querySelector(".gran-btn.bg-blue-600")?.dataset.gran || "monthly");
  loadBreakdown();
  loadTransactions();
  loadCategories();
  loadRules();
}

refreshAll();