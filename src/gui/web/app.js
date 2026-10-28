/**
 * OmniToys Frontend Logic
 * Implements navigation, reactive state updates, and backend API communication.
 */

// State
let appData = {
  modules: [],
  global_settings: {}
};

const OMNI_TOKEN = document.querySelector('meta[name="omni-token"]')?.content || '';

// Navigation
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    const targetPage = item.getAttribute('data-page');
    switchPage(targetPage);
  });
});

function switchPage(pageId) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const activeNav = document.querySelector(`.nav-item[data-page="${pageId}"]`);
  if (activeNav) activeNav.classList.add('active');

  document.querySelectorAll('.page-view').forEach(p => p.style.display = 'none');
  const targetView = document.getElementById(`page-${pageId}`);
  if (targetView) targetView.style.display = 'block';
}

// API Bridge
async function apiCall(endpoint, method = 'GET', body = null) {
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (method !== 'GET') {
      opts.headers['X-OmniToys-Token'] = OMNI_TOKEN;
    }
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(endpoint, opts);
    if (!res.ok) {
      console.warn(`[API] ${endpoint} returned HTTP ${res.status}`);
      return null;
    }
    return await res.json();
  } catch (err) {
    console.warn(`[API] Error on ${endpoint}:`, err);
    return null;
  }
}

// Initial Load & Dashboard
async function refreshDashboard() {
  const data = await apiCall('/api/dashboard');
  if (!data) return;
  appData = data;
  renderDashboard(data);
  renderBatteryPage(data);
  renderAwakePage(data);
  renderPinnerPage(data);
  renderSettingsPage(data);
}

function renderDashboard(data) {
  const container = document.getElementById('dashboard-cards');
  if (!container) return;
  container.innerHTML = '';

  const svgIcons = {
    battery: '<svg viewBox="0 0 24 24" fill="none" class="dash-svg-icon"><rect x="2" y="6" width="17" height="12" rx="3" stroke="#28a745" stroke-width="2"/><path d="M21 10v4" stroke="#28a745" stroke-width="2" stroke-linecap="round"/><path d="M10 8l-3 4h4l-2 4" stroke="#00e5ff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    rename: '<svg viewBox="0 0 24 24" fill="none" class="dash-svg-icon"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" stroke="#a78bfa" stroke-width="1.8"/><path d="M14 2v6h6M8 13h8M8 17h5" stroke="#a78bfa" stroke-width="1.8" stroke-linecap="round"/></svg>',
    coffee: '<svg viewBox="0 0 24 24" fill="none" class="dash-svg-icon"><path d="M18 8h1a4 4 0 0 1 0 8h-1M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z" stroke="#f59e0b" stroke-width="1.8"/><path d="M6 1v3M10 1v3M14 1v3" stroke="#f59e0b" stroke-width="1.8" stroke-linecap="round"/></svg>',
    pin: '<svg viewBox="0 0 24 24" fill="none" class="dash-svg-icon"><path d="M12 17v5M5 7l3 3-4 6 7-2 3 3 2-2-9-9 2-2-2-2-4 4z" stroke="#ec4899" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    widgets: '<svg viewBox="0 0 24 24" fill="none" class="dash-svg-icon"><circle cx="12" cy="12" r="3" stroke="#94a3b8" stroke-width="1.8"/></svg>'
  };

  data.modules.forEach(mod => {
    const card = document.createElement('div');
    card.className = 'dashboard-card';
    card.onclick = () => switchPage(mod.id);

    const statusClass = mod.enabled ? 'active' : 'disabled';
    const statusText = mod.enabled ? '已启用' : '已停用';
    const icon = svgIcons[mod.icon] || '📦';

    card.innerHTML = `
      <div class="dash-top">
        <span class="dash-icon">${icon}</span>
        <span class="dash-status ${statusClass}">${statusText}</span>
      </div>
      <div class="dash-bottom">
        <h3>${escapeHtml(mod.name)}</h3>
        <p>${escapeHtml(mod.description)}</p>
      </div>
    `;
    container.appendChild(card);
  });

  // Quick battery list on dashboard
  const batteryMod = data.modules.find(m => m.id === 'omni_battery');
  const quickContainer = document.getElementById('dashboard-quick-devices');
  if (batteryMod && quickContainer) {
    renderDeviceCards(batteryMod.state?.devices || [], quickContainer);
  }
}

