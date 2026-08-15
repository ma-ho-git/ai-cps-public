"""Gesamtflow aus klar getrennten Tab-Bausteinen zusammensetzen."""

from .hmi import update_low_code_hmi
from .initialization import _tabs, build_init_nodes
from .modules import build_module_nodes
from .pipeline import build_pipeline_nodes
from .semaphore import build_semaphore_nodes
from .state_capture import build_state_nodes
from .subflows import build_subflows

def build_low_code_flow(existing: list[dict]) -> list[dict]:
    """Vollstaendigen Flow mit Dashboard und Konfiguration bauen."""
    config_nodes = [
        dict(node) for node in existing
        if not node.get("z") and node.get("type") not in {"tab", "subflow"}
    ]
    return (
        _tabs()
        + build_subflows()
        + build_init_nodes()
        + build_state_nodes()
        + build_module_nodes()
        + build_semaphore_nodes()
        + build_pipeline_nodes()
        + update_low_code_hmi(existing)
        + config_nodes
    )
