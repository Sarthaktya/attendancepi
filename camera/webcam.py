import cv2


class WebcamStream:
    def __init__(self, size=(640, 480), camera_index=0):
        width, height = size

        self.cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        if not self.cap.isOpened():
            raise RuntimeError("Could not open webcam.")

    def read(self):
        ret, frame = self.cap.read()
        return ret, frame   # frame is BGR (OpenCV default)

    def release(self):
        self.cap.release()
