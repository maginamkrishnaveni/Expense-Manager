// ===== STATE =====
const STORAGE_KEY = 'flat_expense_manager';

const MEMBER_COLORS = [
  '#6c63ff', '#ff6584', '#43b89c', '#f39c12',
  '#9b59b6', '#e67e22', '#1abc9c', '#e74c3c'
];

let state = {
  members: ['You', 'Flatmate 1', 'Flatmate 2'],
  contributions: [],  // { id, member, amount, note, date }
  expenses: []        // { id, paidBy, amount, category, description, date, splitBetween[] }
};

// ===== PERSISTENCE =====
function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function loadState() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored) {
    try {
      const parsed = JSON.parse(stored);
      state = { ...state, ...parsed };
    } catch (e) {
      console.error('Failed to load state', e);
    }
  }
}

// ===== UTILITIES =====
function genId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

function formatCurrency(amount) {
  return '₹' + Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

function todayValue() {
  return new Date().toISOString().split('T')[0];
}

function getMemberColor(index) {
  return MEMBER_COLORS[index % MEMBER_COLORS.length];
}

function getMemberInitials(name) {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

// ===== RENDER MEMBERS =====
function renderMembers() {
  const list = document.getElementById('members-list');
  list.innerHTML = state.members.map((m, i) => `
    <div class="member-chip">
      <div class="member-avatar" style="background:${getMemberColor(i)}">${getMemberInitials(m)}</div>
      ${m}
    </div>
  `).join('');
}

// ===== POPULATE SELECTS =====
function populateSelects() {
  const memberSelects = ['contrib-member', 'exp-paid-by'];
  memberSelects.forEach(id => {
    const sel = document.getElementById(id);
    const current = sel.value;
    sel.innerHTML = state.members.map(m => `<option value="${m}">${m}</option>`).join('');
    if (state.members.includes(current)) sel.value = current;
  });

  // Split between checkboxes
  const splitDiv = document.getElementById('exp-split-members');
  splitDiv.innerHTML = state.members.map((m, i) => `
    <label class="checkbox-label">
      <input type="checkbox" value="${m}" checked />
      <span class="member-avatar" style="background:${getMemberColor(i)};width:18px;height:18px;font-size:0.6rem">${getMemberInitials(m)}</span>
      ${m}
    </label>
  `).join('');
}

// ===== RENDER SUMMARY =====
function renderSummary() {
  const totalContrib = state.contributions.reduce((s, c) => s + Number(c.amount), 0);
  const totalExpenses = state.expenses.reduce((s, e) => s + Number(e.amount), 0);
  const pool = totalContrib - totalExpenses;

  // Per-member stats
  const memberStats = {};
  state.members.forEach(m => {
    memberStats[m] = { contributed: 0, spent: 0 };
  });

  state.contributions.forEach(c => {
    if (memberStats[c.member]) {
      memberStats[c.member].contributed += Number(c.amount);
    }
  });

  state.expenses.forEach(e => {
    if (memberStats[e.paidBy]) {
      memberStats[e.paidBy].spent += Number(e.amount);
    }
  });

  const content = document.getElementById('summary-content');

  const statsHtml = `
    <div class="summary-grid">
      <div class="summary-stat">
        <div class="stat-label">Total Collected</div>
        <div class="stat-value" style="color:#2ecc71">${formatCurrency(totalContrib)}</div>
      </div>
      <div class="summary-stat">
        <div class="stat-label">Total Spent</div>
        <div class="stat-value" style="color:#e74c3c">${formatCurrency(totalExpenses)}</div>
      </div>
      <div class="summary-stat">
        <div class="stat-label">Pool Balance</div>
        <div class="stat-value" style="color:${pool >= 0 ? '#2ecc71' : '#e74c3c'}">${formatCurrency(pool)}</div>
      </div>
      <div class="summary-stat">
        <div class="stat-label">Transactions</div>
        <div class="stat-value">${state.expenses.length}</div>
      </div>
    </div>

    <div class="member-balance-list">
      ${state.members.map((m, i) => {
        const stats = memberStats[m] || { contributed: 0, spent: 0 };
        const net = stats.contributed - stats.spent;
        const netClass = net > 0 ? 'positive' : net < 0 ? 'negative' : 'zero';
        const netLabel = net > 0 ? `+${formatCurrency(net)}` : formatCurrency(net);
        return `
          <div class="member-balance-item">
            <div class="member-avatar" style="background:${getMemberColor(i)}">${getMemberInitials(m)}</div>
            <div class="name">${m}</div>
            <div class="contrib">↑ ${formatCurrency(stats.contributed)}</div>
            <div class="spent">↓ ${formatCurrency(stats.spent)}</div>
            <div class="net ${netClass}">${netLabel}</div>
          </div>
        `;
      }).join('')}
    </div>

    <div class="pool-info ${pool < 0 ? 'overspent' : ''}">
      ${pool >= 0
        ? `✅ Pool has ${formatCurrency(pool)} remaining. You're on track!`
        : `⚠️ Pool is short by ${formatCurrency(Math.abs(pool))}. Someone covered from their own pocket.`}
    </div>
  `;

  content.innerHTML = statsHtml;
}

// ===== RENDER CONTRIBUTIONS =====
function renderContributions() {
  const list = document.getElementById('contributions-list');
  if (!state.contributions.length) {
    list.innerHTML = '<div class="empty-state">No contributions yet. Add one above!</div>';
    return;
  }
  const sorted = [...state.contributions].sort((a, b) => new Date(b.date) - new Date(a.date));
  list.innerHTML = sorted.map((c, i) => {
    const mi = state.members.indexOf(c.member);
    return `
      <div class="history-item">
        <div class="history-icon contribution" style="background:#eafaf1">💰</div>
        <div class="history-info">
          <div class="title" style="color:${getMemberColor(mi >= 0 ? mi : 0)}">${c.member}</div>
          <div class="meta">${c.note || 'Contribution'} · ${formatDate(c.date)}</div>
        </div>
        <div class="history-amount contribution">${formatCurrency(c.amount)}</div>
        <button class="delete-btn" onclick="deleteContribution('${c.id}')" title="Delete">🗑</button>
      </div>
    `;
  }).join('');
}

// ===== RENDER EXPENSES =====
function renderExpenses() {
  const list = document.getElementById('expenses-list');
  if (!state.expenses.length) {
    list.innerHTML = '<div class="empty-state">No expenses yet. Add one above!</div>';
    return;
  }

  const categoryEmoji = {
    Groceries: '🥦', Vegetables: '🥕', Household: '🧹',
    Electricity: '💡', Water: '💧', Gas: '🔥', Rent: '🏠', Other: '📦'
  };

  const sorted = [...state.expenses].sort((a, b) => new Date(b.date) - new Date(a.date));
  list.innerHTML = sorted.map(e => {
    const mi = state.members.indexOf(e.paidBy);
    const emoji = categoryEmoji[e.category] || '📦';
    const splitInfo = e.splitBetween && e.splitBetween.length > 0
      ? `Split: ${e.splitBetween.join(', ')}`
      : 'No split info';
    return `
      <div class="history-item">
        <div class="history-icon expense" style="font-size:1.1rem">${emoji}</div>
        <div class="history-info">
          <div class="title">${e.description}</div>
          <div class="meta">
            Paid by <strong style="color:${getMemberColor(mi >= 0 ? mi : 0)}">${e.paidBy}</strong>
            · ${e.category} · ${formatDate(e.date)}
          </div>
          <div class="meta">${splitInfo}</div>
        </div>
        <div class="history-amount expense">-${formatCurrency(e.amount)}</div>
        <button class="delete-btn" onclick="deleteExpense('${e.id}')" title="Delete">🗑</button>
      </div>
    `;
  }).join('');
}

// ===== DELETE HANDLERS =====
function deleteContribution(id) {
  if (!confirm('Delete this contribution?')) return;
  state.contributions = state.contributions.filter(c => c.id !== id);
  saveState();
  renderAll();
}

function deleteExpense(id) {
  if (!confirm('Delete this expense?')) return;
  state.expenses = state.expenses.filter(e => e.id !== id);
  saveState();
  renderAll();
}

// ===== RENDER ALL =====
function renderAll() {
  renderMembers();
  populateSelects();
  renderSummary();
  renderContributions();
  renderExpenses();
}

// ===== CONTRIBUTION FORM =====
document.getElementById('contribution-form').addEventListener('submit', function (e) {
  e.preventDefault();
  const member = document.getElementById('contrib-member').value;
  const amount = parseFloat(document.getElementById('contrib-amount').value);
  const note = document.getElementById('contrib-note').value.trim();
  const date = document.getElementById('contrib-date').value;

  if (!member || !amount || !date) return;

  state.contributions.push({ id: genId(), member, amount, note, date });
  saveState();
  renderAll();

  // Reset form
  this.reset();
  document.getElementById('contrib-date').value = todayValue();
  document.getElementById('contrib-member').value = state.members[0];
});

// ===== EXPENSE FORM =====
document.getElementById('expense-form').addEventListener('submit', function (e) {
  e.preventDefault();
  const paidBy = document.getElementById('exp-paid-by').value;
  const amount = parseFloat(document.getElementById('exp-amount').value);
  const category = document.getElementById('exp-category').value;
  const description = document.getElementById('exp-desc').value.trim();
  const date = document.getElementById('exp-date').value;

  const checkboxes = document.querySelectorAll('#exp-split-members input[type="checkbox"]:checked');
  const splitBetween = Array.from(checkboxes).map(cb => cb.value);

  if (!paidBy || !amount || !description || !date) return;

  state.expenses.push({ id: genId(), paidBy, amount, category, description, date, splitBetween });
  saveState();
  renderAll();

  // Reset form
  this.reset();
  document.getElementById('exp-date').value = todayValue();
  document.getElementById('exp-paid-by').value = state.members[0];
  // Re-check all split boxes
  document.querySelectorAll('#exp-split-members input[type="checkbox"]').forEach(cb => cb.checked = true);
});

// ===== TABS =====
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', function () {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    this.classList.add('active');

    const tab = this.dataset.tab;
    document.getElementById('contributions-tab').classList.toggle('hidden', tab !== 'contributions');
    document.getElementById('expenses-tab').classList.toggle('hidden', tab !== 'expenses');
  });
});

// ===== MEMBERS MODAL =====
function openMembersModal() {
  renderModalMembers();
  document.getElementById('members-modal').classList.remove('hidden');
  document.getElementById('modal-overlay').classList.remove('hidden');
}

function closeMembersModal() {
  document.getElementById('members-modal').classList.add('hidden');
  document.getElementById('modal-overlay').classList.add('hidden');
}

function renderModalMembers() {
  const list = document.getElementById('modal-members-list');
  list.innerHTML = state.members.map((m, i) => `
    <div class="modal-member-row">
      <div class="member-avatar" style="background:${getMemberColor(i)};width:28px;height:28px">${getMemberInitials(m)}</div>
      <span>${m}</span>
      ${state.members.length > 1 ? `<button class="btn btn-danger" onclick="removeMember(${i})">✕</button>` : ''}
    </div>
  `).join('');
}

function removeMember(index) {
  if (state.members.length <= 1) return alert('Need at least one member!');
  const name = state.members[index];
  const hasData = state.contributions.some(c => c.member === name) ||
                  state.expenses.some(e => e.paidBy === name);
  if (hasData && !confirm(`${name} has existing data. Remove anyway?`)) return;
  state.members.splice(index, 1);
  renderModalMembers();
}

document.getElementById('add-member-btn').addEventListener('click', function () {
  const input = document.getElementById('new-member-name');
  const name = input.value.trim();
  if (!name) return;
  if (state.members.includes(name)) return alert('Member already exists!');
  state.members.push(name);
  input.value = '';
  renderModalMembers();
});

document.getElementById('new-member-name').addEventListener('keydown', function (e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    document.getElementById('add-member-btn').click();
  }
});

document.getElementById('save-members-btn').addEventListener('click', function () {
  saveState();
  renderAll();
  closeMembersModal();
});

document.getElementById('edit-members-btn').addEventListener('click', openMembersModal);
document.getElementById('modal-overlay').addEventListener('click', function () {
  saveState();
  renderAll();
  closeMembersModal();
});

// ===== INIT =====
function init() {
  loadState();
  // Set today's date as default
  document.getElementById('contrib-date').value = todayValue();
  document.getElementById('exp-date').value = todayValue();
  renderAll();
}

init();
