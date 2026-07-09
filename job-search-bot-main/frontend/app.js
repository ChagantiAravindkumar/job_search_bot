// State Management
let appState = {
    dates: [],
    selectedDate: '',
    allJobs: [], // Cache of jobs for the currently selected date
    filters: {
        search: '',
        city: '',
        verifiedOnly: false
    }
};

// API Endpoint Configuration
// Assumes running on the same host/port. Fallback to localhost:8000 for local development
const API_BASE_URL = window.location.origin;

// DOM Elements
const elements = {
    dateList: document.getElementById('date-list'),
    jobGrid: document.getElementById('job-grid'),
    searchInput: document.getElementById('search-input'),
    cityFilter: document.getElementById('city-filter'),
    verifiedFilter: document.getElementById('verified-filter'),
    currentDateDisplay: document.getElementById('current-date-display'),
    statTotal: document.getElementById('stat-total'),
    statVerified: document.getElementById('stat-verified'),
    statVerifiedPct: document.getElementById('stat-verified-pct'),
    statTopCity: document.getElementById('stat-top-city')
};

// Initialize the Application
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    loadDates();
});

// Event Listeners Configuration
function initEventListeners() {
    // Search input instant filtering
    elements.searchInput.addEventListener('input', (e) => {
        appState.filters.search = e.target.value.toLowerCase().trim();
        applyFiltersAndRender();
    });

    // City dropdown change filtering
    elements.cityFilter.addEventListener('change', (e) => {
        appState.filters.city = e.target.value;
        applyFiltersAndRender();
    });

    // Verified Toggle change filtering
    elements.verifiedFilter.addEventListener('change', (e) => {
        appState.filters.verifiedOnly = e.target.checked;
        applyFiltersAndRender();
    });

    // Trigger scraper button listener
    const scanBtn = document.getElementById('scan-now-btn');
    if (scanBtn) {
        scanBtn.addEventListener('click', () => triggerLiveScrape(scanBtn));
    }
}

