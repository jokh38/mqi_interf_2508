"""
Configuration loader for MQI Communicator system.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from .exceptions import ConfigurationError
from .logger import get_logger


def get_project_root() -> Path:
    """
    Get the project root directory dynamically.

    Returns:
        Path to the project root directory
    """
    return Path(__file__).resolve().parent.parent.parent


def load_config(config_path: Optional[str] = None, db_manager=None) -> Dict[str, Any]:
    """
    Load and validate YAML configuration file.

    Priority order:
    1. Provided config_path parameter
    2. MQI_CONFIG_PATH environment variable
    3. Default fallback to config/config.default.yaml

    Args:
        config_path: Path to the configuration file (optional)
        db_manager: Database manager instance for logging (optional)

    Returns:
        Configuration dictionary

    Raises:
        ConfigurationError: If configuration is invalid or missing
    """
    # Initialize logger with database manager
    logger = get_logger(__name__, db_manager)

    if config_path is None:
        # Priority: check MQI_CONFIG_PATH environment variable first
        env_config_path = os.environ.get('MQI_CONFIG_PATH')
        if env_config_path:
            config_path = env_config_path
        else:
            # Fallback to default configuration path string
            config_path = 'config/config.default.yaml'

    project_root = get_project_root()
    config_path_obj = Path(config_path)
    if not config_path_obj.is_absolute():
        config_path_obj = project_root / config_path_obj

    logger.info(f"Attempting to load configuration from: {config_path_obj.resolve()}")

    if not config_path_obj.is_file():
        logger.error(f"Configuration file not found at: {config_path_obj.resolve()}")
        raise ConfigurationError(f"Configuration file not found: {config_path_obj.resolve()}")

    try:
        with open(config_path_obj, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)

        if config is None:
            raise ConfigurationError(f"Configuration file is empty: {config_path}")

        validate_config(config)
        return config

    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML in configuration file: {e}")
    except Exception as e:
        raise ConfigurationError(f"Error loading configuration: {e}")


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate configuration structure for all required sections and components.

    This unified validation ensures all system components have the configuration
    they need to operate properly.

    Args:
        config: Configuration dictionary to validate

    Raises:
        ConfigurationError: If configuration is invalid or missing
    """
    # Validate core required sections
    required_core_sections = ['database', 'rabbitmq']
    for section in required_core_sections:
        if section not in config:
            raise ConfigurationError(f"Missing required configuration section: {section}")

    # Validate database configuration
    database_config = config['database']
    required_db_keys = ['path']
    for key in required_db_keys:
        if key not in database_config:
            raise ConfigurationError(f"Missing required database configuration: {key}")

    # Validate RabbitMQ configuration
    rabbitmq_config = config['rabbitmq']
    required_rabbitmq_keys = ['url']
    for key in required_rabbitmq_keys:
        if key not in rabbitmq_config:
            raise ConfigurationError(f"Missing required rabbitmq configuration: {key}")

    # Validate queue mappings (if present)
    if 'queue_mappings' in config:
        queue_mappings = config['queue_mappings']
        if not isinstance(queue_mappings, dict):
            raise ConfigurationError("Queue mappings configuration must be a dictionary")

    # Validate scanner configuration (if present)
    if 'scanner' in config:
        scanner_config = config['scanner']
        required_scanner_keys = ['target_directory', 'scan_interval_sec']
        for key in required_scanner_keys:
            if key not in scanner_config:
                raise ConfigurationError(f"Missing required scanner configuration: {key}")

    # Validate SFTP configuration (if present)
    if 'sftp' in config:
        sftp_config = config['sftp']
        required_sftp_keys = ['host', 'port', 'username', 'private_key_path']
        for key in required_sftp_keys:
            if key not in sftp_config:
                raise ConfigurationError(f"Missing required sftp configuration: {key}")

    # Validate SSH configuration (if present)
    if 'ssh' in config:
        ssh_config = config['ssh']
        required_ssh_keys = ['host', 'port', 'username', 'private_key_path']
        for key in required_ssh_keys:
            if key not in ssh_config:
                raise ConfigurationError(f"Missing required ssh configuration: {key}")

    # Validate curator configuration (if present)
    if 'curator' in config:
        curator_config = config['curator']
        required_curator_keys = ['monitor_interval_sec', 'gpu_monitor_command']
        for key in required_curator_keys:
            if key not in curator_config:
                raise ConfigurationError(f"Missing required curator configuration: {key}")

    # Validate archiver configuration (if present)
    if 'archiver' in config:
        archiver_config = config['archiver']
        required_archiver_keys = ['schedule_interval_sec', 'archive_directory']
        for key in required_archiver_keys:
            if key not in archiver_config:
                raise ConfigurationError(f"Missing required archiver configuration: {key}")

    # Validate workflow definitions (if present)
    if 'workflows' in config:
        workflows = config['workflows']
        if not isinstance(workflows, dict):
            raise ConfigurationError("Workflows configuration must be a dictionary")
        for workflow_name, steps in workflows.items():
            if not isinstance(steps, list):
                raise ConfigurationError(f"Workflow '{workflow_name}' must be a list of steps")
            if not steps:
                raise ConfigurationError(f"Workflow '{workflow_name}' cannot be empty")

    # Validate logging configuration (if present)
    if 'logging' in config:
        logging_config = config['logging']
        if not isinstance(logging_config, dict):
            raise ConfigurationError("Logging configuration must be a dictionary")

    # Validate dashboard configuration (if present)
    if 'dashboard' in config:
        dashboard_config = config['dashboard']
        if not isinstance(dashboard_config, dict):
            raise ConfigurationError("Dashboard configuration must be a dictionary")