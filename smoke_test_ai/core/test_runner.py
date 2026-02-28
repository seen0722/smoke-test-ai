from dataclasses import dataclass
from enum import Enum


class TestStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class TestResult:
    id: str
    name: str
    status: TestStatus
    message: str = ""
    duration: float = 0.0
    screenshot_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == TestStatus.PASS

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "duration": self.duration,
            "screenshot_path": self.screenshot_path,
        }
