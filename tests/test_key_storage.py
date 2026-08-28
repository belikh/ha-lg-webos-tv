"""Tests for the in-memory key storage (plan AD-2)."""

from __future__ import annotations

from custom_components.bscpylgtv.key_storage import InMemoryKeyStorage


async def test_create_factory_roundtrip() -> None:
    """The async factory pre-pairs the key; the lookup key is ignored."""
    storage = await InMemoryKeyStorage.create("pre-paired-key")
    assert await storage.get_key("ignored-lookup-key") == "pre-paired-key"


async def test_get_key_unset_returns_none() -> None:
    storage = InMemoryKeyStorage()
    assert await storage.get_key("any") is None


async def test_set_key_rotates_and_lists() -> None:
    """A freshly paired key is stored and listed under its key name."""
    storage = InMemoryKeyStorage("old-key")
    await storage.set_key("192.168.1.42", "new-key")
    assert await storage.get_key("192.168.1.42") == "new-key"
    assert await storage.list_keys() == {"192.168.1.42": "new-key"}


async def test_list_keys_empty_before_first_write() -> None:
    """No set_key yet: the listing is empty even with a pre-paired key."""
    storage = InMemoryKeyStorage("pre-paired-key")
    assert await storage.list_keys() == {}
