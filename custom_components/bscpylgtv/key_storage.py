"""Minimal in-memory client-key storage for bscpylgtv.

The integration persists the pairing key itself via ``client.client_key``
in the config entry, so the library's ``StorageProto`` contract is
satisfied without touching the filesystem (plan AD-2).

An injected storage object is required even when ``client_key=`` is passed:
``connect_handler`` calls ``await storage.set_key(ip, key)`` whenever the
TV returns a freshly paired key (webos_client.py registration path), which
would raise ``AttributeError`` if ``self.storage`` were ``None``.
"""

from __future__ import annotations

from bscpylgtv.storage_proto import StorageProto


class InMemoryKeyStorage(StorageProto):
    """Hold a single webOS client key in memory only."""

    def __init__(self, client_key: str | None = None) -> None:
        """Initialize with an optional pre-paired key."""
        self._key = client_key
        self._key_name: str | None = None

    @classmethod
    async def create(cls, client_key: str | None = None) -> InMemoryKeyStorage:
        """Async factory matching the library's ``storage.create()`` shape."""
        return cls(client_key)

    async def get_key(self, key: str) -> str | None:
        """Return the stored key (one TV per client; lookup key ignored)."""
        return self._key

    async def set_key(self, key: str, value: str) -> None:
        """Store the key in memory."""
        self._key = value
        self._key_name = key

    async def list_keys(self) -> dict[str, str | None]:
        """Return the stored key/value pairs."""
        if self._key_name is None:
            return {}
        return {self._key_name: self._key}
