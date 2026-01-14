// Google Ads Intelligence Dashboard - JavaScript

const API_BASE = '';

// ==================== Utility Functions ====================

async function apiCall(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'API request failed');
        }

        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');

    toastMessage.textContent = message;
    toast.className = `fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg transform transition-transform duration-300 ${
        type === 'error' ? 'bg-red-600' : type === 'warning' ? 'bg-yellow-600' : 'bg-green-600'
    } text-white`;

    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 3000);
}

function formatDate(dateString) {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function getStatusBadge(status) {
    const colors = {
        pending: 'bg-yellow-100 text-yellow-800',
        running: 'bg-blue-100 text-blue-800',
        completed: 'bg-green-100 text-green-800',
        failed: 'bg-red-100 text-red-800',
        blocked: 'bg-gray-100 text-gray-800',
        active: 'bg-green-100 text-green-800',
        inactive: 'bg-gray-100 text-gray-800'
    };
    return `<span class="px-2 py-1 text-xs font-medium rounded-full ${colors[status] || colors.pending}">${status}</span>`;
}

// ==================== Tab Navigation ====================

function showTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.tab-btn').forEach(el => {
        el.classList.remove('tab-active');
        el.classList.add('text-gray-500');
    });

    // Show selected tab
    document.getElementById(`content-${tabName}`).classList.remove('hidden');
    document.getElementById(`tab-${tabName}`).classList.add('tab-active');
    document.getElementById(`tab-${tabName}`).classList.remove('text-gray-500');

    // Load data for the tab
    switch (tabName) {
        case 'keywords':
            loadKeywords();
            break;
        case 'advertisers':
            loadAdvertisers();
            break;
        case 'jobs':
            loadJobs();
            break;
        case 'adcopy':
            loadKeywordsForAdCopy();
            break;
    }
}

// ==================== Health Check ====================

async function checkHealth() {
    try {
        const health = await apiCall('/health');
        const statusEl = document.getElementById('health-status');

        const isHealthy = health.status === 'healthy';
        statusEl.innerHTML = `
            <span class="w-2 h-2 ${isHealthy ? 'bg-green-500' : 'bg-yellow-500'} rounded-full"></span>
            <span class="text-sm ${isHealthy ? 'text-green-600' : 'text-yellow-600'}">${health.status}</span>
        `;
    } catch (error) {
        const statusEl = document.getElementById('health-status');
        statusEl.innerHTML = `
            <span class="w-2 h-2 bg-red-500 rounded-full"></span>
            <span class="text-sm text-red-600">Offline</span>
        `;
    }
}

// ==================== Keywords ====================

