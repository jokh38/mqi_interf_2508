import pytest
import yaml
import os
from common.config_loader import load_config, validate_config
from common.exceptions import ConfigurationError

@pytest.fixture
def valid_config_data():
    """Provides a valid config dictionary."""
    return {
        'database': {'path': '/tmp/test.db'},
        'rabbitmq': {'url': 'amqp://guest:guest@localhost:5672/'},
        'logging': {'level': 'INFO'}
    }

@pytest.fixture
def temp_config_file(tmp_path, valid_config_data):
    """Creates a temporary YAML config file for testing."""
    config_file = tmp_path / "config.yaml"
    with open(config_file, 'w') as f:
        yaml.dump(valid_config_data, f)
    return str(config_file)

@pytest.fixture
def invalid_yaml_file(tmp_path):
    """Creates a temporary invalid YAML file."""
    invalid_content = "database: { path: /tmp/test.db\nrabbitmq: url: 'amqp://guest:guest@localhost:5672/'"
    config_file = tmp_path / "invalid_config.yaml"
    with open(config_file, 'w') as f:
        f.write(invalid_content)
    return str(config_file)

@pytest.fixture
def empty_config_file(tmp_path):
    """Creates an empty temporary file."""
    config_file = tmp_path / "empty.yaml"
    config_file.touch()
    return str(config_file)

def test_load_config_success(temp_config_file, valid_config_data):
    """Tests that a valid YAML config file is loaded correctly."""
    config = load_config(temp_config_file)
    assert config == valid_config_data

def test_load_config_file_not_found():
    """Tests that a ConfigurationError is raised for a non-existent file."""
    with pytest.raises(ConfigurationError, match="Configuration file not found"):
        load_config("non_existent_file.yaml")

def test_load_config_invalid_yaml(invalid_yaml_file):
    """Tests that a ConfigurationError is raised for a malformed YAML file."""
    with pytest.raises(ConfigurationError, match="Invalid YAML in configuration file"):
        load_config(invalid_yaml_file)

def test_load_config_empty_file_raises_error(empty_config_file):
    """Tests that a ConfigurationError is raised for an empty config file."""
    with pytest.raises(ConfigurationError, match="Configuration file is empty"):
        load_config(empty_config_file)

def test_validate_config_success(valid_config_data):
    """Tests that a valid config passes validation."""
    try:
        validate_config(valid_config_data)
    except ConfigurationError:
        pytest.fail("validate_config raised ConfigurationError unexpectedly!")

def test_validate_config_missing_section():
    """Tests that a ConfigurationError is raised if a required section is missing."""
    invalid_config = {
        'rabbitmq': {'url': 'amqp://guest:guest@localhost:5672/'}
    }
    with pytest.raises(ConfigurationError, match="Missing required configuration section: database"):
        validate_config(invalid_config)

def test_validate_config_missing_key_in_section():
    """Tests that a ConfigurationError is raised if a required key is missing from a section."""
    invalid_config = {
        'database': {'path': '/tmp/test.db'},
        'rabbitmq': {} # Missing 'url'
    }
    with pytest.raises(ConfigurationError, match="Missing required rabbitmq configuration: url"):
        validate_config(invalid_config)
