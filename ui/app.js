
/**
 * Custom SSE Fetch parser.
 * Replaces @microsoft/fetch-event-source to avoid bundling completely.
 * Natively supports X-API-Key headers for authentication.
 */
async function fetchSSE(url, options, onMessage) {
    const response = await fetch(url, options);
    if (!response.ok) {
        if (response.status === 401 || response.status === 422) {
            localStorage.removeItem('qf_api_key');
            document.getElementById('auth-modal').classList.remove('hidden');
            throw new Error("Invalid API Key");
        }
        const text = await response.text();
        throw new Error(`HTTP ${response.status}: ${text}`);
    }
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    
    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop(); // Keep the last incomplete chunk in buffer
        
        for (const block of lines) {
            if (!block.trim()) continue;
            let eventType = "message";
            let dataLines = [];
            for (const line of block.split('\n')) {
                if (line.startsWith("event: ")) eventType = line.substring(7);
                else if (line.startsWith("data: ")) dataLines.push(line.substring(6));
            }
            const dataStr = dataLines.join('\n');
            if (dataStr) {
                try {
                    onMessage(eventType, JSON.parse(dataStr));
                } catch (e) {
                    console.error("Failed to parse SSE JSON", e, dataStr);
                }
            }
        }
    }
}

const DOM = {
    modal: document.getElementById('auth-modal'),
    authForm: document.getElementById('auth-form'),
    keyInput: document.getElementById('api-key-input'),
    btnLogout: document.getElementById('btn-logout'),
    
    form: document.getElementById('query-form'),
    input: document.getElementById('query-input'),
    submitBtn: document.getElementById('query-submit'),
    chatHistory: document.getElementById('chat-history'),
    
    sqlOutput: document.getElementById('sql-output'),
    badges: document.getElementById('status-badges'),
    badgeAst: document.getElementById('badge-ast'),
    badgeConf: document.getElementById('badge-conf'),
    
    table: document.getElementById('data-table'),
    tableHead: document.getElementById('data-table-head'),
    tableBody: document.getElementById('data-table-body'),
    tableEmpty: document.getElementById('data-empty'),
    btnExport: document.getElementById('btn-export'),
    
    btnNewSession: document.getElementById('btn-new-session'),

    
    badgeRag: document.getElementById('badge-rag')
};

let currentResults = [];
let currentSessionId = localStorage.getItem('qf_session_id') || null;

function getApiKey() {
    return localStorage.getItem('qf_api_key');
}

function checkAuth() {
    if (!getApiKey()) {
        DOM.modal.classList.remove('hidden');
    } else {
        DOM.modal.classList.add('hidden');
    }
}

DOM.authForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const key = DOM.keyInput.value.trim();
    if (key) {
        localStorage.setItem('qf_api_key', key);
        checkAuth();
        DOM.keyInput.value = '';
    }
});

DOM.btnLogout.addEventListener('click', () => {
    localStorage.removeItem('qf_api_key');
    checkAuth();
});

async function createSession() {
    try {
        const res = await fetch('/api/v1/sessions', {
            method: 'POST',
            headers: { 'X-API-Key': getApiKey() }
        });
        if (res.ok) {
            const data = await res.json();
            currentSessionId = data.session_id;
            localStorage.setItem('qf_session_id', currentSessionId);
            DOM.chatHistory.innerHTML = ''; // Clear chat
            appendAiMessage("Session reset. What data would you like to explore today?");
        }
    } catch (e) {
        console.error("Failed to create session", e);
    }
}

DOM.btnNewSession.addEventListener('click', createSession);

async function loadHistory() {
    if (!currentSessionId) return;
    try {
        const res = await fetch(`/api/v1/sessions/${currentSessionId}/history`, {
            headers: { 'X-API-Key': getApiKey() }
        });
        if (res.ok) {
            const data = await res.json();
            if (data.messages && data.messages.length > 0) {
                DOM.chatHistory.innerHTML = '';
                data.messages.forEach(msg => {
                    if (msg.type === 'human') appendUserMessage(msg.content);
                    else if (msg.type === 'ai') appendAiMessage(msg.content);
                });
            }
        }
    } catch (e) {
        console.error("Failed to load history", e);
    }
}

