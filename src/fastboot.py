#  Python version of the KyDevTool flashing utility
#  Copyright (C) 2026 chkndrp
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

import json
import shutil
import subprocess
import tarfile
import tempfile
import time
import zipfile

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

FASTBOOT_BIN = "fastboot"


def checkEnvironment(tool_dir: Path) -> None:
    """Check if required directories and binaries exist."""

    factory_dir = tool_dir / "factory"

    if not factory_dir.is_dir():
        raise RuntimeError(f'"factory/" directory does not exist at: {factory_dir}')

    if shutil.which(FASTBOOT_BIN) is None:
        raise RuntimeError(f'"{FASTBOOT_BIN}" binary was not found in PATH.')


def getFastbootDevices() -> list[str]:
    """Get a list of connected fastboot device serials."""

    res = subprocess.run(
        [FASTBOOT_BIN, "devices"],
        capture_output=True,
        encoding="utf-8",
        check=False,
        text=True
    )

    devices = []
    for line in res.stdout.strip().splitlines():
        parts = line.strip().split()

        if parts and "permissions" not in line.lower():
            devices.append(parts[0])

    return devices


@dataclass(slots=True)
class FlashOptions:
    """Configuration options for FastbootFlasher."""

    IMAGE_PATH: Path
    TOOL_DIR: Path
    BOOTINFO_PATH: Path = Path()
    FASTBOOT_BIN: str = FASTBOOT_BIN
    DEVICE_SERIAL: str = ""
    REBOOT_AFTER_FLASH: bool = False
    LOG_CB: Callable[[str, str], None] | None = None
    PROGRESS_CB: Callable[[int, int], None] | None = None


