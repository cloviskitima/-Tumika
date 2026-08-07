import cv2

from object_detector import detect_objects
from text_recognition import detect_text

image_path = "images/test_1.png"
image = cv2.imread(image_path)

#Object Detection
results = detect_objects(image)

print("\n==========OBJECTS==========\n")
for result in results:
    for box in result.boxes:
        cls = int(box.cls[0])
        confidence = float(box.conf[0])
        label = result.names[cls]

        print(f"{label} ({confidence:.2f})")

        x1, y1, x2, y2 = map(int, box.xyxy[0])

        cv2.rectangle(
            image,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )
        cv2.putText(
            image,
            f"{label} {confidence:.2f}",
            (x1, y1-10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2
        )

#Text Recognition
print("\n==========TEXT==========\n")

ocr_data = detect_text(image)

for i in range(len(ocr_data["text"])):
    text= ocr_data["text"][i].strip()
    if text == "":
        continue

    conf = float(ocr_data["conf"][i])

    if conf < 50:
        continue

    print(f"{text} ({conf:.2f})")
    x = ocr_data["left"][i]
    y = ocr_data["top"][i]
    w = ocr_data["width"][i]
    h = ocr_data["height"][i]

    cv2.rectangle(
        image,
        (x, y),
        (x + w, y + h),
        (255, 0, 0),
        2
    )

    cv2.putText(
        image,
        text,
        (x, y-10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 0, 0),
        2
    )

cv2.imwrite("output/result.png", image)
cv2.imshow("AI Vision Assistant", image)
cv2.waitKey(0)
cv2.destroyAllWindows()