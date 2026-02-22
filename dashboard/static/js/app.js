/**
 * SRE Command Center — Frontend Logic
 * Handles data fetching, view switching, approval workflows, and real-time updates.
 */

// ── State ──────────────────────────────────────────────────
let autoScroll = true;
let refreshInterval = null;
let incidents = [];
let ws = null;

// ── Initialization ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    refreshAll();
    startAutoRefresh();
    connectWebSocket();
});

// ── Auto Refresh ───────────────────────────────────────────
function startAutoRefresh() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(() => {
        loadIncidents();
        loadHealth();
    }, 15000);
}

function refreshAll() {
    showLoading(true);
    Promise.all([loadIncidents(), loadHealth(), loadLogs(), loadArchives(), loadMetrics()])
        .finally(() => {
            showLoading(false);
            document.getElementById('lastUpdated').textContent =
                'Updated: ' + new Date().toLocaleTimeString();
        });
}

// ── WebSocket ──────────────────────────────────────────────
function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws`;

    try {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => {
            document.getElementById('statusDot').classList.remove('disconnected');
            document.getElementById('connectionText').textContent = 'Connected';
        };
        ws.onclose = () => {
            document.getElementById('statusDot').classList.add('disconnected');
            document.getElementById('connectionText').textContent = 'Reconnecting...';
            setTimeout(connectWebSocket, 3000);
        };
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'incident_update') {
                loadIncidents();
                const status = data.status || 'unknown';
                const msgs = {
                    completed: { text: `Remediation completed for incident ${data.incident_id?.split('_')[0] || ''}`, type: 'success' },
                    failed: { text: `Remediation failed: ${data.output?.substring(0, 80) || 'Check logs'}`, type: 'error' },
                    rejected: { text: 'Remediation was rejected', type: 'info' },
                    timeout: { text: 'Remediation timed out', type: 'warning' },
                };
                const msg = msgs[status] || { text: `Incident updated: ${status}`, type: 'info' };
                showToast(msg.text, msg.type);
            }
        };
    } catch (e) {
        console.log('WebSocket not available, using polling');
    }
}

// ── View Switching ─────────────────────────────────────────
function switchView(viewId) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    document.getElementById(`view-${viewId}`).classList.add('active');
    document.querySelector(`.nav-item[data-view="${viewId}"]`).classList.add('active');

    switch (viewId) {
        case 'logs': loadLogs(); break;
        case 'health': loadHealth(); break;
        case 'archives': loadArchives(); break;
        case 'incidents': loadIncidents(); break;
        case 'metrics': loadMetrics(); break;
    }
}

// ── Loading Bar ────────────────────────────────────────────
function showLoading(show) {
    document.getElementById('loadingBar').classList.toggle('active', show);
}

// ══════════════════════════════════════════════════════════════
// DATA LOADING
// ══════════════════════════════════════════════════════════════

// ── Incidents ──────────────────────────────────────────────
async function loadIncidents() {
    try {
        const resp = await fetch('/api/incidents');
        const data = await resp.json();
        incidents = data.incidents || [];

        updateStats();
        renderIncidentList();
        renderPendingApprovals();
        renderRecentActivity();
    } catch (e) {
        console.error('Failed to load incidents:', e);
    }
}

function updateStats() {
    const pending = incidents.filter(i => i.status === 'pending_approval');
    const active = incidents.filter(i => ['pending_approval', 'executing'].includes(i.status));
    const resolved = incidents.filter(i => ['completed', 'auto_remediated'].includes(i.status));

    document.getElementById('stat-active').textContent = active.length;
    document.getElementById('stat-active-detail').textContent =
        `${pending.length} pending, ${active.length - pending.length} executing`;

    document.getElementById('stat-pending').textContent = pending.length;
    document.getElementById('stat-resolved').textContent = resolved.length;

    const badge = document.getElementById('incidentBadge');
    if (pending.length > 0) {
        badge.style.display = 'inline';
        badge.textContent = pending.length;
    } else {
        badge.style.display = 'none';
    }
}

function renderIncidentList() {
    const container = document.getElementById('incidentList');

    if (incidents.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                </div>
                <p>No incidents recorded. Trigger a chaos scenario to begin!</p>
            </div>`;
        return;
    }

    container.innerHTML = incidents.map(inc => renderIncidentCard(inc)).join('');
}

