document.addEventListener('DOMContentLoaded', () => {
    // Tab switching logic
    const tabs = document.querySelectorAll('.tab');
    const views = document.querySelectorAll('.view');
    
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            views.forEach(v => v.classList.remove('active-view'));
            
            tab.classList.add('active');
            document.getElementById(tab.dataset.target).classList.add('active-view');
            
            if(tab.dataset.target === 'results-view') {
                loadJobs();
            }
        });
    });

    // Settings Modal Logic
    const settingsModal = document.getElementById('settings-modal');
    document.getElementById('btn-settings').onclick = () => {
        fetch('/api/settings').then(r => r.json()).then(data => {
            document.getElementById('agency-name').value = data.name || '';
            document.getElementById('agency-services').value = data.services || '';
            document.getElementById('agency-cta').value = data.cta || '';
            settingsModal.style.display = 'flex';
        });
    };
    document.getElementById('close-settings').onclick = () => settingsModal.style.display = 'none';
    
    document.getElementById('save-settings-btn').onclick = async () => {
        const payload = {
            name: document.getElementById('agency-name').value,
            services: document.getElementById('agency-services').value,
            cta: document.getElementById('agency-cta').value
        };
        const btn = document.getElementById('save-settings-btn');
        btn.textContent = "Saving...";
        await fetch('/api/settings', {
            method: 'POST', 
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        btn.textContent = "Save Profile";
        settingsModal.style.display = 'none';
    };

    // Slide Panel Logic
    const outreachPanel = document.getElementById('outreach-panel');
    document.getElementById('close-panel').onclick = () => outreachPanel.classList.remove('open');

    // Quick Search Logic
    const qsInput = document.getElementById('quick-search-input');
    const qsModal = document.getElementById('quick-search-modal');
    qsInput.addEventListener('keypress', async (e) => {
        if(e.key === 'Enter') {
            const companyName = qsInput.value.trim();
            if(!companyName) return;
            
            qsInput.value = '';
            qsInput.blur();
            qsModal.style.display = 'flex';
            document.getElementById('qs-title').textContent = `Intel on ${companyName}`;
            document.getElementById('qs-loading').style.display = 'block';
            document.getElementById('qs-result').style.display = 'none';
            
            try {
                const res = await fetch('/api/quick_search', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({company_name: companyName})
                });
                const data = await res.json();
                
                if(data.success) {
                    const lead = data.lead_data;
                    document.getElementById('qs-loading').style.display = 'none';
                    document.getElementById('qs-result').style.display = 'block';
                    
                    document.getElementById('qs-company').textContent = lead.business_name || lead.company_name;
                    document.getElementById('qs-website').href = lead.website_link !== 'Not Found' ? lead.website_link : '#';
                    document.getElementById('qs-website').textContent = lead.website_link !== 'Not Found' ? lead.website_link + ' ↗' : 'No Website Found';
                    document.getElementById('qs-decision-maker').textContent = lead.decision_maker;
                    document.getElementById('qs-niche').textContent = lead.niche;
                    document.getElementById('qs-summary').textContent = lead.summary;
                    document.getElementById('qs-pitch-angle').textContent = lead.pitch_angle;
                    
                    document.getElementById('qs-draft-btn').onclick = () => {
                        qsModal.style.display = 'none';
                        const nameToUse = lead.business_name || lead.company_name;
                        const safeName = nameToUse.replace(/'/g, "\\'");
                        const safeEmail = lead.email !== 'Not Found' ? lead.email.replace(/'/g, "\\'") : '';
                        
                        // Switch to Results Tab so panel looks correct contextually
                        document.querySelector('[data-target="results-view"]').click();
                        
                        openPitchDeck(lead.id, safeName, safeEmail);
                    };
                    
                    // Auto-load jobs to update history with this new 1-item job
                    loadJobs();
                } else {
                    document.getElementById('qs-loading').innerHTML = `<p style="color:var(--danger)">Error: ${data.error}</p>`;
                }
            } catch(e) {
                document.getElementById('qs-loading').innerHTML = `<p style="color:var(--danger)">Connection Error.</p>`;
            }
        }
    });
    document.getElementById('close-qs').onclick = () => {
        qsModal.style.display = 'none';
        document.getElementById('qs-loading').innerHTML = `<p style="color: var(--text-muted); margin-bottom: 1rem;">Deploying crawler & Llama 3 analysis...</p><div class="spinner"></div>`;
    };

    // Ollama Status Check
    fetch('/api/ollama-status')
        .then(res => res.json())
        .then(data => {
            const dot = document.querySelector('.dot');
            const text = document.querySelector('.status-text');
            if (data.online) {
                dot.classList.add('online');
                text.textContent = 'Active (Ready)';
            } else {
                text.textContent = 'Offline (Start Llama 3)';
            }
        });

    // File Upload Drag & Drop Interface
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('csv-file');
    const fileNameDisplay = document.getElementById('file-name');
    
    dropZone.addEventListener('click', () => fileInput.click());
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            fileNameDisplay.textContent = fileInput.files[0].name;
            fileNameDisplay.style.color = 'var(--accent)';
            fileNameDisplay.style.fontWeight = '600';
        }
    });
    
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
            fileNameDisplay.textContent = fileInput.files[0].name;
            fileNameDisplay.style.color = 'var(--accent)';
            fileNameDisplay.style.fontWeight = '600';
        }
    });

    // Thread Slider updating displays
    const threadSlider = document.getElementById('thread-count');
    const threadDisplay = document.getElementById('thread-display');
    threadSlider.addEventListener('input', (e) => threadDisplay.textContent = `${e.target.value} Threads`);

    // Job Execution & SSE Streams
    let currentJobId = null;
    let eventSource = null;
    let progressInterval = null;

    document.getElementById('upload-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        if (!fileInput.files.length) {
            alert('Please select a CSV file first.');
            return;
        }

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('threads', threadSlider.value);
        formData.append('use_ai', document.getElementById('use-ai').checked);

        const btn = e.target.querySelector('button');
        btn.textContent = "Initializing Engine…";
        btn.disabled = true;

        try {
            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            
            if (res.ok && data.job_id) {
                currentJobId = data.job_id;
                startStreaming(currentJobId);
                // Transition to live progress
                document.querySelector('[data-target="run-view"]').click();
                document.getElementById('progress-text').textContent = "Warming up headless browsers...";
                document.getElementById('progress-bar').style.width = '2%';
                document.getElementById('log-feed').innerHTML = '';
                document.getElementById('preview-feed').innerHTML = '';
            } else {
                alert(data.error || "Failed to launch batch pipeline");
            }
        } catch (err) {
            alert('Connection Error starting job: ' + err);
        } finally {
            btn.textContent = "Launch Batch Pipeline \u2192";
            btn.disabled = false;
            fileInput.value = "";
            fileNameDisplay.textContent = "";
        }
    });

    function startStreaming(jobId) {
        if(eventSource) eventSource.close();
        if(progressInterval) clearInterval(progressInterval);
        
        eventSource = new EventSource(`/api/stream/${jobId}`);
        const logFeed = document.getElementById('log-feed');
        const previewFeed = document.getElementById('preview-feed');
        
        progressInterval = setInterval(() => {
            fetch(`/api/leads/${jobId}`)
                .then(r => r.json())
                .then(d => {
                    const status = d.status;
                    if(status) {
                        const total = status.total_records || 1;
                        const done = status.completed_records + status.failed_records;
                        const pct = Math.min(100, Math.round((done / total) * 100));
                        document.getElementById('progress-bar').style.width = pct + '%';
                        document.getElementById('progress-text').textContent = `Processed ${done} of ${total} prospects (${pct}%)`;
                        
                        if(status.status === 'completed' || status.status === 'failed' || status.status === 'stopped') {
                            clearInterval(progressInterval);
                            eventSource.close();
                            document.getElementById('progress-text').textContent = status.status === 'completed' ? "Batch pipeline successfully completed! Switch to Results to export." : "Batch pipeline encountered a fatal error or was stopped.";
                            document.querySelector('.progress-bar').style.backgroundColor = status.status === 'completed' ? "var(--success)" : "var(--danger)";
                            document.getElementById('execution-controls').style.display = 'none';
                        }
                    }
                });
        }, 3000);
        
        const controls = document.getElementById('execution-controls');
        controls.style.display = 'flex';
        
        document.getElementById('btn-pause').onclick = () => {
            fetch(`/api/job/${jobId}/pause`, {method:'POST'});
            document.getElementById('btn-pause').style.display = 'none';
            document.getElementById('btn-resume').style.display = 'block';
            document.getElementById('progress-text').textContent += ' (PAUSED)';
        };
        document.getElementById('btn-resume').onclick = () => {
            fetch(`/api/job/${jobId}/resume`, {method:'POST'});
            document.getElementById('btn-resume').style.display = 'none';
            document.getElementById('btn-pause').style.display = 'block';
            document.getElementById('progress-text').textContent = document.getElementById('progress-text').textContent.replace(' (PAUSED)', '');
        };
        document.getElementById('btn-stop').onclick = () => {
            if(confirm("Are you sure you want to completely stop this job?")) {
                fetch(`/api/job/${jobId}/stop`, {method:'POST'});
                controls.style.display = 'none';
            }
        };

        eventSource.onmessage = function(e) {
            const data = JSON.parse(e.data);
            
            // Append terminal log inline
            const line = document.createElement('div');
            line.className = `log-line log-${data.level}`;
            line.textContent = `> ${data.message}`;
            logFeed.appendChild(line);
            logFeed.scrollTop = logFeed.scrollHeight;

            // Generate aesthetic UI card mapping on successful enrichment
            if (data.lead_data && (data.level === 'success' || data.level === 'error')) {
                const card = document.createElement('div');
                card.className = `preview-card ${data.level}`;
                
                const isSuccess = data.level === 'success';
                const name = data.lead_data.company_name || 'Prospect';
                const icon = isSuccess ? '✅ ' : '❌ ';
                
                let inner = `<h4>${icon}${name}</h4>`;
                if(isSuccess && data.lead_data.pitch_angle && data.lead_data.pitch_angle !== 'Not Analyzed') {
                    inner += `<div class="text-sm text-muted">${data.lead_data.summary}</div>`;
                    inner += `<div class="preview-badge">🔍 Angle: ${data.lead_data.pitch_angle}</div>`;
                } else if (data.lead_data && data.lead_data.status === 'Missing_Website') {
                    inner += `<div class="text-sm text-muted">⚠️ Website not found. Please provide a manual URL in History & Results.</div>`;
                } else if (!isSuccess) {
                    inner += `<div class="text-sm text-muted">⚠️ Could not load website or find contact data. Skipped to save resources.</div>`;
                } else {
                    inner += `<div class="text-sm text-muted">Data captured without deep strategic analysis.</div>`;
                }
                
                card.innerHTML = inner;
                // Add to top visually
                previewFeed.prepend(card);
            }
        };
    }

    // Interactive Results Table Logic
    const jobSelect = document.getElementById('job-select');
    const downloadBtn = document.getElementById('download-btn');
    const deleteJobBtn = document.getElementById('delete-job-btn');
    
    function loadJobs() {
        fetch('/api/jobs')
            .then(r => r.json())
            .then(jobs => {
                jobSelect.innerHTML = '<option value="">Select a previous dataset</option>';
                jobs.forEach(j => {
                    const opt = document.createElement('option');
                    opt.value = j.id;
                    opt.textContent = `Batch #${j.id} - ${j.filename} (${new Intl.DateTimeFormat(undefined, {dateStyle:'medium', timeStyle:'short'}).format(new Date(j.created_at))})`;
                    jobSelect.appendChild(opt);
                });
                
                if(currentJobId && jobs.find(j=>j.id == currentJobId)) {
                    jobSelect.value = currentJobId;
                    loadLeads(currentJobId);
                } else if (jobs.length > 0) {
                    jobSelect.value = jobs[0].id;
                    loadLeads(jobs[0].id);
                }
            });
    }

    jobSelect.addEventListener('change', (e) => {
        if(e.target.value) {
            loadLeads(e.target.value);
        }
    });

    downloadBtn.addEventListener('click', () => {
        const jId = jobSelect.value;
        if(jId) window.location.href = `/api/download/${jId}`;
    });

    deleteJobBtn.addEventListener('click', async () => {
        const jId = jobSelect.value;
        if(!jId) return;
        const label = jobSelect.options[jobSelect.selectedIndex].text;
        if(!confirm(`Delete "${label}" and all its leads permanently? This cannot be undone.`)) return;
        
        deleteJobBtn.textContent = 'Deleting…';
        deleteJobBtn.disabled = true;
        
        await fetch(`/api/job/${jId}/delete`, { method: 'DELETE' });
        
        // Clear table and reload the jobs list
        document.getElementById('results-body').innerHTML = '<tr><td colspan="5" style="text-align:center; padding:3rem; color:var(--text-muted)">Batch deleted.</td></tr>';
        downloadBtn.disabled = true;
        deleteJobBtn.textContent = '🗑️ Delete Batch';
        await loadJobs();
    });

    // Global Search Logic
    let searchTimeout;
    const globalSearchInput = document.getElementById('global-search');
    globalSearchInput.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        const query = e.target.value.trim();
        searchTimeout = setTimeout(() => {
            if (query.length === 0) {
                // Return to batch if cleared
                const jId = jobSelect.value;
                if(jId) {
                    loadLeads(jId);
                } else {
                    document.getElementById('results-body').innerHTML = '';
                }
                return;
            }
            
            jobSelect.value = ""; // Deselect batch
            downloadBtn.disabled = true;
            deleteJobBtn.disabled = true;
            
            const tbody = document.getElementById('results-body');
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:3rem; color:var(--text-muted)">Searching entire database...</td></tr>';
            
            fetch(`/api/leads/search?q=${encodeURIComponent(query)}`)
                .then(r => r.json())
                .then(data => {
                    renderLeads(data.leads, true);
                });
                
        }, 400); // 400ms debounce
    });

    function renderLeads(leads, isSearch = false) {
        const tbody = document.getElementById('results-body');
        tbody.innerHTML = '';
        
        if (!isSearch) {
            deleteJobBtn.disabled = false;
        }

        if(leads.length > 0) {
            if (!isSearch) downloadBtn.disabled = false;
            
            leads.forEach(lead => {
                const tr = document.createElement('tr');
                
                let contactList = [];
                if(lead.email && lead.email !== 'Not Found') contactList.push(`<strong class="text-primary">${lead.email}</strong>`);
                if(lead.phone && lead.phone !== 'Not Found') contactList.push(`<span class="text-muted">${lead.phone}</span>`);
                if(lead.location && lead.location !== 'Not Found') contactList.push(`<span class="text-muted" style="font-size:0.75rem">${lead.location.replace('\\n', ', ')}</span>`);
                
                let retryUI = '';
                if(lead.status === 'Missing_Website' || lead.status === 'Failed') {
                    retryUI = `
                        <div class="retry-form" id="retry-form-${lead.id}">
                            <input type="text" id="retry-url-${lead.id}" class="retry-input" placeholder="Paste website URL...">
                            <button class="btn btn-secondary btn-sm" onclick="retryLead(${lead.id})">Retry</button>
                        </div>
                    `;
                }
                
                let pitchUI = '';
                if(lead.status === 'Success' && lead.pitch_angle && lead.pitch_angle !== 'Unknown' && lead.pitch_angle !== 'Not Analyzed') {
                    const safeName = lead.business_name.replace(/'/g, "\\'");
                    const safeEmail = lead.email !== 'Not Found' ? lead.email.replace(/'/g, "\\'") : '';
                    pitchUI = `<br><button class="btn btn-primary btn-sm mt-1" onclick="openPitchDeck(${lead.id}, '${safeName}', '${safeEmail}')">✉️ Draft Email</button>`;
                }

                tr.innerHTML = `
                    <td>
                        <strong style="font-size: 1.05rem; display:block; margin-bottom:0.25rem">${lead.business_name}</strong>
                        ${lead.website && lead.website !== 'Not Found' ? `<a href="${lead.website}" class="text-sm text-accent" target="_blank" style="text-decoration:none">Visit Website ↗</a>` : ''}
                        ${retryUI}
                        ${pitchUI}
                    </td>
                    <td>
                        <span class="font-500">${lead.niche}</span><br>
                        <span class="text-muted text-sm" style="display:inline-block; max-width: 250px">${lead.summary}</span>
                    </td>
                    <td class="text-sm" style="line-height:1.4">${contactList.join('<br>')}</td>
                    <td><span style="display:inline-block; padding:0.25rem 0.6rem; background:rgba(255,255,255,0.05); border-radius:4px; font-size:0.875rem;">${lead.decision_maker}</span></td>
                    <td class="text-sm text-muted" style="max-width:300px">
                        <strong>Opening:</strong> ${lead.opening_line || 'N/A'}<br>
                        <strong style="color:var(--warning); margin-top:0.5rem; display:inline-block">Angle:</strong> ${lead.pitch_angle || 'N/A'}
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            downloadBtn.disabled = true;
            const message = isSearch ? 'No prospects found globally matching your search.' : 'Awaiting prospects...';
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 3rem; color: var(--text-muted)">${message}</td></tr>`;
        }
    }

    function loadLeads(jobId) {
        fetch(`/api/leads/${jobId}`)
            .then(r => r.json())
            .then(data => {
                renderLeads(data.leads, false);
            });
    }

    // Manual Retry Function
    window.retryLead = async function(leadId) {
        const urlInput = document.getElementById(`retry-url-${leadId}`);
        const url = urlInput.value.trim();
        if(!url) return alert('Enter a URL first');
        
        const btn = urlInput.nextElementSibling;
        btn.textContent = 'Retrying...';
        btn.disabled = true;
        urlInput.disabled = true;
        
        try {
            const res = await fetch(`/api/retry/lead/${leadId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url: url})
            });
            if(res.ok) {
                btn.textContent = 'Queued! Refreshing soon...';
                btn.classList.add('text-success');
                // Auto reload leads after 10s to see result
                setTimeout(() => loadLeads(jobSelect.value), 10000);
            } else {
                alert("Retry failed");
                btn.textContent = 'Retry';
                btn.disabled = false;
                urlInput.disabled = false;
            }
        } catch(e) {
            alert("Error: " + e);
            btn.disabled = false;
            urlInput.disabled = false;
        }
    }

    // Outreach Mode Pitch Drafter
    window.openPitchDeck = async function(leadId, businessName, email) {
        outreachPanel.classList.add('open');
        document.getElementById('pitch-lead-name').textContent = `Pitching: ${businessName}`;
        document.getElementById('pitch-lead-contact').textContent = email ? `To: ${email}` : `No direct email found. Draft generated anyway.`;
        
        document.getElementById('draft-loading').style.display = 'block';
        document.getElementById('draft-result').style.display = 'none';
        
        try {
            const res = await fetch(`/api/draft_email/${leadId}`);
            const data = await res.json();
            
            document.getElementById('draft-loading').style.display = 'none';
            document.getElementById('draft-result').style.display = 'block';
            
            if(data.draft) {
                const textarea = document.getElementById('drafted-email');
                textarea.value = data.draft;
                
                // Handlers
                const copyBtn = document.getElementById('copy-draft-btn');
                copyBtn.onclick = () => {
                    navigator.clipboard.writeText(textarea.value);
                    copyBtn.textContent = '✅ Copied!';
                    setTimeout(() => copyBtn.textContent = '📋 Copy', 2000);
                };
                
                const mailBtn = document.getElementById('mailto-btn');
                if(email) {
                    const subject = encodeURIComponent(`Question for ${businessName}`);
                    const body = encodeURIComponent(textarea.value);
                    mailBtn.href = `mailto:${email}?subject=${subject}&body=${body}`;
                    mailBtn.style.display = 'inline-flex';
                } else {
                    mailBtn.style.display = 'none';
                }
            } else {
                document.getElementById('drafted-email').value = "Error generating draft.";
            }
        } catch(e) {
            document.getElementById('draft-loading').style.display = 'none';
            alert("Connection error generating draft");
        }
    }
});
