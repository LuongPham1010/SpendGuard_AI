/**
 * SpendGuard AI - Frontend Orchestration Engine
 * Shenzhen International FinTech Competition 2026 - Topic A Prototype
 */

// Application State
let currentCurrency = 'VND';
const VND_TO_USD_RATE = 25400.0;
let dashboardData = null;
let subscriptionsData = [];
let statementTransactions = [];
let pendingTier3Transfer = null;
let pendingScamTransferReq = null;
let currentSelectedSub = null;
let currentSubLang = 'EN';
let activeQuizQuestions = [];
let coolingTimerInterval = null;
let coolingSecondsRemaining = 3600;

// Chart Instances
let chart503020Instance = null;
let chartCashflowInstance = null;
let chartMonteCarloInstance = null;

// Initialize on DOM Ready
document.addEventListener('DOMContentLoaded', async () => {
  await fetchHealthAndStatus();
  await loadDashboardOverview();
  await loadTransactions();
  await loadSubscriptions();
  await fetchAuditLogs();
  initMonteCarloSliders();

  // Run initial Monte Carlo simulation for instant rich visualization
  runMonteCarloSimulation();
});

// Toast Notifications
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  const colors = {
    info: 'bg-blue-900/90 text-blue-200 border-blue-700',
    success: 'bg-emerald-900/90 text-emerald-200 border-emerald-700',
    warning: 'bg-amber-900/90 text-amber-200 border-amber-700',
    danger: 'bg-rose-900/90 text-rose-200 border-rose-700',
  };
  toast.className = `px-4 py-3 rounded-xl border shadow-xl text-xs font-semibold backdrop-blur-md pointer-events-auto transition-all transform translate-y-2 opacity-0 ${colors[type] || colors.info}`;
  toast.innerHTML = `<div class="flex items-center gap-2"><i class="fa-solid fa-circle-info"></i><span>${message}</span></div>`;
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.remove('translate-y-2', 'opacity-0');
  });

  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Currency Formatter
function formatCurrency(amountVND, targetCurrency = currentCurrency) {
  if (typeof amountVND !== 'number') amountVND = parseFloat(amountVND) || 0;
  if (targetCurrency === 'USD') {
    const usd = amountVND / VND_TO_USD_RATE;
    return `$${usd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `${amountVND.toLocaleString('vi-VN')} ₫`;
}

function setCurrency(curr) {
  currentCurrency = curr;
  const btnVnd = document.getElementById('btn-curr-vnd');
  const btnUsd = document.getElementById('btn-curr-usd');

  if (curr === 'VND') {
    if (btnVnd) btnVnd.className = 'px-2.5 py-1 rounded-md text-xs font-bold transition-all bg-blue-600 text-white';
    if (btnUsd) btnUsd.className = 'px-2.5 py-1 rounded-md text-xs font-medium text-slate-400 transition-all hover:text-white';
  } else {
    if (btnUsd) btnUsd.className = 'px-2.5 py-1 rounded-md text-xs font-bold transition-all bg-blue-600 text-white';
    if (btnVnd) btnVnd.className = 'px-2.5 py-1 rounded-md text-xs font-medium text-slate-400 transition-all hover:text-white';
  }

  if (dashboardData) updateDashboardUI(dashboardData);
  if (subscriptionsData) renderSubscriptionsTable(subscriptionsData);
  if (statementTransactions) renderStatementTable(statementTransactions);
  updateMonteCarloLabels();
}

async function fetchHealthAndStatus() {
  try {
    const res = await fetch('/api/health');
    const data = await res.json();
    const pill = document.getElementById('gemini-status-pill');
    if (pill) {
      if (data.gemini_configured) {
        pill.innerHTML = `
          <span class="w-2 h-2 rounded-full bg-emerald-400 pulse-badge"></span>
          <span class="font-medium">${data.gemini_model} Active</span>
        `;
      } else {
        pill.innerHTML = `
          <span class="w-2 h-2 rounded-full bg-blue-400 pulse-badge"></span>
          <span class="font-medium">Gemini Flash Fallback Engine</span>
        `;
      }
    }
  } catch (err) {
    console.warn('Health check warning:', err);
  }
}

async function loadDashboardOverview() {
  try {
    const res = await fetch('/api/dashboard/overview');
    dashboardData = await res.json();
    updateDashboardUI(dashboardData);
  } catch (err) {
    console.error('Failed to load dashboard overview:', err);
    showToast('Failed to load dashboard data from server.', 'danger');
  }
}

function updateDashboardUI(data) {
  if (document.getElementById('kpi-total-balance')) document.getElementById('kpi-total-balance').textContent = formatCurrency(data.total_balance);
  if (document.getElementById('kpi-inflow')) document.getElementById('kpi-inflow').textContent = formatCurrency(data.total_income_month);
  if (document.getElementById('kpi-outflow')) document.getElementById('kpi-outflow').textContent = formatCurrency(data.total_expense_month);
  if (document.getElementById('kpi-adherence')) document.getElementById('kpi-adherence').textContent = `${data.budget_adherence_pct} / 100`;

  (data.wallets || []).forEach(w => {
    if (w.id === 'main' && document.getElementById('wallet-main-balance')) {
      document.getElementById('wallet-main-balance').textContent = formatCurrency(w.balance);
    } else if (w.id === 'emergency' && document.getElementById('wallet-emergency-balance')) {
      document.getElementById('wallet-emergency-balance').textContent = formatCurrency(w.balance);
    } else if (w.id === 'fun' && document.getElementById('wallet-fun-balance')) {
      document.getElementById('wallet-fun-balance').textContent = formatCurrency(w.balance);
    }
  });

  const breakdown = data.adherence_50_30_20.breakdown;
  if (document.getElementById('breakdown-needs-val')) document.getElementById('breakdown-needs-val').textContent = `${formatCurrency(breakdown.Needs.amount)} (${breakdown.Needs.actual_pct}%)`;
  if (document.getElementById('breakdown-wants-val')) document.getElementById('breakdown-wants-val').textContent = `${formatCurrency(breakdown.Wants.amount)} (${breakdown.Wants.actual_pct}%)`;
  if (document.getElementById('breakdown-savings-val')) document.getElementById('breakdown-savings-val').textContent = `${formatCurrency(breakdown.Savings.amount)} (${breakdown.Savings.actual_pct}%)`;

  render503020Chart(breakdown);
  renderCashflowChart(data);
}

function render503020Chart(breakdown) {
  const el = document.getElementById('chart-50-30-20');
  if (!el) return;
  const ctx = el.getContext('2d');
  if (chart503020Instance) chart503020Instance.destroy();

  chart503020Instance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Needs (50%)', 'Wants (30%)', 'Savings (20%)'],
      datasets: [{
        data: [breakdown.Needs.amount, breakdown.Wants.amount, breakdown.Savings.amount],
        backgroundColor: ['#3b82f6', '#8b5cf6', '#10b981'],
        borderWidth: 2,
        borderColor: '#0e1626',
        hoverOffset: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#94a3b8', font: { family: 'Plus Jakarta Sans', size: 11 }, boxWidth: 12 }
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              const label = context.label || '';
              const value = context.raw || 0;
              return ` ${label}: ${formatCurrency(value)}`;
            }
          }
        }
      },
      cutout: '72%'
    }
  });
}

function renderCashflowChart(data) {
  const el = document.getElementById('chart-cashflow');
  if (!el) return;
  const ctx = el.getContext('2d');
  if (chartCashflowInstance) chartCashflowInstance.destroy();

  const income = data.total_income_month;
  const needs = data.spending_by_category['Needs'] || 0;
  const wants = data.spending_by_category['Wants'] || 0;
  const savings = data.spending_by_category['Savings/Debts'] || 0;

  chartCashflowInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Monthly Inflow', 'Essential Needs', 'Discretionary Wants', 'Vault Savings'],
      datasets: [{
        data: [income, needs, wants, savings],
        backgroundColor: ['#10b981', '#3b82f6', '#8b5cf6', '#06b6d4'],
        borderRadius: 8,
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(context) {
              return ` Amount: ${formatCurrency(context.raw)}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#94a3b8', font: { family: 'Plus Jakarta Sans', size: 11 } }
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: {
            color: '#94a3b8',
            font: { family: 'Plus Jakarta Sans', size: 10 },
            callback: function(val) {
              return currentCurrency === 'USD' ? `$${(val / VND_TO_USD_RATE).toFixed(0)}` : `${(val / 1000000).toFixed(0)}M ₫`;
            }
          }
        }
      }
    }
  });
}

