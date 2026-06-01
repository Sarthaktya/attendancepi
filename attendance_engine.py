from datetime import datetime
import csv
import os


class AttendanceEngine:
    def __init__(self, save_dir="attendance_logs"):
        self.records  = {}
        self.save_dir = save_dir

        os.makedirs(save_dir, exist_ok=True)

        timestamp      = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.file_path = os.path.join(save_dir, f"attendance_{timestamp}.csv")

        # Write the header immediately so the file exists from the start
        with open(self.file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "Time"])

    def mark_present(self, name):
        if name in self.records:
            return False

        time_now = datetime.now().strftime("%H:%M:%S")
        self.records[name] = time_now

        # Append immediately so data is not lost if the process crashes
        with open(self.file_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([name, time_now])

        return True

    def save_csv(self):
        # Rows are already written incrementally — just return the path
        return self.file_path
