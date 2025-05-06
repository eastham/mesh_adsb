"""Keep an ordered queue of which trackers we've seen recently and at what 
time."""

import logging
import os
import json
import time
from typing import List

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.debug("Logging is set up.")

class TrackerStatus:
    def __init__(self, mesh_id: str, name: str, last_seen: int, shared_with_us: bool):
        self.mesh_id = mesh_id
        self.name = name
        self.last_seen = last_seen
        self.shared_with_us = shared_with_us # was shared over network

class TrackerQueue:
    def __init__(self, max_size: int = 100):
        self.queue: List[TrackerStatus] = []
        self.max_size = max_size

    def add_tracker(self, tracker: TrackerStatus):
        """Add a tracker to the queue, remove any existing tracker with the same 
        mesh_id, and sort by last_seen time. If the queue exceeds max_size, 
        remove the oldest."""

        # Remove any existing tracker with the same mesh_id
        self.queue = [t for t in self.queue if t.mesh_id != tracker.mesh_id]

        self.queue.append(tracker)
        self.queue.sort(key=lambda t: t.last_seen, reverse=True)

        if len(self.queue) > self.max_size:
            removed_tracker = self.queue.pop()
            logger.debug(f"Removed oldest tracker: {removed_tracker.mesh_id}")

    def get_trackers(self) -> List[TrackerStatus]:
        return self.queue.copy()

    def clear(self):
        self.queue.clear()

    def save_to_file(self, filename: str):
        with open(filename, 'w') as f:
            json.dump([tracker.__dict__ for tracker in self.queue], f)

    def load_from_file(self, filename: str):
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    trackers = json.load(f)
                    for tracker in trackers:
                        self.add_tracker(TrackerStatus(**tracker))
            except json.JSONDecodeError as e:
                logger.debug(f"Error decoding JSON from file {filename}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error while loading file {filename}: {e}")
        else:
            logger.debug(f"File {filename} does not exist. No trackers loaded.")
        logger.debug(f"Loaded {len(self.queue)} trackers from file.")

    def format_nth_entry(self, n: int) -> str:
        if n < 0 or n >= len(self.queue):
            return ""
        tracker = self.queue[n]
        id = tracker.mesh_id[-4:]
        if tracker.shared_with_us:
            id = id + "*"
        latency = int(time.time() - tracker.last_seen)
        if latency >= 100:
            latency = "xx"
        return f"{id} {latency}"
