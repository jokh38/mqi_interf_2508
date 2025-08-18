"""
Entry point for running the dashboard service with uvicorn.
"""
import sys
import uvicorn

from src.common.config_loader import load_config, ConfigurationError
from src.common.db_utils import DatabaseManager
from src.common.logger import get_logger
from .dashboard_service import DashboardService


def main(config_path: str):
    """Main entry point for dashboard service."""
    logger = None
    try:
        # Load configuration from the provided path
        config = load_config(config_path)

        # Initialize database manager for centralized logging
        db_path = config.get('database', {}).get('path')
        if not db_path:
            raise ConfigurationError("Database path not found in configuration.")
        db_manager = DatabaseManager(db_path)

        # Initialize a DB-aware logger
        logger = get_logger('dashboard', db_manager=db_manager)

        # Get dashboard configuration
        dashboard_config = config.get('dashboard')
        if not dashboard_config:
            raise ConfigurationError("Dashboard configuration not found.")

        host = dashboard_config.get('host', '127.0.0.1')
        port = int(dashboard_config.get('port', 8080))

        logger.info(f"Dashboard available at http://{host}:{port}")

        # Create dashboard service, now passing the full config and logger
        dashboard = DashboardService(config, logger)

        # Run the server using uvicorn
        uvicorn.run(
            dashboard.app,
            host=host,
            port=port,
            log_level=dashboard_config.get('log_level', 'info').lower(),
            access_log=False  # Disable uvicorn access log in favor of our logger
        )

    except ConfigurationError as e:
        if logger:
            logger.error(f"Configuration error: {e}")
        else:
            print(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        if logger:
            logger.info("Dashboard terminated by user")
        else:
            print("Dashboard terminated by user")
    except Exception as e:
        if logger:
            logger.error(f"Unexpected error in dashboard: {e}", exc_info=True)
        else:
            print(f"Unexpected error in dashboard: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.dashboard.main <config_path>")
        sys.exit(1)
    main(sys.argv[1])
