# Release notes: v2.0.10

**LG WebOS TV (bscpylgtv) for Home Assistant**

Version 2.0.10 makes problems easier to report and to diagnose. It changes no
entity behavior. Upgrade via the Marketplace or HACS and restart Home Assistant.

## Issue forms

Bug reports now use a form that asks for the install method, what happened,
the steps and a debug log. The integration, Home Assistant and webOS version
fields and the TV model are optional when you attach the diagnostics file.
Feature requests ask for the use case and the TV model.

## Diagnostics

The diagnostics download lists the integration, `bscpylgtv` and Home Assistant
versions. It also shows whether the current channel is set and whether the
channel retry is running.

## Debug log

Connect, reconnect and liveness-probe failures and the end of the channel
retry are logged at debug level. The key and MAC update lines name the TV
instead of its IP address. Connection errors from the library can still
include the IP address, so read the log before posting it.

The README section "Reporting a problem" describes how to download the debug
log (Enable debug logging on the integration page, repeat the problem, then
Disable debug logging) and the diagnostics file.

## Thanks

- **@fast2doc**: issue #17.
- **chros73**, author of the
  [bscpylgtv](https://github.com/chros73/bscpylgtv) library this integration
  is built on.
