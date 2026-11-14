.. raw:: html

   <p align="right">
     <picture>
       <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/belikh/design/latest/packages/graphics/logo/jupiter-logo-dark.svg">
       <img alt="jupiter.au" src="https://raw.githubusercontent.com/belikh/design/latest/packages/graphics/logo/jupiter-logo-light.svg" width="260">
     </picture>
   </p>

   <h1>LG WebOS TV (bscpylgtv) for Home Assistant</h1>

.. meta::
   :description: Home Assistant integration for LG TVs running webOS, built on the bscpylgtv library with a single websocket connection to the TV.

A Home Assistant integration for LG TVs running webOS. It uses the `bscpylgtv <https://github.com/chros73/bscpylgtv>`__ library by `chros73 <https://github.com/chros73>`__ and keeps one websocket connection open to the TV, so state changes arrive as they happen instead of being polled.

The design follows the built-in Home Assistant ``webostv`` integration. On top of that it adds picture calibration sliders, picture mode, sound output and channel selects, power-state and channel sensors, a remote with pointer and text input, screen notifications and raw SSAP commands.

`Install`_ ·
`Set up`_ ·
`Entities`_ ·
`Services`_ ·
`Troubleshooting`_ ·
`Documentation`_ ·
`Develop`_

|

.. raw:: html

   <p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/rule/end-dark.svg"><img alt="" src="https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/rule/end-light.svg" width="50%"></picture></p>

|

Features
--------

- Setup from the UI with SSDP discovery. Pairing is a prompt on the TV; PIN pairing is not supported.
- Push updates over a supervised websocket that reconnects after TV restarts and network drops.
- Turn on through Wake-on-LAN, with the MAC address detected when the TV reports it.
- Reauthentication when the pairing key is lost, and reconfigure when the host changes.
- Diagnostics download with sensitive data redacted.
- Entities on the media player, remote, notify, button, number, select, sensor and switch platforms.
- Six services, including raw SSAP commands and screenshots.

|

Install
-------

With HACS:

.. image:: https://my.home-assistant.io/badges/hacs_repository.svg
   :alt: Add to Home Assistant
   :target: https://my.home-assistant.io/redirect/hacs_repository/?owner=belikh&repository=ha-lg-webos-tv&category=integration

1. Select the button above and choose **Download**, or search for **LG WebOS TV (bscpylgtv)** in HACS.
2. Restart Home Assistant.

If the search finds nothing, add ``https://github.com/belikh/ha-lg-webos-tv`` as a custom repository with category **Integration** (HACS, three-dot menu, **Custom repositories**). To install by hand, copy ``custom_components/bscpylgtv`` into the ``custom_components`` directory of your configuration and restart. See `Install <https://docs.jupiter.au/lg-webos-tv/start/install/>`__.

|

Set up
------

1. Go to **Settings > Devices & Services > Add Integration** and search for **LG WebOS TV (bscpylgtv)**. If the TV is on the same network, Home Assistant usually offers it as a discovered device.
2. Enter the hostname or IP address of the TV. The TV must be on.
3. Accept the pairing prompt on the TV screen.

The TV then appears as a device with its entities. `Set up a TV <https://docs.jupiter.au/lg-webos-tv/start/set-up/>`__ covers reauthentication and a changed IP address.

``turn_on`` sends a Wake-on-LAN packet to the MAC address of the TV, because the websocket is closed while the TV is off. If the MAC address was not detected, enter it in **Configure**. Wi-Fi may need a setting on the TV. See `Turn the TV on <https://docs.jupiter.au/lg-webos-tv/guides/turn-on/>`__.

|

Entities
--------

.. list-table::
   :header-rows: 1

   * - Platform
     - Entities
   * - |i-monitor-l| |i-monitor-d| ``media_player``
     - Power, volume, mute, source, transport controls, ``play_media`` for apps and channels
   * - |i-signal-l| |i-signal-d| ``remote``
     - Library buttons plus pointer and text commands
   * - |i-bell-l| |i-bell-d| ``notify``
     - Toast notifications on the TV screen
   * - |i-play-l| |i-play-d| ``button``
     - Turn screen off, turn screen on, reboot (disabled by default)
   * - |i-sliders-l| |i-sliders-d| ``number``
     - Backlight, contrast, brightness, color, sharpness, color temperature (disabled by default)
   * - |i-filter-l| |i-filter-d| ``select``
     - Picture mode, sound output, channel
   * - |i-pulse-l| |i-pulse-d| ``sensor``
     - Current app, volume, power state, current channel
   * - |i-switch-l| |i-switch-d| ``switch``
     - TPC and GSR OLED burn-in protection (disabled by default)

.. raw:: html

   <table>
     <tr align="left"><th>Warning</th></tr>
     <tr><td>

TPC and GSR protect OLED panels. Turning them off can raise the risk of burn-in.

.. raw:: html

     </td></tr>
   </table>

The full list with categories and ranges is in `Entities <https://docs.jupiter.au/lg-webos-tv/reference/entities/>`__. Soundbar volume settings are in `Options <https://docs.jupiter.au/lg-webos-tv/reference/options/>`__.

