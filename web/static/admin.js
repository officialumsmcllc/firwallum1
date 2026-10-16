// OFFICIALUM1 — Admin Command Center Controller

document.addEventListener('DOMContentLoaded', () => {
  const tokenKey = 'officialum1_admin_auth';
  const authModal = document.getElementById('authGateModal');
  const passwordInput = document.getElementById('adminPasswordInput');
  const loginBtn = document.getElementById('adminLoginBtn');
  const errorMsg = document.getElementById('authErrorMsg');

  // 1. Auth Gate
  function checkAuth() {
    const token = localStorage.getItem(tokenKey);
    if (token === 'active') {
      authModal.style.display = 'none';
      initAdminDashboard();
    } else {
      authModal.style.display = 'flex';
    }
  }

  async function handleLogin() {
    const password = passwordInput.value.trim();
    if (!password) return;
    try {
      const res = await fetch('/api/admin/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
      });
      const data = await res.json();
      if (data.authenticated) {
        localStorage.setItem(tokenKey, 'active');
        authModal.style.display = 'none';
        initAdminDashboard();
      } else {
        errorMsg.style.display = 'block';
      }
    } catch (e) {
      errorMsg.style.display = 'block';
    }
  }

  loginBtn.addEventListener('click', handleLogin);
  passwordInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleLogin();
  });

  document.getElementById('adminLogoutBtn').addEventListener('click', () => {
    localStorage.removeItem(tokenKey);
    window.location.reload();
  });

  // Tab Switching
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const target = document.getElementById(btn.dataset.tab);
      if (target) target.classList.add('active');

      if (btn.dataset.tab === 'usersTab') fetchUsers();
      if (btn.dataset.tab === 'tenantsTab') fetchTenants();
      if (btn.dataset.tab === 'portsProxiesTab') fetchPortsAndProxies();
      if (btn.dataset.tab === 'globalLogsTab') fetchGlobalLogs();
      if (btn.dataset.tab === 'cloudflareTab') fetchCloudflareSettings();
    });
  });

  // 2. Admin Initialization
  function initAdminDashboard() {
    fetchOverview();
    fetchTenants();
    fetchUsers();
    fetchPortsAndProxies();
    fetchGlobalLogs();

    setInterval(fetchOverview, 4000);
    setInterval(fetchTenants, 6000);
    setInterval(fetchUsers, 6000);
    setInterval(fetchGlobalLogs, 3000);
  }

  // 3. Overview Metrics
  async function fetchOverview() {
    try {
      const res = await fetch('/api/admin/overview');
      const data = await res.json();
      document.getElementById('statTotalTenants').textContent = `${data.total_tenants} Accounts`;
      document.getElementById('statActiveTenants').textContent = `${data.active_tenants} Active`;
      document.getElementById('statGlobalBandwidth').textContent = `${data.total_mb} MB (${data.total_gb} GB)`;
      document.getElementById('statGlobalQueries').textContent = Number(data.total_queries).toLocaleString();
      document.getElementById('statBlockedAds').textContent = `${Number(data.blocked_ads).toLocaleString()} Ads`;
      document.getElementById('statBlockedAdult').textContent = `${Number(data.blocked_adult).toLocaleString()} Blocked`;
      document.getElementById('statActiveProxies').textContent = `${data.active_proxies} of ${data.total_proxies} Active`;
    } catch (e) {}
  }

  // 4. Tenants Table
  async function fetchTenants() {
    try {
      const res = await fetch('/api/admin/tenants');
      const data = await res.json();
      const tbody = document.getElementById('tenantsTableBody');
      if (!data.tenants || data.tenants.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-sub); padding: 24px;">No customer tenants found.</td></tr>';
        return;
      }

      tbody.innerHTML = data.tenants.map(t => {
        const isActive = t.is_active;
        const statusPill = isActive
          ? `<span class="status-pill-active">● ACTIVE (${t.days_left}d left)</span>`
          : `<span class="status-pill-suspended">● SUSPENDED</span>`;
        
        return `
          <tr>
            <td>
              <div style="font-weight: 700; color: #fff;">${t.name}</div>
              <code style="font-size: 11px; color: #38bdf8; background: rgba(0,0,0,0.4); padding: 2px 6px; border-radius: 4px;">${t.id}</code>
            </td>
            <td>
              <span class="badge" style="background: rgba(59,130,246,0.15); color: #93c5fd; font-size: 11px;">${(t.plan_tier || 'home_pro').toUpperCase()}</span>
            </td>
            <td>${statusPill}</td>
            <td><code style="color: #6ee7b7; font-size: 11.5px;">${t.linked_ip_count > 0 ? 'Linked (' + t.linked_ip_count + ' IP)' : 'Not Linked'}</code></td>
            <td><strong>${t.device_count || 0}</strong> Devices</td>
            <td><strong>${t.query_count || 0}</strong> Queries</td>
            <td>
              <div style="display: flex; gap: 8px; align-items: center;">
                <label title="Adblock" style="cursor: pointer; font-size: 11px;">🛡️ <input type="checkbox" class="form-switch toggle-feature" data-id="${t.id}" data-key="adblock_enabled" ${t.adblock_enabled ? 'checked' : ''}></label>
                <label title="18+ Adult Shield" style="cursor: pointer; font-size: 11px;">🔞 <input type="checkbox" class="form-switch toggle-feature" data-id="${t.id}" data-key="adult_block_enabled" ${t.adult_block_enabled ? 'checked' : ''}></label>
                <label title="Smart TV Shield" style="cursor: pointer; font-size: 11px;">📺 <input type="checkbox" class="form-switch toggle-feature" data-id="${t.id}" data-key="smart_tv_shield" ${t.smart_tv_shield ? 'checked' : ''}></label>
              </div>
            </td>
            <td style="text-align: right;">
              <div style="display: inline-flex; gap: 6px;">
                <button class="btn-action-sm btn-renew" data-id="${t.id}" title="Renew +30 Days">🔄 +30d</button>
                <button class="btn-action-sm btn-suspend" data-id="${t.id}" data-status="${t.status}" title="${isActive ? 'Suspend' : 'Reactivate'}">
                  ${isActive ? '⏸️ Suspend' : '▶️ Resume'}
                </button>
                <a href="/?config=${t.id}" target="_blank" class="btn-action-sm" style="background: rgba(59,130,246,0.2); color: #60a5fa; text-decoration: none;">👁️ View</a>
                ${t.id !== 'default' ? `<button class="btn-action-sm btn-del" data-id="${t.id}">🗑️</button>` : ''}
              </div>
            </td>
          </tr>
        `;
      }).join('');

      // Wire Toggles
      document.querySelectorAll('.toggle-feature').forEach(chk => {
        chk.addEventListener('change', async (e) => {
          const tid = e.target.dataset.id;
          const key = e.target.dataset.key;
          const val = e.target.checked ? 1 : 0;
          await fetch('/api/admin/tenants/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: tid, updates: { [key]: val } })
          });
        });
      });

      // Wire Renew
      document.querySelectorAll('.btn-renew').forEach(btn => {
        btn.addEventListener('click', async () => {
          btn.textContent = 'Renewing...';
          await fetch('/api/admin/tenants/renew', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: btn.dataset.id, days: 30 })
          });
          fetchTenants();
        });
      });

      // Wire Suspend / Resume
      document.querySelectorAll('.btn-suspend').forEach(btn => {
        btn.addEventListener('click', async () => {
          const tid = btn.dataset.id;
          const isSuspended = btn.dataset.status === 'suspended';
          if (isSuspended) {
            await fetch('/api/admin/tenants/renew', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ id: tid, days: 30 })
            });
          } else {
            await fetch('/api/admin/tenants/suspend', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ id: tid })
            });
          }
          fetchTenants();
        });
      });

      // Wire Delete
      document.querySelectorAll('.btn-del').forEach(btn => {
        btn.addEventListener('click', async () => {
          if (!confirm(`Delete customer tenant '${btn.dataset.id}'?`)) return;
          await fetch('/api/admin/tenants/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: btn.dataset.id })
          });
          fetchTenants();
        });
      });

    } catch (e) {}
  }

  // 5. Add Tenant Modal
  const addModal = document.getElementById('addTenantModal');
  document.getElementById('openAddTenantModalBtn').addEventListener('click', () => {
    addModal.style.display = 'flex';
  });
  document.getElementById('closeAddTenantModalBtn').addEventListener('click', () => {
    addModal.style.display = 'none';
  });
  document.getElementById('cancelAddTenantBtn').addEventListener('click', () => {
    addModal.style.display = 'none';
  });

  // Auto generate ID
  document.getElementById('newTenantName').addEventListener('input', (e) => {
    const autoId = e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-');
    document.getElementById('newTenantId').value = autoId;
  });

  document.getElementById('addTenantForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('newTenantId').value.trim();
    const name = document.getElementById('newTenantName').value.trim();
    const plan = document.getElementById('newTenantPlan').value;
    const days = document.getElementById('newTenantDays').value;

    await fetch('/api/admin/tenants/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, name, plan_tier: plan, days_valid: days })
    });

    addModal.style.display = 'none';
    fetchTenants();
    fetchOverview();
  });

  // 6. Ports and Proxies
  async function fetchPortsAndProxies() {
    try {
      const [portsRes, proxiesRes] = await Promise.all([
        fetch('/api/ports'),
        fetch('/api/proxies')
      ]);
      const portsData = await portsRes.json();
      const proxiesData = await proxiesRes.json();

      // Render ports
      const pbody = document.getElementById('adminPortsTableBody');
      pbody.innerHTML = (portsData.ports || []).map(p => `
        <tr>
          <td><strong style="color: #38bdf8; font-family: monospace;">Port ${p.port}</strong></td>
          <td>${p.device_name}</td>
          <td>${p.proxy_name ? `<span class="badge" style="background: rgba(16,185,129,0.15); color: #34d399;">${p.proxy_name} (${p.exit_ip})</span>` : '<span style="color: var(--text-sub);">Direct Line (No Proxy)</span>'}</td>
          <td><code style="color: #93c5fd;">${p.speed_kbps || 0} KB/s</code></td>
          <td><strong>${p.total_mb || 0} MB</strong></td>
          <td><span class="status-pill-active">${p.status}</span></td>
        </tr>
      `).join('');

      // Render proxies list
      const plist = document.getElementById('proxyFleetList');
      if (!proxiesData.proxies || proxiesData.proxies.length === 0) {
        plist.innerHTML = '<p style="font-size: 12px; color: var(--text-sub);">No external proxies configured. Traffic is direct high-speed DNS shielded.</p>';
      } else {
        plist.innerHTML = proxiesData.proxies.map(pr => `
          <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: rgba(0,0,0,0.3); border-radius: 8px; margin-bottom: 8px;">
            <div>
              <strong>${pr.name}</strong> <span style="font-size: 11px; color: #94a3b8;">(${pr.protocol.toUpperCase()} • ${pr.host}:${pr.port})</span>
              <div style="font-size: 11px; color: #34d399;">Exit IP: ${pr.exit_ip} (${pr.country}) • Latency: ${pr.latency_ms}ms</div>
            </div>
            <button class="btn btn-secondary btn-sm test-proxy-btn" data-id="${pr.id}">⚡ Test</button>
          </div>
        `).join('');
      }
    } catch (e) {}
  }

  // 7. Global Logs
  async function fetchGlobalLogs() {
    try {
      const res = await fetch('/api/dns-logs?id=all&limit=30');
      const data = await res.json();
      const tbody = document.getElementById('globalLogsTableBody');
      if (!data.logs || data.logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-sub); padding: 20px;">No telemetry queries recorded yet.</td></tr>';
        return;
      }

      tbody.innerHTML = data.logs.map(log => {
        const timeStr = new Date(log.timestamp * 1000).toLocaleTimeString();
        let statusBadge = '<span class="status-pill-active">ALLOWED</span>';
        if (log.status === 'BLOCKED_AD') statusBadge = '<span class="status-pill-suspended">BLOCKED (AD)</span>';
        if (log.status === 'BLOCKED_ADULT') statusBadge = '<span style="background: rgba(192,132,252,0.15); color: #c084fc; border: 1px solid rgba(192,132,252,0.3); padding: 3px 8px; border-radius: 20px; font-size: 11px; font-weight: 700;">BLOCKED (18+)</span>';
        if (log.status === 'BLOCKED_SMART_TV') statusBadge = '<span style="background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); padding: 3px 8px; border-radius: 20px; font-size: 11px; font-weight: 700;">BLOCKED (TV SPY)</span>';

        return `
          <tr>
            <td style="font-size: 11px; color: var(--text-sub); font-family: monospace;">${timeStr}</td>
            <td><code style="color: #38bdf8; font-size: 11px;">${log.config_id}</code></td>
            <td>${statusBadge}</td>
            <td style="font-family: monospace; font-size: 12px; color: #fff;">${log.domain}</td>
            <td style="font-size: 11px; color: #94a3b8; font-family: monospace;">${log.client_ip}</td>
          </tr>
        `;
      }).join('');
    } catch (e) {}
  }

  document.getElementById('clearGlobalLogsBtn').addEventListener('click', async () => {
    await fetch('/api/dns-logs/clear?id=all', { method: 'POST' });
    fetchGlobalLogs();
  });

  // =========================================================================
  // 5. CUSTOMER USER ACCOUNTS & CREDENTIALS
  // =========================================================================

  async function fetchUsers() {
    try {
      const res = await fetch('/api/admin/users');
      const data = await res.json();
      const users = data.users || [];

      // Update counters
      const totalEl = document.getElementById('statTotalUsers');
      const activeEl = document.getElementById('statActiveUsers');
      if (totalEl) totalEl.textContent = `${users.length} Users`;
      if (activeEl) {
        const activeCount = users.filter(u => u.status === 'active').length;
        activeEl.textContent = `${activeCount} Active`;
      }

      const tbody = document.getElementById('usersTableBody');
      if (!tbody) return;

      if (users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-sub); padding: 24px;">No customer accounts registered yet.</td></tr>';
        return;
      }

      tbody.innerHTML = users.map((u, idx) => {
        const isAct = u.status === 'active';
        const statusBadge = isAct
          ? '<span class="status-pill-active">● ACTIVE</span>'
          : '<span class="status-pill-suspended">● SUSPENDED</span>';

        const tierBadge = `<span class="badge" style="background: rgba(56,189,248,0.15); color: #38bdf8; font-size: 11px; font-weight: 700;">${(u.plan_tier || 'home_pro').toUpperCase()}</span>`;
        const regDate = u.created_at ? new Date(u.created_at * 1000).toLocaleDateString() : 'Initial';

        return `
          <tr>
            <td style="color: var(--text-sub); font-size: 11px;">#${u.id}</td>
            <td>
              <div style="font-weight: 700; color: #fff;">${u.full_name || u.username}</div>
              <span style="font-size: 10.5px; color: #94a3b8; text-transform: uppercase;">Role: ${u.role || 'customer'}</span>
            </td>
            <td>
              <div style="font-family: monospace; color: #e2e8f0; font-size: 12px;">${u.username}</div>
              <div style="font-size: 11px; color: #64748b;">${u.email || 'No email'}</div>
            </td>
            <td>
              <a href="/?config=${encodeURIComponent(u.config_id || 'default')}" target="_blank" style="color: #38bdf8; text-decoration: none; font-family: monospace; font-size: 11.5px; background: rgba(56,189,248,0.1); padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(56,189,248,0.2);">
                ${u.config_id || 'default'} ↗
              </a>
            </td>
            <td>${tierBadge}</td>
            <td>${statusBadge}</td>
            <td style="font-size: 11px; color: #94a3b8; font-family: monospace;">${regDate}</td>
            <td style="text-align: right;">
              <div style="display: inline-flex; gap: 8px;">
                <button class="btn-action-sm" onclick="openResetPasswordModal(${u.id}, '${escape(u.username)}')" style="background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.3);" title="Reset Password Manually">
                  🔑 Reset Pass
                </button>
                <button class="btn-action-sm" onclick="openUpgradeTierModal(${u.id}, '${escape(u.username)}', '${u.plan_tier}')" style="background: rgba(59,130,246,0.2); color: #60a5fa; border: 1px solid rgba(59,130,246,0.4);" title="Upgrade Account Plan">
                  ⚡ Upgrade
                </button>
              </div>
            </td>
          </tr>
        `;
      }).join('');

    } catch (e) {
      console.warn('Failed to load users:', e);
    }
  }

  // Refresh users button
  const refreshUsersBtn = document.getElementById('refreshUsersBtn');
  if (refreshUsersBtn) {
    refreshUsersBtn.addEventListener('click', fetchUsers);
  }

  // --- PASSWORD RESET MODAL CONTROLLERS ---
  window.openResetPasswordModal = function(userId, username) {
    document.getElementById('resetTargetUserId').value = userId;
    document.getElementById('resetTargetUserLabel').textContent = unescape(username);
    document.getElementById('resetNewPasswordInput').value = '';
    const errMsg = document.getElementById('resetErrorMsg');
    if (errMsg) errMsg.style.display = 'none';
    document.getElementById('resetPasswordModal').style.display = 'flex';
  };

  window.closeResetPasswordModal = function() {
    document.getElementById('resetPasswordModal').style.display = 'none';
  };

  window.handleResetPasswordSubmit = async function(e) {
    e.preventDefault();
    const userId = document.getElementById('resetTargetUserId').value;
    const newPassword = document.getElementById('resetNewPasswordInput').value;
    const saveBtn = document.getElementById('savePasswordBtn');
    const errMsg = document.getElementById('resetErrorMsg');

    saveBtn.disabled = true;
    saveBtn.textContent = 'Updating...';

    try {
      const res = await fetch(`/api/admin/users/${userId}/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPassword })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to reset password');

      alert(`Success: Password for user updated successfully!`);
      closeResetPasswordModal();
    } catch (err) {
      if (errMsg) {
        errMsg.textContent = err.message;
        errMsg.style.display = 'block';
      }
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save New Password';
    }
  };

  // --- UPGRADE TIER MODAL CONTROLLERS ---
  window.openUpgradeTierModal = function(userId, username, currentTier) {
    document.getElementById('upgradeTargetUserId').value = userId;
    document.getElementById('upgradeTargetUserLabel').textContent = unescape(username);
    if (currentTier && document.getElementById('upgradePlanTierSelect')) {
      document.getElementById('upgradePlanTierSelect').value = currentTier;
    }
    const errMsg = document.getElementById('upgradeErrorMsg');
    if (errMsg) errMsg.style.display = 'none';
    document.getElementById('upgradeTierModal').style.display = 'flex';
  };

  window.closeUpgradeTierModal = function() {
    document.getElementById('upgradeTierModal').style.display = 'none';
  };

  window.handleUpgradeTierSubmit = async function(e) {
    e.preventDefault();
    const userId = document.getElementById('upgradeTargetUserId').value;
    const planTier = document.getElementById('upgradePlanTierSelect').value;
    const extendDays = parseInt(document.getElementById('upgradeExtendDaysSelect').value, 10);
    const saveBtn = document.getElementById('saveUpgradeBtn');
    const errMsg = document.getElementById('upgradeErrorMsg');

    saveBtn.disabled = true;
    saveBtn.textContent = 'Upgrading...';

    try {
      const res = await fetch(`/api/admin/users/${userId}/upgrade`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_tier: planTier, extend_days: extendDays })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to upgrade tier');

      alert(`Account upgraded successfully to ${planTier.toUpperCase()}!`);
      closeUpgradeTierModal();
      fetchUsers();
      fetchTenants();
    } catch (err) {
      if (errMsg) {
        errMsg.textContent = err.message;
        errMsg.style.display = 'block';
      }
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Apply Account Upgrade';
    }
  // --- CLOUDFLARE ZERO TRUST INTEGRATION ---
  window.fetchCloudflareSettings = async function() {
    try {
      const res = await fetch('/api/admin/settings/cloudflare');
      const data = await res.json();
      const statusEl = document.getElementById('cfTokenStatus');
      const accountInput = document.getElementById('cfAccountIdInput');
      if (data.configured) {
        statusEl.innerHTML = `🟢 Token Active (${data.token_masked})`;
        statusEl.style.color = '#34d399';
      } else {
        statusEl.innerHTML = '⚪ Token not configured (Default Anycast IPs active)';
        statusEl.style.color = '#94a3b8';
      }
      if (data.account_id && accountInput) {
        accountInput.value = data.account_id;
      }
    } catch (e) {
      console.error('Error fetching CF settings:', e);
    }
  };

  window.handleSaveCloudflareSettings = async function(e) {
    e.preventDefault();
    const token = document.getElementById('cfApiTokenInput').value.trim();
    const accountId = document.getElementById('cfAccountIdInput').value.trim();
    const saveBtn = document.getElementById('saveCfBtn');
    const notice = document.getElementById('cfSaveNotice');

    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';

    try {
      const res = await fetch('/api/admin/settings/cloudflare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_token: token, account_id: accountId })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to save');

      notice.textContent = '✓ Saved successfully!';
      notice.style.display = 'inline';
      setTimeout(() => { notice.style.display = 'none'; }, 4000);
      fetchCloudflareSettings();
    } catch (err) {
      alert('Error: ' + err.message);
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save Cloudflare Credentials';
    }
  };

  checkAuth();
});
