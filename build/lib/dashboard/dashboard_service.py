# File: src/dashboard/dashboard_service.py
"""
FastAPI-based dashboard service. Exposes REST endpoints and an SSE stream.
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio
import json
from typing import Dict, Any, AsyncGenerator
from pathlib import Path
import time

from .data_collector import DataCollector


class DashboardService:
    """Main dashboard service using FastAPI."""

    def __init__(self, config: Dict[str, Any], logger: Any):
        self.config = config
        self.logger = logger
        self.data_collector = DataCollector(config, logger)

        # Initialize FastAPI app
        self.app = FastAPI(title="MQI System Dashboard")
        self.setup_static_and_templates()
        self.setup_routes()

        # Start the health monitor's background data collection
        self.data_collector.health_monitor.start_monitoring()

    def setup_static_and_templates(self):
        dashboard_dir = Path(__file__).parent
        static_dir = dashboard_dir / "static"
        templates_dir = dashboard_dir / "templates"

        # Ensure paths exist (they may not in dev stub environment)
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        else:
            self.logger.warning("Static directory not found: %s", static_dir)

        if templates_dir.exists():
            self.templates = Jinja2Templates(directory=str(templates_dir))
        else:
            self.templates = None
            self.logger.warning("Templates directory not found: %s", templates_dir)

    def setup_routes(self):
        """Setup all API routes."""

        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard_page(request: Request):
            if self.templates:
                return self.templates.TemplateResponse(
                    "index.html",
                    {"request": request, "cache_bust": int(time.time())}
                )
            # If templates are unavailable, return a minimal page
            return HTMLResponse("<html><body><h1>MQI System Dashboard</h1><p>Templates not found.</p></body></html>")

        @self.app.get("/api/status")
        async def get_status():
            return await self.data_collector.get_system_status()

        @self.app.get("/api/jobs")
        async def get_jobs():
            return await self.data_collector.get_active_jobs()

        @self.app.get("/api/gpu")
        async def get_gpu():
            return await self.data_collector.get_gpu_metrics()

        @self.app.get("/api/workers")
        async def get_workers():
            return await self.data_collector.get_worker_status()

        @self.app.get("/api/health")
        async def get_health():
            return await self.data_collector.get_system_health()

        @self.app.get("/api/activity")
        async def get_activity():
            return await self.data_collector.get_recent_activity()

        @self.app.get("/events")
        async def event_stream():
            return StreamingResponse(
                self.generate_events(),
                media_type="text/event-stream"
            )

    async def generate_events(self) -> AsyncGenerator[str, None]:
        """Generate Server-Sent Events for real-time updates."""
        refresh = int(self.config.get('dashboard', {}).get('refresh_interval_sec', 5))
        while True:
            try:
                # Collect all dashboard data concurrently using asyncio.gather
                status_task = self.data_collector.get_system_status()
                jobs_task = self.data_collector.get_active_jobs()
                gpu_task = self.data_collector.get_gpu_metrics()
                workers_task = self.data_collector.get_worker_status()
                health_task = self.data_collector.get_system_health()
                activity_task = self.data_collector.get_recent_activity(10)

                status, jobs, gpu, workers, health, activity = await asyncio.gather(
                    status_task, jobs_task, gpu_task, workers_task, health_task, activity_task,
                    return_exceptions=True
                )

                # Handle any exceptions that occurred during gathering
                data = {}
                data['status'] = status if not isinstance(status, Exception) else {'error': str(status)}
                data['jobs'] = jobs if not isinstance(jobs, Exception) else []
                data['gpu'] = gpu if not isinstance(gpu, Exception) else []
                data['workers'] = workers if not isinstance(workers, Exception) else []
                data['health'] = health if not isinstance(health, Exception) else {}
                data['activity'] = activity if not isinstance(activity, Exception) else []

                yield f"data: {json.dumps(data)}\n\n"

            except Exception as e:
                self.logger.error(f"Error generating event: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

            await asyncio.sleep(refresh)