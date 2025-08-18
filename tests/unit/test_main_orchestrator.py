import pytest
from main_orchestrator import MainOrchestrator

def test_orchestrator_instantiation(monkeypatch):
    """
    Smoke test to ensure MainOrchestrator can be instantiated.
    Mocks all external dependencies.
    """
    # Mock all dependencies initialized in MainOrchestrator.__init__
    monkeypatch.setattr("main_orchestrator.load_config", lambda x: {"database": {"path": "dummy.db"}, "rabbitmq": {"url": "dummy_url"}})
    monkeypatch.setattr("main_orchestrator.DatabaseManager", lambda x: None)

    # The get_logger mock needs to return an object with an info method
    class MockLogger:
        def info(self, msg):
            pass
        def warning(self, msg):
            pass
        def error(self, msg, exc_info=False):
            pass
    monkeypatch.setattr("main_orchestrator.get_logger", lambda x: MockLogger())
    monkeypatch.setattr("main_orchestrator.setup_logging", lambda level, db_manager: None)

    # Mock signal handling
    monkeypatch.setattr("signal.signal", lambda signum, handler: None)

    # We can now instantiate the orchestrator
    orchestrator = MainOrchestrator(config_file="dummy_config.yaml")

    assert orchestrator is not None
    assert orchestrator.config_file == "dummy_config.yaml"
    assert orchestrator.running is False