// Fetch Dates list from Backend
async function loadDates() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/dates`);
        if (!response.ok) throw new Error('Failed to fetch dates');
        
        const dates = await response.ok ? await response.json() : [];
        appState.dates = dates;
        
        renderDateSidebar();
        
        if (dates.length > 0) {
            // Select the latest date by default
            selectDate(dates[0]);
        } else {
            renderEmptyState("No job scrapings found. Run the job_scanner.py script to populate the database!");
            updateStatsUI(0, 0, {});
        }
    } catch (error) {
        console.error('Error loading dates:', error);
        renderErrorState('Could not load scraping history. Is the backend FastAPI server running?');
    }
}

// Render Date items in Sidebar
function renderDateSidebar() {
    elements.dateList.innerHTML = '';
    
    if (appState.dates.length === 0) {
        elements.dateList.innerHTML = '<div class="sidebar-empty">No dates available</div>';
        return;
    }

    appState.dates.forEach(date => {
        // Format date string for readability (e.g., "09-Jun-2026")
        const formattedDate = formatDateString(date);
        
        const dateBtn = document.createElement('div');
        dateBtn.className = `date-item ${date === appState.selectedDate ? 'active' : ''}`;
        dateBtn.innerHTML = `
            <span>${formattedDate}</span>
            <svg class="arrow" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
        `;
        
        dateBtn.addEventListener('click', () => selectDate(date));
        elements.dateList.appendChild(dateBtn);
    });
}

// Handle selecting a specific date
function selectDate(date) {
    appState.selectedDate = date;
    
    // Update active class in sidebar
    const dateElements = elements.dateList.querySelectorAll('.date-item');
    dateElements.forEach((el, index) => {
        if (appState.dates[index] === date) {
            el.classList.add('active');
        } else {
            el.classList.remove('active');
        }
    });

    elements.currentDateDisplay.textContent = formatDateString(date);
    
    // Fetch jobs and stats for this date
    loadJobsForDate(date);
}

// Fetch Jobs and Stats for selected date
async function loadJobsForDate(date) {
    renderLoadingState();
    
    try {
        // Fetch jobs & stats in parallel
        const [jobsRes, statsRes] = await Promise.all([
            fetch(`${API_BASE_URL}/api/jobs?date=${date}`),
            fetch(`${API_BASE_URL}/api/stats?date=${date}`)
        ]);
        
        if (!jobsRes.ok || !statsRes.ok) throw new Error('API fetch failed');
        
        const jobs = await jobsRes.json();
        const stats = await statsRes.json();
        
        appState.allJobs = jobs;
        
        // Update stats
        updateStatsUI(stats.total, stats.verified, stats.by_city);
        
        // Apply current filters and render job list
        applyFiltersAndRender();
        
    } catch (error) {
        console.error('Error loading jobs:', error);
        renderErrorState('Failed to retrieve job listings for the selected date.');
    }
}

// Apply Search and Filters to Cached Job List
function applyFiltersAndRender() {
    let filteredJobs = appState.allJobs;

    // 1. Text Search Filter (Title or Company)
    if (appState.filters.search) {
        filteredJobs = filteredJobs.filter(job => 
            (job.title && job.title.toLowerCase().includes(appState.filters.search)) ||
            (job.company && job.company.toLowerCase().includes(appState.filters.search))
        );
    }

    // 2. City Filter
    if (appState.filters.city) {
        filteredJobs = filteredJobs.filter(job => 
            job.location && job.location.toLowerCase().includes(appState.filters.city.toLowerCase())
        );
    }

    // 3. Verified-Only Filter
    if (appState.filters.verifiedOnly) {
        filteredJobs = filteredJobs.filter(job => 
            job.verification_status && job.verification_status.toLowerCase().startsWith('verified')
        );
    }

    renderJobGrid(filteredJobs);
}

// Render Job Card List
function renderJobGrid(jobs) {
    elements.jobGrid.innerHTML = '';
    
    if (jobs.length === 0) {
        renderEmptyState("No matching jobs found. Try clearing your search filters.");
        return;
    }

    jobs.forEach(job => {
        const cardClass = getCardStatusClass(job.verification_status);
        const badgeHTML = getBadgeHTML(job.verification_status, job.platform);
        
        const jobCard = document.createElement('div');
        jobCard.className = `job-card ${cardClass}`;
        
        // Clean up location display (e.g. "Bengaluru, India" -> "Bengaluru")
        const cityDisplay = job.location ? job.location.split(',')[0].trim() : 'N/A';
        
        jobCard.innerHTML = `
            <div class="card-top">
                <div class="badge-row">
                    ${badgeHTML}
                    <span class="post-date">${job.date_posted || 'Recently'}</span>
                </div>
                <h2 class="job-title">${job.title}</h2>
                <div class="company-name">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="14" x="2" y="7" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
                    <span>${job.company}</span>
                </div>
            </div>
            <div class="card-bottom">
                <div class="job-details">
                    <div class="detail-item">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>
                        <span>${cityDisplay}</span>
                    </div>
                    <div class="detail-item">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/><path d="m9 16 2 2 4-4"/></svg>
                        <span>Deadline: <span style="font-weight: 500; color: ${job.application_deadline && job.application_deadline !== 'N/A' ? '#38bdf8' : 'var(--text-muted)'}">${job.application_deadline || 'N/A'}</span></span>
                    </div>
                </div>
                <a href="${job.job_url}" target="_blank" class="apply-btn">
                    <span>${job.verification_status.startsWith('Verified') ? 'Apply on Career Page' : 'View Job Listing'}</span>
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>
                </a>
            </div>
        `;
        
        elements.jobGrid.appendChild(jobCard);
    });
}

// Update UI Statistics Indicators
function updateStatsUI(total, verified, cityCounts) {
    elements.statTotal.textContent = total;
    elements.statVerified.textContent = verified;
    
    // Success rate percentage
    const pct = total > 0 ? Math.round((verified / total) * 100) : 0;
    elements.statVerifiedPct.textContent = `${pct}% verification rate`;
    
    // Top location calculation
    let topCity = '-';
    let maxJobs = 0;
    
    for (const [city, count] of Object.entries(cityCounts)) {
        if (count > maxJobs) {
            maxJobs = count;
            topCity = `${city} (${count})`;
        }
    }
    
    elements.statTopCity.textContent = topCity;
}

// Get the CSS status class for card border/highlights
function getCardStatusClass(status) {
    if (!status) return 'status-unverified';
    const s = status.toLowerCase();
    
    if (s.includes('ats')) {
        return 'status-verified-ats';
    } else if (s.includes('direct')) {
        return 'status-verified-direct';
    }
    return 'status-unverified';
}

// Get Badge HTML based on Verification Status
function getBadgeHTML(status, platform) {
    if (!status) return `<span class="verified-badge unverified">Unverified</span>`;
    const s = status.toLowerCase();
    
    if (s.includes('ats')) {
        return `
            <span class="verified-badge ats">
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                Verified ATS (${platform})
            </span>
        `;
    } else if (s.includes('direct')) {
        return `
            <span class="verified-badge direct">
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                Verified Company site
            </span>
        `;
    }
    
    return `
        <span class="verified-badge unverified">
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
            Unverified
        </span>
    `;
}

// Render Loaders and Message States
function renderLoadingState() {
    elements.jobGrid.innerHTML = `
        <div class="loading-state">
            <div class="loading-spinner"></div>
            <p>Fetching matching jobs from SQLite...</p>
        </div>
    `;
}

function renderEmptyState(message) {
    elements.jobGrid.innerHTML = `
        <div class="empty-state">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" width="48" height="48"><circle cx="12" cy="12" r="10"/><line x1="8" x2="16" y1="12" y2="12"/></svg>
            <h3>No Jobs Displayed</h3>
            <p>${message}</p>
        </div>
    `;
}

function renderErrorState(message) {
    elements.jobGrid.innerHTML = `
        <div class="error-state">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" width="48" height="48"><polygon points="12 2 22 22 2 22"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/></svg>
            <h3>Database Connection Failed</h3>
            <p>${message}</p>
        </div>
    `;
}

// Utility: Format Date Strings (YYYY-MM-DD -> DD MMM YYYY)
function formatDateString(dateStr) {
    if (!dateStr) return '';
    try {
        const parts = dateStr.split('-');
        if (parts.length !== 3) return dateStr;
        
        const date = new Date(parts[0], parts[1] - 1, parts[2]);
        return date.toLocaleDateString('en-GB', {
            day: '2-digit',
            month: 'short',
            year: 'numeric'
        });
    } catch (e) {
        return dateStr;
    }
}

// Trigger the live scraper via the backend API
async function triggerLiveScrape(btn) {
    if (btn.classList.contains('loading')) return;
    
    btn.classList.add('loading');
    const span = btn.querySelector('span');
    const originalText = span.textContent;
    span.textContent = 'Scanning... (2 min)';
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/scrape`, { method: 'POST' });
        if (!response.ok) throw new Error('Failed to trigger scraper');
        
        const data = await response.json();
        alert("🚀 Scraper started in the background!\nIt will search for fresh listings and update the database.\n\nPlease wait about 2 minutes, then refresh this page to see the new jobs.");
        
        // Restore button state after 2 minutes (120000 ms)
        setTimeout(() => {
            btn.classList.remove('loading');
            span.textContent = originalText;
            loadDates(); // Reload dates sidebar to fetch newly added days
        }, 120000);
        
    } catch (error) {
        console.error('Error triggering scrape:', error);
        alert('❌ Failed to trigger scraper. Please make sure the local FastAPI server is running.');
        btn.classList.remove('loading');
        span.textContent = originalText;
    }
}