function appendAiMessage(text) {
    const bubble = createAiMessageBubble();
    bubble.statusText.remove();
    bubble.contentBox.textContent = text;
}


checkAuth(); // Initial check
if (getApiKey()) {
    if (currentSessionId) loadHistory();
    else createSession();
}

function appendUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'msg-group user fade-up';
    div.innerHTML = `
        <div class="msg-avatar user">You</div>
        <div class="msg-body" style="align-items:flex-end;">
            <span class="msg-name">You</span>
            <div class="bubble user"></div>
        </div>
    `;
    div.querySelector('.bubble.user').textContent = text;
    DOM.chatHistory.appendChild(div);
    DOM.chatHistory.scrollTop = DOM.chatHistory.scrollHeight;
}

function createAiMessageBubble() {
    const div = document.createElement('div');
    div.className = 'msg-group fade-up';
    div.innerHTML = `
        <div class="msg-avatar ai">QF</div>
        <div class="msg-body">
            <span class="msg-name">QueryForce</span>
            <div class="bubble ai">
                <div class="thinking status-text">
                    <div class="dots"><span></span><span></span><span></span></div>
                    <span>Thinking...</span>
                </div>
            </div>
        </div>
    `;
    DOM.chatHistory.appendChild(div);
    DOM.chatHistory.scrollTop = DOM.chatHistory.scrollHeight;

    const bubble = div.querySelector('.bubble.ai');
    return {
        container: div,
        contentBox: bubble,
        statusText: div.querySelector('.status-text')
    };
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function highlightSql(sql) {
    const keywords = new Set(['SELECT', 'FROM', 'WHERE', 'GROUP', 'ORDER', 'BY', 'LIMIT', 'JOIN', 'LEFT', 'INNER', 'ON', 'AS', 'AND', 'OR', 'COUNT', 'SUM', 'AVG', 'MAX', 'MIN', 'WITH', 'HAVING', 'DISTINCT', 'BETWEEN', 'IN', 'NOT', 'NULL', 'LIKE', 'DESC', 'ASC', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'COLLATE', 'NOCASE']);
    const tokens = sql.split(/(\b|\s+|[(),.*;])/);
    return tokens.map(token => {
        if (keywords.has(token.toUpperCase())) {
            return `<span class="sql-kw">${escapeHtml(token)}</span>`;
        }
        return escapeHtml(token);
    }).join('');
}

function renderTable(results) {
    currentResults = results;
    if (!results || results.length === 0) {
        DOM.table.style.display = 'none';
        DOM.btnExport.style.display = 'none';
        DOM.tableEmpty.style.display = 'flex';
        DOM.tableEmpty.textContent = "Query executed successfully, but returned 0 rows.";
        return;
    }
    
    DOM.tableEmpty.style.display = 'none';
    DOM.table.style.display = 'table';
    DOM.btnExport.style.display = 'flex';
    
    const headers = Object.keys(results[0]);
    
    const trHead = document.createElement('tr');
    headers.forEach(h => {
        const th = document.createElement('th');
        th.textContent = h;
        trHead.appendChild(th);
    });
    DOM.tableHead.innerHTML = '';
    DOM.tableHead.appendChild(trHead);
    
    DOM.tableBody.innerHTML = '';
    results.forEach((row) => {
        const tr = document.createElement('tr');
        headers.forEach(h => {
            const td = document.createElement('td');
            td.textContent = row[h] !== null ? row[h] : 'NULL';
            tr.appendChild(td);
        });
        DOM.tableBody.appendChild(tr);
    });
}

DOM.form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = DOM.input.value.trim();
    if (!query) return;
    
    DOM.input.value = '';
    DOM.submitBtn.disabled = true;
    DOM.submitBtn.innerHTML = `<svg style="width:15px;height:15px;animation:spin .9s linear infinite;" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="white" stroke-width="4" opacity=".3"></circle><path fill="white" opacity=".8" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>`;
    
    appendUserMessage(query);
    const bubble = createAiMessageBubble();
    
    currentResults = [];
    DOM.sqlOutput.textContent = "Pipeline activated...";
    DOM.badges.style.opacity = '0';
    DOM.table.style.display = 'none';
    DOM.tableEmpty.style.display = 'flex';
    DOM.tableEmpty.textContent = "Awaiting execution...";
    DOM.btnExport.style.display = 'none';
    
    try {
        await fetchSSE('/api/v1/stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': getApiKey()
            },
            body: JSON.stringify({ query, session_id: currentSessionId })
        }, (event, data) => {
            
            if (event === 'status') {
                bubble.statusText.textContent = data.msg;
            } 
            else if (event === 'data_chunk') {
                if (data.sql && DOM.sqlOutput.textContent === "Pipeline activated...") {
                    DOM.sqlOutput.innerHTML = highlightSql(data.sql);
                    
                    setTimeout(() => { DOM.badges.style.opacity = '1'; }, 50);
                    
                    DOM.badgeAst.textContent = "VALID";
                    DOM.badgeAst.className = 'badge badge-ok';

                    const confPct = Math.round(data.confidence * 100);
                    DOM.badgeConf.textContent = `${confPct}%`;
                    DOM.badgeConf.className = confPct < 20 ? 'badge badge-warn' : 'badge badge-default';

                    if (data.rag_mode) {
                        DOM.badgeRag.textContent = data.rag_mode === 'doc_rag' ? 'doc' : 'sql';
                        DOM.badgeRag.className = 'badge badge-default';
                    }

                    if (data.latency_ms) {
                        DOM.sqlOutput.innerHTML += `<span style="color:var(--text-dim);font-size:11px;"> -- ${data.latency_ms}ms</span>`;
                    }
                    
                    if (data.retries > 0) {
                        bubble.statusText.textContent = `Auto-corrected syntax after ${data.retries} retries...`;
                    }
                }
                
                if (data.results && data.results.length > 0) {
                    currentResults = currentResults.concat(data.results);
                    renderTable(currentResults);
                } else if (currentResults.length === 0) {
                    renderTable([]); // Force empty state render
                }
            }
            else if (event === 'complete') {
                bubble.statusText.remove();
                bubble.contentBox.textContent = data.answer;
            }
            else if (event === 'error') {
                bubble.statusText.remove();
                const errEl = document.createElement('div');
                errEl.className = 'error-msg';
                errEl.textContent = data.msg;
                bubble.contentBox.innerHTML = '';
                bubble.contentBox.appendChild(errEl);
                
                DOM.sqlOutput.textContent = "Execution halted due to error.";
                DOM.tableEmpty.textContent = "No data returned.";
                
                if (data.msg.includes("Security")) {
                    DOM.badges.style.opacity = '1';
                    DOM.badgeAst.textContent = "blocked";
                    DOM.badgeAst.className = 'badge badge-error';
                }
            }
            
            DOM.chatHistory.scrollTop = DOM.chatHistory.scrollHeight;
        });
        
    } catch (e) {
        if (e.message !== "Invalid API Key") {
            bubble.statusText.textContent = "Connection failed.";
            bubble.statusText.classList.remove('animate-pulse');
            bubble.statusText.classList.add('text-red-400');
        } else {
            bubble.container.remove();
        }
    } finally {
        DOM.submitBtn.disabled = false;
        DOM.submitBtn.innerHTML = `<svg width="15" height="15" fill="none" stroke="white" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 12h14M12 5l7 7-7 7"/></svg>`;
        DOM.input.focus();
    }
});

DOM.btnExport.addEventListener('click', () => {
    if (!currentResults || currentResults.length === 0) return;
    
    const headers = Object.keys(currentResults[0]);
    const csvRows = [];
    csvRows.push(headers.map(h => `"${h.replace(/"/g, '""')}"`).join(','));
    
    for (const row of currentResults) {
        const values = headers.map(h => {
            const val = row[h] !== null ? String(row[h]) : '';
            return `"${val.replace(/"/g, '""')}"`;
        });
        csvRows.push(values.join(','));
    }
    
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `queryforce_export_${new Date().getTime()}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
});