function switchTab(tabId) {
  const tabs = ['ghost', 'debate', 'montecarlo', 'antiscam'];
  tabs.forEach(t => {
    const btn = document.getElementById(`tab-btn-${t}`);
    const content = document.getElementById(`tab-content-${t}`);
    if (!btn || !content) return;
    if (t === tabId) {
      btn.className = 'tab-btn active px-4 py-2.5 rounded-xl border border-transparent text-sm transition-all flex items-center gap-2';
      content.classList.remove('hidden');
    } else {
      btn.className = 'tab-btn px-4 py-2.5 rounded-xl border border-transparent text-sm transition-all flex items-center gap-2 text-slate-400 hover:text-white';
      content.classList.add('hidden');
    }
  });
}

async function loadTransactions() {
  try {
    const res = await fetch('/api/transactions');
    const data = await res.json();
    statementTransactions = data.transactions || [];
    renderStatementTable(statementTransactions);
    const countEl = document.getElementById('tx-count-display');
    if (countEl) countEl.textContent = statementTransactions.length;
  } catch (err) {
    console.error('Failed to load transactions:', err);
  }
}

function renderStatementTable(txs) {
  const tbody = document.getElementById('statement-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (txs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-4 text-center text-slate-500">No transactions match your search.</td></tr>`;
    return;
  }

  txs.forEach(tx => {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-slate-800/40 transition-colors';

    const isInflow = tx.type.toLowerCase() === 'inflow' || tx.category === 'Income';
    const amtColor = isInflow ? 'text-emerald-400 font-bold' : 'text-rose-400 font-semibold';
    const typeBadge = isInflow
      ? '<span class="px-2 py-0.5 rounded text-[10px] bg-emerald-950/70 text-emerald-300 border border-emerald-800/60 font-semibold">Inflow</span>'
      : '<span class="px-2 py-0.5 rounded text-[10px] bg-rose-950/70 text-rose-300 border border-rose-800/60 font-semibold">Outflow</span>';

    const catBadges = {
      'Needs': 'bg-blue-950/70 text-blue-300 border border-blue-800/60',
      'Wants': 'bg-purple-950/70 text-purple-300 border border-purple-800/60',
      'Savings/Debts': 'bg-emerald-950/70 text-emerald-300 border border-emerald-800/60',
      'Income': 'bg-teal-950/70 text-teal-300 border border-teal-800/60',
    };
    const cBadge = catBadges[tx.category] || 'bg-slate-800 text-slate-300 border border-slate-700';
    const isMasked = tx.description.includes('****') || tx.description.includes('***');

    tr.innerHTML = `
      <td class="p-2.5 font-mono text-slate-400 text-[10px]">${tx.id}</td>
      <td class="p-2.5 font-mono text-slate-400 text-[10px] whitespace-nowrap">${tx.date}</td>
      <td class="p-2.5 text-slate-200">
        <div class="flex items-center gap-1.5 flex-wrap">
          <span>${tx.description}</span>
          ${isMasked ? '<span class="px-1.5 py-0.2 rounded text-[9px] bg-emerald-900/60 text-emerald-300 font-bold border border-emerald-700/50"><i class="fa-solid fa-shield-halved mr-0.5"></i>PII Masked</span>' : ''}
          ${tx.is_subscription ? '<span class="px-1.5 py-0.2 rounded text-[9px] bg-amber-900/60 text-amber-300 font-bold border border-amber-700/50"><i class="fa-solid fa-ghost mr-0.5"></i>Sub</span>' : ''}
        </div>
      </td>
      <td class="p-2.5 ${amtColor} whitespace-nowrap">${isInflow ? '+' : '-'}${formatCurrency(tx.amount)}</td>
      <td class="p-2.5 whitespace-nowrap">${typeBadge}</td>
      <td class="p-2.5 whitespace-nowrap">
        <span class="px-2 py-0.5 rounded text-[10px] font-medium ${cBadge}">${tx.category}</span>
        <span class="text-[10px] text-slate-400 block mt-0.5">${tx.subcategory || ''}</span>
      </td>
      <td class="p-2.5 text-slate-400 text-[10px] whitespace-nowrap">${tx.wallet}</td>
    `;
    tbody.appendChild(tr);
  });
}

function filterTransactions() {
  const query = (document.getElementById('tx-search-input')?.value || '').toLowerCase().trim();
  if (!query) {
    renderStatementTable(statementTransactions);
    return;
  }
  const filtered = statementTransactions.filter(tx =>
    tx.description.toLowerCase().includes(query) ||
    tx.id.toLowerCase().includes(query) ||
    tx.category.toLowerCase().includes(query) ||
    (tx.merchant && tx.merchant.toLowerCase().includes(query)) ||
    (tx.subcategory && tx.subcategory.toLowerCase().includes(query)) ||
    tx.wallet.toLowerCase().includes(query)
  );
  renderStatementTable(filtered);
}

async function handleStatementCsvUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  showToast(`Uploading statement: ${file.name}...`, 'info');
  try {
    const res = await fetch('/api/transactions/upload', {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(data.message, 'success');
      closeModal('modal-upload-csv');
      await loadDashboardOverview();
      await loadTransactions();
      await loadSubscriptions();
      await fetchAuditLogs();
    } else {
      showToast(data.detail || 'Failed to parse CSV.', 'danger');
    }
  } catch (err) {
    showToast('Failed to upload CSV statement.', 'danger');
  }
}

async function loadSampleStatement(type) {
  closeModal('modal-upload-csv');
  showToast('Reloading benchmark 50-transaction statement...', 'info');
  await loadDashboardOverview();
  await loadTransactions();
  await loadSubscriptions();
  await fetchAuditLogs();
  showToast('Standard 50-transaction statement benchmark reloaded.', 'success');
}

async function loadSubscriptions() {
  try {
    const res = await fetch('/api/subscriptions');
    const data = await res.json();
    subscriptionsData = data.subscriptions || [];
    renderSubscriptionsTable(subscriptionsData);

    const activeLeakage = data.active_annual_leakage_vnd !== undefined ? data.active_annual_leakage_vnd : data.total_annual_leakage_vnd;
    const savedLeakage = data.saved_annual_leakage_vnd || 0;

    if (document.getElementById('ghost-total-leakage')) {
      document.getElementById('ghost-total-leakage').textContent = `${formatCurrency(activeLeakage)} / yr`;
    }

    const savedContainer = document.getElementById('ghost-saved-container');
    const savedEl = document.getElementById('ghost-saved-leakage');
    if (savedContainer && savedEl) {
      if (savedLeakage > 0) {
        savedContainer.classList.remove('hidden');
        savedEl.textContent = `${formatCurrency(savedLeakage)} / yr`;
      } else {
        savedContainer.classList.add('hidden');
      }
    }
  } catch (err) {
    console.error('Failed to load subscriptions:', err);
  }
}