function renderBatteryPage(data) {
  const batteryMod = data.modules.find(m => m.id === 'omni_battery');
  if (!batteryMod) return;

  const toggle = document.getElementById('toggle-battery');
  if (toggle) toggle.checked = batteryMod.enabled;

  const intervalSelect = document.getElementById('select-battery-interval');
  if (intervalSelect && batteryMod.state?.poll_interval != null) {
    const value = String(batteryMod.state.poll_interval);
    if ([...intervalSelect.options].some(o => o.value === value)) {
      intervalSelect.value = value;
    }
  }

  const alertSelect = document.getElementById('select-battery-alert');
  if (alertSelect && batteryMod.state?.alert_threshold != null) {
    const value = String(batteryMod.state.alert_threshold);
    if ([...alertSelect.options].some(o => o.value === value)) {
      alertSelect.value = value;
    }
  }

  const container = document.getElementById('device-list-container');
  if (container) {
    renderDeviceCards(batteryMod.state?.devices || [], container);
  }
}

function renderDeviceCards(devices, container) {
  container.innerHTML = '';
  if (!devices || devices.length === 0) {
    container.innerHTML = `
      <div class="fluent-card" style="justify-content: center; color: var(--text-secondary); padding: 30px;">
        未检测到活跃的罗技 2.4G / 蓝牙 / 国产外设。请确认设备已开机或插入接收器。
      </div>
    `;
    return;
  }

  devices.forEach(dev => {
    const card = document.createElement('div');
    card.className = 'device-card';

    const rawPct = Number(dev.percentage);
    const pct = Number.isFinite(rawPct) ? rawPct : -1;
    let barColor = 'var(--accent-green)';
    if (pct < 20) barColor = 'var(--accent-red)';
    else if (pct < 45) barColor = 'var(--accent-yellow)';
    if (dev.charging) barColor = 'var(--accent-cyan)';
    const fillPct = Math.max(0, Math.min(100, pct));

    const devIcons = { Mouse: '🖱️', Keyboard: '⌨️', Headset: '🎧', Gamepad: '🎮', Other: '🔌' };
    const icon = devIcons[dev.category] || '🖱️';
    const voltage = dev.voltage_mv ? `<span class="tag">${escapeHtml(dev.voltage_mv)} mV</span>` : '';

    card.innerHTML = `
      <div class="device-left">
        <div class="card-icon" style="font-size: 20px;">${icon}</div>
        <div class="device-meta">
          <div class="device-name">${escapeHtml(dev.name)}</div>
          <div class="device-tags">
            <span class="tag">${escapeHtml(dev.connection)}</span>
            ${dev.charging ? '<span class="tag tag-charging">⚡ 充电中</span>' : ''}
            ${voltage}
          </div>
        </div>
      </div>
      <div class="device-right">
        <div class="battery-display">
          <div class="battery-bar-bg">
            <div class="battery-bar-fill" style="width: ${fillPct}%; background-color: ${barColor};"></div>
          </div>
          <div class="battery-num" style="color: ${barColor}">${pct >= 0 ? pct + '%' : '未知'}</div>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}


function renderAwakePage(data) {
  const mod = data.modules.find(m => m.id === 'awake');
  if (!mod) return;
  const toggle = document.getElementById('toggle-awake');
  const screenToggle = document.getElementById('toggle-awake-screen');
  const tag = document.getElementById('awake-status-tag');
  if (toggle) toggle.checked = !!mod.enabled;
  if (screenToggle) screenToggle.checked = mod.state?.keep_screen_on !== false;
  if (tag) {
    if (mod.state?.is_active) {
      tag.textContent = '运行中 (电脑不休眠)';
      tag.style.color = 'var(--accent-green)';
      tag.style.background = 'rgba(40, 167, 69, 0.2)';
    } else {
      tag.textContent = '未激活';
      tag.style.color = 'var(--text-secondary)';
      tag.style.background = 'rgba(255, 255, 255, 0.06)';
    }
  }
}

function renderPinnerPage(data) {
  const mod = data.modules.find(m => m.id === 'window_pinner');
  if (!mod) return;

  const toggle = document.getElementById('toggle-pinner');
  if (toggle) toggle.checked = !!mod.enabled;

  const hotkey = document.getElementById('pinner-hotkey');
  if (hotkey) hotkey.textContent = mod.state?.shortcut || 'Ctrl + Win + T';

  const status = document.getElementById('pinner-status');
  if (status) {
    if (!mod.enabled) {
      status.textContent = '未启用';
      status.style.color = 'var(--text-secondary)';
    } else if (mod.state?.hotkey_registered) {
      status.textContent = '热键已注册';
      status.style.color = 'var(--accent-green)';
    } else {
      status.textContent = '热键不可用 / 被占用';
      status.style.color = 'var(--accent-red)';
    }
  }
}

function renderSettingsPage(data) {
  const settings = data.global_settings || {};
  const startup = document.getElementById('toggle-startup');
  const closeTray = document.getElementById('toggle-close-tray');
  if (startup) startup.checked = !!settings.run_on_startup;
  if (closeTray) closeTray.checked = settings.close_to_tray !== false;
}

// Event Listeners
document.getElementById('btn-refresh-battery')?.addEventListener('click', async () => {
  const btn = document.getElementById('btn-refresh-battery');
  btn.textContent = '⏳ 正在扫描...';
  btn.disabled = true;
  await apiCall('/api/action', 'POST', { module_id: 'omni_battery', action: 'refresh', payload: {} });
  await refreshDashboard();
  btn.textContent = '🔄 立即扫描刷新';
  btn.disabled = false;
});

document.getElementById('btn-diagnose-usb')?.addEventListener('click', async () => {
  const container = document.getElementById('usb-diag-container');
  const content = document.getElementById('usb-diag-content');
  if (container.style.display === 'block') {
    container.style.display = 'none';
    return;
  }
  container.style.display = 'block';
  content.innerHTML = '<span style="color: var(--text-secondary)">正在扫描主板与显示器 HUB 上的全部 USB/HID 拓扑...</span>';

  const res = await apiCall('/api/action', 'POST', {
    module_id: 'omni_battery',
    action: 'diagnose_usb',
    payload: {}
  });

  if (res && res.status === 'ok') {
    const list = res.diagnostics || [];
    if (list.length === 0) {
      content.innerHTML = '<span style="color: var(--accent-yellow)">未检测到任何 HID 端点。请检查显示器 USB 上行线 (Upstream Cable) 是否插好。</span>';
      return;
    }
    let html = '<table style="width:100%; border-collapse:collapse; text-align:left;">';
    html += '<tr style="color:var(--text-secondary); border-bottom:1px solid var(--border-color);"><th>设备名称</th><th>VID:PID</th><th>UsagePage</th></tr>';
    list.forEach(d => {
      html += `<tr style="border-bottom:1px solid rgba(255,255,255,0.04); padding:4px 0;">
        <td style="color:#ffffff; padding:4px 0;">${escapeHtml(d.name)}</td>
        <td style="color:var(--accent-cyan); padding:4px 0;">${d.vid_hex}:${d.pid_hex}</td>
        <td style="color:var(--text-secondary); padding:4px 0;">${d.usage_page}</td>
      </tr>`;
    });
    html += '</table>';
    content.innerHTML = html;
  } else {
    content.innerHTML = '<span style="color: var(--accent-red)">扫描失败。</span>';
  }
});


// Module on/off switches
function bindModuleToggle(elementId, moduleId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.addEventListener('change', async () => {
    const desired = el.checked;
    el.disabled = true;
    const res = await apiCall('/api/toggle_module', 'POST', {
      module_id: moduleId,
      enabled: desired
    });
    el.disabled = false;
    if (!res || res.status !== 'ok') {
      el.checked = !desired;
      alert('模块切换失败，请查看日志。');
    }
    await refreshDashboard();
  });
}

bindModuleToggle('toggle-battery', 'omni_battery');
bindModuleToggle('toggle-awake', 'awake');
bindModuleToggle('toggle-pinner', 'window_pinner');
bindModuleToggle('toggle-power-rename', 'power_rename');

document.getElementById('toggle-awake-screen')?.addEventListener('change', async (e) => {
  await apiCall('/api/action', 'POST', {
    module_id: 'awake',
    action: 'update_settings',
    payload: { keep_screen_on: e.target.checked }
  });
  await refreshDashboard();
});

document.getElementById('select-battery-interval')?.addEventListener('change', async (e) => {
  await apiCall('/api/action', 'POST', {
    module_id: 'omni_battery',
    action: 'update_settings',
    payload: { poll_interval: parseInt(e.target.value, 10) }
  });
  await refreshDashboard();
});

document.getElementById('select-battery-alert')?.addEventListener('change', async (e) => {
  await apiCall('/api/action', 'POST', {
    module_id: 'omni_battery',
    action: 'update_settings',
    payload: { alert_threshold: parseInt(e.target.value, 10) }
  });
  await refreshDashboard();
});

async function setGlobalSetting(key, value, revertElement) {
  const res = await apiCall('/api/global', 'POST', { key, value });
  if (!res || res.status !== 'ok') {
    if (revertElement) revertElement.checked = !value;
    alert(res?.message || '设置失败。');
  }
  await refreshDashboard();
}

document.getElementById('toggle-startup')?.addEventListener('change', async (e) => {
  await setGlobalSetting('run_on_startup', e.target.checked, e.target);
});

document.getElementById('toggle-close-tray')?.addEventListener('change', async (e) => {
  await setGlobalSetting('close_to_tray', e.target.checked, e.target);
});

document.getElementById('btn-test-pin')?.addEventListener('click', async () => {
  const res = await apiCall('/api/action', 'POST', { module_id: 'window_pinner', action: 'pin_current', payload: {} });
  alert(res?.status === 'ok' ? `窗口置顶状态已切换: ${res.state}` : '测试置顶已触发');
});

// Periodic polling (15s interval to keep CPU at 0% when idle)
setInterval(refreshDashboard, 15000);
window.addEventListener('DOMContentLoaded', refreshDashboard);

// ================= PowerRename Logic =================
let renameLoadedFiles = [];
let renameCurrentPreview = [];
let previewDebounceTimer = null;

// Scan directory
document.getElementById('btn-scan-files')?.addEventListener('click', async () => {
  const folder = document.getElementById('rename-folder-input').value.trim();
  if (!folder) {
    alert('请输入有效的文件夹路径！');
    return;
  }
  const recursive = document.getElementById('rename-recursive').checked;
  const btn = document.getElementById('btn-scan-files');
  btn.textContent = '⏳ 正在加载...';
  btn.disabled = true;

  const res = await apiCall('/api/action', 'POST', {
    module_id: 'power_rename',
    action: 'scan',
    payload: { folder, recursive }
  });

  btn.textContent = '📂 加载文件';
  btn.disabled = false;

  if (res && res.status === 'ok') {
    renameLoadedFiles = res.files || [];
    document.getElementById('rename-scanned-count').textContent = `已找到 ${renameLoadedFiles.length} 个文件`;
    triggerRenamePreview();
  } else {
    alert('未能扫描该路径，请检查路径是否存在！');
  }
});

// Trigger preview on any input change
function triggerRenamePreview() {
  clearTimeout(previewDebounceTimer);
  previewDebounceTimer = setTimeout(runRenamePreview, 150);
}

[
  'rename-search-input',
  'rename-replace-input',
  'rename-opt-regex',
  'rename-opt-case',
  'rename-opt-all',
  'rename-opt-apply-to',
  'rename-opt-formatting',
  'rename-opt-enum',
  'rename-opt-enum-pad'
].forEach(id => {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener('input', triggerRenamePreview);
    el.addEventListener('change', triggerRenamePreview);
  }
});

async function runRenamePreview() {
  if (!renameLoadedFiles || renameLoadedFiles.length === 0) {
    renderRenameTable([]);
    return;
  }

  const rules = {
    search_pattern: document.getElementById('rename-search-input').value,
    replace_with: document.getElementById('rename-replace-input').value,
    use_regex: document.getElementById('rename-opt-regex').checked,
    match_case: document.getElementById('rename-opt-case').checked,
    match_all: document.getElementById('rename-opt-all').checked,
    apply_to: document.getElementById('rename-opt-apply-to').value,
    text_formatting: document.getElementById('rename-opt-formatting').value,
    add_enumeration: document.getElementById('rename-opt-enum').checked,
    enum_padding: parseInt(document.getElementById('rename-opt-enum-pad').value || '1'),
    enum_start: 1,
    enum_placement: 'suffix'
  };

  const res = await apiCall('/api/action', 'POST', {
    module_id: 'power_rename',
    action: 'preview',
    payload: { items: renameLoadedFiles, rules }
  });

  if (res && res.status === 'ok') {
    renameCurrentPreview = res.preview || [];
    renderRenameTable(renameCurrentPreview);
  }
}

function renderRenameTable(previewItems) {
  const tbody = document.getElementById('rename-table-body');
  const applyBtn = document.getElementById('btn-rename-apply');
  if (!tbody) return;

  if (!previewItems || previewItems.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" style="text-align: center; color: var(--text-secondary); padding: 30px;">
          暂无文件或未载入路径。
        </td>
      </tr>
    `;
    if (applyBtn) applyBtn.disabled = true;
    return;
  }

  let html = '';
  let willChangeCount = 0;

  previewItems.forEach((item, index) => {
    const isChanged = item.changed;
    const isValid = item.valid !== false;
    if (isChanged && isValid) willChangeCount++;

    let statusTag;
    if (!isValid) {
      statusTag = '<span class="tag" style="color: var(--accent-red)">名称非法</span>';
    } else if (isChanged) {
      statusTag = '<span class="tag tag-charging" style="color: #38d39f; background: rgba(56, 211, 159, 0.15)">准备就绪</span>';
    } else {
      statusTag = '<span class="tag">未变更</span>';
    }

    const newNameClass = isChanged ? 'diff-changed' : 'diff-same';

    html += `
      <tr>
        <td style="text-align: center;">
          <input type="checkbox" class="rename-item-chk" data-idx="${index}"
                 ${item.selected ? 'checked' : ''} ${isValid ? '' : 'disabled'}>
        </td>
        <td style="color: var(--text-secondary)">${escapeHtml(item.original_name)}</td>
        <td class="${newNameClass}">${escapeHtml(item.new_name)}</td>
        <td>${statusTag}</td>
      </tr>
    `;
  });

  tbody.innerHTML = html;

  if (applyBtn) {
    applyBtn.disabled = (willChangeCount === 0);
    applyBtn.textContent = `✅ 执行重命名 (${willChangeCount} 个文件)`;
  }

  // Row checkbox changes
  tbody.querySelectorAll('.rename-item-chk').forEach(chk => {
    chk.addEventListener('change', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (renameCurrentPreview[idx]) {
        renameCurrentPreview[idx].selected = e.target.checked;
      }
    });
  });
}

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Select all toggle
document.getElementById('rename-select-all')?.addEventListener('change', (e) => {
  const checked = e.target.checked;
  renameCurrentPreview.forEach(p => {
    p.selected = checked && p.changed && p.valid !== false;
  });
  document.querySelectorAll('.rename-item-chk').forEach(c => {
    const idx = parseInt(c.getAttribute('data-idx'));
    const item = renameCurrentPreview[idx];
    c.checked = !!(item && item.selected);
  });
});

