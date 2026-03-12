import os
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
        # Pre-flash commands (e.g., OEM unlock)
        for pre_cmd in config.get("pre_flash", []):
            logger.info(f"Pre-flash: {pre_cmd}")
            result = self._run(*pre_cmd.split()[1:]) if pre_cmd.startswith("fastboot ") else \
                subprocess.run(pre_cmd.split(), capture_output=True, text=True, timeout=60)
            if hasattr(result, 'returncode') and result.returncode != 0:
                logger.warning(f"Pre-flash command returned {result.returncode}: {getattr(result, 'stderr', '')}")

        # Script mode: run vendor flash script directly
        script = config.get("script")
        if script:
            self._run_script(script, config)
            return

        # Partition-by-partition mode
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

    def _run_script(self, script: str, config: dict) -> None:
        if not os.path.isfile(script):
            raise FileNotFoundError(f"Flash script not found: {script}")

        script_dir = os.path.dirname(os.path.abspath(script))
        timeout = config.get("script_timeout", 600)

        logger.info(f"Running flash script: {script} (timeout={timeout}s)")
        env = os.environ.copy()
        if self.serial:
            env["ANDROID_SERIAL"] = self.serial

        result = subprocess.run(
            ["bash", script],
            cwd=script_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n")[-10:]:
                logger.info(f"  {line}")
        if result.returncode != 0:
            raise RuntimeError(
                f"Flash script failed (exit {result.returncode}):\n{result.stderr[-500:]}"
            )
