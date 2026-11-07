import atexit
import logging
import os
import re
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Optional

from app.config.settings import get_settings
from app.proxy.vpn_health import probe_socks5, wait_for_port

logger = logging.getLogger("ghostgrid.vpn")

SOCKS_HOST = "127.0.0.1"
SOCKS_PORT = 1080
SOCKS_PORT_WAIT_SECONDS = 20.0     # Wireproxy must bind within this window
PROBE_TIMEOUT_SECONDS = 10.0       # end-to-end probe after port opens

_SOCKS_BLOCK_RE = re.compile(
    r"\[Socks5\][^\[]*", re.IGNORECASE | re.DOTALL
)
_SOCKS_BIND_RE = re.compile(
    r"(BindAddress\s*=\s*)([^\r\n]+)", re.IGNORECASE
)


class VPNManager:
    def __init__(self):
        self.settings = get_settings()
        self.base_dir = Path(os.getcwd())
        self.bin_dir = self.base_dir / "bin"
        self.vpn_dir = self.base_dir / "vpn_configs"
        self.process: Optional[subprocess.Popen] = None
        self.socks_port: int = SOCKS_PORT
        self.proxy_url: str = f"socks5://{SOCKS_HOST}:{SOCKS_PORT}"
        self.current_config_file: Optional[str] = None
        self._degraded: bool = False
        atexit.register(self.stop_vpn)

    # ------------------------------------------------------------------ binary
    def _get_wireproxy_binary(self) -> Path:
        self.bin_dir.mkdir(exist_ok=True)
        is_win = sys.platform == "win32"
        binary_name = "wireproxy_1.0.7.exe" if is_win else "wireproxy_1.0.7"
        binary_path = self.bin_dir / binary_name
        if binary_path.exists():
            return binary_path

        logger.info("Wireproxy v1.0.7 not found. Downloading (this happens once per ephemeral deploy)...")
        url = (
            "https://github.com/pufferffish/wireproxy/releases/download/v1.0.7/wireproxy_windows_amd64.tar.gz"
            if is_win
            else "https://github.com/pufferffish/wireproxy/releases/download/v1.0.7/wireproxy_linux_amd64.tar.gz"
        )
        tar_path = self.bin_dir / "wireproxy.tar.gz"
        urllib.request.urlretrieve(url, tar_path)

        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(path=self.bin_dir)
        tar_path.unlink()

        extracted_name = "wireproxy.exe" if is_win else "wireproxy"
        extracted_path = self.bin_dir / extracted_name
        if extracted_path.exists():
            extracted_path.rename(binary_path)
        if not is_win:
            binary_path.chmod(binary_path.stat().st_mode | stat.S_IEXEC)
        logger.info("Wireproxy binary ready at %s", binary_path)
        return binary_path

    # ------------------------------------------------------------------ config
    def _build_wireproxy_config(self, source_conf: Path) -> Path:
        self.vpn_dir.mkdir(exist_ok=True)
        target_conf = self.vpn_dir / "wireproxy_active.conf"
        content = source_conf.read_text(encoding="utf-8")

        # Keepalive injection (only once)
        if "PersistentKeepalive" not in content and "[Peer]" in content:
            content = content.replace("[Peer]", "[Peer]\nPersistentKeepalive = 25", 1)

        # SOCKS5 block: normalize to our port, whether present or absent
        if _SOCKS_BLOCK_RE.search(content):
            content = _SOCKS_BLOCK_RE.sub(
                f"[Socks5]\nBindAddress = {SOCKS_HOST}:{SOCKS_PORT}\n",
                content,
                count=1,
            )
            logger.info("Normalized existing [Socks5] block to %s:%d", SOCKS_HOST, SOCKS_PORT)
        else:
            content += f"\n\n[Socks5]\nBindAddress = {SOCKS_HOST}:{SOCKS_PORT}\n"

        target_conf.write_text(content, encoding="utf-8")

        # Sanity: confirm the bind line really is our port
        m = _SOCKS_BIND_RE.search(content)
        if not m or f":{SOCKS_PORT}" not in m.group(2):
            logger.error("Built config does not bind SOCKS5 to :%d (got %r)", SOCKS_PORT, m.group(2) if m else None)
        return target_conf

    # ------------------------------------------------------------------ start
    def start_vpn(self, config_filename: str) -> bool:
        self.current_config_file = config_filename

        # Already alive?
        if self.process is not None:
            code = self.process.poll()
            if code is None:
                logger.info("VPN process already running (pid=%s)", self.process.pid)
                return True
            logger.warning("VPN process died earlier (exit=%s). Restarting.", code)
            self.process = None

        # Locate config
        candidates = [
            self.vpn_dir / config_filename,
            Path(f"/etc/secrets/{config_filename}"),
            self.base_dir / config_filename,
        ]
        source_conf = next((p for p in candidates if p.exists()), None)
        if source_conf is None:
            logger.error("VPN config %s not found in any expected location %s",
                         config_filename, [str(c) for c in candidates])
            return False

        # Build + spawn
        try:
            binary = self._get_wireproxy_binary()
            active_conf = self._build_wireproxy_config(source_conf)
            env = os.environ.copy()
            env["WG_DISABLE_LANDLOCK"] = "1"
            env["DISABLE_LANDLOCK"] = "1"
            logger.info("Starting Wireproxy with config %s (source=%s)", active_conf, source_conf)
            t0 = time.monotonic()
            self.process = subprocess.Popen(
                [str(binary), "-c", str(active_conf)],
                stdout=sys.stdout,
                stderr=sys.stderr,
                env=env,
            )
        except Exception as exc:
            logger.error("Failed to spawn Wireproxy: %s: %s", exc.__class__.__name__, exc)
            self.process = None
            return False

        # Wait for port
        if not wait_for_port(SOCKS_HOST, SOCKS_PORT, SOCKS_PORT_WAIT_SECONDS):
            exit_code = self.process.poll() if self.process else None
            logger.error("Wireproxy did not open %s:%d in %.1fs (exit=%s). Killing.",
                         SOCKS_HOST, SOCKS_PORT, SOCKS_PORT_WAIT_SECONDS, exit_code)
            self.stop_vpn()
            return False

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info("Wireproxy ready on %s:%d in %d ms", SOCKS_HOST, SOCKS_PORT, elapsed_ms)

        # End-to-end probe (informational — do NOT kill on failure, handshake may still be in flight)
        try:
            import asyncio
            ok = asyncio.get_event_loop().run_until_complete(
                probe_socks5(self.proxy_url, timeout=PROBE_TIMEOUT_SECONDS)
            ) if not asyncio.get_event_loop().is_running() else False
        except Exception as exc:
            logger.warning("End-to-end probe raised: %s: %s", exc.__class__.__name__, exc)
            ok = False

        self._degraded = not ok
        if ok:
            logger.info("VPN end-to-end probe OK (Handshake likely complete)")
        else:
            logger.warning("VPN port open but end-to-end probe failed. "
                           "Handshake may still be completing, or peer is unreachable.")
        return True

    # ------------------------------------------------------------------ stop
    def stop_vpn(self):
        self._degraded = False
        self.socks_port = SOCKS_PORT
        if self.process is None:
            return
        logger.info("Shutting down VPN proxy (pid=%s)...", self.process.pid)
        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Wireproxy did not exit in 5s, killing.")
                self.process.kill()
        except Exception as exc:
            logger.warning("Error stopping Wireproxy: %s: %s", exc.__class__.__name__, exc)
        finally:
            self.process = None

    # ------------------------------------------------------------------ public
    def get_active_node_proxy(self, node_key: str) -> Optional[str]:
        if node_key == "us":
            if self.start_vpn("proton_us.conf"):
                return self.proxy_url
            logger.error("US node requested but VPN failed to become ready; returning None.")
            return None

        nodes = self.settings.available_nodes
        if node_key in nodes:
            return nodes[node_key].get("url")
        return None


vpn_manager = VPNManager()