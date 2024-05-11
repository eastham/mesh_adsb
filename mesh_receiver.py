"""
Subscribe to meshtastic position messages coming in on USB, 
and inject them into a readsb instance.

TODO: 
tar1090 display persists for 40s after packet received, too short?
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
        self.reconnect_counter = Counter(
            'reconnect', 'Number of reconnections')
        
        with open(icao_yaml_file, 'r') as file:
            self.icao_dict = yaml.safe_load(file)

        pub.subscribe(self.on_position_receive, "meshtastic.receive.position")
        pub.subscribe(self.on_receive, "meshtastic.receive")

    def on_position_receive(self, packet, interface):  # pylint: disable=unused-argument
        """called when a position packet arrives"""

        self.position_callback_counter.inc()
        if packet.get('fromId'):
            print(f" *** Position packet from: {packet['fromId']}")
            if packet['fromId'] in self.icao_dict:
                print(f" *** ICAO: {self.icao_dict[packet['fromId']]}")
                icao = int(self.icao_dict[packet['fromId']], 16)
            elif 'default' in self.icao_dict:
                icao = int(self.icao_dict['default'], 16)
            else:
                print(" *** No ICAO found for this ID " + packet['fromId'])
                return

        if packet.get('decoded'):
            if packet['decoded'].get('portnum') == 'POSITION_APP':
                pos = packet['decoded']['position']
                if pos.get('altitude') is None:
                    alt = self.icao_dict['default_alt']
                else:
                    alt = pos['altitude']
                print(f" *** icao {icao} lat: {pos['latitude']} lng: {pos['longitude']} ",
                      f"alt: {alt}")

                self.inject_position(icao,
                                     pos['latitude'],
                                     pos['longitude'],
                                     alt)
                self.position_decode_counter.inc()

    def on_receive(self, packet, interface):  # pylint: disable=unused-argument"""
        """Gets called for all packets, including position.
        Count and print all packets for debugging and liveness monitoring."""
        print(f"** Generic packet from: {packet['fromId']}")
        if packet.get('decoded'):
            decoded = packet['decoded']
            decoded_only = {x: decoded[x] for x in decoded if x != 'raw'}
            print(f"** Decoded packet: {decoded_only}")
        self.packet_callback_counter.inc()

    def inject_position(self, icao, lat, lon, alt):
        """Inject a position into readsb."""
        res1, res2 = ADSB_Encoder.encode(icao, lat, lon, alt)
        self.readsb.inject(res1, res2)
        self.readsb.inject(res1, res2)  # send twice to cause tar1090 rendering

    def build_test_packet(self):
        """Return a packet with a fake location for testing purposes."""
        test_pack = {}
        test_pack['fromId'] = '!cafebabe'
        test_pack['decoded'] = {}
        test_pack['decoded']['portnum'] = 'POSITION_APP'
        test_pos = test_pack['decoded']['position'] = {}
        test_pos['latitude'] = 40.7859839
        test_pos['longitude'] = -119.2470743
        test_pos['altitude'] = 4500
        return test_pack

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mesh Receiver.')
    parser.add_argument('--host', help='The readsb host to connect to.',
                        required=True)
    parser.add_argument('--port', type=int, default=30001,
                        help='The readsb port to connect to.')
    parser.add_argument('--test', action='store_true',
                        help='Inject a fake packet every 10s')
    parser.add_argument('--path', help='Path to icao_map.yaml',
                        default='icao_map.yaml')

    args = parser.parse_args()
    start_http_server(PROM_PORT)     # prometheus metrics

    print("running")

    mesh_receiver = MeshReceiver(args.host, args.port, args.path)

    try:
        iface = meshtastic.serial_interface.SerialInterface()
        while True:
            if args.test:
                test_packet = mesh_receiver.build_test_packet()
                mesh_receiver.on_position_receive(test_packet, None)
            if not hasattr(iface, "stream") or not iface.stream:
                print("Attempting reconnect to meshtastic")
                mesh_receiver.reconnect_counter.inc()
                iface = meshtastic.serial_interface.SerialInterface()
            time.sleep(10)
        iface.close()
    except Exception as ex:  # pylint: disable=broad-except
        print(f"Error: Connection problem: {ex}")
        sys.exit(1)