|

Services
--------

All services target the ``media_player`` entity of the TV.

.. list-table::
   :header-rows: 1

   * - Service
     - Purpose
   * - ``bscpylgtv.button``
     - Press a remote button
   * - ``bscpylgtv.command``
     - Send a raw SSAP endpoint
   * - ``bscpylgtv.select_sound_output``
     - Change the sound output
   * - ``bscpylgtv.launch_app``
     - Launch an app, optionally with parameters
   * - ``bscpylgtv.take_screenshot``
     - Capture the screen to a file or a base64 response
   * - ``bscpylgtv.set_settings``
     - Write settings through the TV settings API

Example:

.. code-block:: yaml

   service: bscpylgtv.launch_app
   target:
     entity_id: media_player.lg_webos_tv
   data:
     app_id: com.webos.app.youtube

Fields, responses and the standard services are in `Services <https://docs.jupiter.au/lg-webos-tv/reference/services/>`__. Write screenshots to ``/media``, never to ``<config>/www``: Home Assistant serves that folder without authentication.

|

Troubleshooting
---------------

Common cases:

- **TV shows unavailable.** It is off or unreachable. Set the MAC address so ``turn_on`` works.
- **Pairing fails.** Accept the prompt on the TV in time, or start reauthentication from the integration page.
- **Picture mode or sliders show unknown.** Some models refuse the read. Set the value once from Home Assistant.

`Troubleshoot <https://docs.jupiter.au/lg-webos-tv/guides/troubleshoot/>`__ lists every symptom with its fix, and `Report a problem <https://docs.jupiter.au/lg-webos-tv/guides/report-a-problem/>`__ shows how to collect a debug log and diagnostics. `Open an issue <https://github.com/belikh/ha-lg-webos-tv/issues/new/choose>`__ with both files.

|

Documentation
-------------

The full documentation is at `docs.jupiter.au/lg-webos-tv <https://docs.jupiter.au/lg-webos-tv/>`__. Its source is in ``docs-src/``.

- `Guides <https://docs.jupiter.au/lg-webos-tv/guides/turn-on/>`__: turn on, apps and channels, soundbar volume, screenshots.
- `Reference <https://docs.jupiter.au/lg-webos-tv/reference/entities/>`__: entities, services, remote commands, options, sound outputs.
- `Concepts <https://docs.jupiter.au/lg-webos-tv/concepts/how-it-works/>`__: connection, pairing, limitations.

To remove the integration, see `Remove the integration <https://docs.jupiter.au/lg-webos-tv/guides/remove/>`__.

|

Develop
-------

.. code-block:: sh

   uv sync
   uv run pytest
   uv run ruff check custom_components tests
   uv run mypy

See `Build and test <https://docs.jupiter.au/lg-webos-tv/develop/build-and-test/>`__ and `Release <https://docs.jupiter.au/lg-webos-tv/develop/release/>`__.

|

Licence
-------

MIT. See `LICENSE <LICENSE>`__. Release history is in `CHANGELOG.md <CHANGELOG.md>`__.

|

Credits
-------

- `chros73 <https://github.com/chros73>`__: author of the
  `bscpylgtv <https://github.com/chros73/bscpylgtv>`__ library that powers this
  integration.
- The **Home Assistant core webostv maintainers**: this integration's
  architecture (coordinator, config flow, media player design) is heavily
  modeled on their work.
- `@Xitee1 <https://github.com/Xitee1>`__: PR #8 *"Fix state updates dying
  due to dict iteration over apps/inputs"*.
- **@AquaCobell** & **@jerielsr**: issue #14, reporting entities unavailable
  after pairing on webOS 26 sets (blacklisted-certificate rejection).
- **@Ramss3s**: issue #13, reporting webOS 26 pairing failure on
  firmware 43.21.71.
- **@NoCleverMoniker** & **@starast**: issue #11, reporting the webOS 25
  pairing timeout caused by the library's ``hello`` handshake.
- **@brei-er**: PR #12, webOS 26 manifest compatibility
  (unsigned-manifest fallback, persisted compatibility mode).
- **@frenck**: security reviews that prompted ``is_allowed_path`` validation
  on the ``take_screenshot`` filename and notify ``icon`` path, and removing the
  screenshot button that wrote into the publicly served ``www`` directory.

|

.. raw:: html

   <p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/rule/end-dark.svg"><img alt="" src="https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/rule/end-light.svg" width="50%"></picture></p>

|

.. raw:: html

   <p align="right"><sub>jupiter.au</sub></p>

.. |i-monitor-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/monitor-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |i-monitor-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/monitor-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |i-signal-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/signal-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |i-signal-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/signal-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |i-bell-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/bell-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |i-bell-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/bell-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |i-play-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/play-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |i-play-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/play-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |i-sliders-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/sliders-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |i-sliders-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/sliders-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |i-filter-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/filter-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |i-filter-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/filter-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |i-pulse-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/pulse-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |i-pulse-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/pulse-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |i-switch-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/switch-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |i-switch-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/switch-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
