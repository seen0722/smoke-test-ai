from abc import ABC, abstractmethod

class FlashDriver(ABC):
    @abstractmethod
    def flash(self, config: dict) -> None:
        ...
