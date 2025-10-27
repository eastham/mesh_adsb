# Meshtastic ADS-B Bridge

A Python application that receives position reports from Meshtastic mesh network devices and injects them into an ADS-B receiver (readsb/tar1090) and/or other UDP endpoint. This enables tracking of ground vehicles, equipment, or personnel on a Meshtastic mesh network using standard ADS-B visualization tools.

## Features

- Receives Meshtastic position packets over USB/serial
- Translates positions to ADS-B Mode S format (DF17)
- Injects into readsb for rendering on tar1090
- Maps Meshtastic device IDs to ICAO addresses
- UDP-based location sharing between multiple instances
- Prometheus metrics for monitoring
- Persistent device tracking and statistics

## Components

- **mesh_receiver.py** - Main application that subscribes to Meshtastic position messages and coordinates all functions
- **ADSB_Encoder.py** - Encodes position data into ADS-B Mode S format with CPR (Compact Position Reporting)
- **inject_adsb.py** - TCP client for connecting to and sending data to readsb
- **location_share.py** - UDP-based location sharing for networked instances
- **tracker_stats.py** - Device tracking and persistence utility
- **icao_map.yaml** - Configuration mapping Meshtastic IDs to ICAO addresses and device names

## Prerequisites

- Python 3.8+
- Meshtastic device connected via USB
- readsb/tar1090 installation (or compatible ADS-B receiver accepting Beast format on TCP)

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd mesh_adsb
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your ICAO mappings in `icao_map.yaml`:
```yaml
icao_map:
  "!abc12345": 0xADF800  # Example device ID to ICAO mapping
default_altitude: 3900    # Default altitude in feet MSL
device_names:
  "!abc12345": "Device 1"
```

## Usage

### Basic Usage

Connect your Meshtastic device via USB and run:

```bash
python mesh_receiver.py --host READSB_HOST [--port READSB_PORT]
```

**Arguments:**
- `--host` - IP address or hostname of readsb server (required)
- `--port` - TCP port for readsb (default: 30001)
- `--icao_yaml` - Path to ICAO mapping file (default: icao_map.yaml)
- `--share_output_ip` - IP address to send location shares via UDP (optional)
- `--share_output_port` - UDP port for location sharing (default: 8869)
- `--share_recv_whitelist` - Comma-separated list of IPs to accept location shares from (optional)

### Location Sharing

To enable location sharing between multiple instances:

**Sender:**
```bash
python mesh_receiver.py --host READSB_HOST --share_output_ip REMOTE_IP
```

**Receiver:**
```bash
python mesh_receiver.py --host READSB_HOST --share_recv_whitelist IP1,IP2
```

### Standalone Location Share Testing

```bash
# Send test position
python location_share.py --send_test_ip TARGET_IP

# Receive positions
python location_share.py --recv_test
```

## Monitoring

Prometheus metrics are exposed on port 9091:
- Position packet counters
- Injection success/failure rates
- Device tracking statistics
- Location share send/receive counts

Access metrics at: `http://localhost:9091/metrics`

## Configuration

The `icao_map.yaml` file contains:
- **icao_map**: Dictionary mapping Meshtastic device IDs to ICAO addresses
- **default_altitude**: Default altitude in feet MSL for positions without altitude data
- **device_names**: Human-readable names for devices (used in logging)
- **shared_icao_map**: Range of ICAO addresses for shared positions from remote instances

## How It Works

1. mesh_receiver connects to a Meshtastic device via USB and subscribes to position messages
2. When a position packet is received, the device ID is looked up in icao_map.yaml
3. The position is encoded into ADS-B Mode S format using CPR encoding
4. Two frames (even/odd) are generated and sent to readsb via TCP (Beast format)
5. readsb processes the data and makes it available to tar1090 for visualization
6. Optionally, positions can be shared to other instances via UDP for multi-site coverage

## Credits

ADS-B encoding implementation derived from:
- Nick Foster (gr-air-modes)
- Junzi Sun (TU Delft)
- Wolfgang Nagele
- Joel Addison

## License

GNU General Public License v3.0

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
