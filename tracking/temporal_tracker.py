import time


class TemporalTracker:
    def __init__(self, min_duration=2.0):
        self.min_duration = min_duration
        self.first_seen   = {}
        self.marked       = set()
        self.last_name    = None   # tracks the previous frame's result

    def update(self, name):
        if name == "Unknown":
            self.last_name = None
            return False

        if name in self.marked:
            return False

        current_time = time.time()

        # Reset the timer whenever the recognised name changes.
        # This means the person must be seen CONTINUOUSLY for min_duration —
        # fragmented time from a flickering match no longer adds up.
        if name != self.last_name:
            self.first_seen[name] = current_time
            self.last_name = name
            return False

        elapsed = current_time - self.first_seen[name]
        if elapsed >= self.min_duration:
            self.marked.add(name)
            return True

        return False
