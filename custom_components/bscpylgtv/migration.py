"""Config-entry/entity-registry migrations for the LG WebOS TV integration.

The lazy v1 → v2 identity migration changes a config entry's unique_id.
Every platform derives its entity unique_ids from the entry id
(``entry.unique_id`` or ``f"{entry.unique_id}_{key}"``), so the entity
registry entries must be rewritten in the same pass: otherwise the next
platform setup registers a second set of entities under the new id and
the old ones linger — the duplicate/triple entities reported after the
v2 upgrade (belikh/ha-lg-webos-tv#9 follow-up).
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import LOGGER


@callback
def async_migrate_entity_unique_ids(
    hass: HomeAssistant,
    entry_id: str,
    old_unique_id: str,
    new_unique_id: str,
) -> None:
    """Rewrite entity registry ids derived from a migrated entry unique_id.

    The registry entry keeps its entity_id, so history and device links
    survive. Entities whose id does not descend from ``old_unique_id``
    (or that already carry a colliding id) are left alone; a collision is
    logged because it can only be resolved by the user removing the
    duplicate.
    """
    registry = er.async_get(hass)
    prefix = f"{old_unique_id}_"
    for entity in er.async_entries_for_config_entry(registry, entry_id):
        if entity.unique_id == old_unique_id:
            migrated = new_unique_id
        elif entity.unique_id.startswith(prefix):
            migrated = f"{new_unique_id}{entity.unique_id[len(old_unique_id) :]}"
        else:
            continue
        try:
            registry.async_update_entity(entity.entity_id, new_unique_id=migrated)
        except HomeAssistantError, ValueError:
            LOGGER.warning(
                "Cannot migrate entity unique_id %s for %s: an entity with the"
                " new id already exists; remove the duplicate entity if the TV"
                " shows duplicate entities",
                entity.unique_id,
                entity.entity_id,
            )
