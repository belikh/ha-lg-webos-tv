# Release notes — v2.0.6

**LG WebOS TV (bscpylgtv) for Home Assistant**

Version 2.0.6 is a small maintenance release. It fixes a startup warning
reported in issue #15. No configuration changes are required; upgrade via
HACS and restart Home Assistant.

## Blocking import at startup

Home Assistant's event-loop detector reported:

```text
Detected blocking call to import_module inside the event loop by custom
integration 'bscpylgtv' at custom_components/bscpylgtv/__init__.py
```

The integration loaded its service module lazily during `async_setup`, which
imports from disk while the event loop is running. The service module is now
imported with the integration (which Home Assistant performs off the event
loop), so startup no longer triggers the warning. Service registration itself
is unchanged.

## Thanks

- **@wichtel77** — issue #15, reporting the blocking import.
- **chros73**, author of the
  [bscpylgtv](https://github.com/chros73/bscpylgtv) library this integration
  is built on.
- The **Home Assistant core `webostv` maintainers**, whose integration served
  as the architecture reference.
