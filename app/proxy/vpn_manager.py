import os
import logging
from typing import Optional
from app.config.settings import get_settings

logger = logging.getLogger("ghostgrid.vpn")

class VPNManager:
    def __init__(self):
        self.settings = get_settings()

    def get_active_node_proxy(self, node_key: str) -> Optional[str]:
        """
        Resolves the proxy mount URL for the requested node.
        If 'us' is requested, validates that the VPN proxy mount is configured.
        """
        nodes = self.settings.available_nodes
        if node_key not in nodes:
            return None
        
        node_data = nodes[node_key]
        proxy_url = node_data.get("url")
        
        if node_key == "us" and not proxy_url:
            logger.warning("US VPN node selected, but PROXY_NODE_US is not defined in environment variables.")
        
        return proxy_url

vpn_manager = VPNManager()