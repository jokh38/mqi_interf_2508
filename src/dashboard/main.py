# File: src/dashboard/main.py
"""
Entry point for running the dashboard service with uvicorn.
"""
import uvicorn
import logging
from pathlib import Path
from typing import Dict, Any

# Import the config loader with proper error handling
try:
    from src.common.config_loader import load_config
    from src.common.db_utils import DatabaseManager
    from src.common.logger import get_logger
except ImportError as e:
    logging.error(f"Failed to import config_loader: {e}")
    def load_config(config_path: str = None) -> Dict[str, Any]:
        """Fallback configuration if config_loader is not available."""
        logging.warning("Using fallback configuration for dashboard")
        return {
            'database': {'path': 'data/mqi_communicator.db'},
            'dashboard': {
                'host': '127.0.0.1', 
                'port': 8080, 
                'log_level': 'info', 
                'refresh_interval_sec': 5
            }
        }

from .dashboard_service import DashboardService


def main():
    """Main entry point for dashboard service."""
    # Load configuration
    import os
    from src.common.config_loader import get_project_root
    
    config_path = os.environ.get('MQI_CONFIG_PATH')
    if config_path and not os.path.isabs(config_path):
        # Make relative paths absolute from project root
        project_root = get_project_root()
        config_path = str(project_root / config_path)
    config = load_config(config_path)
    
    # Initialize database manager before logger for centralized logging
    try:
        db_manager = DatabaseManager(config.get('database', {}).get('path', 'data/mqi_system_dev.db'))
        logger = get_logger(__name__, db_manager=db_manager)
    except Exception as e:
        # Fallback to basic logging if database manager fails
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to initialize database logger, using fallback: {e}")

    # Setup basic logging as fallback
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Get dashboard configuration
    dashboard_config = config.get('dashboard', {
        'host': '127.0.0.1',
        'port': 8080,
        'log_level': 'info',
        'auto_open_browser': False
    })

    host = dashboard_config.get('host', '127.0.0.1')
    port = int(dashboard_config.get('port', 8080))
    
    # Auto-open browser if configured
    if dashboard_config.get('auto_open_browser', False):
        import threading
        import webbrowser
        import time
        
        def open_browser():
            time.sleep(1.5)  # Wait for server to start
            webbrowser.open(f"http://{host}:{port}")
        
        threading.Thread(target=open_browser, daemon=True).start()
        logger.info(f"Dashboard will open automatically in browser at http://{host}:{port}")
    else:
        logger.info(f"Dashboard available at http://{host}:{port}")

    # Create dashboard service
    dashboard = DashboardService(config)

    # Run the server
    uvicorn.run(
        dashboard.app,
        host=host,
        port=port,
        log_level=dashboard_config.get('log_level', 'info'),
        access_log=True
    )


if __name__ == "__main__":
    main()