function renderPendingApprovals() {
    const container = document.getElementById('pendingApprovals');
    const pending = incidents.filter(i => i.status === 'pending_approval');

    if (pending.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                </div>
                <p>No pending approvals &mdash; all clear!</p>
            </div>`;
        return;
    }

    container.innerHTML = `<div class="incident-list">${pending.map(i => renderIncidentCard(i)).join('')}</div>`;
}

function renderRecentActivity() {
    const container = document.getElementById('recentActivity');
    const recent = incidents.slice(0, 5);

    if (recent.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/></svg>
                </div>
                <p>No activity yet</p>
            </div>`;
        return;
    }

    container.innerHTML = `<div class="incident-list">${recent.map(i => renderIncidentCard(i)).join('')}</div>`;
}

function renderIncidentCard(inc) {
    const statusLabel = (inc.status || 'unknown').replace(/_/g, ' ');
    const statusClass = inc.status || 'unknown';
    const ts = inc.created_at ? new Date(inc.created_at).toLocaleString() : 'Unknown';

    // ── AI Explanation Panel ──
    let aiAnalysisHtml = '';
    if (inc.ai_reasoning) {
        aiAnalysisHtml = `
            <details class="ai-analysis-panel" style="margin-bottom:10px">
                <summary style="cursor:pointer;font-size:12px;color:var(--text-muted);margin-bottom:6px;display:flex;align-items:center;gap:4px">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 01-1 1h-6a1 1 0 01-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z"/><line x1="9" y1="21" x2="15" y2="21"/></svg>
                    AI Analysis
                </summary>
                <div style="font-size:12px;color:var(--text-secondary);padding:8px 12px;background:rgba(124,58,237,0.06);border-left:3px solid var(--purple);border-radius:4px;line-height:1.5">${escapeHtml(inc.ai_reasoning)}</div>
            </details>`;
    }

    // ── Command Section (editable for pending, static otherwise) ──
    let commandHtml = '';
    if (inc.ai_suggestion) {
        if (inc.status === 'pending_approval') {
            commandHtml = `
                <div class="incident-suggestion">
                    <div class="incident-suggestion-label">AI Suggested Remediation (editable)</div>
                    <textarea class="command-editor" id="cmd-${inc.incident_id}" rows="2">${escapeHtml(inc.ai_suggestion)}</textarea>
                </div>`;
        } else {
            commandHtml = `
                <div class="incident-suggestion">
                    <div class="incident-suggestion-label">${inc.custom_command ? 'Custom Command Executed' : 'AI Suggested Remediation'}</div>
                    <code>$ ${escapeHtml(inc.custom_command || inc.ai_suggestion)}</code>
                </div>`;
        }
    }

    // ── Actions ──
    let actionsHtml = '';
    if (inc.status === 'pending_approval') {
        actionsHtml = `
            <div class="incident-actions">
                <button class="btn btn-success" onclick="approveIncident('${inc.incident_id}', this)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                    Approve & Execute
                </button>
                <button class="btn btn-danger" onclick="rejectIncident('${inc.incident_id}', this)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    Reject
                </button>
            </div>`;
    } else if (inc.status === 'executing') {
        actionsHtml = `
            <div class="incident-actions">
                <button class="btn btn-secondary" disabled>
                    <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--blue);animation:pulse-dot 1s infinite"></span>
                    Executing...
                </button>
            </div>`;
    }

    // ── Report Button (for resolved incidents) ──
    let reportBtnHtml = '';
    if (['completed', 'failed', 'rejected', 'timeout'].includes(inc.status)) {
        reportBtnHtml = `
            <button class="btn btn-secondary" style="margin-top:8px;font-size:11px" onclick="generateReport('${inc.incident_id}')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                Generate Report
            </button>`;
    }

    // ── Remediation Output ──
    let outputHtml = '';
    if (inc.remediation_output) {
        outputHtml = `
            <details style="margin-top:10px">
                <summary style="cursor:pointer;font-size:12px;color:var(--text-muted);margin-bottom:6px;display:flex;align-items:center;gap:4px">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
                    Remediation Output
                </summary>
                <div class="incident-suggestion"><code>${escapeHtml(inc.remediation_output)}</code></div>
            </details>`;
    }

    // ── Diagnostics ──
    let diagnosticsHtml = '';
    if (inc.diagnostics) {
        diagnosticsHtml = `
            <details style="margin-bottom:10px">
                <summary style="cursor:pointer;font-size:12px;color:var(--text-muted);margin-bottom:6px;display:flex;align-items:center;gap:4px">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                    View Diagnostics
                </summary>
                <div class="incident-suggestion" style="max-height:200px;overflow-y:auto"><code>${escapeHtml(inc.diagnostics)}</code></div>
            </details>`;
    }

    // ── Timeline ──
    let timelineHtml = '';
    const timeline = inc.timeline || [];
    if (timeline.length > 0) {
        const steps = timeline.map(entry => {
            const time = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '';
            const evtIcons = {
                approved: '<polyline points="20 6 9 17 4 12"/>',
                completed: '<path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
                failed: '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
                rejected: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
                timeout: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
            };
            const icon = evtIcons[entry.event] || '<circle cx="12" cy="12" r="10"/>';
            return `
                <div class="timeline-step">
                    <div class="timeline-dot">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${icon}</svg>
                    </div>
                    <div class="timeline-content">
                        <span class="timeline-event">${escapeHtml(entry.event)}</span>
                        <span class="timeline-time">${time}</span>
                        ${entry.detail ? `<span class="timeline-detail">${escapeHtml(entry.detail.substring(0, 80))}</span>` : ''}
                    </div>
                </div>`;
        }).join('');
        timelineHtml = `
            <details style="margin-top:10px">
                <summary style="cursor:pointer;font-size:12px;color:var(--text-muted);margin-bottom:6px;display:flex;align-items:center;gap:4px">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    Incident Timeline (${timeline.length} events)
                </summary>
                <div class="incident-timeline">${steps}</div>
            </details>`;
    }

    return `
        <div class="incident-card">
            <div class="incident-header">
                <div class="incident-title">${escapeHtml(inc.alarm_name || 'Unknown Alarm')}</div>
                <span class="status-badge ${statusClass}">${statusLabel}</span>
            </div>
            <div class="incident-meta">
                <span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
                    ${escapeHtml(inc.instance_id || 'N/A')}
                </span>
                <span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    ${ts}
                </span>
            </div>
            ${inc.alarm_description ? `<div style="font-size:12px;color:var(--text-muted);margin-bottom:10px">${escapeHtml(inc.alarm_description)}</div>` : ''}
            ${aiAnalysisHtml}
            ${diagnosticsHtml}
            ${commandHtml}
            ${actionsHtml}
            ${outputHtml}
            ${timelineHtml}
            ${reportBtnHtml}
        </div>`;
}

