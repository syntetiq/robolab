import cv2
import os
import sys

video_path = r"C:\RoboLab_Data\episodes\88a2aaf1-a3f8-4a46-9e93-2f7c13d82a5c\camera_2_external.mp4"
output_dir = r"c:\Users\max\Documents\Cursor\robolab\video_frames"

# Create output directory
os.makedirs(output_dir, exist_ok=True)

# Open video
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print(f"Error: Could not open video file {video_path}")
    sys.exit(1)

# Get video properties
fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
duration = total_frames / fps if fps > 0 else 0

print(f"Video properties:")
print(f"  FPS: {fps}")
print(f"  Total frames: {total_frames}")
print(f"  Duration: {duration:.2f} seconds")
print(f"  Resolution: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")

# Extract frames at different points
# Start (0%), 25%, 50%, 75%, and end (100%)
frame_positions = [0, 0.25, 0.5, 0.75, 1.0]
frame_names = ["start", "quarter", "middle", "three_quarter", "end"]

# Also extract frames every second for detailed analysis
frames_per_second = 1
total_seconds = int(duration)

print(f"\nExtracting frames...")

# Extract key position frames
for pos, name in zip(frame_positions, frame_names):
    frame_num = int(total_frames * pos) if pos < 1.0 else total_frames - 1
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    if ret:
        timestamp = frame_num / fps
        output_path = os.path.join(output_dir, f"frame_{name}_{timestamp:.2f}s.jpg")
        cv2.imwrite(output_path, frame)
        print(f"  Saved: {output_path}")

# Extract frames every second
for second in range(total_seconds + 1):
    frame_num = int(second * fps)
    if frame_num >= total_frames:
        break
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    if ret:
        output_path = os.path.join(output_dir, f"frame_{second:03d}s.jpg")
        cv2.imwrite(output_path, frame)
        print(f"  Saved frame at {second}s")

cap.release()
print(f"\nAll frames saved to: {output_dir}")
