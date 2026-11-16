# Jacuzzi ProLink for Home Assistant

A Home Assistant integration for Jacuzzi spas fitted with the **ProLink WiFi
module**. It talks to the module directly over your local network, with no
cloud account, MQTT broker or extra hardware, so you can monitor and control
the spa from Home Assistant.

> **Status: early but working.** Developed and tested on a **Jacuzzi J-480**
> (UK, Celsius). It should work on other J-300/J-400 series spas with ProLink,
> but some readings may sit differently on other models. See
> [Tested on](#tested-on).

## What you get

### Controls

| Entity | What it does |
| --- | --- |
| Thermostat | Shows the water temperature, whether the spa is heating, and sets the target (18.5–40 °C in 0.5 ° steps, or 65–104 °F) |
| Heat mode | **Auto** (heat at all times), **Eco** (heat only 5pm–7am) or **Day** (heat only 7am–5pm) |
| Secondary filter | How often the secondary filtration runs: **Frequent**, **Infrequent** or **Away** |
| Jets 1, Jets 2 | Turn each set of jets on and off |
| Lights | On, off and brightness in the panel's five steps (20–100 %) |
| Sync spa clock | Sets the spa's date and clock to Home Assistant's local time |

### Sensors

| Entity | Notes |
| --- | --- |
| Water temperature, Target temperature | °C or °F, following the spa's own setting |
| Circulation pump, Pump 1, Pump 2 | Off / Low / High (single-speed jets show High when on) |
| Heating | Whether the heater is running |
| Filter cycle, ClearRay, Water flow | Running or not |
| Panel lock | Whether the topside panel is locked |
| Error, Error code | Spa error reporting (0 = no error) |
| Light brightness | 0–100 %, with colour mode and RGB as attributes |
| Connected, Last update | Whether the module is sending data |
| Diagnostics | Spa state, spa clock, WiFi state |

Hidden by default, because their meaning is not confirmed: Pump 3, plumbing
temperature, and the ClearRay, water and filter timers. Enable them under
**Settings → Entities** if you want to look at them.

The spa pushes its status several times a second, so entities update as soon
as something changes.

## Requirements

- Home Assistant 2025.1 or later (2026.3 or later to show the integration's icon)
- A Jacuzzi spa with a ProLink WiFi module on the same network as Home Assistant
- [HACS](https://hacs.xyz/)

## Install

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/jonjayaleisicle/ha-jacuzzi-prolink` with type
   **Integration**.
3. Search for **Jacuzzi ProLink**, download it, and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Jacuzzi ProLink**
   and enter the ProLink module's IP address. Leave the port at 4257.

Give the module a fixed IP address (a DHCP reservation on your router) so it
keeps the same address.

## Updating

When a new release is published, HACS offers it as an update like any other
integration: install it and restart Home Assistant.

HACS checks for updates periodically. To check straight away, open
**Jacuzzi ProLink** in HACS and choose ⋮ → **Update information**. If HACS
shows a version like `ef2626c` instead of a number like `0.6.0`, it installed
from a commit rather than a release; choose ⋮ → **Redownload** and pick the
latest release.

After updating, refresh your browser (Ctrl+Shift+R, or Cmd+Shift+R on a Mac)
if the icon or entity controls look out of date.

## Tips

### Keeping the spa clock right

The spa's clock drifts and resets after a power cut. To keep it in sync,
create an automation that presses **Sync spa clock** once a day, for example
at 03:00, and when the **Connected** sensor turns on.

### Why the spa isn't heating

In **Eco** the spa only heats between 5pm and 7am, and in **Day** only between
7am and 5pm. Outside those hours you can still change the target temperature,
but the heater waits for its window. Switch **Heat mode** to **Auto** to heat
straight away.

### How commands work

- **Target temperature, heat mode, secondary filter, lights and clock** are set directly to the value you
  ask for.
- **Jets** work by simulating a press of the panel's jets button, which
  toggles them. The integration only presses when the jets are not already in
  the state you asked for, so repeated clicks cannot switch them back.
- After every command, the integration waits a few seconds for the spa to
  report the change. If it does not, it assumes the connection has gone
  stale (the module can drop it without warning), reconnects, reads the spa's
  latest state, and sends the command once more only if the change still has
  not happened. If the spa still does not respond, you get an error.

## Troubleshooting

- **Entities unavailable / "Connected" off.** The ProLink module can doze off
  when the spa has been idle. The integration reconnects by itself; pressing a
  button on the topside panel usually wakes it.
- **Connection keeps dropping.** The module may accept only one connection at
  a time, so the Jacuzzi phone app could push Home Assistant off. Close the app
  and the integration reconnects within a few seconds.
- **"The spa did not respond to the command".** The command was sent twice
  and the spa never reported the change. Check the spa is powered and not
  locked at the panel, then try again.
- **Values look wrong.** Some readings may sit differently on other models.
  Please open an issue with the integration's diagnostics (device page → ⋮ →
  **Download diagnostics**; your IP address is redacted) and what the topside
  panel showed at the time. Diagnostics include the last 30 timestamped
  messages of each type and a log of every command sent, so note the time of
  anything you did.

### Capturing raw data without Home Assistant

`tools/capture.py` records what the module sends. It needs only Python 3.10+:

```bash
python3 tools/capture.py 192.168.1.50 --seconds 120 --out capture.txt
```

While it runs, write down what the topside panel shows and press a few
buttons, noting the time of each press. Disable the integration in Home
Assistant first, in case the module accepts only one connection at a time.

## Tested on

| Feature | J-480 (UK) |
| --- | --- |
| Water and target temperature | Confirmed |
| Setting the target temperature | Confirmed |
| Spa clock and date, Sync spa clock | Confirmed |
| Jets 1 and 2, separately and together | Confirmed |
| Lights on/off and brightness | Confirmed |
| Circulation pump | Confirmed |
| Light colours and cycle speeds | Not yet decoded |
| Heat mode reading (Auto / Eco / Day) | Confirmed |
| Heating indicator | Confirmed |
| Secondary filter reading (Frequent / Infrequent / Away) | Confirmed |
| Changing the heat mode and secondary filter | Confirmed |
| Primary filter cycle times | Not yet decoded |
| Filter cycle, ClearRay | Not confirmed |

Reports from other models are welcome. Open an issue with your model and a
diagnostics download.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

The protocol code (`protocol.py`) and the network client (`client.py`) have no
Home Assistant imports and can be tested on their own. Tests use frames
captured from real spas; see `tests/frames.py` for where each came from.

### Publishing a release

HACS shows release tags as version numbers and offers them as updates.

1. Set `version` in `custom_components/jacuzzi_prolink/manifest.json` to the
   new version, for example `0.6.0`, and push it to `main`.
2. On GitHub, open **Releases → Draft a new release**.
3. Under **Choose a tag**, type the same version with a `v` in front (for
   example `v0.6.0`), choose **Create new tag**, and target `main`.
4. Give it the same title, optionally choose **Generate release notes**, and
   select **Publish release**.

Keep the tag and the manifest version the same, so the version Home
Assistant reports matches the release.

## Credits

This builds on the reverse-engineering work of
[Jacuzzi-RS485](https://github.com/jackbrown1993/Jacuzzi-RS485) (whose
`protocol.py` this integration's protocol module is adapted from),
[pyjacuzzi](https://github.com/dhmsjs/pyjacuzzi),
[sundance780-jacuzzi-balboa-rs485-tcp](https://github.com/HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp),
[balboa_worldwide_app](https://github.com/ccutrer/balboa_worldwide_app) and
[pybalboa](https://github.com/garbled1/pybalboa). See `NOTICE`.

Not affiliated with or endorsed by Jacuzzi Inc. "Jacuzzi" and "ProLink" are
trademarks of their owners.

## License

Apache License 2.0.
