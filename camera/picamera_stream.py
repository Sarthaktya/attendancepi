from picamera2 import Picamera2


class PiCameraStream:
    def __init__(self, size=(640, 480)):
        self.picam2 = Picamera2()

        # 🔥 Force BGR output directly
        config = self.picam2.create_preview_configuration(
            main={"size": size, "format": "BGR888"}
        )
        self.picam2.configure(config)
        self.picam2.start()

    def read(self):
        frame = self.picam2.capture_array()
        return True, frame   # ✅ NO color conversion

    def release(self):
        self.picam2.stop()
