import cv2

for i in range(0, 36):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        print(f"Camera works at index {i}")
        cap.release()