function renderSubscriptionsTable(subs) {
  const tbody = document.getElementById('subscriptions-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (subs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-4 text-center text-slate-500">No recurring subscriptions detected in current statement.</td></tr>`;
    return;
  }

  subs.forEach((sub, idx) => {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-slate-800/40 transition-colors';
    const isCancelled = sub.status === 'cancelled';

    const actionCell = isCancelled
      ? `<span class="px-2.5 py-1 rounded-lg bg-emerald-950/70 text-emerald-300 border border-emerald-800 font-bold text-[11px] flex items-center gap-1 w-max ml-auto">
           <i class="fa-solid fa-circle-check text-emerald-400"></i>
           <span>Cancelled</span>
         </span>`
      : `<button onclick="openUnsubscribeModal(${idx})" class="px-2.5 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 font-semibold transition-all flex items-center gap-1 ml-auto text-[11px]">
           <i class="fa-solid fa-ban text-[10px]"></i>
           <span>1-Click Unsubscribe</span>
         </button>`;

    tr.innerHTML = `
      <td class="p-3 font-bold text-white flex items-center gap-2">
        <i class="fa-solid fa-ghost ${isCancelled ? 'text-slate-500' : 'text-amber-400'}"></i>
        <span class="${isCancelled ? 'line-through text-slate-400' : ''}">${sub.merchant}</span>
      </td>
      <td class="p-3 font-semibold ${isCancelled ? 'text-slate-400' : 'text-rose-400'}">${formatCurrency(sub.amount)}</td>
      <td class="p-3 text-slate-300">${sub.frequency_days} days</td>
      <td class="p-3 text-slate-300">${sub.occurrences}</td>
      <td class="p-3 font-black ${isCancelled ? 'text-emerald-400' : 'text-rose-400'}">${formatCurrency(sub.annual_leakage)}</td>
      <td class="p-3 text-slate-400 font-mono text-[11px]">${sub.last_charged}</td>
      <td class="p-3 text-right">
        ${actionCell}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function openUnsubscribeModal(subIndex) {
  currentSelectedSub = subscriptionsData[subIndex];
  if (!currentSelectedSub) return;

  document.getElementById('unsub-modal-title').textContent = `Cancel ${currentSelectedSub.merchant} Subscription`;
  document.getElementById('unsub-portal-link').href = currentSelectedSub.unsubscribe_url;
  setUnsubLang('EN');
  openModal('modal-unsubscribe');
}

function setUnsubLang(lang) {
  currentSubLang = lang;
  const btnEn = document.getElementById('btn-unsub-lang-en');
  const btnVi = document.getElementById('btn-unsub-lang-vi');
  const textarea = document.getElementById('unsub-template-text');

  if (lang === 'EN') {
    if (btnEn) btnEn.className = 'px-3 py-1 rounded-lg text-xs font-bold bg-blue-600 text-white';
    if (btnVi) btnVi.className = 'px-3 py-1 rounded-lg text-xs font-medium text-slate-400 hover:text-white bg-slate-800';
    if (textarea) textarea.value = currentSelectedSub ? currentSelectedSub.email_template_en : '';
  } else {
    if (btnVi) btnVi.className = 'px-3 py-1 rounded-lg text-xs font-bold bg-blue-600 text-white';
    if (btnEn) btnEn.className = 'px-3 py-1 rounded-lg text-xs font-medium text-slate-400 hover:text-white bg-slate-800';
    if (textarea) textarea.value = currentSelectedSub ? currentSelectedSub.email_template_vi : '';
  }
}

function copyUnsubTemplate() {
  const textarea = document.getElementById('unsub-template-text');
  if (!textarea) return;
  navigator.clipboard.writeText(textarea.value);
  const btnText = document.getElementById('copy-btn-text');
  if (btnText) {
    btnText.textContent = 'Copied to Clipboard!';
    setTimeout(() => { btnText.textContent = 'Copy Email Notice'; }, 2000);
  }
  showToast('Cancellation template copied to clipboard.', 'success');
}

async function dispatchAutonomousUnsubscribe() {
  if (!currentSelectedSub) return;
  try {
    const res = await fetch(`/api/subscriptions/${encodeURIComponent(currentSelectedSub.merchant)}/cancel`, { method: 'POST' });
    const data = await res.json();
    showToast(`Autonomous unsubscribe notice logged for ${currentSelectedSub.merchant}.`, 'success');
    closeModal('modal-unsubscribe');
    await loadSubscriptions();
    await loadDashboardOverview();
    fetchAuditLogs();
  } catch (err) {
    showToast('Failed to dispatch autonomous cancellation.', 'danger');
  }
}

function fillDebatePreset(item, price, cat, just) {
  document.getElementById('debate-item-name').value = item;
  document.getElementById('debate-price').value = price;
  document.getElementById('debate-justification').value = just;
}

async function runFinancialDebate() {
  const item = document.getElementById('debate-item-name').value.trim();
  const price = parseFloat(document.getElementById('debate-price').value) || 0;
  const income = parseFloat(document.getElementById('debate-income').value) || 35000000;
  const justification = document.getElementById('debate-justification').value.trim();

  if (!item || price <= 0) {
    showToast('Please provide a valid item name and price.', 'warning');
    return;
  }

  const btn = document.getElementById('btn-run-debate');
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-sm"></i><span>Debating across 3 Agents...</span>`;

  try {
    const res = await fetch('/api/debate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_name: item,
        price: price,
        user_income: income,
        user_justification: justification
      })
    });
    const data = await res.json();
    renderDebateResults(data);
    fetchAuditLogs();
  } catch (err) {
    showToast('Failed to run financial debate.', 'danger');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="fa-solid fa-users-rays"></i><span>Trigger 3-Agent Financial Debate</span>`;
  }
}

function renderDebateResults(data) {
  const verdictCard = document.getElementById('debate-verdict-card');
  if (!verdictCard) return;
  verdictCard.classList.remove('hidden');

  const verdictStyles = {
    APPROVED: 'bg-emerald-950/40 border-emerald-600/60 text-emerald-300',
    CONDITIONAL_APPROVAL: 'bg-blue-950/40 border-blue-600/60 text-blue-300',
    DELAYED: 'bg-amber-950/40 border-amber-600/60 text-amber-300',
    DENIED: 'bg-rose-950/40 border-rose-600/60 text-rose-300',
  };

  const style = verdictStyles[data.verdict] || verdictStyles.DENIED;

  verdictCard.className = `p-4 rounded-2xl border transition-all ${style}`;
  verdictCard.innerHTML = `
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="text-xs font-bold uppercase tracking-wider">Executive Verdict:</span>
        <span class="px-2.5 py-0.5 rounded-full text-xs font-black bg-white/10 uppercase">${data.verdict}</span>
      </div>
      <span class="text-xs font-bold">Confidence: ${data.confidence_score}%</span>
    </div>
    <p class="text-xs mt-2 text-slate-200 leading-relaxed">${data.executive_summary}</p>
    <div class="mt-3 pt-2 border-t border-white/10 space-y-1">
      <span class="text-[11px] font-bold uppercase block text-slate-400">Mandated Action Plan:</span>
      ${data.action_plan.map(step => `<div class="flex items-center gap-1.5 text-xs text-slate-300"><i class="fa-solid fa-check text-[10px] text-emerald-400"></i><span>${step}</span></div>`).join('')}
    </div>
  `;

  const feed = document.getElementById('debate-feed');
  if (!feed) return;
  feed.innerHTML = '';

  data.turns.forEach(turn => {
    const bubble = document.createElement('div');
    const isOpt = turn.agent.includes('Optimist');
    const isRisk = turn.agent.includes('Risk');

    const bubbleClass = isOpt ? 'chat-bubble-optimist' : (isRisk ? 'chat-bubble-risk' : 'chat-bubble-arbiter');
    const avatarColor = isOpt ? 'text-emerald-400' : (isRisk ? 'text-rose-400' : 'text-purple-400');
    const icon = isOpt ? 'fa-wand-magic-sparkles' : (isRisk ? 'fa-triangle-exclamation' : 'fa-scale-balanced');

    bubble.className = `p-4 rounded-2xl ${bubbleClass} space-y-2`;
    bubble.innerHTML = `
      <div class="flex items-center justify-between text-xs font-bold">
        <span class="flex items-center gap-1.5 ${avatarColor}">
          <i class="fa-solid ${icon}"></i>
          <span>${turn.agent}</span>
        </span>
        <span class="text-[10px] uppercase px-2 py-0.5 rounded bg-black/30 text-slate-300">${turn.stance}</span>
      </div>
      <p class="text-xs text-slate-200 leading-relaxed">${turn.message}</p>
      ${turn.arguments.length ? `
        <div class="pt-1 flex flex-wrap gap-2 text-[10px] text-slate-400">
          ${turn.arguments.map(arg => `<span class="bg-black/20 px-2 py-0.5 rounded border border-white/5"><i class="fa-solid fa-arrow-right text-[8px] mr-1"></i>${arg}</span>`).join('')}
        </div>
      ` : ''}
    `;
    feed.appendChild(bubble);
  });
}

function initMonteCarloSliders() {
  updateMonteCarloLabels();
}

function updateMonteCarloLabels() {
  const savEl = document.getElementById('mc-input-savings');
  const incEl = document.getElementById('mc-input-income');
  const expEl = document.getElementById('mc-input-expenses');
  if (!savEl || !incEl || !expEl) return;

  const sav = parseFloat(savEl.value);
  const inc = parseFloat(incEl.value);
  const exp = parseFloat(expEl.value);

  document.getElementById('mc-disp-savings').textContent = formatCurrency(sav);
  document.getElementById('mc-disp-income').textContent = formatCurrency(inc);
  document.getElementById('mc-disp-expenses').textContent = formatCurrency(exp);
}

async function runMonteCarloSimulation() {
  const savEl = document.getElementById('mc-input-savings');
  const incEl = document.getElementById('mc-input-income');
  const expEl = document.getElementById('mc-input-expenses');
  if (!savEl || !incEl || !expEl) return;

  const sav = parseFloat(savEl.value);
  const inc = parseFloat(incEl.value);
  const exp = parseFloat(expEl.value);

  const btn = document.getElementById('btn-run-mc');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-sm"></i><span>Simulating 1,000 Stochastic Paths...</span>`;
  }

  try {
    const res = await fetch('/api/monte-carlo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        initial_savings: sav,
        monthly_income: inc,
        monthly_expenses: exp,
        num_simulations: 1000,
        months: 12
      })
    });
    const result = await res.json();
    renderMonteCarloResults(result);
  } catch (err) {
    console.error('Monte Carlo error:', err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-dice text-sm"></i><span>Simulate 1,000 Paths (12 Months)</span>`;
    }
  }
}

