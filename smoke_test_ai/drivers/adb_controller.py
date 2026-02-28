import subprocess
import time
from pathlib import Path
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class AdbController:
    def __init__(self, serial: str | None = None, adb_path: str = "adb"):
        self.serial = serial
        self.adb_path = adb_path

    def _build_cmd(self, *args: str) -> list[str]:
        cmd = [self.adb_path]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(args)
        return cmd

    def _run(self, *args: str, timeout: int = 30, **kwargs) -> subprocess.CompletedProcess:
        cmd = self._build_cmd(*args)
        logger.debug(f"ADB: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)

    def shell(self, command: str, timeout: int = 30) -> subprocess.CompletedProcess:
        return self._run("shell", command, timeout=timeout)

    def getprop(self, prop: str) -> str:
        result = self.shell(f"getprop {prop}")
        return result.stdout.strip()

    def is_connected(self) -> bool:
        result = self._run("devices")
        if self.serial:
            return f"{self.serial}\tdevice" in result.stdout
        lines = result.stdout.strip().split("\n")
        return any("\tdevice" in line for line in lines[1:])

    def wait_for_device(self, timeout: int = 60) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_connected():
                logger.info(f"Device {self.serial or 'any'} connected")
                return True
            time.sleep(2)
        logger.warning(f"Timeout waiting for device {self.serial or 'any'}")
        return False

    def screencap(self, output_path: Path) -> None:
        self._run("exec-out", "screencap", "-p", timeout=10)

    def install(self, apk_path: str) -> subprocess.CompletedProcess:
        return self._run("install", "-r", apk_path, timeout=120)

    def connect_wifi(self, ssid: str, password: str) -> subprocess.CompletedProcess:
        return self.shell(f'cmd wifi connect-network "{ssid}" wpa2 "{password}"', timeout=30)

    def get_user_state(self) -> str:
        """Get user storage state: RUNNING_UNLOCKED, RUNNING_LOCKED, etc."""
        result = self.shell("dumpsys user | grep 'State:'")
        for line in result.stdout.strip().splitlines():
            if "State:" in line:
                return line.split("State:")[1].strip()
        return "UNKNOWN"

    def unlock_keyguard(self, pin: str | None = None) -> bool:
        """Unlock the keyguard/lockscreen. Returns True if unlocked."""
        self.shell("input keyevent KEYCODE_WAKEUP")
        time.sleep(1)
        # Swipe up to dismiss lockscreen / show PIN entry
        self.shell("input swipe 540 1800 540 600")
        time.sleep(1)
        if pin:
            self.shell(f"input text {pin}")
            time.sleep(0.5)
            self.shell("input keyevent KEYCODE_ENTER")
            time.sleep(2)
        # Verify unlock
        state = self.get_user_state()
        return state == "RUNNING_UNLOCKED"

    def reboot(self, mode: str = "") -> subprocess.CompletedProcess:
        if mode:
            return self._run("reboot", mode)
        return self._run("reboot")
