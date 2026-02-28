import subprocess
from smoke_test_ai.drivers.flash.base import FlashDriver
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

class CustomFlashDriver(FlashDriver):
    def flash(self, config: dict) -> None:
        for cmd_str in config.get("commands", []):
            logger.info(f"Custom flash: {cmd_str}")
            result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                raise RuntimeError(f"Custom flash failed: {cmd_str}\n{result.stderr}")
