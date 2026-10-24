# Release notes — v2.0.5

**LG WebOS TV (bscpylgtv) for Home Assistant**

Version 2.0.5 is a security release. It removes the **Screenshot** button,
which wrote the current TV picture into Home Assistant's publicly served
`www` directory. No re-pairing or configuration changes are required; upgrade
via HACS and restart Home Assistant.

## The Screenshot button is gone

The button saved the picture to
`<config>/www/bscpylgtv_<unique_id>.jpg`. Home Assistant serves everything
under `<config>/www` at `/local/` **without authentication**, so anyone who
could reach the Home Assistant URL could fetch whatever was on the TV, and the
file name (the device UUID, MAC address, or host) was not a secret either.

There is no safe fixed location for the button to use: a file in `www` is
public, while a file elsewhere must be explicitly allow-listed. The button has
therefore been removed rather than moved.

### Taking screenshots now

Use the **`bscpylgtv.take_screenshot`** service from Developer Tools,
automations, or scripts:

```yaml
service: bscpylgtv.take_screenshot
target:
  entity_id: media_player.lg_webos_tv
data:
  filename: /media/tv_screen.jpg
```

- Omit `filename` to get the JPEG back as base64 in the service response.
- With `filename`, the path must be inside an existing allowed directory.
  `/media` and `<config>/www` are allowed by default; other directories must be
  added to `allowlist_external_dirs` in `configuration.yaml`.
- **Do not use `<config>/www`** (or any other publicly served directory) for
  screenshots. Use `/media` or another allow-listed private directory.

If you previously added a dashboard card or automation that displayed
`/local/bscpylgtv_<deviceUUID>.jpg`, remove it and use the service response or
a private path instead. The orphaned Screenshot button entity can be deleted
from the entity registry after upgrading.

## Under the hood

- Documentation and the `services.yaml` example no longer point at `www`.
- The `take_screenshot` path validation added in v2.0.4 is unchanged.
- No dependency or config-entry schema changes.

## Thanks

- **@frenck** — security review that identified the publicly served screenshot
  file and prompted this change.
- **chros73**, author of the
  [bscpylgtv](https://github.com/chros73/bscpylgtv) library this integration
  is built on.
- The **Home Assistant core `webostv` maintainers**, whose integration served
  as the architecture reference.
