from abc import ABC, abstractmethod
import numpy as np

class ScreenCapture(ABC):
    @abstractmethod
    def capture(self) -> np.ndarray | None:
        ...
    def open(self) -> None:
        pass
    def close(self) -> None:
        pass
    def __enter__(self):
        self.open()
        return self
    def __exit__(self, *args):
        self.close()