// Execute Rename
document.getElementById('btn-rename-apply')?.addEventListener('click', async () => {
  const selectedTasks = renameCurrentPreview.filter(
    p => p.selected && p.changed && p.valid !== false
  );
  if (selectedTasks.length === 0) {
    alert('没有选中的待重命名文件！');
    return;
  }

  if (!confirm(`确定要重命名 ${selectedTasks.length} 个文件吗？`)) {
    return;
  }

  const btn = document.getElementById('btn-rename-apply');
  btn.textContent = '⏳ 正在重命名...';
  btn.disabled = true;

  const res = await apiCall('/api/action', 'POST', {
    module_id: 'power_rename',
    action: 'apply',
    payload: { tasks: selectedTasks }
  });

  if (res && (res.status === 'ok' || res.status === 'partial')) {
    const errorText = res.errors && res.errors.length
      ? `\n\n${res.errors.length} 个失败:\n${res.errors.slice(0, 5).join('\n')}`
      : '';
    alert(`重命名完成！成功 ${res.success_count} 个文件。${errorText}`);
    const undoBtn = document.getElementById('btn-rename-undo');
    if (undoBtn) undoBtn.disabled = !res.undo_available;
    // Reload directory
    document.getElementById('btn-scan-files')?.click();
  } else {
    alert('重命名遇到错误，请查看控制台日志。');
  }
  btn.textContent = '✅ 执行重命名';
});

// Undo Rename
document.getElementById('btn-rename-undo')?.addEventListener('click', async () => {
  if (!confirm('确定要撤销上一次重命名操作吗？')) return;

  const res = await apiCall('/api/action', 'POST', {
    module_id: 'power_rename',
    action: 'undo',
    payload: {}
  });

  if (res && (res.status === 'ok' || res.status === 'partial')) {
    const errorText = res.errors && res.errors.length
      ? `\n${res.errors.length} 个失败`
      : '';
    alert(`成功撤销 ${res.reverted_count} 个文件的更名！${errorText}`);
    const undoBtn = document.getElementById('btn-rename-undo');
    if (undoBtn) undoBtn.disabled = !res.undo_available;
    // Reload directory
    document.getElementById('btn-scan-files')?.click();
  } else {
    alert(res?.message || '撤销失败');
  }
});
