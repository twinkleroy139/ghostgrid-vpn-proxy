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
        self.current_config_file = None
        
        atexit.register(self.stop_vpn)

    def _get_wireproxy_binary(self) -> Path:
        self.bin_dir.mkdir(exist_ok=True)
        is_win = sys.platform == "win32"
        
        binary_name = "wireproxy_1.0.7.exe" if is_win else "wireproxy_1.0.7"
        binary_path = self.bin_dir / binary_name

        if binary_path.exists():
            return binary_path

        logger.info("Wireproxy v1.0.7 not found. Downloading...")
        url = "https://github.com/pufferffish/wireproxy/releases/download/v1.0.7/wireproxy_windows_amd64.tar.gz" if is_win \
            else "https://github.com/pufferffish/wireproxy/releases/download/v1.0.7/wireproxy_linux_amd64.tar.gz"
        
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
            
        return binary_path

    def _build_wireproxy_config(self, source_conf: Path) -> Path:
        self.vpn_dir.mkdir(exist_ok=True)
        target_conf = self.vpn_dir / "wireproxy_active.conf"
        
        with open(source_conf, "r") as f:
            content = f.read()

        # Fix 1: Force PersistentKeepalive to prevent idle timeout crashes
        if "PersistentKeepalive" not in content:
            content = content.replace("[Peer]", "[Peer]\nPersistentKeepalive = 25")

        if "[Socks5]" not in content:
            content += "\n\n[Socks5]\nBindAddress = 127.0.0.1:1080\n"

        with open(target_conf, "w") as f:
            f.write(content)
            
        return target_conf

    def start_vpn(self, config_filename: str):
        self.current_config_file = config_filename
        
        # Fix 2: Auto-restart mechanism if process died unexpectedly
        if self.process:
            poll_result = self.process.poll()
            if poll_result is None:
                return # Still running happily
            else:
                logger.warning(f"VPN process died unexpectedly with code {poll_result}. Restarting...")
                self.process = None
            
        possible_paths = [
            self.vpn_dir / config_filename,
            Path(f"/etc/secrets/{config_filename}"),
            self.base_dir / config_filename
        ]
        
        source_conf = None
        for path in possible_paths:
            if path.exists():
                source_conf = path
                break
                
        if not source_conf:
            logger.error(f"VPN config {config_filename} not found in any expected location!")
            return

        try:
            binary = self._get_wireproxy_binary()
            active_conf = self._build_wireproxy_config(source_conf)
            
            env = os.environ.copy()
            env["WG_DISABLE_LANDLOCK"] = "1"
            env["DISABLE_LANDLOCK"] = "1"
            
            logger.info(f"Starting Userspace WireGuard using config from {source_conf}...")
            self.process = subprocess.Popen(
                [str(binary), "-c", str(active_conf)],
                stdout=sys.stdout,
                stderr=sys.stderr,
                env=env
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