async function loadKeywords() {
    const tbody = document.getElementById('keywords-table');

    try {
        const keywords = await apiCall('/api/keywords');

        if (keywords.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="px-6 py-12 text-center text-gray-500">
                        No keywords yet. Click "Add Keyword" to get started.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = keywords.map(kw => `
            <tr class="hover:bg-gray-50">
                <td class="px-6 py-4">
                    <div class="font-medium text-gray-900">${kw.keyword}</div>
                </td>
                <td class="px-6 py-4 text-sm text-gray-500">${kw.category || '-'}</td>
                <td class="px-6 py-4">
                    <span class="px-2 py-1 text-xs font-medium rounded bg-indigo-100 text-indigo-800">${kw.crawl_priority}</span>
                </td>
                <td class="px-6 py-4 text-sm text-gray-500">${formatDate(kw.last_crawled_at)}</td>
                <td class="px-6 py-4">${getStatusBadge(kw.is_active ? 'active' : 'inactive')}</td>
                <td class="px-6 py-4 text-right space-x-2">
                    <button onclick="scrapeKeyword(${kw.id})" class="text-primary hover:text-indigo-700 text-sm font-medium">Scrape</button>
                    <button onclick="viewKeywordAds(${kw.id})" class="text-gray-600 hover:text-gray-900 text-sm font-medium">View Ads</button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="px-6 py-12 text-center text-red-500">
                    Failed to load keywords: ${error.message}
                </td>
            </tr>
        `;
    }
}

function openAddKeywordModal() {
    document.getElementById('add-keyword-modal').classList.remove('hidden');
    document.getElementById('add-keyword-modal').classList.add('flex');
}

function closeAddKeywordModal() {
    document.getElementById('add-keyword-modal').classList.add('hidden');
    document.getElementById('add-keyword-modal').classList.remove('flex');
    document.getElementById('new-keyword').value = '';
    document.getElementById('new-category').value = '';
    document.getElementById('new-priority').value = '5';
}

async function addKeyword() {
    const keyword = document.getElementById('new-keyword').value.trim();
    const category = document.getElementById('new-category').value.trim();
    const priority = parseInt(document.getElementById('new-priority').value);

    if (!keyword) {
        showToast('Please enter a keyword', 'error');
        return;
    }

    try {
        await apiCall('/api/keywords', {
            method: 'POST',
            body: JSON.stringify({
                keyword: keyword,
                category: category || null,
                crawl_priority: priority
            })
        });

        showToast('Keyword added successfully');
        closeAddKeywordModal();
        loadKeywords();
        loadKeywordsForAdCopy();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function scrapeKeyword(keywordId) {
    try {
        showToast('Starting scrape job...');
        await apiCall(`/api/keywords/${keywordId}/scrape`, {
            method: 'POST',
            body: JSON.stringify({ geo: 'US', device: 'desktop' })
        });
        showToast('Scrape job queued successfully');
        loadKeywords();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function viewKeywordAds(keywordId) {
    try {
        const data = await apiCall(`/api/keywords/${keywordId}/advertisers`);

        if (data.length === 0) {
            showToast('No ads found for this keyword yet', 'warning');
            return;
        }

        // Switch to advertisers tab with filtered view
        showTab('advertisers');
        showToast(`Showing ${data.length} advertisers for this keyword`);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

// ==================== Advertisers ====================

async function loadAdvertisers() {
    const grid = document.getElementById('advertisers-grid');

    try {
        const advertisers = await apiCall('/api/advertisers');

        if (advertisers.length === 0) {
            grid.innerHTML = `
                <div class="col-span-full text-center py-12 text-gray-500">
                    No advertisers discovered yet. Scrape some keywords to find advertisers.
                </div>
            `;
            return;
        }

        grid.innerHTML = advertisers.map(adv => `
            <div class="bg-white rounded-xl border p-4 hover:shadow-md transition">
                <div class="flex items-start justify-between mb-3">
                    <div>
                        <h4 class="font-semibold text-gray-900">${adv.domain}</h4>
                        <p class="text-sm text-gray-500">${adv.company_name || adv.root_domain}</p>
                    </div>
                    ${getStatusBadge(adv.is_active ? 'active' : 'inactive')}
                </div>
                <div class="space-y-2 text-sm">
                    <div class="flex justify-between">
                        <span class="text-gray-500">Keywords:</span>
                        <span class="font-medium">${adv.total_keywords_count}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-gray-500">Est. Spend:</span>
                        <span class="font-medium">${adv.estimated_monthly_spend ? '$' + parseFloat(adv.estimated_monthly_spend).toLocaleString() : '-'}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-gray-500">First Seen:</span>
                        <span class="font-medium">${new Date(adv.first_seen_at).toLocaleDateString()}</span>
                    </div>
                </div>
                <div class="mt-4 pt-3 border-t">
                    <button onclick="viewAdvertiserDetails(${adv.id})" class="text-primary hover:text-indigo-700 text-sm font-medium">View Details</button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        grid.innerHTML = `
            <div class="col-span-full text-center py-12 text-red-500">
                Failed to load advertisers: ${error.message}
            </div>
        `;
    }
}

async function viewAdvertiserDetails(advertiserId) {
    try {
        const adv = await apiCall(`/api/advertisers/${advertiserId}`);
        showToast(`Viewing ${adv.domain}`);
        // Could open a modal with detailed info
    } catch (error) {
        showToast(error.message, 'error');
    }
}

// ==================== Ad Copy Generator ====================

async function loadKeywordsForAdCopy() {
    const select = document.getElementById('adcopy-keyword');

    try {
        const keywords = await apiCall('/api/keywords');

        if (keywords.length === 0) {
            select.innerHTML = '<option value="">No keywords - add some first</option>';
            return;
        }

        select.innerHTML = '<option value="">Select a keyword...</option>' +
            keywords.map(kw => `<option value="${kw.id}">${kw.keyword}</option>`).join('');
    } catch (error) {
        select.innerHTML = '<option value="">Failed to load keywords</option>';
    }
}

async function generateAdCopy() {
    const keywordId = document.getElementById('adcopy-keyword').value;
    const businessName = document.getElementById('adcopy-business').value.trim();
    const description = document.getElementById('adcopy-description').value.trim();
    const audience = document.getElementById('adcopy-audience').value.trim();
    const tone = document.getElementById('adcopy-tone').value;
    const focus = document.getElementById('adcopy-focus').value;
    const variations = parseInt(document.getElementById('adcopy-variations').value);
    const useCompetitor = document.getElementById('adcopy-competitor').checked;

    if (!keywordId) {
        showToast('Please select a keyword', 'error');
        return;
    }

    const btn = document.getElementById('generate-btn');
    const results = document.getElementById('adcopy-results');

    btn.disabled = true;
    btn.innerHTML = '<div class="loader mx-auto"></div>';
    results.innerHTML = '<div class="text-center py-12"><div class="loader mx-auto mb-4"></div><p class="text-gray-500">Generating ad copies with AI...</p></div>';

    try {
        const copies = await apiCall(`/api/adcopy/generate/${keywordId}`, {
            method: 'POST',
            body: JSON.stringify({
                business_name: businessName || null,
                business_description: description || null,
                target_audience: audience || null,
                tone: tone,
                conversion_focus: focus,
                num_variations: variations,
                use_competitor_insights: useCompetitor
            })
        });

        results.innerHTML = copies.map((copy, index) => `
            <div class="border rounded-lg p-4 hover:shadow-md transition">
                <div class="flex justify-between items-start mb-3">
                    <span class="text-xs font-medium text-gray-500 uppercase">Variation ${index + 1}</span>
                    <div class="flex items-center space-x-2">
                        <span class="px-2 py-1 text-xs rounded bg-indigo-100 text-indigo-800">Quality: ${copy.quality_score}/10</span>
                        <button onclick="toggleFavorite(${copy.id})" class="text-gray-400 hover:text-yellow-500">
                            <svg class="w-5 h-5" fill="${copy.is_favorite ? 'currentColor' : 'none'}" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"></path>
                            </svg>
                        </button>
                    </div>
                </div>

                <div class="space-y-3">
                    <div>
                        <div class="text-xs text-gray-500 mb-1">Headlines</div>
                        <div class="text-blue-600 font-medium">${copy.headline_1}</div>
                        <div class="text-blue-600">${copy.headline_2}</div>
                        ${copy.headline_3 ? `<div class="text-blue-600">${copy.headline_3}</div>` : ''}
                    </div>

                    <div>
                        <div class="text-xs text-gray-500 mb-1">Descriptions</div>
                        <div class="text-gray-700 text-sm">${copy.description_1}</div>
                        ${copy.description_2 ? `<div class="text-gray-600 text-sm mt-1">${copy.description_2}</div>` : ''}
                    </div>

                    ${copy.display_path_1 ? `
                    <div>
                        <div class="text-xs text-gray-500 mb-1">Display Path</div>
                        <div class="text-green-700 text-sm">yoursite.com/${copy.display_path_1}${copy.display_path_2 ? '/' + copy.display_path_2 : ''}</div>
                    </div>
                    ` : ''}

                    ${copy.call_to_action ? `
                    <div class="pt-2 border-t">
                        <span class="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">CTA: ${copy.call_to_action}</span>
                    </div>
                    ` : ''}
                </div>

                <div class="mt-4 pt-3 border-t flex justify-between items-center">
                    <div class="flex space-x-2">
                        <span class="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded">${copy.tone}</span>
                        <span class="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">${copy.conversion_focus}</span>
                    </div>
                    <button onclick="copyToClipboard(\`${copy.headline_1}\\n${copy.headline_2}\\n${copy.description_1}\`)" class="text-sm text-primary hover:text-indigo-700">Copy</button>
                </div>
            </div>
        `).join('');

        showToast(`Generated ${copies.length} ad variations`);
    } catch (error) {
        results.innerHTML = `
            <div class="text-center py-12 text-red-500">
                <p class="font-medium">Failed to generate ad copies</p>
                <p class="text-sm mt-2">${error.message}</p>
            </div>
        `;
        showToast(error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Generate Ad Copies';
    }
}

async function toggleFavorite(copyId) {
    try {
        await apiCall(`/api/adcopy/${copyId}/favorite`, { method: 'PATCH' });
        showToast('Favorite updated');
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard');
    }).catch(() => {
        showToast('Failed to copy', 'error');
    });
}

// ==================== Jobs ====================

async function loadJobs() {
    const tbody = document.getElementById('jobs-table');

    try {
        // Load job stats
        const stats = await apiCall('/api/jobs/stats');
        document.getElementById('stat-pending').textContent = stats.pending;
        document.getElementById('stat-running').textContent = stats.running;
        document.getElementById('stat-completed').textContent = stats.completed;
        document.getElementById('stat-failed').textContent = stats.failed;
        document.getElementById('stat-total').textContent = stats.total;

        // Load jobs list
        const jobs = await apiCall('/api/jobs');

        if (jobs.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="px-6 py-12 text-center text-gray-500">
                        No jobs yet. Scrape a keyword to create jobs.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = jobs.map(job => `
            <tr class="hover:bg-gray-50">
                <td class="px-6 py-4 text-sm font-mono text-gray-500">#${job.id}</td>
                <td class="px-6 py-4 text-sm">
                    <span class="px-2 py-1 text-xs rounded bg-gray-100 text-gray-700">${job.job_type}</span>
                </td>
                <td class="px-6 py-4 text-sm font-medium text-gray-900">${job.target}</td>
                <td class="px-6 py-4">${getStatusBadge(job.status)}</td>
                <td class="px-6 py-4 text-sm text-gray-500">${formatDate(job.created_at)}</td>
                <td class="px-6 py-4 text-sm text-gray-500">${job.attempts}/${job.max_attempts}</td>
            </tr>
        `).join('');
    } catch (error) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="px-6 py-12 text-center text-red-500">
                    Failed to load jobs: ${error.message}
                </td>
            </tr>
        `;
    }
}

// ==================== Initialization ====================

document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    loadKeywords();

    // Set up search
    document.getElementById('advertiser-search')?.addEventListener('input', (e) => {
        // Could implement client-side filtering here
    });

    // Refresh health status periodically
    setInterval(checkHealth, 30000);
});