// ── Approval Workflow ──────────────────────────────────────
async function approveIncident(incidentId, btn) {
    if (!confirm('Execute the remediation command on the instance?')) return;

    btn.disabled = true;
    btn.innerHTML = '<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--blue);animation:pulse-dot 1s infinite"></span> Dispatching...';

    // Read custom command from textarea (if edited)
    const textarea = document.getElementById(`cmd-${incidentId}`);
    const customCommand = textarea ? textarea.value.trim() : null;

    try {
        const resp = await fetch(`/api/approve/${incidentId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ custom_command: customCommand || null }),
        });
        const data = await resp.json();

        if (resp.ok) {
            showToast('Command dispatched. Watch for live status updates.', 'success');
        } else {
            showToast(`Approval failed: ${data.detail}`, 'error');
        }
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }

    loadIncidents();
}

async function rejectIncident(incidentId, btn) {
    if (!confirm('Reject this remediation? The incident will be marked as rejected.')) return;

    btn.disabled = true;
    try {
        await fetch(`/api/reject/${incidentId}`, { method: 'POST' });
        showToast('Remediation rejected', 'info');
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
    loadIncidents();
}

// ── Logs ───────────────────────────────────────────────────
async function loadLogs() {
    try {
        const minutes = document.getElementById('logMinutes')?.value || 60;
        const resp = await fetch(`/api/logs?minutes=${minutes}&limit=300`);
        const data = await resp.json();
        const logs = data.logs || [];

        const container = document.getElementById('logEntries');
        document.getElementById('logCount').textContent = `${logs.length} entries`;

        if (logs.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    </div>
                    <p>No log entries in this time range</p>
                </div>`;
            return;
        }

        container.innerHTML = logs.map(log => {
            let msg = escapeHtml(log.message);
            // Highlight key log phrases
            msg = msg.replace(/(\[INFO\])/g, '<span style="color:var(--blue)">$1</span>');
            msg = msg.replace(/(\[ERROR\])/g, '<span style="color:var(--red)">$1</span>');
            msg = msg.replace(/(\[WARNING\])/g, '<span style="color:var(--amber)">$1</span>');
            msg = msg.replace(/(AI Suggested Remediation:)/g, '<span style="color:var(--cyan);font-weight:600">$1</span>');
            msg = msg.replace(/(Diagnostic Output)/g, '<span style="color:var(--cyan);font-weight:600">$1</span>');
            msg = msg.replace(/(Handling incident)/g, '<span style="color:var(--cyan);font-weight:600">$1</span>');
            msg = msg.replace(/(Remediation (?:Success|Failed|timed out))/gi, '<span style="color:var(--cyan);font-weight:600">$1</span>');
            msg = msg.replace(/(Sending SSM command)/g, '<span style="color:var(--cyan);font-weight:600">$1</span>');

            return `
                <div class="log-line ${log.level || ''}">
                    <span class="log-time">${log.formatted_time || ''}</span>
                    <span class="log-msg">${msg}</span>
                </div>`;
        }).join('');

        if (autoScroll) {
            const el = document.getElementById('logEntries');
            el.scrollTop = el.scrollHeight;
        }
    } catch (e) {
        console.error('Failed to load logs:', e);
    }
}

