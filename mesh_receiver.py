"""
Subscribe to meshtastic position messages coming in on USB, 
and inject them into a readsb instance.

TODO: 
tar1090 display persists for 40s after packet received, too short?
"""

import sys
import time
import argparse
import threading
from queue import Queue
import yaml

from pubsub import pub
import meshtastic
import meshtastic.serial_interface
from prometheus_client import start_http_server, Counter

import ADSB_Encoder
import inject_adsb
from location_share import LocationReceiver, LocationSender, LocationShare

PROM_PORT = 9091

class MeshReceiver:
    """Subscribe to meshtastic position messages coming in on USB,
    and inject them into a readsb instance."""

    def __init__(self, host: str, port: int, icao_yaml_file: str,
                 share_ip: str, share_port: int):
        """icao_yaml_file maps from meshtastic ids to icao addresses.
        share_* will additioanlly send the locations via UDP to another server."""

        self.readsb = inject_adsb.ReadsbConnection(host, port)
        self.position_callback_counter = Counter(
            'position_callback', 'Number of position callbacks')
        self.position_decode_counter = Counter(
            'position_decode', 'Number of position decodes')
        self.packet_callback_counter = Counter(
            'packet_callback', 'All packets received')
        self.reconnect_counter = Counter(
            'reconnect', 'Number of reconnections to meshtastic device')
        self.xmit_fail_counter = Counter(
            'xmit_fail', 'Number of failed sends to readsb')
        self.known_trackers_counter = Counter(
            'known_trackers', 'Recognized devices seen', ['icao', 'name'])
        self.all_trackers_counter = Counter(
            'all_trackers', 'All devices seen', ['id'])
        self.shared_locations_out_counter = Counter(
            'shared_locs_out', 'Shared locations sent to internet')
        self.shared_locations_out_error_counter = Counter(
            'shared_locs_out_error', 'Shared location send errors')

        with open(icao_yaml_file, 'r', encoding='utf-8') as file:
            self.icao_dict = yaml.safe_load(file)

        if share_ip:
            self.location_sender = LocationSender(share_ip, share_port)
        else:
            self.location_sender = None

        pub.subscribe(self.on_position_receive, "meshtastic.receive.position")
        pub.subscribe(self.on_receive, "meshtastic.receive")

    def on_position_receive(self, packet, interface):  # pylint: disable=unused-argument
        """Called when a position packet arrives from meshtastic."""

        self.position_callback_counter.inc()
        self.handle_position_packet(packet, True)

    def get_icao_for_packet(self, packet):
        """Get the corresponding ICAO for the sender of this packet according to yaml."""

        if not packet.get('fromId'):
            return None
        from_id = packet['fromId']

        print(f" *** Translating packet from: {from_id}")
        self.all_trackers_counter.labels(id=from_id).inc()

        if from_id[0] != '!':
            # Non-meshtastic ID, just use it as-is. (from test or share)
            icao = int(from_id, 16)
            print(f" *** Non-meshtastic ID: {hex(icao)}")
        elif from_id in self.icao_dict:
            # Translate from meshtastic ID to our ICAO space
            icao = int(self.icao_dict[from_id], 16)
            print(f" *** Got ICAO from yaml: {hex(icao)}")
        elif 'default' in self.icao_dict:
            icao = int(self.icao_dict['default'], 16)
            print(f" *** Using default ICAO: {hex(icao)}")
        else:
            print(" *** No ICAO mapping found for this ID: " +
                    from_id + ", not sending")
            return None
        return icao

    def get_names_for_packet(self, packet, icao: int):
        """Return the familiar name and unit number for a packet, either
        from the yaml (if mesh) or from the packet itself (if not)."""
        try:
            start = int(self.icao_dict['icao_start'], 16)
            share_start = int(self.icao_dict['icao_share_start'], 16)
            if icao < share_start:
                return (self.icao_dict[hex(icao)], icao - start)

            return (packet['familiar_name'], packet['unit_no'])
        except KeyError:
            return ("UNKNOWN", 0)

    def handle_position_packet(self, packet, share: bool):
        """Inject the position into readsb, and also send it to
        location share if we have one."""

        icao = self.get_icao_for_packet(packet)
        if not icao:
            print(" *** No fromId in packet, not sending")
            return
        (familiar_name, unit_no) = self.get_names_for_packet(packet, icao)

        print(f" *** Translated packet names: {hex(icao)}->{familiar_name} unit {unit_no}")
        self.known_trackers_counter.labels(icao=icao,
                                           name=familiar_name).inc()

        # Sanity checks, these do sometimes occur
        if (not packet.get('decoded') or
            packet['decoded'].get('portnum') != 'POSITION_APP'):
            print(" *** Not a position packet, not sending")
            return
        pos = packet['decoded']['position']
        if not pos.get('latitude') or not pos.get('longitude'):
            print(" *** No lat or long in position packet")
            return

        if pos.get('altitude') is None:
            alt = self.icao_dict['default_alt']
        else:
            alt = int(pos['altitude'] * 3.28084) # meters to feet

        # We have a good position
        self.position_decode_counter.inc()
        print(f" *** icao {icao} lat: {pos['latitude']} lng: {pos['longitude']} ",
              f"alt: {alt}")

        # Send position to ADS-B stream
        self.inject_position(icao, pos['latitude'], pos['longitude'], alt)

        # Send position to others over the internet
        if share and self.location_sender:
            self.send_to_location_share(pos, alt, familiar_name, unit_no)

    def send_to_location_share(self, pos, alt, familiar_name, unit_no):
        """Send the position to the location share server."""
        ts = int(time.time())
        locshare = LocationShare(pos['latitude'],
                                 pos['longitude'],
                                 alt, ts, "AIRPORT", unit_no,
                                 familiar_name)
        result = self.location_sender.send_location(locshare)
        if result:
            print("Error sharing location data to internet")
            self.shared_locations_out_error_counter.inc()
        else:
            print(f"Shared location to internet: {locshare.to_json()}")
            self.shared_locations_out_counter.inc()

    def on_receive(self, packet, interface):  # pylint: disable=unused-argument
        """Gets called for all packets, including position.
        Count and print all packets for debugging and liveness monitoring."""

        print(f"** FYI, generic packet from: {packet['fromId']}")
        if packet.get('decoded'):
            decoded = packet['decoded']
            decoded_only = {x: decoded[x] for x in decoded if x != 'raw'}
            print(f"** Decoded packet: {decoded_only}")
        self.packet_callback_counter.inc()

    def inject_position(self, icao, lat, lon, alt):
        """Inject a position into readsb."""

        sentence1, sentence2 = ADSB_Encoder.encode(icao, lat, lon, alt)
        ret1 = self.readsb.inject(sentence1, sentence2)
        ret2 = self.readsb.inject(sentence1, sentence2)  # send twice to force tar1090 rendering
        if ret1 + ret2:
            self.xmit_fail_counter.inc()
            print("Failed to send position to readsb")
        return ret1 + ret2

    def build_test_packet(self):
        """Return a packet with a fake location for testing purposes."""
        test_pack = {}
        test_pack['fromId'] = '!cafebabe'
        test_pack['decoded'] = {}
        test_pack['decoded']['portnum'] = 'POSITION_APP'
        test_pos = test_pack['decoded']['position'] = {}
        test_pos['latitude'] = 40.7859839
        test_pos['longitude'] = -119.2470743
        test_pos['altitude'] = 4000 / 3.28084   # feet to meters
        return test_pack

    def build_packet_from_shared_location(self, loc: LocationShare):
        """Return a packet with a location based on the LocationShare position."""

        pack = {}

        # Set the fromId to be in the shared ICAO range as defined in the yaml.
        share_start = int(self.icao_dict['icao_share_start'], 16)
        share_end = int(self.icao_dict['icao_share_end'], 16)
        pack['fromId'] = share_start + loc.unit_no
        if pack['fromId'] > share_end:
            print("Error: unit_no exceeds icao_end")
            pack['fromId'] = share_end
        pack['fromId'] = hex(pack['fromId'])

        pack['unit_no'] = loc.unit_no
        pack['familiar_name'] = loc.name
        pack['decoded'] = {}
        pack['decoded']['portnum'] = 'POSITION_APP'
        pos = pack['decoded']['position'] = {}
        pos['latitude'] = loc.lat
        pos['longitude'] = loc.lon
        pos['altitude'] = int(loc.alt_ft_msl / 3.28084)  # feet to meters
        return pack

