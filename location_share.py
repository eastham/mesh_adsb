#!/usr/bin/env python3
"""
This module provides classes for sharing and receiving location data over UDP.
Wire format is JSON.  See the __main__ block for example usage.

There are also some command-line capabilities...
To send a test location to port 8869, then exit:
python3 location_share.py --send_test_ip=localhost --send_test_port=8869

To listen for shared locations on port 6666, and print them out:
python3 location_share.py --port=6666
"""
import argparse
import socket
import sys
import time
import json
import logging

class LocationShare:
    """
    Object representing a single shared location observation.

    lat: Latitude in decimal degrees
    lon: Longitude in decimal degrees
    alt_ft_msl: Altitude in feet MSL
    timestamp: Unix timestamp in seconds UTC, when the location was recorded
    department: string - organization name
    unit_no: int - Unit/vehicle/target number, ideally unique per department
    name: string - Human-readable name of the object being tracked, if available
    """

    def __init__(self, lat: float, lon: float, alt_ft_msl: int,  # pylint: disable=too-many-arguments
                 timestamp: int, department: str, unit_no: int,
                 name: str = None):
        self.lat = lat
        self.lon = lon
        self.alt_ft_msl = alt_ft_msl
        self.timestamp = timestamp
        self.department = department
        self.unit_no = unit_no
        if name:
            self.name = name
        else:
            self.name = f"{department}_{unit_no}"

    @classmethod
    def from_dict(cls, location_dict):
        """ Create a LocationShare object from a dictionary."""
        loc = None
        try:
            loc = cls(**location_dict)
        except (KeyError, TypeError) as e:
            logging.error(f"Error creating LocationShare object: {e}")

        return loc

    def to_dict(self):
        """Return a dictionary representation of the object."""
        return vars(self)

    def to_json(self):
        """Return a JSON string representation of the object."""
        return json.dumps(self.to_dict())

class LocationSender:
    """Class that sends LocationShare objects to a specified IP and port."""
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def __del__(self):
        self.sock.close()

    def send_location(self, loc: LocationShare) -> int:
        """Send a LocationShare object, returns 0 on success."""
        try:
            location_json = loc.to_json()
            location_bytes = location_json.encode()
        except Exception as e:      # pylint: disable=broad-except
            logging.error(f"Error encoding location data: {e}")
            return -1

        try:
            self.sock.sendto(location_bytes, (self.ip, self.port))
        except Exception as e:      # pylint: disable=broad-except
            logging.error(f"Error sending location data: {e}")
            return -1

        return 0

class LocationReceiver:
    def __init__(self, ip: str, port: int, ip_whitelist: list = None):
        """Class for receiving LocationShare objects.
        
        ip: IP address to bind to
        port: Port to bind to
        ip_whitelist: List of IP addresses to accept data from. 
            If None, all IPs are accepted.
        """
        self.ip = ip
        self.port = port
        self.ip_whitelist = ip_whitelist

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.ip, self.port))

    def __del__(self):
        self.sock.close()

    def receive_location(self) -> LocationShare:
        """Blocking call, returns one location position, or None on failure."""
        try:
            RECV_LEN = 1024
            location_bytes, address = self.sock.recvfrom(RECV_LEN)

            if len(location_bytes) >= RECV_LEN:
                logging.warning(f"Received data len >= {RECV_LEN} bytes")
            if self.ip_whitelist and address[0] not in self.ip_whitelist:
                logging.error("Received data from unauthorized address: " + address[0])
                return None

            location_json = location_bytes.decode()
            location_dict = json.loads(location_json)
            loc = LocationShare.from_dict(location_dict)
            return loc
        except Exception as e:      # pylint: disable=broad-except
            logging.error(f"Error receiving shared location: {e}")
            return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Location Share')
    parser.add_argument('--port', type=int, default=6666,
                        help='The port to listen on.')
    parser.add_argument('--send_test_ip', type=str, default=None,
                        help='Send a test location to the given ip, then exit')
    parser.add_argument('--send_test_port', type=int, default=8869,
                        help='Port to send the test location to.')
    args = parser.parse_args()

    # Send a test location and exit
    if args.send_test_ip:
        sender = LocationSender(args.send_test_ip, args.send_test_port)
        ts = int(time.time())
        test_loc = LocationShare(40.8678983, -119.3353406, 4000, ts,
                                 "AIRPORT_TEST", 1, "Airport Truck #1")
        sender.send_location(test_loc)
        print(f"Sent test location to {args.send_test_ip}, exiting: ",
              f"{test_loc.to_json()}")
        sys.exit(0)

    # Listen for data and print it to stdout
    print(f"Listening for shared locations on port {args.port}")
    receiver = LocationReceiver("localhost", args.port, None)
    while True:
        received_loc = receiver.receive_location()
        if received_loc is not None:
            print("Received shared location: " + received_loc.to_json())
