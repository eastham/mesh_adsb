"""
Subscribe to meshtastic position messages coming in on USB, 
and inject them into a readsb instance.

TODO: tar1090 display persists for 40s after packet received, too short?
"""

import sys
import time
import argparse
import yaml
from pubsub import pub
import meshtastic
import meshtastic.serial_interface
from prometheus_client import start_http_server, Counter

import ADSB_Encoder
import inject_adsb

PROM_PORT = 9091

class MeshReceiver:
    """Subscribe to meshtastic position messages coming in on USB,
    and inject them into a readsb instance."""

    def __init__(self, host: str, port: int, icao_yaml_file: str):
        """icao_yaml_file maps from meshtastic ids to icao addresses."""

        self.readsb = inject_adsb.ReadsbConnection(host, port)
        self.position_callback_counter = Counter(
            'position_callback', 'Number of position callbacks')
        self.position_decode_counter = Counter(
            'position_decode', 'Number of position decodes')
        self.packet_callback_counter = Counter(
            'packet_callback', 'All packets received')

        with open(icao_yaml_file, 'r') as file:
            self.icao_dict = yaml.safe_load(file)

        pub.subscribe(self.on_position_receive, "meshtastic.receive.position")
        pub.subscribe(self.on_receive, "meshtastic.receive")

    def on_position_receive(self, packet, interface):  # pylint: disable=unused-argument
        """called when a position packet arrives"""

        self.position_callback_counter.inc()
        if packet.get('fromId'):
            print(f"*** Position packet from: {packet['fromId']}")
            if packet['fromId'] in self.icao_dict:
                print(f"*** ICAO: {self.icao_dict[packet['fromId']]}")
                icao = int(self.icao_dict[packet['fromId']], 16)

        if packet.get('decoded'):
            if packet['decoded'].get('portnum') == 'POSITION_APP':
                pos = packet['decoded']['position']
                print(f"*** lat: {pos['latitude']} lng: {pos['longitude']} ",
                      f"alt: {pos['altitude']}")

                self.inject_position(icao,
                                     pos['latitude'],
                                     pos['longitude'],
                                     pos['altitude'])
                self.position_decode_counter.inc()

    def on_receive(self, packet, interface):  # pylint: disable=unused-argument
        """Count all packets for debugging and liveness monitoring."""
        print(f"** Generic packet from: {packet['fromId']}")
        print(f"** Packet contents: {packet}")
        self.packet_callback_counter.inc()

    def inject_position(self, icao, lat, lon, alt):
        """Inject a position into readsb."""
        res1, res2 = ADSB_Encoder.encode(icao, lat, lon, alt)
        self.readsb.inject(res1, res2)
        self.readsb.inject(res1, res2)  # send twice to cause tar1090 rendering


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mesh Receiver.')
    parser.add_argument('--host', help='The readsb host to connect to.')
    parser.add_argument('--port', type=int, default=30001,
                        help='The readsb port to connect to.')

    args = parser.parse_args()
    start_http_server(PROM_PORT)     # prometheus metrics

    print("running")

    mesh_receiver = MeshReceiver(args.host, args.port, 'icao_map.yaml')

    try:
        iface = meshtastic.serial_interface.SerialInterface()
        while True:
            time.sleep(1000)
        iface.close()
    except Exception as ex:  # pylint: disable=broad-except
        print(f"Error: Connection problem: {ex}")
        sys.exit(1)