class LocationShareInputThread:     # pylint: disable=too-few-public-methods
    """Thread to receive shared locations from the internet and put them in a queue."""
    def __init__(self, port: int, shared_location_q: Queue):
        if not port:
            return
        self.location_receiver = LocationReceiver("localhost", port)
        self.shared_location_q = shared_location_q

        self.shared_locations_in_counter = Counter(
            'shared_locs_in', 'Shared locations received from internet')
        self.shared_locations_in_error_counter = Counter(
            'shared_locs_in_error', 'Shared location errors')

        self.thread = threading.Thread(target=self.monitor_location_receiver)
        self.thread.start()

    def monitor_location_receiver(self):
        """Loop to receive shared locations and put them in the shared_location_q.
        This is a separate thread."""
        while True:
            loc = self.location_receiver.receive_location()     # blocks
            if loc:
                print(f"Received shared location: {loc.to_json()}")
                self.shared_location_q.put(loc)
                self.shared_locations_in_counter.inc()
            else:
                self.shared_locations_in_error_counter.inc()
            time.sleep(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mesh Receiver.')
    parser.add_argument('--host', help='The readsb host to connect to.',
                        required=True)
    parser.add_argument('--port', type=int, default=30001,
                        help='The readsb port to connect to.')
    parser.add_argument('--share_input_port', type=int)
    parser.add_argument('--share_output_ip', type=str)
    parser.add_argument('--share_output_port', type=int)
    parser.add_argument('--test', action='store_true',
                        help='Inject a fake packet every 10s')
    parser.add_argument('--path', help='Path to icao_map.yaml',
                        default='icao_map.yaml')

    args = parser.parse_args()
    if (args.share_output_ip and not args.share_output_port) or \
            (args.share_output_port and not args.share_output_ip):
        print("Error: Must specify both share_output_ip and share_output_port")
        sys.exit(1)

    start_http_server(PROM_PORT)     # prometheus metrics

    print("running")

    shared_location_queue = Queue()
    location_receive_thread = LocationShareInputThread(args.share_input_port,
                                                       shared_location_queue)
    mesh_receiver = MeshReceiver(args.host, args.port, args.path,
                                 args.share_output_ip, args.share_output_port)

    # Main loop.  Note, the most important work is done in callbacks, not here.
    try:
        iface = meshtastic.serial_interface.SerialInterface()
        while True:
            # Handle loss of serial connection to mesh device
            if not hasattr(iface, "stream") or not iface.stream:
                print("Attempting reconnect to meshtastic")
                mesh_receiver.reconnect_counter.inc()
                iface = meshtastic.serial_interface.SerialInterface()

            # Got a shared location over the IP network
            if shared_location_queue.qsize() > 0:
                queue_loc = shared_location_queue.get()
                print(f"de-q shared location: {queue_loc.to_json()}")
                shared_packet = mesh_receiver.build_packet_from_shared_location(queue_loc)
                mesh_receiver.handle_position_packet(shared_packet, False)

            if args.test:
                test_packet = mesh_receiver.build_test_packet()
                mesh_receiver.handle_position_packet(test_packet, False)

            time.sleep(1)
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error: Connection problem: {e}")
        sys.exit(1)
