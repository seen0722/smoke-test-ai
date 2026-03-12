import os
import re
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

        # Script mode: parse vendor script and execute with system fastboot
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
        """Parse vendor flash script and execute each fastboot command
        using the system fastboot binary (cross-platform compatible)."""
        if not os.path.isfile(script):
            raise FileNotFoundError(f"Flash script not found: {script}")

        script_dir = os.path.dirname(os.path.abspath(script))
        commands = self._parse_script(script)

        logger.info(f"Parsed {len(commands)} fastboot commands from: {script}")
        for i, cmd_args in enumerate(commands, 1):
            # Resolve image paths relative to script directory
            resolved = []
            for arg in cmd_args:
                if arg.startswith("${image_dir}"):
                    resolved.append(os.path.join(script_dir, arg.replace("${image_dir}", "")))
                elif not arg.startswith("-") and os.path.isfile(os.path.join(script_dir, arg)):
                    resolved.append(os.path.join(script_dir, arg))
                else:
                    resolved.append(arg)

            logger.info(f"  [{i}/{len(commands)}] fastboot {' '.join(resolved)}")
            result = self._run(*resolved)
            if result.returncode != 0:
                raise RuntimeError(
                    f"Flash command failed [{i}/{len(commands)}]: "
                    f"fastboot {' '.join(resolved)}\n{result.stderr}"
                )

        logger.info("Flash script execution complete")

    @staticmethod
    def _parse_script(script_path: str) -> list[list[str]]:
        """Parse a vendor fastboot.bash script into a list of fastboot
        command argument lists, skipping comments and non-fastboot lines."""
        commands = []
        # Match lines like: $fastboot_tool flash boot_a ${image_dir}boot.img
        # or: sudo ./fastboot flash boot_a boot.img
        fastboot_re = re.compile(
            r'^\s*(?:\$fastboot_tool|(?:sudo\s+)?\.?/?fastboot)\s+(.+)$'
        )
        with open(script_path) as f:
            for line in f:
                stripped = line.strip()
                # Skip empty, comments, and commented-out lines
                if not stripped or stripped.startswith("#"):
                    continue
                m = fastboot_re.match(stripped)
                if m:
                    args_str = m.group(1).strip()
                    # Remove trailing comments
                    args_str = args_str.split("#")[0].strip()
                    if args_str:
                        commands.append(args_str.split())
        return commands
