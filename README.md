# Jacuzzi ProLink for Home Assistant

A Home Assistant integration for Jacuzzi spas fitted with the **ProLink WiFi
module**. It talks to the module directly over your local network, with no
cloud account, MQTT broker or extra hardware, and shows the spa's status in
Home Assistant.

> **Status: early, read-only.** This version only *listens* to the spa. It
> never sends commands, so it cannot change anything on your spa. Controls
> (set temperature, pumps, lights) are planned once the decoding has been
> confirmed on real hardware. Developed for a J-480, and should work on other
> J-300/J-400 series spas with ProLink.

## What you get

| Entity | Notes |
| --- | --- |
| Water temperature | °C or °F, following the spa's own setting |
| Target temperature | The set point |
| Plumbing temperature | Second sensor, in the plumbing (meaning not fully confirmed) |
| Circulation pump, Pump 1–3 | Off / Low / High |
| Filter cycle, ClearRay | Running or not (bit positions not fully confirmed) |
| Panel lock | Whether the topside panel is locked |
| Error, Error code | Spa error reporting (0 = no error) |
| Light brightness | Light colour mode and RGB as attributes |
| Connected, Last update | Whether the module is sending data |
| Diagnostics | Heat mode state, spa state, spa clock, WiFi state, and (disabled by default) ClearRay/water/filter timers |

Updates are pushed by the spa (several per second while awake), so entities
change as soon as the spa reports something new.

## Install with HACS

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/jonjayaleisicle/ha-jacuzzi-prolink` with type
   **Integration**.
3. Search for **Jacuzzi ProLink**, download it, and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Jacuzzi ProLink**
   and enter the ProLink module's IP address. Leave the port at 4257.

Give the module a fixed IP address (a DHCP reservation on your router) so it
keeps the same address.

## Troubleshooting

- **Entities unavailable / "Connected" off.** The ProLink module is known to
  doze off when the spa has been idle for a while. The integration reconnects
  by itself; pressing a button on the topside panel usually wakes it.
- **Values look wrong.** The protocol was reverse-engineered on other Jacuzzi
  models and some fields may sit differently on yours. Please open an issue
  with the integration's diagnostics (device page → ⋮ → **Download
  diagnostics**; your IP address is redacted) and what the topside panel
  showed at the time. The diagnostics include the raw frames the spa sent.

### Capturing raw data without Home Assistant

`tools/capture.py` records what the module sends. It needs only Python 3.10+:

```bash
python3 tools/capture.py 192.168.1.50 --seconds 120 --out capture.txt
```

While it runs, write down what the topside panel shows and press a few buttons,
noting the time of each press. Disable the integration in Home Assistant first,
in case the module accepts only one connection at a time.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

The protocol code (`protocol.py`) and the network client (`client.py`) have no
Home Assistant imports and can be tested on their own.

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
