from ultralytics import YOLO

model = YOLO("yolov8n.pt")

def detect_objects(image):
    res = model(image)
    return res