function toggleAutoScroll() {
    autoScroll = !autoScroll;
    const btn = document.getElementById('autoScrollBtn');
    const label = autoScroll ? 'Auto-Scroll' : 'Manual';
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg> ${label}`;
    btn.classList.toggle('btn-primary', autoScroll);
    btn.classList.toggle('btn-secondary', !autoScroll);
}

// ── Health ─────────────────────────────────────────────────
async function loadHealth() {
    try {
        const resp = await fetch('/api/health');
        const data = await resp.json();

        // Instances
        const instGrid = document.getElementById('instanceGrid');
        if (data.instances && data.instances.length > 0) {
            const healthy = data.instances.filter(i => i.health === 'Healthy').length;
            document.getElementById('stat-healthy').textContent = `${healthy}/${data.instances.length}`;
            document.getElementById('stat-healthy-detail').textContent =
                `${data.asg?.name || 'ASG'} (${data.asg?.min}-${data.asg?.max} capacity)`;

            instGrid.innerHTML = data.instances.map(inst => `
                <div class="health-card">
                    <div class="health-card-header">
                        <span class="health-card-title">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="2" style="margin-right:4px;vertical-align:middle"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
                            ${inst.id}
                        </span>
                        <span class="status-badge ${inst.health === 'Healthy' ? 'completed' : 'failed'}">${inst.health}</span>
                    </div>
                    <div class="health-card-detail">
                        <span>State: ${inst.state}</span>
                        <span>AZ: ${inst.az}</span>
                    </div>
                </div>`).join('');
        } else {
            instGrid.innerHTML = `<div class="empty-state"><div class="empty-icon"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg></div><p>No instances found</p></div>`;
        }

        // Alarms
        const alarmGrid = document.getElementById('alarmGrid');
        if (data.alarms && data.alarms.length > 0) {
            alarmGrid.innerHTML = data.alarms.map(alarm => {
                const badgeClass = alarm.state === 'ALARM' ? 'failed' :
                    alarm.state === 'OK' ? 'completed' : 'pending_approval';
                return `
                    <div class="health-card">
                        <div class="health-card-header">
                            <span class="health-card-title">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="2" style="margin-right:4px;vertical-align:middle"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>
                                ${alarm.name}
                            </span>
                            <span class="status-badge ${badgeClass}">${alarm.state}</span>
                        </div>
                        <div class="health-card-detail">
                            <span>Metric: ${alarm.metric}</span>
                            <span>Threshold: ${alarm.threshold}</span>
                            <span>Description: ${alarm.description}</span>
                            <span style="font-size:11px">Updated: ${new Date(alarm.updated).toLocaleString()}</span>
                        </div>
                    </div>`;
            }).join('');
        } else {
            alarmGrid.innerHTML = `<div class="empty-state"><div class="empty-icon"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg></div><p>No alarms configured</p></div>`;
        }
    } catch (e) {
        console.error('Failed to load health:', e);
    }
}

// ── Archives ───────────────────────────────────────────────
async function loadArchives() {
    try {
        const resp = await fetch('/api/archives');
        const data = await resp.json();
        const archives = data.archives || [];

        const tbody = document.getElementById('archiveBody');
        const bucketEl = document.getElementById('archiveBucket');

        if (data.bucket) {
            bucketEl.innerHTML = `<span style="display:flex;align-items:center;gap:4px"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0022 16z"/></svg> S3 Bucket: ${data.bucket}</span>`;
        }

        if (archives.length === 0) {
            tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;padding:32px;color:var(--text-muted)">No archived files found</td></tr>`;
            return;
        }

        tbody.innerHTML = archives.map(a => `
            <tr>
                <td class="file-name">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" stroke-width="2" style="margin-right:4px;vertical-align:middle"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    ${a.key}
                </td>
                <td>${a.size_mb} MB</td>
                <td>${new Date(a.last_modified).toLocaleString()}</td>
            </tr>`).join('');
    } catch (e) {
        console.error('Failed to load archives:', e);
    }
}