function renderMonteCarloResults(data) {
  if (document.getElementById('mc-resilience-score')) document.getElementById('mc-resilience-score').textContent = `${data.resilience_score} / 100`;
  if (document.getElementById('mc-depletion-risk')) document.getElementById('mc-depletion-risk').textContent = `${data.bankruptcy_probability} %`;
  if (document.getElementById('mc-rec-buffer')) document.getElementById('mc-rec-buffer').textContent = formatCurrency(data.recommended_emergency_buffer);
  if (document.getElementById('mc-summary-banner')) document.getElementById('mc-summary-banner').textContent = data.analysis_summary;

  const chartEl = document.getElementById('chart-monte-carlo');
  if (!chartEl) return;
  const ctx = chartEl.getContext('2d');
  if (chartMonteCarloInstance) chartMonteCarloInstance.destroy();

  chartMonteCarloInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.months,
      datasets: [
        {
          label: 'P90 (Optimistic 90th %)',
          data: data.percentile_90,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          fill: '+1',
          tension: 0.3,
          pointRadius: 2,
        },
        {
          label: 'P50 (Median Trajectory)',
          data: data.percentile_50,
          borderColor: '#8b5cf6',
          backgroundColor: 'transparent',
          borderWidth: 2.5,
          tension: 0.3,
          pointRadius: 3,
        },
        {
          label: 'P10 (Pessimistic Stress 10th %)',
          data: data.percentile_10,
          borderColor: '#f43f5e',
          backgroundColor: 'rgba(244, 63, 94, 0.1)',
          fill: '-1',
          tension: 0.3,
          pointRadius: 2,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          labels: { color: '#94a3b8', font: { family: 'Plus Jakarta Sans', size: 10 }, boxWidth: 12 }
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              return ` ${context.dataset.label}: ${formatCurrency(context.raw)}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#94a3b8', font: { family: 'Plus Jakarta Sans', size: 10 } }
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: {
            color: '#94a3b8',
            font: { family: 'Plus Jakarta Sans', size: 10 },
            callback: function(val) {
              return currentCurrency === 'USD' ? `$${(val / VND_TO_USD_RATE).toFixed(0)}` : `${(val / 1000000).toFixed(0)}M ₫`;
            }
          }
        }
      }
    }
  });
}

function fillScamPreset(preset) {
  if (preset === 'benign') {
    document.getElementById('scam-recipient').value = 'Nguyen Van Nam';
    document.getElementById('scam-account').value = '1029384756';
    document.getElementById('scam-bank').value = 'Vietcombank';
    document.getElementById('scam-amount').value = 500000;
    document.getElementById('scam-note').value = 'Tien chia hoa don an trua sinh nhat';
    document.getElementById('scam-yield').value = 0;
    document.getElementById('scam-source').value = 'Direct Friend Chat';
  } else if (preset === 'ponzi') {
    document.getElementById('scam-recipient').value = 'VIP Investment Robot AI';
    document.getElementById('scam-account').value = '999888777666';
    document.getElementById('scam-bank').value = 'Digital Overseas Bank';
    document.getElementById('scam-amount').value = 25000000;
    document.getElementById('scam-note').value = 'Chuyen tien gap trong 15 phut de vao phong VIP nhan lai 2.5% ngay';
    document.getElementById('scam-yield').value = 2.5;
    document.getElementById('scam-source').value = 'Telegram VIP Group Admin';
  } else if (preset === 'police') {
    document.getElementById('scam-recipient').value = 'Tai Khoan Tam Giu Chuyen An 09';
    document.getElementById('scam-account').value = '19034567890123';
    document.getElementById('scam-bank').value = 'Techcombank';
    document.getElementById('scam-amount').value = 30000000;
    document.getElementById('scam-note').value = 'Lenh bat khan cap yeu cau nop tien vao tai khoan bao chung trong 30 phut';
    document.getElementById('scam-yield').value = 0;
    document.getElementById('scam-source').value = 'Gia danh Cong An dieu tra';
  }
}

async function scanAntiScamTransfer() {
  const req = {
    recipient_name: document.getElementById('scam-recipient').value,
    recipient_account: document.getElementById('scam-account').value,
    bank_name: document.getElementById('scam-bank').value,
    amount: parseFloat(document.getElementById('scam-amount').value) || 0,
    transfer_note: document.getElementById('scam-note').value,
    advertised_yield_daily_pct: parseFloat(document.getElementById('scam-yield').value) || 0,
    source_context: document.getElementById('scam-source').value,
  };
  pendingScamTransferReq = req;

  try {
    const res = await fetch('/api/anti-scam/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req)
    });
    const data = await res.json();
    renderScamVerdict(data);
    fetchAuditLogs();

    if (data.is_locked) {
      openScamQuizModal(data);
    }
  } catch (err) {
    showToast('Failed to complete pre-flight scan.', 'danger');
  }
}

function renderScamVerdict(data) {
  const scoreDisp = document.getElementById('scam-score-display');
  const levelBadge = document.getElementById('scam-badge-level');
  const explanation = document.getElementById('scam-explanation');
  const tacticsList = document.getElementById('scam-tactics-list');

  if (scoreDisp) scoreDisp.textContent = `${data.risk_score} / 100 Risk Score`;
  if (explanation) explanation.textContent = data.explanation;

  const levelStyles = {
    LOW: 'bg-emerald-950 text-emerald-300 border border-emerald-800',
    MEDIUM: 'bg-amber-950 text-amber-300 border border-amber-800',
    HIGH: 'bg-orange-950 text-orange-300 border border-orange-800',
    CRITICAL: 'bg-rose-950 text-rose-300 border border-rose-800 font-black',
  };

  if (levelBadge) {
    levelBadge.className = `px-2.5 py-0.5 rounded-full text-xs uppercase ${levelStyles[data.risk_level] || ''}`;
    levelBadge.textContent = `${data.risk_level} RISK`;
  }

  if (tacticsList) {
    if (data.manipulation_tactics && data.manipulation_tactics.length > 0) {
      tacticsList.classList.remove('hidden');
      tacticsList.innerHTML = data.manipulation_tactics.map(t => `
        <div class="flex items-start gap-1.5 text-xs text-rose-300 bg-rose-950/30 p-2 rounded-lg border border-rose-900/30">
          <i class="fa-solid fa-triangle-exclamation text-[10px] mt-0.5 text-rose-400"></i>
          <span>${t}</span>
        </div>
      `).join('');
    } else {
      tacticsList.classList.add('hidden');
    }
  }
}

function openScamQuizModal(data) {
  activeQuizQuestions = data.cognitive_quiz || [];
  const container = document.getElementById('quiz-questions-container');
  if (!container) return;
  container.innerHTML = '';

  activeQuizQuestions.forEach((q, qIdx) => {
    const qDiv = document.createElement('div');
    qDiv.className = 'p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2 text-xs';
    qDiv.innerHTML = `
      <p class="font-bold text-slate-200">Question ${qIdx + 1}: ${q.question}</p>
      <div class="space-y-1.5 pt-1">
        ${q.options.map((opt, optIdx) => `
          <label class="flex items-start gap-2 p-2 rounded-lg hover:bg-slate-800 cursor-pointer text-slate-300 text-[11px] border border-transparent has-[:checked]:border-blue-500 has-[:checked]:bg-blue-950/20">
            <input type="radio" name="quiz_q_${qIdx}" value="${optIdx}" class="mt-0.5 text-blue-500">
            <span>${opt}</span>
          </label>
        `).join('')}
      </div>
    `;
    container.appendChild(qDiv);
  });

  startCoolingTimer(data.cooling_off_minutes || 60);
  openModal('modal-quiz');
}

function startCoolingTimer(minutes) {
  if (coolingTimerInterval) clearInterval(coolingTimerInterval);
  coolingSecondsRemaining = minutes * 60;

  function updateDisplay() {
    const m = Math.floor(coolingSecondsRemaining / 60);
    const s = coolingSecondsRemaining % 60;
    const disp = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    const el = document.getElementById('quiz-cooling-timer');
    if (el) el.textContent = disp;
  }

  updateDisplay();
  coolingTimerInterval = setInterval(() => {
    coolingSecondsRemaining--;
    if (coolingSecondsRemaining <= 0) {
      clearInterval(coolingTimerInterval);
    }
    updateDisplay();
  }, 1000);
}

async function submitCognitiveQuiz() {
  if (activeQuizQuestions.length === 0) return;

  let allCorrect = true;
  for (let i = 0; i < activeQuizQuestions.length; i++) {
    const selected = document.querySelector(`input[name="quiz_q_${i}"]:checked`);
    if (!selected || parseInt(selected.value) !== activeQuizQuestions[i].correct_option_index) {
      allCorrect = false;
      break;
    }
  }

  if (allCorrect) {
    showToast('Cognitive Quiz Passed! Prefrontal cortex reflection verified.', 'success');
    closeModal('modal-quiz');
    // This scanner is a preview: no money moves from here. A locked transfer is unlocked only in the
    // Agent Console, where cooling-off, quiz and one-time code are checked on the server.
    showToast('To release a locked transfer, use the Agent Console approval queue (one-time code required).', 'warning');
  } else {
    showToast('Incorrect answer: Please review the warnings carefully to protect against scam patterns.', 'danger');
  }
}

function openTransferModal(defaultSrc = 'Main Wallet') {
  document.getElementById('transfer-src').value = defaultSrc;
  openModal('modal-transfer');
}

async function executeWalletTransfer() {
  const src = document.getElementById('transfer-src').value;
  const dst = document.getElementById('transfer-dst').value;
  const amount = parseFloat(document.getElementById('transfer-amount').value) || 0;
  const note = document.getElementById('transfer-note').value;

  try {
    const res = await fetch('/api/wallets/transfer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_wallet: src,
        destination_wallet: dst,
        amount: amount,
        note: note,
        security_override: false
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      closeModal('modal-transfer');
      await loadDashboardOverview();
      await fetchAuditLogs();
    } else {
      if (data.status === 'HELD_FOR_APPROVAL') {
        pendingTier3Transfer = { src, dst, amount, note };
        document.getElementById('tier3-approval-reason').textContent = data.message;
        document.getElementById('tier3-from-wallet').textContent = src;
        document.getElementById('tier3-to-wallet').textContent = dst;
        document.getElementById('tier3-amount').textContent = formatCurrency(amount);
        openModal('modal-tier3-approval');
      } else {
        showToast(data.message, 'danger');
      }
    }
  } catch (err) {
    showToast('Transfer execution failed.', 'danger');
  }
}

async function confirmTier3HumanApproval() {
  if (!pendingTier3Transfer) return;
  // Tier 3 approval needs a one-time code checked on the server, which only the Agent Console offers.
  closeModal('modal-tier3-approval');
  closeModal('modal-transfer');
  showToast('Tier 3 transfers are approved in the Agent Console with a one-time code. Ask the agent there to make this transfer.', 'warning');
}

async function triggerAutoSavingsSweep() {
  try {
    const res = await fetch('/api/wallets/auto-sweep', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(`Autonomous Sweep: ${data.message}`, 'success');
      await loadDashboardOverview();
      await fetchAuditLogs();
    } else {
      showToast(`Sweep Status: ${data.message}`, 'info');
    }
  } catch (err) {
    showToast('Auto savings sweep error.', 'danger');
  }
}

async function handleOcrFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  showToast(`Uploading ${file.name} to Gemini Multimodal OCR...`, 'info');
  try {
    const res = await fetch('/api/ocr/receipt', { method: 'POST', body: formData });
    const data = await res.json();
    displayOcrResult(data);
  } catch (err) {
    showToast('OCR upload error.', 'danger');
  }
}

async function simulateOcrSample(filename) {
  const blob = new Blob(['simulated-receipt-content'], { type: 'image/jpeg' });
  const formData = new FormData();
  formData.append('file', blob, filename);

  try {
    const res = await fetch('/api/ocr/receipt', { method: 'POST', body: formData });
    const data = await res.json();
    displayOcrResult(data);
  } catch (err) {
    showToast('Simulate OCR error.', 'danger');
  }
}

function displayOcrResult(data) {
  const box = document.getElementById('ocr-result-box');
  if (!box) return;
  box.classList.remove('hidden');
  const d = data.data || {};
  box.innerHTML = `
    <div class="flex items-center justify-between text-indigo-300 font-bold border-b border-slate-800 pb-1">
      <span>OCR Extraction (${data.source})</span>
      <span class="text-white">${formatCurrency(d.total_amount)}</span>
    </div>
    <div class="text-slate-300 pt-1">
      <div><strong>Merchant:</strong> ${d.merchant}</div>
      <div><strong>Date:</strong> ${d.date}</div>
      <div><strong>Category:</strong> ${d.suggested_category} (${d.suggested_subcategory})</div>
      <div><strong>Notes:</strong> ${d.notes || 'N/A'}</div>
    </div>
  `;
  showToast(`Receipt analyzed: ${d.merchant} (${formatCurrency(d.total_amount)})`, 'success');
  fetchAuditLogs();
}

async function fetchAuditLogs() {
  try {
    const res = await fetch('/api/audit-logs?limit=30');
    const data = await res.json();
    renderAuditLogsTable(data.logs || []);
  } catch (err) {
    console.warn('Failed to fetch audit logs:', err);
  }
}

function renderAuditLogsTable(logs) {
  const tbody = document.getElementById('audit-logs-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (logs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-3 text-center text-slate-600">No logs generated yet.</td></tr>`;
    return;
  }

  logs.forEach(entry => {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-slate-900/60 transition-colors';

    const tierColors = {
      'Tier 1': 'text-slate-400 bg-slate-900',
      'Tier 2': 'text-blue-400 bg-blue-950/40',
      'Tier 3': 'text-rose-400 bg-rose-950/40 font-bold',
    };

    const statusColors = {
      SUCCESS: 'text-emerald-400',
      AUTO_EXECUTED: 'text-blue-400',
      ACTIVE: 'text-emerald-400',
      HELD_FOR_APPROVAL: 'text-amber-400',
      LOCKDOWN_ENFORCED: 'text-rose-400 font-bold',
    };

    const tColor = tierColors[entry.tier] || 'text-slate-400';
    const sColor = statusColors[entry.status] || 'text-slate-300';
    const shortTime = entry.timestamp.split('T')[1]?.split('.')[0] || entry.timestamp;

    tr.innerHTML = `
      <td class="p-2 text-slate-500">${shortTime}</td>
      <td class="p-2"><span class="px-1.5 py-0.5 rounded text-[10px] ${tColor}">${entry.tier}</span></td>
      <td class="p-2 text-slate-300 font-semibold">${entry.module}</td>
      <td class="p-2 text-blue-300">${entry.action}</td>
      <td class="p-2 ${sColor}">${entry.status}</td>
      <td class="p-2 text-slate-500 font-mono text-[10px]">${entry.trace_hash}</td>
      <td class="p-2 text-slate-400 max-w-xs truncate" title='${JSON.stringify(entry.details)}'>${JSON.stringify(entry.details)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('hidden');
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden');
}

// ---------------------------------------------------------------------------
// Agent hero (pipeline rail, conversation, approvals, Guardian intercept)
// Upgraded with Payee Verification Details, Live Step Progress, and closest() fix
// ---------------------------------------------------------------------------
(function () {
  const PHASES = ['INTAKE', 'GUARDRAIL', 'PLAN', 'PREFLIGHT', 'EXECUTE', 'REPLAN', 'AWAIT_HUMAN', 'REFLECT'];
  const PHASE_LABELS = {
    INTAKE: '1/8 INTAKE · Loading profile & statement...',
    GUARDRAIL: '2/8 GUARDRAIL · Scanning Prompt Injection & PII...',
    PLAN: '3/8 PLAN · Selecting tools...',
    PREFLIGHT: '4/8 PREFLIGHT · Validating 3-Tier Matrix & Guardian...',
    EXECUTE: '5/8 EXECUTE · Running sandbox tools...',
    REPLAN: '6/8 REPLAN · Checking follow-up rules...',
    AWAIT_HUMAN: '7/8 AWAIT_HUMAN · Updating approval queue...',
    REFLECT: '8/8 REFLECT · Verifying numbers (Zero-Hallucination)...'
  };
  const agentSession = 'web-' + Math.random().toString(36).slice(2, 8);
  let pendingAttachment = null;
  let coolTimers = [];
  let heroThinkingTimer = null;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const vnd = (n) => Number(n).toLocaleString('en-US') + ' ₫';
  const tierCls = (t) => ({ 'Tier 1': 't1', 'Tier 2': 't2', 'Tier 3': 't3' }[t] || '');
  const vColor = (v) => ({ EXECUTE: 'text-emerald-300', AWAIT_HUMAN: 'text-amber-300', LOCKED: 'text-rose-300', REJECT: 'text-slate-500' }[v] || 'text-slate-300');

  function maskAccount(acc) {
    const s = String(acc || '').trim();
    if (!s) return '';
    return s.length >= 8 ? `${s.slice(0, 3)}****${s.slice(-3)}` : '****';
  }

  function formatApprovalDetails(args, tool) {
    if (!args) return '';
    const parts = [];
    if (tool === 'transfer_external') {
      if (args.payee_name) parts.push(`👤 Người nhận: <b>${esc(args.payee_name)}</b>`);
      if (args.bank) parts.push(`🏦 Ngân hàng: <b>${esc(String(args.bank).toUpperCase())}</b>`);
      if (args.payee_account) parts.push(`💳 STK: <b>${esc(maskAccount(args.payee_account))}</b>`);
    } else if (tool === 'transfer_internal') {
      const src = args.source ? String(args.source).replace(/_/g, ' ').toUpperCase() : 'MAIN';
      const dst = args.destination ? String(args.destination).replace(/_/g, ' ').toUpperCase() : 'VAULT';
      parts.push(`🔄 Chuyển nội bộ: <b>${esc(src)}</b> ➔ <b>${esc(dst)}</b>`);
    } else if (tool === 'cancel_subscription') {
      if (args.merchant) parts.push(`🚫 Hủy đăng ký: <b>${esc(args.merchant)}</b>`);
    }
    return parts.join(' · ');
  }

  async function getJSON(url, opts) {
    const r = await fetch(url, opts);
    if (r.status === 401) throw new Error('Access token missing: open the page with ?token=...');
    return r.json();
  }

  function refreshDashboard() {
    for (const fn of ['loadDashboardOverview', 'fetchAuditLogs', 'loadTransactions', 'loadSubscriptions']) {
      if (typeof window[fn] === 'function') { try { window[fn](); } catch (e) { /* optional */ } }
    }
  }

  async function loadModelChip() {
    try {
      const h = await getJSON('/api/health');
      const el = $('hero-model');
      if (!el) return;
      el.innerHTML = h.gemini_configured
        ? `<i class="fa-solid fa-circle text-[7px] text-emerald-400 mr-1"></i>${esc(h.gemini_model)} · ${h.gemini_keys} key${h.gemini_keys === 1 ? '' : 's'}`
        : `<i class="fa-solid fa-circle text-[7px] text-amber-400 mr-1"></i>offline rules · no model`;
    } catch (e) { /* ignore */ }
  }

  function resetRail() {
    if (heroThinkingTimer) { clearInterval(heroThinkingTimer); heroThinkingTimer = null; }
    document.querySelectorAll('#agent-rail .rail-node').forEach(n => { n.className = 'rail-node'; n.querySelector('.rail-detail').textContent = ''; });
  }

  function startHeroThinking() {
    resetRail();
    let idx = 0;
    const bubbleId = 'hero-thinking-' + Date.now();
    $('agent-chat').insertAdjacentHTML('beforeend', `
      <div id="${bubbleId}" class="flex items-start gap-3">
        <div class="h-7 w-7 rounded-lg bg-emerald-500/20 text-emerald-300 flex items-center justify-center shrink-0"><i class="fa-solid fa-spinner fa-spin text-xs"></i></div>
        <div class="bg-slate-900/90 border border-emerald-500/40 rounded-2xl rounded-tl-sm px-4 py-3 text-xs text-emerald-300 font-mono space-y-2 flex-1">
          <div class="thinking-label">${esc(PHASE_LABELS[PHASES[0]])}</div>
          <div class="flex flex-wrap gap-1">
            ${PHASES.map((p, i) => `<span data-hstep="${p}" class="px-2 py-0.5 rounded border ${i === 0 ? 'bg-emerald-500 text-slate-900 border-emerald-400 font-bold' : 'border-slate-700 text-slate-500'} text-[10px]">${p}</span>`).join('')}
          </div>
        </div>
      </div>`);
    scrollChat();

    const first = document.querySelector(`#agent-rail .rail-node[data-phase="${PHASES[0]}"]`);
    if (first) { first.className = 'rail-node active pulse'; first.querySelector('.rail-detail').textContent = 'running...'; }

    heroThinkingTimer = setInterval(() => {
      idx = Math.min(idx + 1, PHASES.length - 1);
      const p = PHASES[idx];
      const n = document.querySelector(`#agent-rail .rail-node[data-phase="${p}"]`);
      if (n) { n.className = 'rail-node active pulse'; n.querySelector('.rail-detail').textContent = 'processing...'; }
      const box = $(bubbleId);
      if (box) {
        const lbl = box.querySelector('.thinking-label');
        if (lbl) lbl.textContent = PHASE_LABELS[p] || p;
        box.querySelectorAll('[data-hstep]').forEach((el, i) => {
          el.className = 'px-2 py-0.5 rounded border text-[10px] ' + (
            i < idx ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' :
            (i === idx ? 'bg-emerald-500 text-slate-900 border-emerald-400 font-bold' : 'border-slate-700 text-slate-500')
          );
        });
      }
    }, 320);

    return bubbleId;
  }

  function stopHeroThinking(bubbleId) {
    if (heroThinkingTimer) { clearInterval(heroThinkingTimer); heroThinkingTimer = null; }
    const box = $(bubbleId);
    if (box) box.remove();
  }

  function railDetail(t, turn) {
    switch (t.phase) {
      case 'INTAKE': return t.detail;
      case 'GUARDRAIL': return turn.flags.includes('INJECTION_SUSPECTED') ? 'injection suspected · autonomy downgraded' : 'clean';
      case 'PLAN': return `${turn.intent} · ${(turn.plan || []).map(c => c.tool).join(' → ') || 'no tools'}`;
      case 'PREFLIGHT': return (turn.decisions || []).map(d => `${d.call.tool.replace('transfer_', '')}: ${d.verdict}`).join(' · ');
      case 'EXECUTE': return `${turn.results.length} tool${turn.results.length === 1 ? '' : 's'} run`;
      case 'REPLAN': return t.detail.replace('added ', '+ ');
      case 'AWAIT_HUMAN': return `${turn.queued.length} waiting for you`;
      case 'REFLECT': return turn.reflect.grounded ? 'every number traced to a tool' : `regenerated (${(turn.reflect.unmatched || []).join(', ')})`;
      default: return t.detail;
    }
  }

  function playRail(turn) {
    resetRail();
    const verdicts = (turn.decisions || []).map(d => d.verdict);
    (turn.trace || []).filter(t => PHASES.includes(t.phase)).forEach((t, i) => {
      setTimeout(() => {
        const n = document.querySelector(`#agent-rail .rail-node[data-phase="${t.phase}"]`);
        if (!n) return;
        let cls = 'rail-node active pulse';
        if (t.phase === 'GUARDRAIL' && turn.flags.includes('INJECTION_SUSPECTED')) cls = 'rail-node warn pulse';
        if (t.phase === 'PREFLIGHT' && verdicts.includes('LOCKED')) cls = 'rail-node alarm pulse';
        else if (t.phase === 'PREFLIGHT' && verdicts.includes('AWAIT_HUMAN')) cls = 'rail-node warn pulse';
        if (t.phase === 'AWAIT_HUMAN') cls = verdicts.includes('LOCKED') ? 'rail-node alarm pulse' : 'rail-node warn pulse';
        if (t.phase === 'REFLECT' && turn.reflect.regenerated) cls = 'rail-node warn pulse';
        n.className = cls;
        n.querySelector('.rail-detail').textContent = railDetail(t, turn);
      }, 90 * i);
    });
    $('agent-trace').innerHTML = (turn.trace || []).map(t => `<li><span class="text-emerald-300">${esc(t.phase)}</span> <span class="text-slate-500">${esc(t.detail)}</span></li>`).join('');
  }

  function scrollChat() { const c = $('agent-chat'); if (c) c.scrollTop = c.scrollHeight; }
  function addUser(text) {
    $('agent-chat').insertAdjacentHTML('beforeend', `<div class="flex justify-end"><div class="bg-blue-600/90 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 max-w-[85%]">${esc(text)}</div></div>`);
    scrollChat();
  }

  function buildHeroInlineActions(turn) {
    const blocks = [];
    if (turn.queued && turn.queued.length) {
      turn.queued.forEach(q => {
        const locked = q.verdict === 'LOCKED';
        const amt = q.args && q.args.amount ? vnd(q.args.amount) : q.tool;
        const until = (q.unlock && q.unlock.cooling_off_until) || '';
        const details = formatApprovalDetails(q.args, q.tool);

        blocks.push(`
          <div class="rounded-xl border ${locked ? 'border-rose-500/60 bg-rose-950/30' : 'border-amber-500/50 bg-slate-900/90'} p-3 mt-2 flex flex-wrap items-center justify-between gap-2" data-req-box="${esc(q.id)}">
            <div class="space-y-0.5">
              <div class="text-[10px] font-mono font-bold ${locked ? 'text-rose-400' : 'text-amber-300'}">${locked ? '⛔ GUARDIAN LOCKDOWN' : '⏳ AWAITING HUMAN APPROVAL'}</div>
              <div class="text-xs font-mono font-semibold text-white">${esc(q.tool)} · ${esc(amt)}</div>
              ${details ? `<div class="text-[11.5px] text-slate-300">${details}</div>` : ''}
              ${locked ? `<div class="text-[11px] font-mono text-amber-300 cool" data-until="${esc(until)}">cooling-off…</div>` : ''}
            </div>
            <div class="flex gap-2 ia-btns">
              <button type="button" class="px-3 py-1.5 rounded-lg text-xs font-semibold ${locked ? 'bg-rose-600 hover:bg-rose-500 text-white' : 'bg-emerald-500 hover:bg-emerald-400 text-slate-900'}" data-approve="${esc(q.id)}" data-quiz="${!!(q.unlock && q.unlock.quiz_required)}" data-until="${esc(until)}">
                ${locked ? '🔓 Unlock (Quiz)' : '✓ Approve'}
              </button>
              <button type="button" class="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-600 hover:border-rose-400 text-slate-200" data-reject="${esc(q.id)}">
                ✕ Cancel / Reject
              </button>
            </div>
          </div>`);
      });
    }

    const subRes = (turn.results || []).find(r => r.tool === 'scan_subscriptions' && r.output && r.output.subscriptions);
    if (subRes) {
      const activeSubs = subRes.output.subscriptions.filter(s => s.status === 'active');
      if (activeSubs.length) {
        blocks.push(`
          <div class="flex flex-wrap items-center gap-1.5 mt-2 p-2.5 rounded-xl border border-slate-800 bg-slate-900/70">
            <span class="text-[11px] font-mono text-slate-400 mr-1">1-Click Cancel:</span>
            ${activeSubs.map(s => `
              <button type="button" class="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-amber-500/10 hover:bg-amber-500 text-amber-300 hover:text-slate-950 border border-amber-500/40 transition-all" data-cancel-sub="${esc(s.merchant)}">
                🚫 Cancel ${esc(s.merchant)} (${vnd(s.amount)})
              </button>`).join('')}
          </div>`);
      }
    }
    return blocks.join('');
  }

  function addAgent(turn) {
    const stepBadges = (turn.trace || []).filter(t => PHASES.includes(t.phase)).map(t =>
      `<span class="px-1.5 py-0.5 rounded bg-emerald-950/80 border border-emerald-700/40 text-emerald-300 text-[10px] font-mono" title="${esc(t.detail)}">✓ ${esc(t.phase)}</span>`
    ).join('<span class="text-slate-600 text-[10px]">→</span>');

    const cards = (turn.decisions || []).map(d => `
      <div class="rounded-xl border border-slate-800 bg-slate-900/70 p-2.5 text-xs">
        <div class="flex justify-between items-center gap-2"><span class="font-mono font-semibold text-slate-200">${esc(d.call.tool)}</span><span class="tier-chip ${tierCls(d.tier)}">${esc(d.tier)}</span></div>
        <div class="font-mono ${vColor(d.verdict)} mt-1">${esc(d.verdict)}</div>
        <div class="text-slate-500 mt-0.5">${esc((d.reasons || []).join(' · '))}</div>
      </div>`).join('');

    const inlineActions = buildHeroInlineActions(turn);
    const meta = [];
    meta.push(turn.reflect && turn.reflect.grounded ? `<span class="text-emerald-400"><i class="fa-solid fa-circle-check mr-1"></i>numbers grounded in tool outputs</span>`
                                    : `<span class="text-amber-400"><i class="fa-solid fa-rotate mr-1"></i>narrative regenerated (${esc((turn.reflect && turn.reflect.unmatched) || []).join(', ')})</span>`);
    if (turn.flags && turn.flags.length) meta.push(`<span class="text-rose-300"><i class="fa-solid fa-triangle-exclamation mr-1"></i>${esc(turn.flags.join(', '))}</span>`);
    meta.push(`<span class="text-slate-500">${(turn.results || []).length} tool${(turn.results || []).length === 1 ? '' : 's'} · ${(turn.queued || []).length} queued</span>`);

    $('agent-chat').insertAdjacentHTML('beforeend', `
      <div class="flex items-start gap-3">
        <div class="h-7 w-7 rounded-lg bg-emerald-500/20 text-emerald-300 flex items-center justify-center shrink-0"><i class="fa-solid fa-robot text-xs"></i></div>
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-1 mb-1.5">${stepBadges}</div>
          <div class="bg-slate-900/80 border border-slate-800 rounded-2xl rounded-tl-sm px-4 py-3 text-slate-100 whitespace-pre-wrap">${esc(turn.response)}</div>
          ${inlineActions}
          <div class="grid grid-cols-1 md:grid-cols-2 gap-1.5 mt-2">${cards}</div>
          <div class="flex flex-wrap gap-3 mt-1.5 text-[11px] font-mono">${meta.join('')}</div>
        </div>
      </div>`);
    bindHeroCoolTimers();
    scrollChat();
  }

  function addNote(html) {
    $('agent-chat').insertAdjacentHTML('beforeend', `<div class="text-[11px] font-mono text-slate-300 pl-10 py-1">${html}</div>`);
    scrollChat();
  }

  async function sendAgent(text) {
    if (!text || !text.trim()) return;
    addUser(text);
    const fd = new FormData();
    fd.append('text', text); fd.append('session_id', agentSession);
    if (pendingAttachment) { fd.append('files', pendingAttachment, pendingAttachment.name); pendingAttachment = null; $('agent-attach').innerHTML = '<i class="fa-regular fa-image mr-1"></i>Screenshot'; }
    $('agent-send').disabled = true;
    const thinkingId = startHeroThinking();
    try {
      const turn = await getJSON('/api/agent/chat', { method: 'POST', body: fd });
      stopHeroThinking(thinkingId);
      playRail(turn); addAgent(turn);
      const locked = (turn.decisions || []).find(d => d.verdict === 'LOCKED' && d.guardian);
      if (locked) showIntercept(locked.guardian);
      loadApprovals(); refreshDashboard();
    } catch (e) {
      stopHeroThinking(thinkingId);
      addNote(`<span class="text-rose-300">request failed: ${esc(e.message)}</span>`);
    } finally { $('agent-send').disabled = false; }
  }

  function bindHeroCoolTimers() {
    coolTimers.forEach(clearInterval); coolTimers = [];
    document.querySelectorAll('.cool[data-until]').forEach(el => {
      const until = el.dataset.until ? new Date(el.dataset.until).getTime() : 0;
      const tick = () => {
        const s = Math.max(0, Math.round((until - Date.now()) / 1000));
        el.textContent = s > 0
          ? `⏳ cooling-off ${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')} · quiz required`
          : '✓ cooling-off over · ready for safety quiz';
      };
      tick(); coolTimers.push(setInterval(tick, 1000));
    });
  }

  async function loadApprovals() {
    try {
      const d = await getJSON('/api/agent/approvals');
      const countEl = $('agent-pending-count');
      if (countEl) countEl.textContent = (d.pending || []).length;
      const box = $('agent-approvals');
      if (!box) return;
      if (!d.pending || !d.pending.length) {
        box.innerHTML = '<div class="text-slate-500">Nothing waiting. Tier 1 and Tier 2 actions run on their own.</div>';
        bindHeroCoolTimers();
        return;
      }
      box.innerHTML = d.pending.map(p => {
        const locked = p.verdict === 'LOCKED';
        const until = (p.unlock && p.unlock.cooling_off_until) || '';
        const amt = p.args.amount ? vnd(p.args.amount) : Object.entries(p.args).filter(([k]) => !['evidence_text', 'note', 'human_approved', 'payee_name', 'payee_account', 'bank'].includes(k)).map(([k, v]) => `${k}=${v}`).join(', ');
        const details = formatApprovalDetails(p.args, p.tool);

        return `<div class="rounded-xl border ${locked ? 'border-rose-500/50' : 'border-slate-700'} bg-slate-900/70 p-2.5">
          <div class="flex justify-between items-center"><span class="font-mono font-semibold text-slate-200">${locked ? '⛔ ' : ''}${esc(p.tool)}</span><span class="tier-chip ${tierCls(p.tier)}">${esc(p.tier)}</span></div>
          <div class="font-mono text-slate-300 mt-1">${esc(amt)}</div>
          ${details ? `<div class="text-[11.5px] text-slate-300 mt-1">${details}</div>` : ''}
          <div class="text-slate-500 mt-0.5">${esc((p.reasons || []).slice(0, 3).join(' · '))}</div>
          ${locked ? `<div class="font-mono text-amber-300 mt-1 cool" data-until="${esc(until)}">cooling-off…</div>` : ''}
          <div class="flex gap-1.5 mt-2">
            <button type="button" class="px-2.5 py-1 rounded-lg ${locked ? 'bg-rose-700 hover:bg-rose-600 text-white' : 'bg-emerald-500 hover:bg-emerald-400 text-slate-900'} font-semibold" data-approve="${esc(p.id)}" data-quiz="${!!(p.unlock && p.unlock.quiz_required)}" data-until="${esc(until)}">${locked ? '🔓 Unlock (quiz)' : '✓ Approve'}</button>
            <button type="button" class="px-2.5 py-1 rounded-lg border border-slate-600 hover:border-rose-400 text-slate-300" data-reject="${esc(p.id)}">✕ Reject</button>
          </div></div>`;
      }).join('');
      bindHeroCoolTimers();
    } catch (e) { /* ignore */ }
  }

  async function decide(id, approve, quiz) {
    const d = await getJSON(`/api/agent/approvals/${id}/decide`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approve, quiz_answers: quiz }) });
    const cls = d.status === 'APPROVED' ? 'text-emerald-400' : (d.status === 'PENDING' ? 'text-amber-400' : 'text-rose-300');
    addNote(`<span class="${cls}">Approval [${esc(id)}] → ${esc(d.status)}: ${esc(d.message || '')}</span>`);
    if (typeof showToast === 'function') showToast(`${d.status}: ${d.message || ''}`, d.status === 'APPROVED' ? 'success' : (d.status === 'PENDING' ? 'warning' : 'info'));
    if (d.status === 'APPROVED' || d.status === 'REJECTED') {
      document.querySelectorAll(`[data-req-box="${id}"]`).forEach(el => {
        const btns = el.querySelector('.ia-btns');
        if (btns) btns.innerHTML = `<span class="${cls} font-mono text-xs">Decision recorded: ${esc(d.status)}</span>`;
      });
    }
    loadApprovals(); refreshDashboard();
  }

  async function openQuiz(id, untilIso) {
    const untilMs = untilIso ? new Date(untilIso).getTime() : 0;
    const remSec = Math.max(0, Math.round((untilMs - Date.now()) / 1000));
    if (remSec > 0) {
      if (typeof showToast === 'function') showToast(`Cooling-off active! Wait ${remSec}s to unlock, or click Reject to cancel immediately.`, 'warning');
      addNote(`<span class="text-amber-300">⏳ Cooling-off period active (${remSec}s remaining). Please wait or click Reject to cancel immediately.</span>`);
      return;
    }
    const q = await getJSON('/api/agent/quiz');
    const form = $('quiz-form');
    form.innerHTML = `<h3 class="text-base font-bold text-rose-400">🛡️ Cognitive safety check</h3>` + q.questions.map((qq, i) => `<fieldset class="space-y-1"><legend class="font-semibold text-slate-100 mb-1">${i + 1}. ${esc(qq.question)}</legend>${qq.options.map((o, j) => `<label class="block text-slate-300 hover:text-white cursor-pointer"><input type="radio" name="q${i}" value="${j}" required class="mr-2">${esc(o)}</label>`).join('')}</fieldset>`).join('')
      + `<div class="flex gap-2 pt-2"><button class="px-4 py-2 rounded-xl bg-emerald-500 text-slate-900 font-semibold" type="submit">Submit answers</button><button type="button" id="quiz-cancel" class="px-4 py-2 rounded-xl border border-slate-600">Cancel</button></div>`;
    form.onsubmit = (e) => { e.preventDefault(); const ans = q.questions.map((_, i) => Number(form[`q${i}`].value)); $('quiz-modal').classList.add('hidden'); decide(id, true, ans); };$('quiz-cancel').onclick = () => $('quiz-modal').classList.add('hidden');$('quiz-modal').classList.remove('hidden');
  }

  function showIntercept(g) {
    const risk = Math.round(g.risk_score), r = 34, c = 2 * Math.PI * r;
    $('guardian-arc').setAttribute('stroke-dasharray', `${(risk / 100) * c} ${c}`);
    $('guardian-score').textContent = risk;
    $('guardian-kind').textContent = (g.scam_type || 'suspicious transfer').replace(/_/g, ' ').toUpperCase();
    $('guardian-reason').textContent = (g.recommended_actions \vert{}\vert{} []).join(' · ');$('guardian-evidence').innerHTML = (g.evidence || []).map(e => `<li>${esc(e)}</li>`).join('') || '<li>Behavioural signals only</li>';
    $('guardian-facts').innerHTML = (g.counter_facts || []).map(e => `<li>${esc(e)}</li>`).join('');
    $('guardian-overlay').classList.remove('hidden');
    let s = g.cooling_off_seconds || 60; const el = $('guardian-countdown'); el.textContent = s;
    const iv = setInterval(() => { s -= 1; el.textContent = Math.max(0, s); if (s <= 0) clearInterval(iv); }, 1000);
  }

  function handleHeroClick(e) {
    const approveBtn = e.target.closest('[data-approve]');
    if (approveBtn) {
      const id = approveBtn.dataset.approve;
      const needsQuiz = approveBtn.dataset.quiz === 'true';
      const until = approveBtn.dataset.until || '';
      if (needsQuiz) openQuiz(id, until);
      else decide(id, true, null);
      return;
    }
    const rejectBtn = e.target.closest('[data-reject]');
    if (rejectBtn) {
      decide(rejectBtn.dataset.reject, false, null);
      return;
    }
    const cancelSubBtn = e.target.closest('[data-cancel-sub]');
    if (cancelSubBtn) {
      const m = cancelSubBtn.dataset.cancelSub;
      cancelSubBtn.disabled = true;
      sendAgent(`cancel my ${m} subscription`);
      return;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const form = $('agent-form');
    if (!form) return;
    loadModelChip(); loadApprovals();
    const ask = new URLSearchParams(location.search).get('ask');
    if (ask) setTimeout(() => sendAgent(ask), 300);
    form.addEventListener('submit', e => { e.preventDefault(); const t = $('agent-text'); const v = t.value; t.value = ''; sendAgent(v); });
    const quickBar = $('agent-quick');
    if (quickBar) {
      quickBar.addEventListener('click', e => {
        const btn = e.target.closest('[data-q]');
        if (btn) sendAgent(btn.dataset.q);
      });
    }
    const monthBtn = $('agent-month');
    if (monthBtn) monthBtn.addEventListener('click', () => sendAgent('run my month'));
    const attachBtn = $('agent-attach');
    if (attachBtn) attachBtn.addEventListener('click', () => $('agent-file').click());
    const fileEl = $('agent-file');
    if (fileEl) fileEl.addEventListener('change', e => { pendingAttachment = e.target.files[0]; if (pendingAttachment && $('agent-attach'))$('agent-attach').innerHTML = '<i class="fa-solid fa-paperclip mr-1"></i>' + esc(pendingAttachment.name); });
    const guardClose = $('guardian-close');
    if (guardClose) guardClose.addEventListener('click', () => $('guardian-overlay').classList.add('hidden'));
    const clearBtn = $('rail-clear');
    if (clearBtn) clearBtn.addEventListener('click', resetRail);
    const appBox = $('agent-approvals');
    if (appBox) appBox.addEventListener('click', handleHeroClick);
    const chatBox = $('agent-chat');
    if (chatBox) chatBox.addEventListener('click', handleHeroClick);
  });
})();
