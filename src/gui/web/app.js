/**
 * OmniToys Frontend Logic
 * Implements navigation, reactive state updates, and backend API communication.
 */

// State
let appData = {
  modules: [],
  global_settings: {}
};

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
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(endpoint, opts);
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
  renderFencesPage(data);
  renderAwakePage(data);
}

function renderDashboard(data) {
  const container = document.getElementById('dashboard-cards');
  if (!container) return;
  container.innerHTML = '';

  const icons = { battery: '🔋', fences: '🗂️', rename: '🏷️', coffee: '☕', pin: '📌', widgets: '🛠️' };

  data.modules.forEach(mod => {
    const card = document.createElement('div');
    card.className = 'dashboard-card';
    card.onclick = () => switchPage(mod.id);

    const statusClass = mod.enabled ? 'active' : 'disabled';
    const statusText = mod.enabled ? '已启用' : '已停用';
    const icon = icons[mod.icon] || '📦';

    card.innerHTML = `
      <div class="dash-top">
        <span class="dash-icon">${icon}</span>
        <span class="dash-status ${statusClass}">${statusText}</span>
      </div>
      <div class="dash-bottom">
        <h3>${mod.name}</h3>
        <p>${mod.description}</p>
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

    const pct = dev.percentage;
    let barColor = 'var(--accent-green)';
    if (pct < 20) barColor = 'var(--accent-red)';
    else if (pct < 45) barColor = 'var(--accent-yellow)';
    if (dev.charging) barColor = 'var(--accent-cyan)';

    const devIcons = { Mouse: '🖱️', Keyboard: '⌨️', Headset: '🎧', Gamepad: '🎮', Other: '🔌' };
    const icon = devIcons[dev.category] || '🖱️';

    card.innerHTML = `
      <div class="device-left">
        <div class="card-icon" style="font-size: 20px;">${icon}</div>
        <div class="device-meta">
          <div class="device-name">${dev.name}</div>
          <div class="device-tags">
            <span class="tag">${dev.connection}</span>
            ${dev.charging ? '<span class="tag tag-charging">⚡ 充电中</span>' : ''}
            ${dev.voltage_mv ? `<span class="tag">${dev.voltage_mv} mV</span>` : ''}
          </div>
        </div>
      </div>
      <div class="device-right">
        <div class="battery-display">
          <div class="battery-bar-bg">
            <div class="battery-bar-fill" style="width: ${Math.max(0, pct)}%; background-color: ${barColor};"></div>
          </div>
          <div class="battery-num" style="color: ${barColor}">${pct >= 0 ? pct + '%' : '未知'}</div>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

function renderFencesPage(data) {
  const mod = data.modules.find(m => m.id === 'desktop_fences');
  if (!mod) return;

  const toggle = document.getElementById('toggle-fences');
  if (toggle) toggle.checked = mod.enabled;

  const container = document.getElementById('fences-list-container');
  if (!container) return;

  const fences = mod.state?.fences || [];
  if (fences.length === 0) {
    container.innerHTML = `
      <div class="fluent-card" style="justify-content: center; color: var(--text-secondary); padding: 30px;">
        桌面暂无活跃栅栏。点击上方“新建桌面栅栏”即可在桌面创建第一个分区！
      </div>
    `;
    return;
  }

  container.innerHTML = '';
  fences.forEach(fence => {
    const card = document.createElement('div');
    card.className = 'fluent-card';
    card.style.marginBottom = '8px';

    const rollText = fence.is_rolled_up ? '▼ 展开' : '▲ 折叠卷起';

    card.innerHTML = `
      <div class="card-info">
        <div class="card-icon">🗂️</div>
        <div class="card-texts">
          <h3>${escapeHtml(fence.title)} (${fence.item_count || 0} 个桌面文件)</h3>
          <p>位置: (${fence.x}, ${fence.y}) | 大小: ${fence.width}x${fence.height} | 路径: ${escapeHtml(fence.folder_path)}</p>
        </div>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <button class="btn btn-rollup-fence" data-id="${fence.id}">${rollText}</button>
        <button class="btn btn-del-fence" data-id="${fence.id}" style="color: var(--accent-red)">删除</button>
      </div>
    `;
    container.appendChild(card);
  });

  // Roll-up button click
  container.querySelectorAll('.btn-rollup-fence').forEach(btn => {
    btn.onclick = async () => {
      const id = btn.getAttribute('data-id');
      await apiCall('/api/action', 'POST', { module_id: 'desktop_fences', action: 'toggle_rollup', payload: { id } });
      await refreshDashboard();
    };
  });

  // Delete button click
  container.querySelectorAll('.btn-del-fence').forEach(btn => {
    btn.onclick = async () => {
      const id = btn.getAttribute('data-id');
      if (confirm('确定要从桌面移除该栅栏吗？(原文件不会被删除)')) {
        await apiCall('/api/action', 'POST', { module_id: 'desktop_fences', action: 'delete_fence', payload: { id } });
        await refreshDashboard();
      }
    };
  });
}

function renderAwakePage(data) {
  const mod = data.modules.find(m => m.id === 'awake');
  if (!mod) return;
  const toggle = document.getElementById('toggle-awake');
  const tag = document.getElementById('awake-status-tag');
  if (toggle) toggle.checked = mod.state?.is_active || false;
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

document.getElementById('toggle-battery')?.addEventListener('change', async (e) => {
  await apiCall('/api/toggle_module', 'POST', { module_id: 'omni_battery', enabled: e.target.checked });
  await refreshDashboard();
});

// Fences Event Listeners
document.getElementById('toggle-fences')?.addEventListener('change', async (e) => {
  await apiCall('/api/toggle_module', 'POST', { module_id: 'desktop_fences', enabled: e.target.checked });
  await refreshDashboard();
});

document.getElementById('btn-open-create-fence')?.addEventListener('click', () => {
  const card = document.getElementById('create-fence-card');
  if (card) card.style.display = 'block';
});

document.getElementById('btn-cancel-create-fence')?.addEventListener('click', () => {
  const card = document.getElementById('create-fence-card');
  if (card) card.style.display = 'none';
});

document.getElementById('btn-confirm-create-fence')?.addEventListener('click', async () => {
  const title = document.getElementById('new-fence-title').value.trim();
  if (!title) {
    alert('请输入栅栏名称！');
    return;
  }
  const folder = document.getElementById('new-fence-folder').value.trim();
  await apiCall('/api/action', 'POST', {
    module_id: 'desktop_fences',
    action: 'create_fence',
    payload: { title, folder_path: folder }
  });
  document.getElementById('create-fence-card').style.display = 'none';
  document.getElementById('new-fence-title').value = '';
  document.getElementById('new-fence-folder').value = '';
  await refreshDashboard();
});

document.getElementById('btn-toggle-all-fences')?.addEventListener('click', async () => {
  const res = await apiCall('/api/action', 'POST', {
    module_id: 'desktop_fences',
    action: 'toggle_all_visibility',
    payload: {}
  });
  const isHidden = res?.is_all_hidden;
  document.getElementById('btn-toggle-all-fences').textContent = isHidden ? '👁️ 恢复显示全部栅栏' : '👁️ 临时隐藏全部栅栏';
});

document.getElementById('toggle-awake')?.addEventListener('change', async (e) => {
  await apiCall('/api/action', 'POST', { module_id: 'awake', action: 'toggle_active', payload: {} });
  await refreshDashboard();
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
    if (isChanged) willChangeCount++;

    const statusTag = isChanged 
      ? '<span class="tag tag-charging" style="color: #38d39f; background: rgba(56, 211, 159, 0.15)">准备就绪</span>'
      : '<span class="tag">未变更</span>';

    const newNameClass = isChanged ? 'diff-changed' : 'diff-same';

    html += `
      <tr>
        <td style="text-align: center;">
          <input type="checkbox" class="rename-item-chk" data-idx="${index}" ${item.selected ? 'checked' : ''}>
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
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Select all toggle
document.getElementById('rename-select-all')?.addEventListener('change', (e) => {
  const checked = e.target.checked;
  renameCurrentPreview.forEach(p => p.selected = checked);
  document.querySelectorAll('.rename-item-chk').forEach(c => c.checked = checked);
});

// Execute Rename
document.getElementById('btn-rename-apply')?.addEventListener('click', async () => {
  const selectedTasks = renameCurrentPreview.filter(p => p.selected && p.changed);
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
    alert(`重命名完成！成功重命名 ${res.success_count} 个文件。`);
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

  if (res && res.status === 'ok') {
    alert(`成功撤销 ${res.reverted_count} 个文件的更名！`);
    const undoBtn = document.getElementById('btn-rename-undo');
    if (undoBtn) undoBtn.disabled = !res.undo_available;
    // Reload directory
    document.getElementById('btn-scan-files')?.click();
  } else {
    alert(res?.message || '撤销失败');
  }
});
