# IHC RS232 MQTT Bridge

Connects your LK/Gardy IHC Controller to Home Assistant via RS232 and MQTT.

## Configuration

### Serial Port
- Default: `/dev/ttyUSB0`
- Find your device: Check Supervisor → System → Hardware
- Common values:
  - `/dev/ttyUSB0` - USB to RS232 adapter
  - `/dev/ttyAMA0` - GPIO UART on Raspberry Pi
  - `/dev/serial/by-id/...` - Persistent device name

### MQTT Settings
- **Host**: Usually `core-mosquitto` if using Mosquitto add-on
- **Port**: Default 1883
- **Username/Password**: Optional, leave empty if not required
- **Topic**: Base topic for all entities (default: `ihc`)

### IHC Settings
- **Output Modules**: Number of output modules (1-16, default: 8)
  - Each module has 8 outputs
- **Input Modules**: Number of input modules (1-16, default: 4)
  - Each module has 16 inputs
- **Poll Interval**: How often to poll status (1-30 seconds, default: 2)

## Hardware Connection

```
IHC Controller RS232 Port
    ↓
USB to RS232 Adapter (DB9)
    ↓
Raspberry Pi USB Port
```

## Home Assistant Integration

After starting the add-on:
1. Go to **Settings → Devices & Services → MQTT**
2. All IHC entities will appear automatically via MQTT Discovery
3. Outputs appear as **Switches** (ihc/output/MODULE/OUTPUT)
4. Inputs appear as **Binary Sensors** (ihc/input/MODULE/INPUT)

## Troubleshooting

### Serial device not found
- Check the logs to see available devices
- Go to Supervisor → System → Hardware to find your device
- Try `/dev/ttyUSB0`, `/dev/ttyUSB1`, etc.

### No MQTT connection
- Ensure Mosquitto broker add-on is installed and running
- Check MQTT username/password if authentication is enabled

### No entities in Home Assistant
- Check add-on logs for errors
- Verify MQTT broker is working: Settings → Devices & Services → MQTT
- Wait 1-2 minutes for discovery to complete

## Support

For issues and questions, visit:
https://github.com/JOUW_USERNAME/homeassistant-ihcRS232-addon/issues