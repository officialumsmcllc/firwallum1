/**
 * OFFICIALUM1 — Premium SaaS Dashboard Logic
 * Reactive port matrix, proxy assignments, live exit IP verification, 
 * system monitor, and uptime tracking.
 */

(function () {
  'use strict';

  let currentHubIp = '192.168.100.158';
  let cachedProxies = [];
  const startTime = Date.now();
  let totalTrafficBytes = 0;

  // --- API HELPERS ---
  async function apiGet(endpoint) {
    try {
      const res = await fetch(`/api/${endpoint}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e) {
      console.warn(`GET /api/${endpoint} error:`, e);
      return null;
    }
  }

  async function apiPost(endpoint, body) {
    try {
      const res = await fetch(`/api/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      return await res.json();
    } catch (e) {
      console.error(`POST /api/${endpoint} error:`, e);
      return null;
    }
  }

  async function apiDelete(endpoint) {
    try {
      const res = await fetch(`/api/${endpoint}`, { method: 'DELETE' });
      return await res.json();
    } catch (e) {
      console.error(`DELETE /api/${endpoint} error:`, e);
      return null;
    }
  }

  // --- TOAST ---
  function showToast(msg, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {
      toast.classList.remove('show');
    }, 3000);
  }

  // --- UPTIME FORMATTER ---
  function formatUptime(ms) {
    const totalSec = Math.floor(ms / 1000);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  function formatBytes(bytes) {
    if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(2) + ' GB';
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
    if (bytes >= 1024) return (bytes / 1024).toFixed(0) + ' KB';
    return bytes + ' B';
  }

  // --- UPDATE SYSTEM MONITOR BAR ---
  function updateSystemMonitor(data) {
    const elapsed = Date.now() - startTime;

    const uptimeEl = document.getElementById('sysUptime');
    const uptimeDisplayEl = document.getElementById('uptimeDisplay');
    if (uptimeEl) uptimeEl.textContent = formatUptime(elapsed);
    if (uptimeDisplayEl) uptimeDisplayEl.textContent = formatUptime(elapsed);

    if (data) {
      const totalTrafficEl = document.getElementById('sysTotalTraffic');
      if (totalTrafficEl && totalTrafficBytes > 0) {
        totalTrafficEl.textContent = formatBytes(totalTrafficBytes);
      }

      const connEl = document.getElementById('sysConnections');
      if (connEl) connEl.textContent = `${data.active_devices || 0} active`;

      const dnsEl = document.getElementById('sysDnsQueries');
      if (dnsEl) dnsEl.textContent = `${(data.blocked_domains_count || 0).toLocaleString()} blocked`;

      const gwEl = document.getElementById('sysGatewayStatus');
      if (gwEl) {
        if (data.proxy_gateway_enabled) {
          gwEl.innerHTML = '<span style="color:#10b981;">●</span>&nbsp;Online';
        } else {
          gwEl.innerHTML = '<span style="color:#f59e0b;">●</span>&nbsp;Bypassed';
        }
      }
    }
  }

  // --- REFRESH STATUS ---
  async function refreshStatus() {
    const data = await apiGet('status');
    if (data) {
      currentHubIp = data.hub_ip;
      const hubIpEl = document.getElementById('hubIpDisplay');
      if (hubIpEl) hubIpEl.textContent = currentHubIp;
      
      const guideHubIp = document.getElementById('guideHubIp');
      if (guideHubIp) guideHubIp.textContent = currentHubIp;
      
      const guideProxyIpCode = document.getElementById('guideProxyIpCode');
      if (guideProxyIpCode) guideProxyIpCode.textContent = currentHubIp;
      
      const guidePacScriptCode = document.getElementById('guidePacScriptCode');
      if (guidePacScriptCode) guidePacScriptCode.textContent = `http://${currentHubIp}:8088/proxy.pac`;

      const totalDevs = data.active_devices || 0;
      const proxyCount = data.proxy_active_count || 0;
      const dnsCount = data.dns_clients_count || 0;
      
      const statActiveEl = document.getElementById('statActiveCount');
      if (statActiveEl) statActiveEl.textContent = `${totalDevs} Active`;

      const subEl = document.getElementById('statActiveSub');
      if (subEl) {
        if (dnsCount > 0) {
          subEl.textContent = `${dnsCount} Wi-Fi · ${proxyCount} Proxy`;
          subEl.title = `Live IPs: ${(data.dns_clients || []).join(', ')}`;
        } else {
          subEl.textContent = `${proxyCount} Proxy Tunnels`;
        }
      }

      const dnsCountEl = document.getElementById('statDnsCount');
      if (dnsCountEl) dnsCountEl.textContent = `${(data.blocked_domains_count || 0).toLocaleString()} threat domains blocked`;

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
      const adultCountEl = document.getElementById('statAdultCount');
      if (adultBtn && adultText) {
        if (data.adult_block_enabled) {
          adultBtn.classList.remove('off');
          adultText.textContent = 'Active';
          if (adultCountEl) adultCountEl.textContent = '18+ adult sites & explicit ads blocked';
        } else {
          adultBtn.classList.add('off');
          adultText.textContent = 'Allowed';
          if (adultCountEl) adultCountEl.textContent = 'Adult filter disabled';
        }
      }

      const proxyBtn = document.getElementById('toggleProxyGatewayBtn');
      const proxyText = document.getElementById('statProxyGatewayText');
      const proxySub = document.getElementById('statProxyGatewaySub');
      if (proxyBtn && proxyText) {
        if (data.proxy_gateway_enabled) {
          proxyBtn.classList.remove('off');
          proxyText.textContent = 'Active';
          if (proxySub) proxySub.textContent = 'Routing Ports 8101-8110';
        } else {
          proxyBtn.classList.add('off');
          proxyText.textContent = 'Bypassed (OFF)';
          if (proxySub) proxySub.textContent = 'Direct Full-Speed Wi-Fi';
        }
      }

      updateSystemMonitor(data);
    }
  }

  // --- REFRESH PORTS ---
  async function refreshPorts() {
    const proxyData = await apiGet('proxies');
    cachedProxies = (proxyData && proxyData.proxies) ? proxyData.proxies : [];
    
    const proxiesCountEl = document.getElementById('statProxiesCount');
    if (proxiesCountEl) proxiesCountEl.textContent = `${cachedProxies.length} Available`;

    const portsData = await apiGet('ports');
    if (!portsData || !portsData.ports) return;

    // Accumulate total traffic
    let portTrafficTotal = 0;
    portsData.ports.forEach(p => {
      if (p.total_mb) portTrafficTotal += p.total_mb;
    });

    const container = document.getElementById('portsGridContainer');
    if (!container) return;
    container.innerHTML = '';

    portsData.ports.forEach(p => {
      const card = document.createElement('div');
      const isActive = p.status === 'ACTIVE';
      card.className = `port-card ${isActive ? 'active-tunnel' : ''}`;

      const exitIpDisplay = p.exit_ip && p.exit_ip !== 'Unknown'
        ? `${p.exit_ip} (${p.country || 'Online'})`
        : (p.proxy_id ? 'Proxy Bound (Ready)' : 'Direct Internet (No Proxy)');

      // Generate Proxy Select Options
      let proxyOptions = `<option value="0">None / Direct Internet</option>`;
      cachedProxies.forEach(pr => {
        const selected = p.proxy_id === pr.id ? 'selected' : '';
        proxyOptions += `<option value="${pr.id}" ${selected}>${pr.name} [${pr.exit_ip || pr.host}]</option>`;
      });

      // Speed display with color coding
      let speedHtml = '';
      if (p.speed_kbps > 100) {
        speedHtml = `<span style="color:#10b981; font-weight:600;">⚡ ${p.speed_kbps} KB/s</span>`;
      } else if (p.speed_kbps > 0) {
        speedHtml = `<span style="color:#60a5fa;">⚡ ${p.speed_kbps} KB/s</span>`;
      } else {
        speedHtml = `<span style="color:#64748b;">0 KB/s</span>`;
      }

      card.innerHTML = `
        <div class="port-card-top">
          <div class="port-badge">PORT ${p.port}</div>
          <span class="port-status-badge ${p.status ? p.status.toLowerCase() : 'standby'}">${p.status || 'STANDBY'}</span>
        </div>

        <div class="device-name-row">
          <div>
            <span class="device-name-text" id="devName-${p.port}">${p.device_name}</span>
            ${p.client_ip ? `<div style="font-size:11px; color:#34d399; font-family:var(--font-mono); margin-top:2px;">🔗 Bound: ${p.client_ip} ${p.client_mac ? `(${p.client_mac})` : ''}</div>` : ''}
          </div>
          <button class="btn btn-secondary btn-sm rename-port-btn" data-port="${p.port}" data-name="${p.device_name}" title="Rename Device">Edit Name</button>
        </div>

        <div class="proxy-select-box">
          <label>ASSIGNED EXIT PROXY / VPN</label>
          <select class="form-control proxy-dropdown" data-port="${p.port}">
            ${proxyOptions}
          </select>
        </div>

        <div class="proxy-select-box" style="margin-top: 8px;">
          <label>SPEED EQUALIZER LIMIT (QOS)</label>
          <select class="form-control speed-limit-dropdown" data-port="${p.port}">
            <option value="0" ${(p.rate_limit_mbps === 0 || !p.rate_limit_mbps) ? 'selected' : ''}>⚡ Unlimited / Max Speed</option>
            <option value="1" ${p.rate_limit_mbps === 1 ? 'selected' : ''}>🐢 1.0 Mbps (Fair-Share Mobile)</option>
            <option value="2" ${p.rate_limit_mbps === 2 ? 'selected' : ''}>🚀 2.0 Mbps (Standard Worker)</option>
            <option value="3" ${p.rate_limit_mbps === 3 ? 'selected' : ''}>🔥 3.0 Mbps (Heavy Freelancer)</option>
            <option value="5" ${p.rate_limit_mbps === 5 ? 'selected' : ''}>⭐ 5.0 Mbps (VIP Priority)</option>
          </select>
        </div>

        <div class="exit-ip-info">
          <div>
            <div class="exit-ip-label">PUBLIC EXIT IP (WHAT FIVERR SEES)</div>
            <div class="exit-ip-val">${exitIpDisplay}</div>
            <div style="font-size:11px; color:#93c5fd; margin-top:3px; font-family:var(--font-mono);">
              ${speedHtml} · Used: ${p.total_mb || 0} MB
            </div>
          </div>
          ${p.latency_ms > 0 ? `<span class="badge-tag online">${p.latency_ms} ms</span>` : ''}
        </div>

        <div class="port-footer">
          <div class="connection-string">${currentHubIp}:${p.port}</div>
          <div style="display: flex; gap: 6px;">
            <button class="btn btn-secondary btn-sm copy-proxy-btn" data-conn="${currentHubIp}:${p.port}">Copy Proxy</button>
            ${p.proxy_id ? `<button class="btn btn-primary btn-sm test-port-proxy-btn" data-proxyid="${p.proxy_id}">Test IP</button>` : ''}
          </div>
        </div>
      `;

      container.appendChild(card);
    });

    // Event Handlers for Ports Grid
    document.querySelectorAll('.speed-limit-dropdown').forEach(sel => {
      sel.addEventListener('change', async (e) => {
        const port = parseInt(e.currentTarget.getAttribute('data-port'));
        const limitVal = parseFloat(e.currentTarget.value);
        await apiPost('ports/limit', { port: port, rate_limit_mbps: limitVal });
        showToast(`Port ${port} limit set to ${limitVal > 0 ? `${limitVal} Mbps` : 'Unlimited'}`);
      });
    });

    document.querySelectorAll('.rename-port-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const port = e.currentTarget.getAttribute('data-port');
        const oldName = e.currentTarget.getAttribute('data-name');
        const newName = prompt(`Enter device label for Port ${port}:`, oldName);
        if (newName && newName.trim()) {
          await apiPost('ports/update', { port: parseInt(port), device_name: newName.trim() });
          showToast(`Port ${port} renamed to "${newName.trim()}"`);
          refreshPorts();
        }
      });
    });

    document.querySelectorAll('.proxy-dropdown').forEach(sel => {
      sel.addEventListener('change', async (e) => {
        const port = parseInt(e.currentTarget.getAttribute('data-port'));
        const proxyId = parseInt(e.currentTarget.value);
        await apiPost('ports/update', { port: port, proxy_id: proxyId });
        showToast(`Port ${port} assigned to selected proxy tunnel!`);
        refreshPorts();
      });
    });

    document.querySelectorAll('.copy-proxy-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const conn = e.currentTarget.getAttribute('data-conn');
        navigator.clipboard.writeText(conn);
        showToast(`Copied "${conn}" to clipboard!`);
      });
    });

    document.querySelectorAll('.test-port-proxy-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const pid = e.currentTarget.getAttribute('data-proxyid');
        showToast('Testing proxy connection & discovering exit IP...');
        const res = await apiPost('proxies/test', { id: pid });
        if (res && res.result) {
          showToast(`Test Result: IP ${res.result.exit_ip} (${res.result.country}) - ${res.result.latency_ms}ms`);
          refreshPorts();
          refreshProxiesTable();
        }
      });
    });
  }

  // --- REFRESH PROXIES TABLE ---
  async function refreshProxiesTable() {
    const data = await apiGet('proxies');
    if (!data || !data.proxies) return;

    const tbody = document.getElementById('proxiesTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (data.proxies.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 36px;">No proxies added yet. Click "Add New Proxy" to connect your first exit tunnel.</td></tr>`;
      return;
    }

    data.proxies.forEach(pr => {
      const tr = document.createElement('tr');
      const statusClass = pr.status ? pr.status.toLowerCase() : 'untested';
      tr.innerHTML = `
        <td style="font-weight: 600; color: #e2e8f0;">${pr.name}</td>
        <td><span class="code-badge">${pr.protocol.toUpperCase()}</span></td>
        <td style="font-family: var(--font-mono); color: #94a3b8; font-size: 12px;">${pr.host}:${pr.port}</td>
        <td style="font-family: var(--font-mono); color: #34d399; font-weight: 600;">${pr.exit_ip || 'Untested'}</td>
        <td style="color: #d1d5db;">${pr.country || '-'}</td>
        <td style="color: #93c5fd; font-family: var(--font-mono);">${pr.latency_ms > 0 ? `${pr.latency_ms} ms` : '-'}</td>
        <td><span class="badge-tag ${statusClass}">${pr.status || 'UNTESTED'}</span></td>
        <td style="text-align: right;">
          <button class="btn btn-secondary btn-sm test-single-proxy-btn" data-id="${pr.id}">Test</button>
          <button class="btn btn-danger btn-sm delete-proxy-btn" data-id="${pr.id}">Delete</button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    document.querySelectorAll('.test-single-proxy-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const pid = e.currentTarget.getAttribute('data-id');
        showToast('Testing proxy and resolving exit IP...');
        const res = await apiPost('proxies/test', { id: pid });
        if (res && res.result) {
          showToast(`Exit IP: ${res.result.exit_ip} (${res.result.country})`);
          refreshProxiesTable();
          refreshPorts();
        }
      });
    });

    document.querySelectorAll('.delete-proxy-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const pid = e.currentTarget.getAttribute('data-id');
        if (confirm('Delete this proxy profile?')) {
          await apiDelete(`proxies/delete?id=${pid}`);
          showToast('Proxy deleted.');
          refreshProxiesTable();
          refreshPorts();
        }
      });
    });
  }

  // --- TABS SWITCHER ---
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-tab');
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const pane = document.getElementById(target);
      if (pane) pane.classList.add('active');

      if (target === 'proxiesTab') refreshProxiesTable();
      if (target === 'portsTab') refreshPorts();
      if (target === 'wifiTab') refreshWifiDevices();
    });
  });

  // --- REFRESH WI-FI DEVICES ---
  let knownDeviceIps = new Set();
  let isInitialDeviceLoad = true;

  async function refreshWifiDevices() {
    const data = await apiGet('wifi-devices');
    const badge = document.getElementById('wifiDeviceCountBadge');
    if (badge && data && data.total_count !== undefined) {
      badge.textContent = `${data.total_count} Online`;
    }

    // Auto-detect newly connected devices and show instant NextDNS-style alert
    if (data && data.devices) {
      data.devices.forEach(d => {
        if (!knownDeviceIps.has(d.ip)) {
          if (!isInitialDeviceLoad) {
            showToast(`🟢 New Device Connected: ${d.name || d.ip}!`);
          }
          knownDeviceIps.add(d.ip);
        }
      });
      isInitialDeviceLoad = false;
    }

    const tbody = document.getElementById('wifiDevicesTableBody');
    if (!tbody) return;

    if (!data || !data.devices || data.devices.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align:center; padding: 48px; color: var(--text-muted);">
            <div style="font-size:28px; margin-bottom:12px;">📡</div>
            Scanning network... No external Wi-Fi clients recorded yet.<br>
            <span style="font-size:12px; color:var(--text-dim); margin-top:6px; display:inline-block;">Turn any mobile or laptop Wi-Fi OFF and ON to connect instantly to OFFICIALUM1 Shield.</span>
          </td>
        </tr>
      `;
      return;
    }

    // Accumulate Wi-Fi device traffic
    let wifiTrafficTotal = 0;
    data.devices.forEach(d => {
      if (d.total_mb) wifiTrafficTotal += d.total_mb;
    });
    totalTrafficBytes = wifiTrafficTotal * 1048576;

    tbody.innerHTML = data.devices.map(d => `
      <tr style="${d.is_blocked ? 'opacity: 0.7; background: rgba(239,68,68,0.03);' : ''}">
        <td>
          <div style="display:flex; align-items:center; gap:10px;">
            <span style="width:9px; height:9px; border-radius:50%; background:${d.is_blocked ? '#ef4444' : '#10b981'}; box-shadow:0 0 8px ${d.is_blocked ? 'rgba(239,68,68,0.5)' : 'rgba(16,185,129,0.5)'}; display:inline-block; flex-shrink:0;"></span>
            <div>
              <div style="font-weight:600; color:${d.is_blocked ? '#f87171' : 'var(--text-main)'}; font-size:13px;">${d.name || 'Wi-Fi Client'}</div>
              <div style="font-family:var(--font-mono); font-size:11px; color:#94a3b8;">${d.ip}</div>
            </div>
          </div>
        </td>
        <td><code class="code-badge">${d.mac}</code></td>
        <td style="color:#e5e7eb; font-size:12px;">${d.type}</td>
        <td>
          ${d.speed_kbps > 0 
            ? `<span class="badge" style="background:rgba(59,130,246,0.12); color:#60a5fa; font-family:var(--font-mono); font-weight:600; font-size:11px;">⚡ ${d.speed_kbps} KB/s</span>` 
            : `<span style="color:var(--text-dim); font-size:11px; font-family:var(--font-mono);">0 KB/s</span>`}
        </td>
        <td style="font-family:var(--font-mono); font-size:12px; color:#d1d5db;">
          ${d.total_mb > 0 ? `${d.total_mb} MB` : '0 MB'}
        </td>
        <td>
          <select class="form-control device-port-select" data-ip="${d.ip}" data-mac="${d.mac}" style="padding: 4px 8px; font-size: 11px; width: 140px; background: rgba(15,23,42,0.7); border: 1px solid rgba(71,85,105,0.3);">
            <option value="0" ${!d.assigned_port ? 'selected' : ''}>Auto Detect</option>
            ${[8101, 8102, 8103, 8104, 8105, 8106, 8107, 8108, 8109, 8110].map(pt => `
              <option value="${pt}" ${d.assigned_port === pt ? 'selected' : ''}>Port ${pt} ${pt === 8101 ? '(Main PC)' : (pt === 8102 ? '(Laptop 2)' : '')}</option>
            `).join('')}
          </select>
        </td>
        <td>
          ${d.is_blocked 
            ? `<span class="badge" style="background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.3); font-size:10px;">🚫 KICKED</span>`
            : `<span class="badge badge-active" style="font-size:10px;">🛡️ ACTIVE</span>`}
        </td>
        <td style="text-align: right;">
          ${d.is_blocked
            ? `<button class="btn btn-secondary btn-sm unblock-device-btn" data-ip="${d.ip}" style="border-color:#10b981; color:#10b981;">🟢 Unblock</button>`
            : `<button class="btn btn-danger btn-sm kick-device-btn" data-ip="${d.ip}" data-mac="${d.mac}">🚫 Kick & Block</button>`}
        </td>
      </tr>
    `).join('');

    // Device Port Binding Listener
    document.querySelectorAll('.device-port-select').forEach(sel => {
      sel.addEventListener('change', async (e) => {
        const ip = e.currentTarget.getAttribute('data-ip');
        const mac = e.currentTarget.getAttribute('data-mac') || '';
        const port = parseInt(e.currentTarget.value);
        await apiPost('ports/bind', { ip, mac, port });
        showToast(`Device ${ip} permanently bound to ${port > 0 ? `Port ${port}` : 'Auto-Detect'}`);
        refreshPorts();
      });
    });

    // Kick and Unblock listeners
    document.querySelectorAll('.kick-device-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const ip = e.currentTarget.getAttribute('data-ip');
        const mac = e.currentTarget.getAttribute('data-mac') || '';
        if (confirm(`Kick & Block device (${ip}) from Wi-Fi internet?`)) {
          await apiPost('wifi-devices/block', { ip, mac });
          showToast(`Device ${ip} Kicked & Blocked!`);
          refreshWifiDevices();
        }
      });
    });

    document.querySelectorAll('.unblock-device-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const ip = e.currentTarget.getAttribute('data-ip');
        await apiPost('wifi-devices/unblock', { ip });
        showToast(`Device ${ip} unblocked and restored!`);
        refreshWifiDevices();
      });
    });
  }

  // --- MODALS ---
  const addProxyModal = document.getElementById('addProxyModal');
  const guideModal = document.getElementById('guideModal');

  document.getElementById('openAddProxyModalBtn').addEventListener('click', () => {
    addProxyModal.classList.add('open');
  });
  document.getElementById('closeAddProxyModalBtn').addEventListener('click', () => {
    addProxyModal.classList.remove('open');
  });
  document.getElementById('cancelAddProxyBtn').addEventListener('click', () => {
    addProxyModal.classList.remove('open');
  });

  document.getElementById('openGuideBtn').addEventListener('click', () => {
    updateShareLink();
    guideModal.classList.add('open');
  });
  document.getElementById('closeGuideModalBtn').addEventListener('click', () => {
    guideModal.classList.remove('open');
  });
  document.getElementById('closeGuideDoneBtn').addEventListener('click', () => {
    guideModal.classList.remove('open');
  });

  // --- DYNAMIC SHARE LINK GENERATOR ---
  const shareInput = document.getElementById('shareDeviceNameInput');
  const shareLinkEl = document.getElementById('shareGeneratedLink');
  const copyShareBtn = document.getElementById('copyShareLinkBtn');
  const privateDnsEl = document.getElementById('guidePrivateDnsHost');

  function updateShareLink() {
    if (!shareInput || !shareLinkEl) return;
    const devName = shareInput.value.trim().replace(/\s+/g, '-') || 'MyDevice';
    const origin = window.location.origin;
    shareLinkEl.textContent = `${origin}/connect?name=${encodeURIComponent(devName)}`;
    if (privateDnsEl) {
      privateDnsEl.textContent = window.location.hostname;
    }
  }

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

  // Copy buttons for NextDNS-style endpoint chips
  document.querySelectorAll('.chip-copy-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const val = e.currentTarget.getAttribute('data-copy');
      if (val) {
        navigator.clipboard.writeText(val);
        showToast(`Copied ${val} to clipboard! 📋`);
      }
    });
  });

  // Close modals on backdrop click
  [addProxyModal, guideModal].forEach(modal => {
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('open');
      });
    }
  });

  // Close modals on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (addProxyModal) addProxyModal.classList.remove('open');
      if (guideModal) guideModal.classList.remove('open');
    }
  });

  // --- ADD PROXY FORM SUBMIT ---
  document.getElementById('addProxyForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('proxyNameInput').value.trim();
    const protocol = document.getElementById('proxyProtocolInput').value;
    const host = document.getElementById('proxyHostInput').value.trim();
    const port = document.getElementById('proxyPortInput').value.trim();
    const username = document.getElementById('proxyUserInput').value.trim();
    const password = document.getElementById('proxyPassInput').value.trim();

    showToast('Saving & testing upstream proxy connection...');
    const res = await apiPost('proxies/add', {
      name, protocol, host, port: parseInt(port), username, password
    });

    if (res && res.status === 'added') {
      showToast(`Proxy added! Exit IP: ${res.test.exit_ip} (${res.test.country})`);
      addProxyModal.classList.remove('open');
      document.getElementById('addProxyForm').reset();
      refreshProxiesTable();
      refreshPorts();
    } else {
      showToast('Error adding proxy.');
    }
  });

  // --- TOGGLE DNS ADBLOCK ---
  document.getElementById('toggleDnsBtn').addEventListener('click', async () => {
    const res = await apiPost('settings/toggle-adblock', {});
    if (res) {
      showToast(`DNS Ad-Blocker is now ${res.dns_adblock ? 'ENABLED' : 'DISABLED'}`);
      refreshStatus();
    }
  });

  // --- TOGGLE PROXY GATEWAY ---
  document.getElementById('toggleProxyGatewayBtn').addEventListener('click', async () => {
    const res = await apiPost('settings/toggle-proxy-gateway', {});
    if (res) {
      showToast(`Proxy Gateway is now ${res.proxy_gateway_enabled ? 'ACTIVE (Tunneling)' : 'BYPASSED (Direct Full Speed)'}`);
      refreshStatus();
      refreshPorts();
    }
  });

  // --- TOGGLE ADULT 18+ SHIELD ---
  const toggleAdultBtn = document.getElementById('toggleAdultBtn');
  if (toggleAdultBtn) {
    toggleAdultBtn.addEventListener('click', async () => {
      const res = await apiPost('settings/toggle-adult-block', {});
      if (res) {
        showToast(`Adult 18+ Shield is now ${res.adult_block_enabled ? 'ACTIVE (Blocked)' : 'DISABLED (Allowed)'}`);
        refreshStatus();
      }
    });
  }

  // --- COPY HUB IP ---
  document.getElementById('copyHubIpBtn').addEventListener('click', () => {
    navigator.clipboard.writeText(currentHubIp);
    showToast(`Copied Hub IP ${currentHubIp} to clipboard!`);
  });

  document.getElementById('refreshPortsBtn').addEventListener('click', () => {
    refreshPorts();
    refreshStatus();
    showToast('Status refreshed.');
  });

  const refreshWifiBtn = document.getElementById('refreshWifiBtn');
  if (refreshWifiBtn) {
    refreshWifiBtn.addEventListener('click', () => {
      refreshWifiDevices();
      refreshStatus();
      showToast('Scanning live Wi-Fi network devices...');
    });
  }

  // --- INITIAL LOAD ---
  refreshStatus();
  refreshPorts();
  refreshWifiDevices();
  
  // System monitor uptime ticker (every 1 sec)
  setInterval(() => updateSystemMonitor(null), 1000);
  
  // Auto-refresh intervals (NextDNS-style Real-Time Auto-Sync)
  setInterval(refreshStatus, 2500);
  setInterval(refreshWifiDevices, 2000);

})();
