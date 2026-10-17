/**
 * OFFICIALUM1 — Multi-Tenant Customer Gateway & Security Hub
 * Client-Side Application Logic (User Dashboard)
 */

(function () {
  'use strict';

  // Extract config_id from URL (?config=xyz) or localStorage
  const urlParams = new URLSearchParams(window.location.search);
  const token = localStorage.getItem('um1_user_token');
  const isGuest = urlParams.get('guest') === '1';

  // Authentication check: redirect to /login if not authenticated
  if (!token && !isGuest) {
    window.location.href = '/login';
    return;
  }

  const currentConfigId = urlParams.get('config') || localStorage.getItem('um1_user_config_id') || 'cfg_officialum1';
  localStorage.setItem('um1_user_config_id', currentConfigId);

  // Setup user profile badge
  try {
    const rawUser = localStorage.getItem('um1_user_info');
    const nameEl = document.getElementById('navUserName');
    const logoutBtn = document.getElementById('logoutBtn');
    if (rawUser && token) {
      const u = JSON.parse(rawUser);
      if (nameEl) {
        nameEl.textContent = `${u.full_name || u.username} [${(u.plan_tier || 'PRO').toUpperCase()}]`;
      }
      const adminNavBtn = document.getElementById('adminConsoleNavBtn');
      if (adminNavBtn) {
        if (u.role === 'admin' || localStorage.getItem('officialum1_admin_auth') === 'active') {
          adminNavBtn.style.display = 'inline-flex';
        } else {
          adminNavBtn.style.display = 'none';
        }
      }
    } else if (isGuest) {
      const adminNavBtn = document.getElementById('adminConsoleNavBtn');
      if (adminNavBtn) adminNavBtn.style.display = 'none';
      if (nameEl) nameEl.textContent = 'Guest Visitor';
      if (logoutBtn) {
        logoutBtn.textContent = '🔑 Log In';
        logoutBtn.style.background = 'rgba(56, 189, 248, 0.2)';
        logoutBtn.style.borderColor = 'rgba(56, 189, 248, 0.4)';
        logoutBtn.style.color = '#38bdf8';
      }
    }
  } catch (e) {}

  window.handleLogout = function () {
    localStorage.removeItem('um1_user_token');
    localStorage.removeItem('um1_user_info');
    localStorage.removeItem('um1_user_config_id');
    window.location.href = '/login';
  };

  let currentHubIp = '172.64.36.1';
  const startTime = Date.now();
  let knownDeviceIps = new Set();
  let isInitialDeviceLoad = true;
  let activeLogs = [];
  let currentDetectedIp = '';
  let isCurrentIpLinked = false;
  let currentTenantData = null;

  // --- API HELPERS (Multi-Tenant Aware) ---
  async function apiGet(endpoint) {
    try {
      const sep = endpoint.includes('?') ? '&' : '?';
      const res = await fetch(`/api/${endpoint}${sep}config=${encodeURIComponent(currentConfigId)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e) {
      console.warn(`GET /api/${endpoint} error:`, e);
      return null;
    }
  }

  async function apiPost(endpoint, body = {}) {
    try {
      const payload = { config_id: currentConfigId, ...body };
      const res = await fetch(`/api/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      return await res.json();
    } catch (e) {
      console.error(`POST /api/${endpoint} error:`, e);
      return null;
    }
  }

  // --- TOAST NOTIFICATIONS ---
  function showToast(msg, type = 'info') {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {
      toast.classList.remove('show');
    }, 3200);
  }

  // --- FORMATTERS ---
  function formatUptime(ms) {
    const totalSec = Math.floor(ms / 1000);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  function getDeviceIcon(name = '', type = '') {
    const s = (name + ' ' + type).toLowerCase();
    if (s.includes('tv') || s.includes('samsung') || s.includes('lg') || s.includes('bravia') || s.includes('roku') || s.includes('firetv')) return '📺';
    if (s.includes('ps5') || s.includes('playstation') || s.includes('xbox') || s.includes('nintendo') || s.includes('switch') || s.includes('console')) return '🎮';
    if (s.includes('pc') || s.includes('laptop') || s.includes('desktop') || s.includes('macbook') || s.includes('windows')) return '💻';
    if (s.includes('iphone') || s.includes('android') || s.includes('vivo') || s.includes('infinix') || s.includes('phone') || s.includes('mobile')) return '📱';
    if (s.includes('ipad') || s.includes('tablet')) return '📱';
    return '📡';
  }

  // --- SYSTEM MONITOR BAR TICKER ---
  function updateSystemMonitor() {
    const elapsed = Date.now() - startTime;
    const uptimeEl = document.getElementById('sysUptime');
    const uptimeDisplayEl = document.getElementById('uptimeDisplay');
    if (uptimeEl) uptimeEl.textContent = formatUptime(elapsed);
    if (uptimeDisplayEl) uptimeDisplayEl.textContent = formatUptime(elapsed);
  }

  // --- REFRESH CONFIG & STATUS ---
  async function refreshStatus() {
    const data = await apiGet('status');
    if (!data) return;

    currentTenantData = data;
    currentHubIp = data.hub_ip || '172.64.36.1';

    // 1. Subscription Expiry Check (Feature 3 Paywall)
    if (data.status === 'suspended' || data.status === 'expired') {
      window.location.href = `/expired?config=${encodeURIComponent(currentConfigId)}`;
      return;
    }

    // Update Hub IP pill
    const hubIpEl = document.getElementById('hubIpDisplay');
    if (hubIpEl) hubIpEl.textContent = currentHubIp;

    // Update Config Banner if present
    const configNameEl = document.getElementById('currentConfigName');
    const configIdEl = document.getElementById('currentConfigId');
    if (configNameEl && data.tenant_name) configNameEl.textContent = data.tenant_name;
    if (configIdEl) configIdEl.textContent = currentConfigId;

    // Top Metrics
    const statActiveEl = document.getElementById('statActiveCount');
    if (statActiveEl) statActiveEl.textContent = `${data.active_devices || 0} Online`;

    const statDnsCount = document.getElementById('statDnsCount');
    if (statDnsCount) statDnsCount.textContent = `${(data.blocked_domains_count || 73658).toLocaleString()} threat domains blocked`;

    // Top Toggles & Status Texts
    const dnsBtn = document.getElementById('toggleDnsBtn');
    const dnsText = document.getElementById('statDnsBlockedText');
    if (dnsBtn && dnsText) {
      if (data.dns_adblock) {
        dnsBtn.classList.remove('off');
        dnsText.textContent = 'Active';
      } else {
        dnsBtn.classList.add('off');
        dnsText.textContent = 'Disabled';
      }
    }

    const adultBtn = document.getElementById('toggleAdultBtn');
    const adultText = document.getElementById('statAdultBlockedText');
    if (adultBtn && adultText) {
      if (data.adult_block_enabled) {
        adultBtn.classList.remove('off');
        adultText.textContent = 'Active';
      } else {
        adultBtn.classList.add('off');
        adultText.textContent = 'Allowed';
      }
    }

    const tvBtn = document.getElementById('toggleTvShieldBtn');
    const tvText = document.getElementById('statTvBlockedText');
    if (tvBtn && tvText) {
      if (data.smart_tv_shield !== false) {
        tvBtn.classList.remove('off');
        tvText.textContent = 'Active';
      } else {
        tvBtn.classList.add('off');
        tvText.textContent = 'Disabled';
      }
    }

    // Sync Shields Tab Switches
    const shieldAdblock = document.getElementById('userShieldAdblockBtn');
    if (shieldAdblock) {
      if (data.dns_adblock) shieldAdblock.classList.add('active');
      else shieldAdblock.classList.remove('active');
    }

    const shieldAdult = document.getElementById('userShieldAdultBtn');
    if (shieldAdult) {
      if (data.adult_block_enabled) shieldAdult.classList.add('active');
      else shieldAdult.classList.remove('active');
    }

    const shieldTv = document.getElementById('userShieldSmartTvBtn');
    if (shieldTv) {
      if (data.smart_tv_shield !== false) shieldTv.classList.add('active');
      else shieldTv.classList.remove('active');
    }

    const shieldSafe = document.getElementById('userShieldSafeSearchBtn');
    if (shieldSafe) {
      if (data.safesearch_enabled) shieldSafe.classList.add('active');
      else shieldSafe.classList.remove('active');
    }
  }

  // --- REFRESH CONNECTED WI-FI DEVICES & BANDWIDTH ---
  async function refreshWifiDevices() {
    const data = await apiGet('wifi-devices');
    const badge = document.getElementById('wifiDeviceCountBadge');
    if (badge && data && data.total_count !== undefined) {
      badge.textContent = `${data.total_count} Online`;
    }

    const tbody = document.getElementById('wifiDevicesTableBody');
    if (!tbody) return;

    if (!data || !data.devices || data.devices.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align:center; padding: 48px; color: var(--text-sub);">
            <div style="font-size:32px; margin-bottom:12px;">📡</div>
            Scanning network... No devices connected yet.<br>
            <span style="font-size:12px; color:var(--text-sub); margin-top:6px; display:inline-block;">
              Configure your Router DNS to <code>172.64.36.1</code> or connect your phone to appear here instantly.
            </span>
          </td>
        </tr>
      `;
      return;
    }

    // Auto-detect newly connected devices and show NextDNS-style alert
    data.devices.forEach(d => {
      if (!knownDeviceIps.has(d.ip)) {
        if (!isInitialDeviceLoad) {
          showToast(`🟢 New Device Online: ${d.name || d.ip}!`);
        }
        knownDeviceIps.add(d.ip);
      }
    });
    isInitialDeviceLoad = false;

    // Calculate Real Aggregated Bandwidth & Speed
    let totalMb = 0;
    let totalSpeed = 0;
    data.devices.forEach(d => {
      totalMb += (d.total_mb || 0);
      totalSpeed += (d.speed_kbps || 0);
    });

    const statTrafficEl = document.getElementById('statTotalTraffic');
    if (statTrafficEl) {
      if (totalMb >= 1024) {
        statTrafficEl.textContent = (totalMb / 1024).toFixed(2) + ' GB';
      } else {
        statTrafficEl.textContent = totalMb.toFixed(1) + ' MB';
      }
    }

    const statSpeedEl = document.getElementById('statLiveSpeed');
    if (statSpeedEl) {
      statSpeedEl.textContent = `${Math.round(totalSpeed)} KB/s`;
    }

    // Render Devices Table Rows
    tbody.innerHTML = data.devices.map(d => {
      const isPaused = (d.status === 'PAUSED');
      const isBlocked = d.is_blocked;
      const icon = getDeviceIcon(d.name, d.type);
      
      let statusBadge = '';
      if (isBlocked) {
        statusBadge = `<span class="badge" style="background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.3); font-size:10px;">🚫 KICKED</span>`;
      } else if (isPaused) {
        statusBadge = `<span class="badge" style="background:rgba(245,158,11,0.15); color:#fbbf24; border:1px solid rgba(245,158,11,0.3); font-size:10px;">⏸️ PAUSED</span>`;
      } else {
        statusBadge = `<span class="badge" style="background:rgba(16,185,129,0.15); color:#34d399; border:1px solid rgba(16,185,129,0.3); font-size:10px;">🟢 SHIELDED</span>`;
      }

      // Format Data Consumed
      let dataUsedStr = '0 MB';
      if (d.total_gb > 0) {
        dataUsedStr = `<strong style="color: #38bdf8; font-size: 13px;">${d.total_gb} GB</strong>`;
      } else if (d.total_mb > 0) {
        dataUsedStr = `<strong style="color: #38bdf8; font-size: 13px;">${d.total_mb} MB</strong>`;
      }

      // Format Live Speed
      let speedStr = '<span style="color:var(--text-sub); font-size:11px;">0 KB/s</span>';
      if (d.speed_kbps > 100) {
        speedStr = `<span class="badge" style="background:rgba(16,185,129,0.18); color:#34d399; font-weight:700; font-size:11px; border: 1px solid rgba(16,185,129,0.4);">⚡ ${d.speed_kbps} KB/s</span>`;
      } else if (d.speed_kbps > 0) {
        speedStr = `<span class="badge" style="background:rgba(59,130,246,0.15); color:#60a5fa; font-weight:600; font-size:11px; border: 1px solid rgba(59,130,246,0.3);">⚡ ${d.speed_kbps} KB/s</span>`;
      }

      return `
        <tr style="${isPaused || isBlocked ? 'opacity: 0.75; background: rgba(0,0,0,0.2);' : ''}">
          <td>
            <div style="display:flex; align-items:center; gap:12px;">
              <span style="font-size: 20px;">${icon}</span>
              <div>
                <div style="font-weight:600; color:${isBlocked ? '#f87171' : (isPaused ? '#fbbf24' : '#ffffff')}; font-size:13.5px;">
                  ${d.name || 'Wi-Fi Client'}
                </div>
                <div style="font-family:var(--font-mono); font-size:11px; color:#94a3b8;">${d.ip}</div>
              </div>
            </div>
          </td>
          <td><code class="code-badge" style="font-size: 11px;">${d.mac || '--'}</code></td>
          <td style="color:#cbd5e1; font-size:12px;">${d.type || 'Connected Device'}</td>
          <td style="font-family:var(--font-mono);">${dataUsedStr}</td>
          <td style="font-family:var(--font-mono);">${speedStr}</td>
          <td>${statusBadge}</td>
          <td style="text-align: right;">
            <div style="display: inline-flex; gap: 6px; align-items: center;">
              ${isPaused
                ? `<button class="btn btn-secondary btn-sm pause-btn" data-ip="${d.ip}" data-pause="false" style="padding: 3px 9px; font-size: 11px; color: #34d399; border-color: rgba(16,185,129,0.3);">▶️ Resume</button>`
                : `<button class="btn btn-secondary btn-sm pause-btn" data-ip="${d.ip}" data-pause="true" style="padding: 3px 9px; font-size: 11px; color: #fbbf24; border-color: rgba(245,158,11,0.3);">⏸️ Pause</button>`}
              
              ${isBlocked
                ? `<button class="btn btn-secondary btn-sm unblock-btn" data-ip="${d.ip}" style="padding: 3px 9px; font-size: 11px; color: #10b981;">🟢 Restore</button>`
                : `<button class="btn btn-danger btn-sm force-kill-btn" data-ip="${d.ip}" style="padding: 3px 9px; font-size: 11px; background: rgba(239,68,68,0.25); border: 1px solid #ef4444; color: #fca5a5;" title="Instantly cut off all internet connection for this device">⚡ Cut-Off</button>`}
            </div>
          </td>
        </tr>
      `;
    }).join('');

    // Event Listeners for Pause Buttons
    document.querySelectorAll('.pause-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const ip = e.currentTarget.getAttribute('data-ip');
        const shouldPause = e.currentTarget.getAttribute('data-pause') === 'true';
        await apiPost('wifi-devices/pause', { ip, paused: shouldPause });
        showToast(shouldPause ? `⏸️ Internet paused on ${ip}` : `▶️ Internet restored on ${ip}`);
        refreshWifiDevices();
      });
    });

    // Event Listeners for Force Kill / Cut-Off Buttons
    document.querySelectorAll('.force-kill-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const ip = e.currentTarget.getAttribute('data-ip');
        if (confirm(`⚡ Hard cut-off internet for ${ip}? Zero web pages or apps will resolve until restored.`)) {
          await apiPost('wifi-devices/force-kill', { ip });
          showToast(`⚡ Device ${ip} internet completely severed & blocked!`);
          refreshWifiDevices();
        }
      });
    });

    // Event Listeners for Kick / Unblock Buttons
    document.querySelectorAll('.kick-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const ip = e.currentTarget.getAttribute('data-ip');
        const mac = e.currentTarget.getAttribute('data-mac') || '';
        if (confirm(`Kick & block ${ip} from Wi-Fi internet?`)) {
          await apiPost('wifi-devices/block', { ip, mac });
          showToast(`🚫 Device ${ip} kicked & blocked!`);
          refreshWifiDevices();
        }
      });
    });

    document.querySelectorAll('.unblock-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const ip = e.currentTarget.getAttribute('data-ip');
        await apiPost('wifi-devices/unblock', { ip });
        showToast(`🟢 Device ${ip} unblocked and restored!`);
        refreshWifiDevices();
      });
    });
  }

  // --- REFRESH REAL-TIME QUERY LOGS ---
  async function refreshDnsLogs() {
    const tbody = document.getElementById('dnsLogsTableBody');
    const countBadge = document.getElementById('dnsLogsCountBadge');
    if (!tbody) return;

    const res = await apiGet(`dns-logs?id=${encodeURIComponent(currentConfigId)}&limit=100`);
    if (res && res.logs) {
      activeLogs = res.logs;
      if (countBadge) countBadge.textContent = `${res.logs.length} Live`;
      renderLogsTable();
    }
  }

  function renderLogsTable() {
    const tbody = document.getElementById('dnsLogsTableBody');
    const filterSelect = document.getElementById('logFilterSelect');
    if (!tbody) return;

    const filterVal = filterSelect ? filterSelect.value : 'ALL';
    let filtered = activeLogs;

    if (filterVal === 'BLOCKED') {
      filtered = activeLogs.filter(l => l.status.startsWith('BLOCKED'));
    } else if (filterVal === 'BLOCKED_AD') {
      filtered = activeLogs.filter(l => l.status === 'BLOCKED_AD');
    } else if (filterVal === 'BLOCKED_ADULT') {
      filtered = activeLogs.filter(l => l.status === 'BLOCKED_ADULT');
    } else if (filterVal === 'ALLOWED') {
      filtered = activeLogs.filter(l => l.status === 'ALLOWED');
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center; color: var(--text-sub); padding: 30px;">
            ${activeLogs.length === 0 ? 'Listening for real-time DNS queries from your router and devices...' : 'No queries match the selected filter.'}
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = filtered.map(log => {
      const d = new Date(log.timestamp * 1000);
      const timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      
      let badgeHtml = '';
      if (log.status === 'BLOCKED_AD') {
        badgeHtml = `<span class="badge" style="background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3); font-size: 10px;">🚫 AD / TRACKER</span>`;
      } else if (log.status === 'BLOCKED_ADULT') {
        badgeHtml = `<span class="badge" style="background: rgba(168,85,247,0.15); color: #c084fc; border: 1px solid rgba(168,85,247,0.3); font-size: 10px;">🔞 18+ ADULT</span>`;
      } else if (log.status === 'BLOCKED_SMART_TV') {
        badgeHtml = `<span class="badge" style="background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.3); font-size: 10px;">📺 SMART TV AD</span>`;
      } else if (log.status === 'BLOCKED_PAUSED') {
        badgeHtml = `<span class="badge" style="background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.3); font-size: 10px;">⏸️ PAUSED</span>`;
      } else if (log.status === 'BLOCKED_KICKED') {
        badgeHtml = `<span class="badge" style="background: rgba(239,68,68,0.25); color: #fca5a5; border: 1px solid rgba(239,68,68,0.5); font-weight: 700; font-size: 10px;">⚡ CUT-OFF / KICKED</span>`;
      } else {
        badgeHtml = `<span class="badge" style="background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); font-size: 10px;">🟢 ALLOWED</span>`;
      }

      return `
        <tr style="${log.status.startsWith('BLOCKED') ? 'background: rgba(239,68,68,0.02);' : ''}">
          <td style="font-family: var(--font-mono); font-size: 11px; color: #94a3b8;">${timeStr}</td>
          <td>${badgeHtml}</td>
          <td>
            <strong style="font-family: var(--font-mono); font-size: 12px; color: ${log.status.startsWith('BLOCKED') ? '#fca5a5' : '#f8fafc'}; word-break: break-all;">
              ${log.domain}
            </strong>
          </td>
          <td>
            <span style="font-family: var(--font-mono); font-size: 11px; color: #60a5fa;">
              ${log.device_name || log.client_ip}
            </span>
          </td>
          <td><code class="code-badge" style="font-size: 10px;">${log.qtype}</code></td>
        </tr>
      `;
    }).join('');
  }

  // --- NETWORK DETECTION & LINKED IP ---
  async function detectDnsStatus() {
    const banner = document.getElementById('nextdnsStatusBanner');
    const mainText = document.getElementById('bannerMainText');
    const subText = document.getElementById('bannerSubText');
    if (!banner || !mainText) return;

    try {
      const res = await apiGet('dns-detect');
      if (res) {
        currentDetectedIp = res.client_ip;
        isCurrentIpLinked = res.is_linked;
        
        const ipDisplay = document.getElementById('detectedPublicIpDisplay');
        if (ipDisplay) ipDisplay.textContent = currentDetectedIp;

        updateLinkIpButton(res.is_linked);

        if (res.is_linked) {
          banner.className = 'nextdns-status-banner active';
          mainText.innerHTML = '🟢 All good! This network is actively shielded by OFFICIALUM1.';
          subText.textContent = `Router WAN IP ${res.client_ip} is linked to configuration '${currentConfigId}'. All devices protected.`;
        } else if (res.is_remote_view) {
          banner.className = 'nextdns-status-banner active';
          const routerIps = (res.linked_ips || []).join(', ');
          mainText.innerHTML = '🟢 Home Network Protected (Remote Mobile View)';
          subText.textContent = `Your Home Router WAN IP (${routerIps}) is actively shielded. Viewing dashboard remotely from mobile network (${res.client_ip}).`;
        } else if (res.is_using_officialum1) {
          banner.className = 'nextdns-status-banner active';
          mainText.innerHTML = '🟢 Shield Active: Protected by OFFICIALUM1.';
          subText.textContent = `Network traffic on configuration '${currentConfigId}' is actively shielded.`;
        } else {
          banner.className = 'nextdns-status-banner inactive';
          mainText.innerHTML = '🔴 This network is not using this configuration.';
          subText.textContent = `Router WAN IP is ${res.client_ip}. Click 'Link IP' or configure your router DHCP.`;
        }
      }
    } catch (e) {
      console.error('Failed to detect DNS status', e);
    }
  }

  function updateLinkIpButton(isLinked) {
    const btn = document.getElementById('toggleLinkIpBtn');
    if (!btn) return;
    if (isLinked) {
      btn.className = 'btn btn-sm btn-secondary';
      btn.innerHTML = '✅ IP Linked';
    } else {
      btn.className = 'btn btn-sm btn-primary';
      btn.innerHTML = '🔗 Link IP';
    }
  }

  async function toggleLinkIp() {
    const action = isCurrentIpLinked ? 'unlink' : 'link';
    const res = await apiPost('config/link-ip', { ip: currentDetectedIp, action });
    if (res) {
      isCurrentIpLinked = (action === 'link');
      updateLinkIpButton(isCurrentIpLinked);
      showToast(`Router WAN IP ${currentDetectedIp} ${isCurrentIpLinked ? 'Linked Successfully! 🎉' : 'Unlinked.'}`);
      detectDnsStatus();
    }
  }

  // --- TAB NAVIGATION SYSTEM ---
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const target = e.currentTarget.getAttribute('data-tab');
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      e.currentTarget.classList.add('active');
      const pane = document.getElementById(target);
      if (pane) pane.classList.add('active');

      if (target === 'wifiTab') refreshWifiDevices();
      if (target === 'logsTab') refreshDnsLogs();
      if (target === 'setupTab') detectDnsStatus();
    });
  });

  // --- CONNECT DEVICE MODAL ---
  const guideModal = document.getElementById('guideModal');
  const openGuideBtn = document.getElementById('openGuideBtn');
  const closeGuideModalBtn = document.getElementById('closeGuideModalBtn');
  const closeGuideDoneBtn = document.getElementById('closeGuideDoneBtn');
  const shareInput = document.getElementById('shareDeviceNameInput');
  const shareLinkEl = document.getElementById('shareGeneratedLink');
  const copyShareBtn = document.getElementById('copyShareLinkBtn');

  function updateShareLink() {
    if (!shareInput || !shareLinkEl) return;
    const devName = shareInput.value.trim().replace(/\s+/g, '-') || 'MyDevice';
    const origin = window.location.origin;
    shareLinkEl.textContent = `${origin}/connect?name=${encodeURIComponent(devName)}&config=${encodeURIComponent(currentConfigId)}`;
  }

  if (openGuideBtn) {
    openGuideBtn.addEventListener('click', () => {
      updateShareLink();
      guideModal.classList.add('open');
    });
  }
  if (closeGuideModalBtn) closeGuideModalBtn.addEventListener('click', () => guideModal.classList.remove('open'));
  if (closeGuideDoneBtn) closeGuideDoneBtn.addEventListener('click', () => guideModal.classList.remove('open'));

  if (shareInput) {
    shareInput.addEventListener('input', updateShareLink);
    updateShareLink();
  }

  if (copyShareBtn && shareLinkEl) {
    copyShareBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(shareLinkEl.textContent);
      showToast('Copied device share link to clipboard! 📋');
    });
  }

  // Copy buttons for setup endpoint chips
  document.querySelectorAll('.chip-copy-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const val = e.currentTarget.getAttribute('data-copy');
      if (val) {
        navigator.clipboard.writeText(val);
        showToast(`Copied ${val} to clipboard! 📋`);
      }
    });
  });

  // --- EVENT LISTENERS: SHIELDS & POLICY TOGGLES ---
  async function updateShield(key, currentVal) {
    const newVal = currentVal ? 0 : 1;
    const res = await apiPost('config/update-shields', { [key]: newVal });
    if (res) {
      showToast(`Shield policy updated successfully! 🛡️`);
      refreshStatus();
    }
  }

  // Top Ribbon Toggles
  const toggleDnsBtn = document.getElementById('toggleDnsBtn');
  if (toggleDnsBtn) {
    toggleDnsBtn.addEventListener('click', () => {
      const active = !toggleDnsBtn.classList.contains('off');
      updateShield('adblock_enabled', active);
    });
  }

  const toggleAdultBtn = document.getElementById('toggleAdultBtn');
  if (toggleAdultBtn) {
    toggleAdultBtn.addEventListener('click', () => {
      const active = !toggleAdultBtn.classList.contains('off');
      updateShield('adult_block_enabled', active);
    });
  }

  const toggleTvShieldBtn = document.getElementById('toggleTvShieldBtn');
  if (toggleTvShieldBtn) {
    toggleTvShieldBtn.addEventListener('click', () => {
      const active = !toggleTvShieldBtn.classList.contains('off');
      updateShield('smart_tv_shield', active);
    });
  }

  // Shields Tab Detailed Cards
  const userShieldAdblock = document.getElementById('userShieldAdblockBtn');
  if (userShieldAdblock) {
    userShieldAdblock.addEventListener('click', () => {
      const active = userShieldAdblock.classList.contains('active');
      updateShield('adblock_enabled', active);
    });
  }

  const userShieldAdult = document.getElementById('userShieldAdultBtn');
  if (userShieldAdult) {
    userShieldAdult.addEventListener('click', () => {
      const active = userShieldAdult.classList.contains('active');
      updateShield('adult_block_enabled', active);
    });
  }

  const userShieldSmartTv = document.getElementById('userShieldSmartTvBtn');
  if (userShieldSmartTv) {
    userShieldSmartTv.addEventListener('click', () => {
      const active = userShieldSmartTv.classList.contains('active');
      updateShield('smart_tv_shield', active);
    });
  }

  const userShieldSafeSearch = document.getElementById('userShieldSafeSearchBtn');
  if (userShieldSafeSearch) {
    userShieldSafeSearch.addEventListener('click', () => {
      const active = userShieldSafeSearch.classList.contains('active');
      updateShield('safesearch_enabled', active);
    });
  }

  const toggleLinkIpBtn = document.getElementById('toggleLinkIpBtn');
  if (toggleLinkIpBtn) {
    toggleLinkIpBtn.addEventListener('click', toggleLinkIp);
  }

  const recheckStatusBtn = document.getElementById('recheckStatusBtn');
  if (recheckStatusBtn) {
    recheckStatusBtn.addEventListener('click', () => {
      detectDnsStatus();
      showToast('Checking network DNS status...');
    });
  }

  const refreshWifiBtn = document.getElementById('refreshWifiBtn');
  if (refreshWifiBtn) {
    refreshWifiBtn.addEventListener('click', () => {
      refreshWifiDevices();
      showToast('Scanning Wi-Fi devices...');
    });
  }

  const clearLogsBtn = document.getElementById('clearLogsBtn');
  if (clearLogsBtn) {
    clearLogsBtn.addEventListener('click', async () => {
      await apiPost('dns-logs/clear', {});
      showToast('DNS query logs cleared.');
      refreshDnsLogs();
    });
  }

  const logFilterSelect = document.getElementById('logFilterSelect');
  if (logFilterSelect) {
    logFilterSelect.addEventListener('change', renderLogsTable);
  }

  // Copy Hub IP
  const copyHubIpBtn = document.getElementById('copyHubIpBtn');
  if (copyHubIpBtn) {
    copyHubIpBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(currentHubIp);
      showToast(`Copied Hub IP ${currentHubIp} to clipboard!`);
    });
  }

  // --- INITIAL BOOTSTRAP ---
  refreshStatus();
  refreshWifiDevices();
  detectDnsStatus();
  refreshDnsLogs();

  // Uptime ticker
  setInterval(updateSystemMonitor, 1000);

  // Background Auto-Sync Intervals
  setInterval(refreshStatus, 3000);
  setInterval(refreshWifiDevices, 2500);
  setInterval(detectDnsStatus, 6000);
  setInterval(() => {
    const logsTab = document.getElementById('logsTab');
    if (logsTab && logsTab.classList.contains('active')) {
      refreshDnsLogs();
    }
  }, 2000);

})();
