"""Optional local JSAUX delegation. No hardware driver or autonomous fallback."""
from .client import BrokerClient
from .protocol import BrokerError

__all__ = ["BrokerClient", "BrokerError"]
