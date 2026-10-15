/**
 * OFFICIALUM1 — High-Tech Networking Canvas & Auth Controller
 */

// ============================================================================
// 1. DYNAMIC NETWORKING TOPOLOGY SIMULATION (HTML5 CANVAS)
// ============================================================================

const canvas = document.getElementById('networkCanvas');
const ctx = canvas.getContext('2d');

let width, height;
let nodes = [];
let packets = [];
const TOTAL_NODES = 55;
const MAX_DISTANCE = 140;

const mouse = {
  x: null,
  y: null,
  radius: 120
};

window.addEventListener('mousemove', (e) => {
  mouse.x = e.clientX;
  mouse.y = e.clientY;
});

window.addEventListener('mouseout', () => {
  mouse.x = null;
  mouse.y = null;
});

function resizeCanvas() {
  width = canvas.width = window.innerWidth;
  height = canvas.height = window.innerHeight;
  initNetwork();
}

window.addEventListener('resize', resizeCanvas);

class NetworkNode {
  constructor() {
    this.x = Math.random() * width;
    this.y = Math.random() * height;
    this.vx = (Math.random() - 0.5) * 0.8;
    this.vy = (Math.random() - 0.5) * 0.8;
    this.radius = Math.random() * 2.5 + 2.0;
    this.isHub = Math.random() > 0.85; // Special high-capacity router node
    if (this.isHub) {
      this.radius = 4.5;
      this.glowColor = '#38bdf8';
    } else {
      this.glowColor = '#60a5fa';
    }
    this.pulse = Math.random() * Math.PI * 2;
  }

  update() {
    this.x += this.vx;
    this.y += this.vy;

    // Bounce off viewport boundaries
    if (this.x < 0 || this.x > width) this.vx *= -1;
    if (this.y < 0 || this.y > height) this.vy *= -1;

    // Gentle mouse repulsion
    if (mouse.x !== null && mouse.y !== null) {
      const dx = mouse.x - this.x;
      const dy = mouse.y - this.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < mouse.radius) {
        const force = (mouse.radius - dist) / mouse.radius;
        this.x -= (dx / dist) * force * 3;
        this.y -= (dy / dist) * force * 3;
      }
    }

    this.pulse += 0.04;
  }

  draw() {
    ctx.beginPath();
    const dynamicRadius = this.radius + Math.sin(this.pulse) * 0.8;
    ctx.arc(this.x, this.y, Math.max(dynamicRadius, 1), 0, Math.PI * 2);
    ctx.fillStyle = this.isHub ? '#38bdf8' : '#818cf8';
    ctx.shadowColor = this.glowColor;
    ctx.shadowBlur = this.isHub ? 14 : 6;
    ctx.fill();
    ctx.shadowBlur = 0; // reset
  }
}

class DataPacket {
  constructor(startNode, endNode) {
    this.start = startNode;
    this.end = endNode;
    this.progress = 0;
    this.speed = Math.random() * 0.015 + 0.008;
    this.color = Math.random() > 0.5 ? '#38bdf8' : '#34d399';
    this.size = Math.random() * 2 + 2;
  }

  update() {
    this.progress += this.speed;
    return this.progress <= 1;
  }

  draw() {
    const curX = this.start.x + (this.end.x - this.start.x) * this.progress;
    const curY = this.start.y + (this.end.y - this.start.y) * this.progress;

    ctx.beginPath();
    ctx.arc(curX, curY, this.size, 0, Math.PI * 2);
    ctx.fillStyle = this.color;
    ctx.shadowColor = this.color;
    ctx.shadowBlur = 10;
    ctx.fill();
    ctx.shadowBlur = 0;
  }
}

function initNetwork() {
  nodes = [];
  packets = [];
  for (let i = 0; i < TOTAL_NODES; i++) {
    nodes.push(new NetworkNode());
  }
}

function renderNetwork() {
  ctx.clearRect(0, 0, width, height);

  // 1. Draw connection links
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const dx = nodes[i].x - nodes[j].x;
      const dy = nodes[i].y - nodes[j].y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < MAX_DISTANCE) {
        const alpha = (1 - dist / MAX_DISTANCE) * 0.35;
        ctx.beginPath();
        ctx.moveTo(nodes[i].x, nodes[i].y);
        ctx.lineTo(nodes[j].x, nodes[j].y);
        ctx.strokeStyle = `rgba(56, 189, 248, ${alpha})`;
        ctx.lineWidth = alpha > 0.25 ? 1.2 : 0.7;
        ctx.stroke();

        // Spawn occasional data packet along this edge
        if (Math.random() < 0.0018 && packets.length < 24) {
          packets.push(new DataPacket(nodes[i], nodes[j]));
        }
      }
    }
  }

  // 2. Update and draw nodes
  for (const node of nodes) {
    node.update();
    node.draw();
  }

  // 3. Update and draw traveling packets
  for (let i = packets.length - 1; i >= 0; i--) {
    const p = packets[i];
    if (p.update()) {
      p.draw();
    } else {
      packets.splice(i, 1);
    }
  }

  requestAnimationFrame(renderNetwork);
}

