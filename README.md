Purpose: receive meshtastic position reports and push them into a readsb ads-b instance, with 
the intention that they be rendered via tar1090.  Meshtastic IDs are mapped to ICAO addresses
using the icao_map.yml file.

Setup: connect meshtastic device to local host via USB

Usage: mesh_receiver.py --host HOST [--port PORT]

