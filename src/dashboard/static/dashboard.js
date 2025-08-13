class Dashboard {
    constructor() {
        this.logElement = document.getElementById('debug-log');
        this.log('Dashboard initializing...');
        this.init();
    }

    log(message) {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.textContent = `[${timestamp}] ${message}`;
        this.logElement.appendChild(logEntry);
        this.logElement.scrollTop = this.logElement.scrollHeight; // Auto-scroll
        console.log(message); // Also log to console for good measure
    }

    init() {
        this.setupEventSource();
        this.loadInitialData();
    }
    setupEventSource() {
        this.log("Setting up EventSource for /events...");
        this.eventSource = new EventSource('/events');

        this.eventSource.onopen = () => {
            this.log("EventSource connection established.");
        };

        this.eventSource.onmessage = e => {
            this.log(`Received event: ${e.data}`);
            try {
                const data = JSON.parse(e.data);
                this.log("Successfully parsed event data.");
                this.updateDashboard(data);
            } catch (error) {
                this.log(`Error parsing event data: ${error}`);
            }
        };

        this.eventSource.onerror = (err) => {
            this.log("EventSource error. Closing connection.");
            console.error("EventSource failed:", err);
            this.eventSource.close();
        };
    }
    async loadInitialData() {
        this.log("Loading initial data from all endpoints...");
        try {
            const endpoints = ['status', 'jobs', 'gpu', 'workers', 'health', 'activity'];
            const requests = endpoints.map(endpoint => {
                this.log(`Fetching /api/${endpoint}...`);
                return fetch(`/api/${endpoint}`)
                    .then(response => {
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        this.log(`Successfully fetched /api/${endpoint}.`);
                        return response.json();
                    })
                    .catch(error => {
                        this.log(`Failed to fetch /api/${endpoint}: ${error}`);
                        return { error: `Failed to load: ${error.message}` };
                    });
            });

            const [status, jobs, gpu, workers, health, activity] = await Promise.all(requests);
            
            this.log("All initial data fetched. Updating dashboard.");
            this.updateDashboard({ status, jobs, gpu, workers, health, activity });

        } catch (error) {
            this.log(`An error occurred during initial data load: ${error}`);
        }
    }

    updateDashboard(data) {
        this.log("Updating dashboard content.");
        this.updatePanel('overall-status', data.status ? data.status.overall : 'Error');
        this.renderJobs(data.jobs);
        this.renderGpu(data.gpu);
        this.renderWorkers(data.workers);
        this.renderHealth(data.health);
        this.renderActivity(data.activity);
        this.log("Dashboard update complete.");
    }

    renderGpu(gpus) {
        const element = document.getElementById('gpu-content');
        if (!element) return;
        element.classList.remove('loading');
        element.innerHTML = '';

        if (!gpus || gpus.length === 0) {
            element.textContent = 'No GPU data available.';
            return;
        }

        const table = document.createElement('table');
        table.className = 'data-table';
        table.innerHTML = `
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Util. (%)</th>
                    <th>Mem. (MiB)</th>
                </tr>
            </thead>
            <tbody>
                ${gpus.map(gpu => `
                    <tr>
                        <td>${gpu.id}</td>
                        <td>${gpu.name}</td>
                        <td>${gpu.utilization_gpu}</td>
                        <td>${gpu.memory_used} / ${gpu.memory_total}</td>
                    </tr>
                `).join('')}
            </tbody>
        `;
        element.appendChild(table);
    }

    renderHealth(health) {
        const element = document.getElementById('health-content');
        if (!element) return;
        element.classList.remove('loading');
        element.innerHTML = '';

        if (!health || Object.keys(health).length === 0) {
            element.textContent = 'No health data available.';
            return;
        }
        
        const list = document.createElement('ul');
        list.className = 'health-list';
        list.innerHTML = `
            <li><strong>CPU:</strong> ${health.cpu_percent}%</li>
            <li><strong>Memory:</strong> ${health.memory_percent}%</li>
            <li><strong>Disk:</strong> ${health.disk_percent}%</li>
            <li><strong>Load:</strong> ${health.load_average ? health.load_average.join(', ') : 'N/A'}</li>
            <li><strong>Processes:</strong> ${health.process_count}</li>
        `;
        element.appendChild(list);
    }

    renderJobs(jobs) {
        const element = document.getElementById('jobs-content');
        if (!element) return;
        element.classList.remove('loading');
        
        if (!jobs || jobs.length === 0) {
            element.textContent = 'No active jobs.';
            return;
        }
        element.textContent = JSON.stringify(jobs, null, 2);
    }

    renderActivity(activity) {
        const element = document.getElementById('activity-content');
        if (!element) return;
        element.classList.remove('loading');

        if (!activity || activity.length === 0) {
            element.textContent = 'No recent activity.';
            return;
        }
        element.textContent = JSON.stringify(activity, null, 2);
    }

    renderWorkers(workers) {
        const element = document.getElementById('workers-content');
        if (!element) {
            this.log(`Element with ID 'workers-content' not found.`);
            return;
        }
        element.classList.remove('loading');
        element.innerHTML = ''; // Clear previous content

        if (!workers || workers.length === 0) {
            element.textContent = 'No worker data received.';
            return;
        }

        const table = document.createElement('table');
        table.className = 'worker-table';
        const thead = document.createElement('thead');
        thead.innerHTML = `
            <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Health</th>
            </tr>
        `;
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        workers.forEach(worker => {
            const row = document.createElement('tr');
            const statusClass = worker.status === 'running' ? 'status-healthy' : 'status-error';
            const healthClass = worker.health === 'ok' ? 'status-healthy' : 'status-error';

            row.innerHTML = `
                <td>${worker.name}</td>
                <td class="${statusClass}">${worker.status}</td>
                <td class="${healthClass}">${worker.health}</td>
            `;
            tbody.appendChild(row);
        });
        table.appendChild(tbody);
        element.appendChild(table);
    }

    updatePanel(elementId, content) {
        const element = document.getElementById(elementId);
        if (!element) {
            this.log(`Element with ID '${elementId}' not found.`);
            return;
        }
        
        element.classList.remove('loading');

        if (typeof content === 'object' && content !== null) {
            if (content.error) {
                element.textContent = content.error;
                element.classList.add('error-state');
            } else {
                element.textContent = JSON.stringify(content, null, 2);
            }
        } else if (content !== undefined) {
            element.textContent = content;
        } else {
            element.textContent = 'No data received.';
        }
    }
}
document.addEventListener('DOMContentLoaded', () => new Dashboard());