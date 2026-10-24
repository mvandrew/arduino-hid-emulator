"""HID v1 client; legacy modules require an explicitly selected old firmware."""
from .device import HidDevice, ConnectionError
from .protocol import Capabilities, Outcome, ProtocolError, Result

__version__ = "1.0.0"
__all__ = ["HidDevice", "ConnectionError", "Capabilities", "Outcome", "ProtocolError", "Result"]
