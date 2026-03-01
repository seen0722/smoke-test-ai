from abc import ABC, abstractmethod
from dataclasses import dataclass

from smoke_test_ai.core.test_runner import TestResult
from smoke_test_ai.drivers.adb_controller import AdbController


@dataclass
class PluginContext:
    adb: AdbController
    settings: dict
    device_capabilities: dict
    snippet: object | None = None
    peer_snippet: object | None = None
    visual_analyzer: object | None = None


class TestPlugin(ABC):
    @abstractmethod
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        """Execute a functional test, return result."""
