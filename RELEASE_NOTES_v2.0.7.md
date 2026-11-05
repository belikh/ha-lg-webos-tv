# Release notes: v2.0.7

**LG WebOS TV (bscpylgtv) for Home Assistant**

Version 2.0.7 fixes turning the TV off. No configuration changes are required;
upgrade via the Marketplace or HACS and restart Home Assistant.

## Turn off fails from the Screen Off state

`media_player.turn_off` and `remote.turn_off` called `turn_screen_off`. A TV
already in the Screen Off state rejects that call:

```text
Communication error while calling async_turn_off ... '500 Application error',
'state': 'Screen Off', 'errorText': "The current state must be 'Active'"
```

Both services now call `power_off` (`system/turnOff`), which puts the TV in
standby from any state. The **Turn screen off** button still switches only the
panel off.

## Thanks

- **@Minustrike**: issue #16, including the fix.
- **chros73**, author of the
  [bscpylgtv](https://github.com/chros73/bscpylgtv) library this integration
  is built on.
- The **Home Assistant core `webostv` maintainers**, whose integration served
  as the architecture reference.