class FastbootFlasher:
    """Handles fastboot commands to flash firmware images."""

    def __init__(self, options: FlashOptions):
        self.OPTIONS = options
        self.STOP_REQUESTED = False
        self.CURRENT_PROC = None


    def fbCmd(self, *args: str) -> list[str]:
        """Build a fastboot command list."""

        cmd = [self.OPTIONS.FASTBOOT_BIN, "--force"]

        if self.OPTIONS.DEVICE_SERIAL and not self.OPTIONS.DEVICE_SERIAL.startswith("?"):
            cmd.extend(["-s", self.OPTIONS.DEVICE_SERIAL])

        cmd.extend(args)
        return cmd


    def log(self, text: str, color: str = "#A1A1AA"):
        """Send log message to the callback."""

        if self.OPTIONS.LOG_CB:
            self.OPTIONS.LOG_CB(text, color)


    def stop(self):
        """Stop the current flashing operation."""

        self.STOP_REQUESTED = True

        if self.CURRENT_PROC and self.CURRENT_PROC.poll() is None:
            try:
                self.CURRENT_PROC.terminate()
                time.sleep(0.2)

                if self.CURRENT_PROC.poll() is None:
                    self.CURRENT_PROC.kill()
            except (OSError, subprocess.SubprocessError):
                pass


    def runCmd(self, cmd: list[str], description: str) -> bool:
        """Execute a command and capture output."""

        if self.STOP_REQUESTED:
            return False

        cmd_str = " ".join(cmd)
        self.log(f"[Running] {description}: {cmd_str}", "#60A5FA")

        try:
            with subprocess.Popen(cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                text=True,
            ) as proc:
                self.CURRENT_PROC = proc
                stdout, stderr = proc.communicate()

                if stdout.strip():
                    self.log(stdout.strip())

                if self.STOP_REQUESTED:
                    self.log(
                        f"[Aborted] {description}",
                        "#EF4444"
                    )
                    return False

                if proc.returncode != 0:
                    if stderr.strip():
                        self.log(
                            stderr.strip(),
                            "#EF4444"
                        )

                    self.log(
                        f"[Failed] {description}",
                        "#EF4444"
                    )
                    return False

                return True
        except (OSError, subprocess.SubprocessError) as e:
            self.log(
                f"[Error] Execution failed: {e}",
                "#EF4444"
            )
            return False
        finally:
            self.CURRENT_PROC = None


    def waitForDevice(self, timeout: int = 15) -> bool:
        """Wait until the target device re-enumerates."""

        self.log(
            "[Info] Waiting for device re-enumeration...",
            "#F59E0B"
        )

        start = time.time()
        cmd = [self.OPTIONS.FASTBOOT_BIN, "devices"]
        old_serial = self.OPTIONS.DEVICE_SERIAL

        res_init = subprocess.run(cmd,
            capture_output=True,
            encoding="utf-8",
            check=False,
            text=True,
        )

        other_devices = {
            line.strip().split()[0]
            for line in res_init.stdout.splitlines()
            if line.strip() and "permissions" not in line.lower()
        } - {old_serial}

        if old_serial:
            while time.time() - start < timeout:
                if self.STOP_REQUESTED:
                    return False

                res = subprocess.run(cmd,
                    capture_output=True,
                    encoding="utf-8",
                    check=False,
                    text=True,
                )

                current = {
                    line.strip().split()[0]
                    for line in res.stdout.splitlines()
                    if line.strip() and "permissions" not in line.lower()
                }

                if old_serial not in current:
                    break

                time.sleep(0.1)

        while time.time() - start < timeout:
            if self.STOP_REQUESTED:
                return False

            res = subprocess.run(cmd,
                capture_output=True,
                encoding="utf-8",
                check=False,
                text=True,
            )

            current = {
                line.strip().split()[0]
                for line in res.stdout.splitlines()
                if line.strip() and "permissions" not in line.lower()
            }

            new_serials = current - other_devices
            if new_serials:
                new_serial = next(iter(new_serials))
                if new_serial.startswith("?"):
                    self.log(
                        f"[Info] Re-enumerated device found: {new_serial}",
                        "#F59E0B"
                    )
                self.OPTIONS.DEVICE_SERIAL = new_serial
                return True

            time.sleep(0.5)
        return False


    def updateJsonPartition(self, json_path: Path, bootinfo_path: Path) -> bool:
        """Update partition JSON file with system image path."""

        if not json_path.is_file():
            self.log(
                f"[Failed] Partition file missing: {json_path}",
                "#EF4444"
            )
            return False

        try:
            bootinfo_name = (
                bootinfo_path.name

                if bootinfo_path.name
                else "bootinfo_emmc.bin"
            )
            mapping = {
                "bootinfo": f"factory/{bootinfo_name}",
                "emmc": self.OPTIONS.IMAGE_PATH.name,
            }

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for part in data.get("partitions", []):
                if name := part.get("name"):
                    if name in mapping:
                        part["image"] = mapping[name]

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

            return True
        except (OSError, json.JSONDecodeError) as e:
            self.log(
                f"[Error] JSON update failed: {e}",
                "#EF4444"
            )
            return False


    def _extractArchiveIfNeeded(self, tmp_dir: Path) -> Path | None:
        """Extract input archive if needed and return target image path."""

        image_path = self.OPTIONS.IMAGE_PATH
        filename = image_path.name.lower()

        if not (filename.endswith((".tar.gz", ".tgz")) or filename.endswith(".zip")):
            return image_path

        self.log(
            f"[Info] Extracting archive: {image_path.name}...",
            "#F59E0B"
        )

        try:
            if filename.endswith((".tar.gz", ".tgz")):
                with tarfile.open(image_path, "r:gz") as tar:
                    tar.extractall(
                        path=tmp_dir
                    )
            elif filename.endswith(".zip"):
                with zipfile.ZipFile(image_path, "r") as zip_ref:
                    zip_ref.extractall(
                        path=tmp_dir
                    )

            extracted = [
                p for p in tmp_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in {".img", ".bin"}
            ]

            if not extracted:
                self.log(
                    "[Error] No *.img or *.bin found in archive.",
                    "#EF4444"
                )
                return None

            target_img = extracted[0]
            self.log(
                f"[Info] Extracted target image: {target_img.name}",
                "#10B981"
            )
            return target_img

        except (tarfile.TarError, zipfile.BadZipFile, OSError) as e:
            self.log(
                f"[Error] Extraction failed: {e}",
                "#EF4444"
            )
            return None


    def flash(self) -> bool:
        """Execute sequence of fastboot flashing commands."""

        factory = self.OPTIONS.TOOL_DIR / "factory"
        json_path = factory / "partition_universal.json"
        bootinfo_file = (
            self.OPTIONS.BOOTINFO_PATH
            if self.OPTIONS.BOOTINFO_PATH.is_file()
            else factory / "bootinfo_emmc.bin"
        )

        with tempfile.TemporaryDirectory() as tmp_dir_str:
            resolved_image = self._extractArchiveIfNeeded(Path(tmp_dir_str))
            if resolved_image is None:
                return False

            self.OPTIONS.IMAGE_PATH = resolved_image

            if not self.updateJsonPartition(json_path, bootinfo_file):
                return False

            steps = [
                (
                    "Staging FSBL",
                    ["stage", str(factory / "FSBL.bin")],
                    1.5,
                ),
                (
                    "Booting FSBL",
                    ["continue"],
                    0.0,
                ),
                (
                    "Staging U-Boot",
                    ["stage", str(factory / "u-boot.itb")],
                    1.5,
                ),
                (
                    "Booting U-Boot",
                    ["continue"],
                    0.0,
                ),
                (
                    "Flashing GPT",
                    ["flash", "gpt", str(json_path)],
                    0.5,
                ),
                (
                    "Flashing BootInfo",
                    ["flash", "bootinfo", str(bootinfo_file)],
                    0.5,
                ),
                (
                    "Flashing FSBL",
                    ["flash", "fsbl", str(factory / "FSBL.bin")],
                    0.5,
                ),
                (
                    "Flashing System Image",
                    ["flash", "emmc", str(self.OPTIONS.IMAGE_PATH)],
                    0.0,
                ),
            ]

            if self.OPTIONS.REBOOT_AFTER_FLASH:
                steps.append(("Rebooting Device", ["reboot"], 0.0))

            total = len(steps)

            for idx, (desc, args, step_delay) in enumerate(steps, start=1):
                if self.STOP_REQUESTED:
                    break

                if self.OPTIONS.PROGRESS_CB:
                    self.OPTIONS.PROGRESS_CB(idx - 1, total)

                cmd = self.fbCmd(*args)

                if not self.runCmd(cmd, desc):
                    return False

                if args and args[0] == "continue":
                    if not self.waitForDevice():
                        if not self.STOP_REQUESTED:
                            self.log(
                                "[Failed] Device re-enumeration timed out!", 
                                "#EF4444"
                            )
                        return False

                if step_delay > 0:
                    step_start = time.time()

                    while time.time() - step_start < step_delay:
                        if self.STOP_REQUESTED:
                            break

                        time.sleep(0.1)

            if self.STOP_REQUESTED:
                self.log(
                    "\n[Cancelled] Flashing process was stopped by user.", 
                    "#EF4444"
                )
                return False

            if self.OPTIONS.PROGRESS_CB:
                self.OPTIONS.PROGRESS_CB(total, total)

            self.log(
                "\n[Success] Flashing completed successfully!",
                "#10B981"
            )
            return True
