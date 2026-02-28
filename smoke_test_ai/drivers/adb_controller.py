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

    def enable_wifi(self, timeout: int = 15) -> bool:
        """Enable WiFi and wait until it's ready. Returns True if enabled."""
        result = self.shell("dumpsys wifi | grep 'Wi-Fi is'")
        if "enabled" in result.stdout:
            logger.info("WiFi is already enabled")
            return True
        logger.info("Enabling WiFi...")
        self.shell("svc wifi enable")
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2)
            result = self.shell("dumpsys wifi | grep 'Wi-Fi is'")
            if "enabled" in result.stdout:
                logger.info("WiFi enabled successfully")
                return True
        logger.warning("Timeout waiting for WiFi to enable")
        return False

    def connect_wifi(self, ssid: str, password: str, security: str = "wpa2", retries: int = 3) -> bool:
        """Enable WiFi, connect to network, and verify connection. Returns True if connected."""
        # Ensure WiFi is enabled first (critical after factory reset)
        if not self.enable_wifi():
            logger.error("Cannot connect WiFi: failed to enable WiFi adapter")
            return False

        for attempt in range(1, retries + 1):
            logger.info(f"Connecting to WiFi '{ssid}' (attempt {attempt}/{retries})...")
            if password:
                self.shell(f'cmd wifi connect-network "{ssid}" {security} "{password}"', timeout=30)
            else:
                self.shell(f'cmd wifi connect-network "{ssid}" open', timeout=30)
            # Wait for connection
            time.sleep(5)
            if self.is_wifi_connected():
                logger.info(f"WiFi connected to '{ssid}'")
                return True
            logger.warning(f"WiFi not connected after attempt {attempt}")
        logger.error(f"Failed to connect to WiFi '{ssid}' after {retries} attempts")
        return False

    def is_wifi_connected(self) -> bool:
        """Check if WiFi is connected with an IP address."""
        result = self.shell("dumpsys wifi | grep 'Wi-Fi is'")
        if "enabled" not in result.stdout:
            return False
        result = self.shell("ip route show table 0 | grep -m1 'wlan0'")
        return "wlan0" in result.stdout

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

    def factory_reset(self) -> None:
        """Factory reset the device. Device will reboot and all data will be erased."""
        logger.warning("Initiating factory reset...")
        self.shell(
            'am broadcast -a android.intent.action.FACTORY_RESET '
            '-p android --receiver-foreground',
            timeout=30,
        )

    def wait_for_boot(self, timeout: int = 180) -> bool:
        """Wait for device to fully boot (sys.boot_completed=1)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_connected():
                boot = self.getprop("sys.boot_completed")
                if boot == "1":
                    logger.info("Device boot completed")
                    return True
            time.sleep(3)
        logger.warning("Timeout waiting for boot completion")
        return False

    def reboot(self, mode: str = "") -> subprocess.CompletedProcess:
        if mode:
            return self._run("reboot", mode)
        return self._run("reboot")