// ── Chaos Engineering ──────────────────────────────────────
async function triggerChaos(mode) {
    const labels = {
        'disk-fill': 'Disk Fill',
        'nginx-crash': 'Nginx Crash',
        'oom': 'Memory Exhaustion'
    };

    if (!confirm(`Trigger ${labels[mode]}?\n\nThis will cause a real incident on your infrastructure. The AI agent will detect it and suggest remediation for your approval.`))
        return;

    showToast(`Triggering ${labels[mode]}...`, 'warning');

    try {
        const resp = await fetch(`/api/chaos/${mode}`, { method: 'POST' });
        const data = await resp.json();

        if (resp.ok) {
            showToast(
                `${labels[mode]} triggered on ${data.instance_id}. Watch for the alarm, AI detection, and approval workflow.`,
                'success'
            );
        } else {
            showToast(`Failed: ${data.detail}`, 'error');
        }
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

// ══════════════════════════════════════════════════════════════
// UTILITIES
// ══════════════════════════════════════════════════════════════

function escapeHtml(text) {
    if (!text) return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span class="toast-dot"></span><span>${message}</span>`;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = 'all 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}


// ══════════════════════════════════════════════════════════════
// METRICS
// ══════════════════════════════════════════════════════════════

async function loadMetrics() {
    try {
        const resp = await fetch('/api/incidents/stats');
        const data = await resp.json();
        if (data.error) { console.error(data.error); return; }

        // Update stat cards
        document.getElementById('metrics-total').textContent = data.total || 0;

        const mttrSec = data.avg_mttr_seconds || 0;
        if (mttrSec > 60) {
            document.getElementById('metrics-mttr').textContent = `${Math.round(mttrSec / 60)}m`;
        } else {
            document.getElementById('metrics-mttr').textContent = `${Math.round(mttrSec)}s`;
        }

        document.getElementById('metrics-success').textContent = `${data.success_rate || 0}%`;
        document.getElementById('metrics-resolved').textContent = data.total_resolved || 0;

        // Render charts
        renderBarChart(data.daily_counts || {});
        renderDonutChart(data.status_counts || {});
    } catch (e) {
        console.error('Failed to load metrics:', e);
    }
}

function renderBarChart(dailyCounts) {
    const container = document.getElementById('barChartContainer');
    const entries = Object.entries(dailyCounts);
    if (entries.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No data available</p></div>';
        return;
    }

    const maxVal = Math.max(...entries.map(([, v]) => v), 1);
    const barWidth = Math.floor(100 / entries.length);
    const chartHeight = 180;

    let barsHtml = entries.map(([day, count], i) => {
        const barH = (count / maxVal) * (chartHeight - 30);
        const x = i * barWidth + barWidth * 0.2;
        const w = barWidth * 0.6;
        const label = day.slice(5); // MM-DD
        return `
            <g>
                <rect x="${x}%" y="${chartHeight - barH - 20}" width="${w}%" height="${barH}"
                      rx="4" fill="var(--blue)" opacity="0.8">
                    <title>${day}: ${count} incidents</title>
                </rect>
                <text x="${x + w / 2}%" y="${chartHeight - barH - 25}" text-anchor="middle"
                      fill="var(--text-secondary)" font-size="10" font-family="inherit">${count}</text>
                <text x="${x + w / 2}%" y="${chartHeight - 4}" text-anchor="middle"
                      fill="var(--text-muted)" font-size="9" font-family="inherit">${label}</text>
            </g>`;
    }).join('');

    container.innerHTML = `
        <svg width="100%" height="${chartHeight}" class="bar-chart-svg">
            <line x1="0" y1="${chartHeight - 20}" x2="100%" y2="${chartHeight - 20}"
                  stroke="var(--border-color)" stroke-width="1" />
            ${barsHtml}
        </svg>`;
}

function renderDonutChart(statusCounts) {
    const container = document.getElementById('donutChartContainer');
    const entries = Object.entries(statusCounts);
    if (entries.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No data available</p></div>';
        return;
    }

    const total = entries.reduce((s, [, v]) => s + v, 0);
    const colors = {
        completed: 'var(--green)',
        pending_approval: 'var(--amber)',
        executing: 'var(--blue)',
        failed: 'var(--red)',
        rejected: '#6b7280',
        timeout: '#f59e0b',
        auto_remediated: '#06b6d4',
    };

    const cx = 90, cy = 90, r = 70, innerR = 45;
    let angle = 0;
    let paths = '';
    let legend = '';

    entries.forEach(([status, count]) => {
        const pct = count / total;
        const startAngle = angle;
        angle += pct * 360;
        const endAngle = angle;

        const start = polarToCartesian(cx, cy, r, startAngle);
        const end = polarToCartesian(cx, cy, r, endAngle);
        const innerStart = polarToCartesian(cx, cy, innerR, endAngle);
        const innerEnd = polarToCartesian(cx, cy, innerR, startAngle);
        const largeArc = pct > 0.5 ? 1 : 0;

        const color = colors[status] || '#4b5563';
        paths += `<path d="M${start.x},${start.y} A${r},${r} 0 ${largeArc},1 ${end.x},${end.y} L${innerStart.x},${innerStart.y} A${innerR},${innerR} 0 ${largeArc},0 ${innerEnd.x},${innerEnd.y} Z" fill="${color}" opacity="0.85"><title>${status.replace(/_/g, ' ')}: ${count}</title></path>`;

        legend += `<div class="donut-legend-item">
            <span class="donut-legend-dot" style="background:${color}"></span>
            <span>${status.replace(/_/g, ' ')}</span>
            <span style="margin-left:auto;font-weight:600">${count}</span>
        </div>`;
    });

    container.innerHTML = `
        <div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap">
            <svg width="180" height="180" viewBox="0 0 180 180">
                ${paths}
                <text x="${cx}" y="${cy - 6}" text-anchor="middle" fill="var(--text-primary)" font-size="22" font-weight="700" font-family="inherit">${total}</text>
                <text x="${cx}" y="${cy + 12}" text-anchor="middle" fill="var(--text-muted)" font-size="10" font-family="inherit">total</text>
            </svg>
            <div class="donut-legend">${legend}</div>
        </div>`;
}

function polarToCartesian(cx, cy, r, angleDeg) {
    const rad = (angleDeg - 90) * Math.PI / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}


// ══════════════════════════════════════════════════════════════
// POST-INCIDENT REPORT
// ══════════════════════════════════════════════════════════════

let currentReportMarkdown = '';

async function generateReport(incidentId) {
    try {
        showToast('Generating report...', 'info');
        const resp = await fetch(`/api/incidents/${incidentId}/report`);
        if (!resp.ok) throw new Error('Failed to fetch report');
        const data = await resp.json();

        currentReportMarkdown = data.markdown;

        // Render markdown as formatted HTML (basic conversion)
        const html = markdownToHtml(data.markdown);
        document.getElementById('reportContent').innerHTML = html;
        document.getElementById('reportModal').style.display = 'flex';
    } catch (e) {
        showToast(`Report error: ${e.message}`, 'error');
    }
}

function closeReportModal() {
    document.getElementById('reportModal').style.display = 'none';
}

function copyReport() {
    navigator.clipboard.writeText(currentReportMarkdown).then(() => {
        showToast('Markdown copied to clipboard', 'success');
    });
}

function downloadReport() {
    const blob = new Blob([currentReportMarkdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `incident-report-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Report downloaded', 'success');
}

function markdownToHtml(md) {
    // Basic markdown to HTML conversion
    return md
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
        .replace(/\|(.+)\|/g, (match) => {
            const cells = match.split('|').filter(c => c.trim());
            if (cells.every(c => /^[-\s]+$/.test(c))) return '';
            const tds = cells.map(c => `<td>${c.trim()}</td>`).join('');
            return `<tr>${tds}</tr>`;
        })
        .replace(/(<tr>.*<\/tr>)/g, '<table class="report-table">$1</table>')
        .replace(/^---$/gim, '<hr>')
        .replace(/^\*(.*)$/gim, '<em>$1</em>')
        .replace(/\n/g, '<br>')
        .replace(/<br><br>/g, '<br>');
}
