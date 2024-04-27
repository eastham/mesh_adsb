Purpose: receive meshtastic position reports over serial/USB and push them into a readsb ads-b TCP port, with 
the intention that they be rendered via tar1090.  Meshtastic IDs are mapped to ICAO addresses
using the icao_map.yml file.

Setup: connect meshtastic device to local host via USB

Usage: mesh_receiver.py --host READSB_HOST [--port READSB_PORT]