// Initialize canvas
resizeCanvas();
requestAnimationFrame(renderNetwork);


// ============================================================================
// 2. AUTHENTICATION & PORTAL INTERACTIONS
// ============================================================================

function showMsg(text, isError = true) {
  const banner = document.getElementById('msgBanner');
  banner.textContent = text;
  banner.className = `msg-banner ${isError ? 'error' : 'success'}`;
  banner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function clearMsg() {
  const banner = document.getElementById('msgBanner');
  banner.textContent = '';
  banner.className = 'msg-banner';
}

function switchTab(mode) {
  clearMsg();
  const tabLogin = document.getElementById('tabLoginBtn');
  const tabSignup = document.getElementById('tabSignupBtn');
  const loginForm = document.getElementById('loginForm');
  const signupForm = document.getElementById('signupForm');

  if (mode === 'login') {
    tabLogin.classList.add('active');
    tabSignup.classList.remove('active');
    loginForm.classList.remove('hidden');
    signupForm.classList.add('hidden');
    document.getElementById('loginUser').focus();
  } else {
    tabSignup.classList.add('active');
    tabLogin.classList.remove('active');
    signupForm.classList.remove('hidden');
    loginForm.classList.add('hidden');
    document.getElementById('regFullName').focus();
  }
}

function selectTier(tier) {
  document.getElementById('regTier').value = tier;
  document.getElementById('tierHome').classList.toggle('selected', tier === 'home_pro');
  document.getElementById('tierBiz').classList.toggle('selected', tier === 'business');
}

async function handleLogin(e) {
  e.preventDefault();
  clearMsg();

  const user = document.getElementById('loginUser').value.trim();
  const pass = document.getElementById('loginPass').value;
  const submitBtn = document.getElementById('loginSubmitBtn');

  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span>Verifying Identity...</span> ⏳';

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'Authentication failed');
    }

    // Persist customer session
    localStorage.setItem('um1_user_token', data.user.token);
    localStorage.setItem('um1_user_info', JSON.stringify(data.user));
    localStorage.setItem('um1_user_config_id', data.user.config_id || 'default');

    showMsg('Access Granted! Connecting to Personal Security Mesh...', false);
    submitBtn.innerHTML = '<span>Access Granted 🚀</span>';

    setTimeout(() => {
      window.location.href = `/?config=${encodeURIComponent(data.user.config_id || 'default')}`;
    }, 600);

  } catch (err) {
    showMsg(err.message, true);
    submitBtn.disabled = false;
    submitBtn.innerHTML = '<span>Connect to Network</span> ⚡';
  }
}

async function handleRegister(e) {
  e.preventDefault();
  clearMsg();

  const fullName = document.getElementById('regFullName').value.trim();
  const username = document.getElementById('regUsername').value.trim();
  const email = document.getElementById('regEmail').value.trim();
  const password = document.getElementById('regPassword').value;
  const planTier = document.getElementById('regTier').value;
  const submitBtn = document.getElementById('regSubmitBtn');

  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span>Provisioning Profile...</span> ⏳';

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        full_name: fullName,
        username: username,
        email: email,
        password: password,
        plan_tier: planTier
      })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'Registration failed');
    }

    // Automatically authenticate new user
    localStorage.setItem('um1_user_token', data.user.token);
    localStorage.setItem('um1_user_info', JSON.stringify(data.user));
    localStorage.setItem('um1_user_config_id', data.user.config_id);

    showMsg('Profile Provisioned! Redirecting to your Dashboard...', false);
    submitBtn.innerHTML = '<span>Profile Ready 🚀</span>';

    setTimeout(() => {
      window.location.href = `/?config=${encodeURIComponent(data.user.config_id)}`;
    }, 800);

  } catch (err) {
    showMsg(err.message, true);
    submitBtn.disabled = false;
    submitBtn.innerHTML = '<span>Deploy My Security Profile</span> 🚀';
  }
}

function handleInstantDemo() {
  document.getElementById('loginUser').value = 'demo';
  document.getElementById('loginPass').value = 'demo123';
  document.getElementById('loginForm').dispatchEvent(new Event('submit', { cancelable: true }));
}
