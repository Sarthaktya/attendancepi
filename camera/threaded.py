import threading


class ThreadedCamera:
    """
    Wraps any camera (WebcamStream or PiCameraStream) and runs capture
    in a background thread. read() always returns the latest frame
    instantly — no blocking on camera I/O during inference.
    """

    def __init__(self, camera):
        self.camera  = camera
        self.ret     = False
        self.frame   = None
        self.stopped = False
        self.lock    = threading.Lock()

        # Start capture thread as daemon so it dies when main program exits
        thread = threading.Thread(target=self._capture_loop, daemon=True)
        thread.start()

        # Wait until the first real frame arrives before returning
        while self.frame is None:
            pass

    def _capture_loop(self):
        while not self.stopped:
            ret, frame = self.camera.read()

            with self.lock:
                self.ret   = ret
                self.frame = frame

    def read(self):
        with self.lock:
            return self.ret, self.frame

    def release(self):
        self.stopped = True
        self.camera.release()
