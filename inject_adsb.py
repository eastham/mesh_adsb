"""Open a socket to readsb and send and ADS-B command (which is made up
of two sentences.)
"""

import socket
import argparse
import logging
from prometheus_client import Counter
logger = logging.getLogger(__name__)

class ReadsbConnection:
    """This class open a socket to readsb and enables sending ADS-B
    sentences to it."""
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

        self.sock = None
        self.connect_counter = Counter('connect',
                                       'Number of connection attempts')
        self.send_counter = Counter('send',
                                    'Number of messages sent')
        self.send_error_counter = Counter('send_error',
                                          'Number of send errors')

        if host:
            self.connect()
        else:
            logger.error('No host specified, skipping connection')

    def connect(self):
        """Open connection, return 0 on success, -1 on failure."""
        self.connect_counter.inc()
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info('connected to readsb')
            return 0
        except Exception as e:    # pylint: disable=broad-except
            logger.error(f'Error connecting to readsb: {e}')
        return -1

    def close(self):
        """Close the connection."""
        self.sock.close()
        logger.info('closed readsb connection')
        self.sock = None

    def send(self, message):
        """Send a message to the server, return 0 on success, -1 on failure."""
        self.send_counter.inc()
        try:
            self.sock.send(message)
            logger.debug('sent readsb message')
        except Exception as e:    # pylint: disable=broad-except
            self.send_error_counter.inc()
            logger.info(f'Error sending readsb message: {e}')
            return -1
        return 0

    def send_and_retry(self, message):
        """Send a message to the server, reconnect if necessary, 
        return 0 on success, -1 on failure."""
        if self.send(message):
            logger.info('readsb reconnecting')
            if self.connect():
                return -1
            return self.send(message)
        return 0

    def inject(self, arg1, arg2):
        """Format and send an ADS-B command to readsb."""
        message = f"*{arg1};\n*{arg2};\n"
        message = message.upper()
        # print(f"message: {message}")

        fail = self.send_and_retry(message.encode())
        if fail:
            logger.error('failed to send message')
            return -1
        return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Inject ADS-B data.')
    parser.add_argument('host', help='The host to connect to.')
    parser.add_argument('port', type=int, help='The port to connect to.')
    parser.add_argument('command1', help='The first command to inject.  '+
                        'String-encoded hex, all caps.')
    parser.add_argument('command2', help='The second command to inject.  '+
                        'String-encoded hex, all caps.')

    args = parser.parse_args()

    readsb = ReadsbConnection(args.host, args.port)
    readsb.inject(args.command1, args.command2)
