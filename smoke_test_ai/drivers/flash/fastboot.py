import subprocess
from smoke_test_ai.drivers.flash.base import FlashDriver
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

class FastbootFlashDriver(FlashDriver):
    def __init__(self, serial: str | None = None, fastboot_path: str = "fastboot"):
        self.serial = serial
        self.fastboot_path = fastboot_path

    def _run(self, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
        cmd = [self.fastboot_path]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(args)
        logger.info(f"Fastboot: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def flash(self, config: dict) -> None:
        for pre_cmd in config.get("pre_flash", []):
            logger.info(f"Pre-flash: {pre_cmd}")
            subprocess.run(pre_cmd.split(), capture_output=True, text=True, timeout=60)
        for image in config.get("images", []):
            partition = image["partition"]
            file_path = image["file"]
            logger.info(f"Flashing {partition}: {file_path}")
            result = self._run("flash", partition, file_path)
            if result.returncode != 0:
                raise RuntimeError(f"Flash failed for {partition}: {result.stderr}")
        for post_cmd in config.get("post_flash", []):
            logger.info(f"Post-flash: {post_cmd}")
            subprocess.run(post_cmd.split(), capture_output=True, text=True, timeout=60)
