import os
import sys
import stat
import logging
import tarfile
import urllib.request
import subprocess
import atexit
from pathlib import Path
from typing import Optional
from app.config.settings import get_settings

logger = logging.getLogger("ghostgrid.vpn")

class VPNManager:
    def __init__(self):
        self.settings = get_settings()
        self.base_dir = Path(os.getcwd())
        self.bin_dir = self.base_dir / "bin"
        self.vpn_dir = self.base_dir / "vpn_configs"
        self.process = None
        self.proxy_url = "socks5://127.0.0.1:1080"
        
        atexit.register(self.stop_vpn)

    def _get_wireproxy_binary(self) -> Path:
        self.bin_dir.mkdir(exist_ok=True)
        is_win = sys.platform == "win32"
        binary_name = "wireproxy.exe" if is_win else "wireproxy"
        binary_path = self.bin_dir / binary_name

        if binary_path.exists():
            return binary_path

        logger.info("Wireproxy binary not found. Downloading...")
        url = "https://github.com/pufferffish/wireproxy/releases/download/v1.0.8/wireproxy_windows_amd64.tar.gz" if is_win \
            else "https://github.com/pufferffish/wireproxy/releases/download/v1.0.8/wireproxy_linux_amd64.tar.gz"
        
        tar_path = self.bin_dir / "wireproxy.tar.gz"
        urllib.request.urlretrieve(url, tar_path)

        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(path=self.bin_dir)
        
        tar_path.unlink()
        
        if not is_win:
            binary_path.chmod(binary_path.stat().st_mode | stat.S_IEXEC)
            
        return binary_path

    def _build_wireproxy_config(self, source_conf: Path) -> Path:
        target_conf = self.vpn_dir / "wireproxy_active.conf"
        
        with open(source_conf, "r") as f:
            content = f.read()

        if "[Socks5]" not in content:
            content += "\n\n[Socks5]\nBindAddress = 127.0.0.1:1080\n"

        with open(target_conf, "w") as f:
            f.write(content)
            
        return target_conf

    def start_vpn(self, config_filename: str):
        if self.process and self.process.poll() is None:
            return
            
        source_conf = self.vpn_dir / config_filename
        if not source_conf.exists():
            logger.error(f"VPN config {source_conf} not found!")
            return

        try:
            binary = self._get_wireproxy_binary()
            active_conf = self._build_wireproxy_config(source_conf)
            
            logger.info("Starting Userspace WireGuard (wireproxy)...")
            # Modified to output directly to the Render logs
            self.process = subprocess.Popen(
                [str(binary), "-c", str(active_conf)],
                stdout=sys.stdout,
                stderr=sys.stderr
            )
        except Exception as e:
            logger.error(f"Failed to start VPN: {e}")

    def stop_vpn(self):
        if self.process:
            logger.info("Shutting down VPN proxy...")
            self.process.terminate()
            self.process = None

    def get_active_node_proxy(self, node_key: str) -> Optional[str]:
        if node_key == "us":
            self.start_vpn("proton_us.conf")
            return self.proxy_url
            
        nodes = self.settings.available_nodes
        if node_key in nodes:
            return nodes[node_key].get("url")
        
        return None

vpn_manager = VPNManager()