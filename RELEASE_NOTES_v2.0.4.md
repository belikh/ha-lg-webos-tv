# Release notes — v2.0.4

**LG WebOS TV (bscpylgtv) for Home Assistant**

Version 2.0.4 is a maintenance release. It fixes webOS 26 (firmware 43.x)
pairing and reconnection issues, and closes a path-traversal report on the
`screenshot` filename and notify `icon` path. No configuration changes are
required for existing installations — upgrade via HACS and restart Home
Assistant.

## Changes that affect your Home Assistant configuration

### 1. webOS 26 manifest compatibility — pairing restored on firmware 43.x

LG blacklists the legacy signed registration manifest on webOS 26 sets
(firmware 43.x), so pairing and reconnection fail with `403 Pairing rejected:
blacklisted certificate detected` (pairing) or entities staying unavailable
(after a stored key is invalidated).

v2.0.4 detects this rejection and retries once with an unsigned compatibility
manifest. The compatibility mode is **persisted across restarts**, so the TV
works without re-pairing on every start. In compatibility mode the integration
avoids requesting `software_info` (which returns `401 insufficient
permissions` on these sets); other state (power, volume, apps, inputs …) is
unchanged.

If your existing entry stops working after a firmware update:

- Run **Re-authentication** from the integration's page (accept the new pairing
  prompt on the TV), **or**
- Remove the integration and add it fresh — re-pairing automatically uses the
  unsigned fallback.

Existing TVs that still accept the signed manifest are unaffected — elevated
permissions only the signed manifest grants (e.g. `WRITE_SETTINGS` for picture
settings) are preserved.

### 2. Path validation on `take_screenshot` filename and notify `icon`

The `bscpylgtv.take_screenshot` service accepts a free-form `filename`, and
the notify entity accepts a free-form `icon` path. Previously an absolute path
was used as-is and parent directories were created, so any HA user or script
could write/read any file the Home Assistant process can access — including
files inside the config directory.

Both paths are now validated with `hass.config.is_allowed_path(...)` before any
file is written or read. Disallowed paths raise a translated
`ServiceValidationError` (matching core `camera.snapshot`). The screenshot
button entity writes to a fixed path under `<config>/www` and is unaffected.

### 3. Invalid pairing keys in compatibility mode

When the stored client key is no longer registered for either manifest, the
integration now starts **re-authentication** (rather than silently retrying
forever). Reconfigure re-checks whether the normal signed manifest works again
before keeping compatibility mode.

## What else is new

- **Dependency bump:** `bscpylgtv` 0.5.4 → 0.5.5.
- **README:** documents the `take_screenshot` path validation and credits all
  reporters and reviewers (see the Credits section).

## Downgrade protection

Config entries use config-entry schema version 2 (unchanged from v2.0.2 /
2.0.3). Home Assistant refuses to load a v2 entry with the old v1 code — if you
roll back the integration files, set the TV up again from scratch (or restore
your v1 `.storage` backup) rather than mixing versions.

## Thanks

- **@AquaCobell** & **@jerielsr** — issue #14, reporting entities unavailable
  after pairing on webOS 26 sets (blacklisted-certificate rejection).
- **@Ramss3s** — issue #13, reporting webOS 26 pairing failure on firmware
  43.21.71.
- **@NoCleverMoniker** & **@starast** — issue #11, reporting the webOS 25
  pairing timeout caused by the library's `hello` handshake (fixed in v2.0.2).
- **@brei-er** — PR #12, robust webOS 26 manifest compatibility
  (unsigned-manifest fallback, persisted compatibility mode).
- **@frenck** — security review that prompted `is_allowed_path` validation on
  the `take_screenshot` filename and notify `icon` path.
- **chros73**, author of the
  [bscpylgtv](https://github.com/chros73/bscpylgtv) library this integration
  is built on.
- The **Home Assistant core `webostv` maintainers**, whose integration served
  as the architecture reference.
