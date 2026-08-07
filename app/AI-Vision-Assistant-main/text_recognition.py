import cv2
from matplotlib import image
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

def detect_text(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    data = pytesseract.image_to_data(
        gray,
        output_type=pytesseract.Output.DICT,
        config="--psm 6"
    )

    return data

# image = cv2.imread("images/test_1.png")



# n = len(data["text"])

# for i in range(n):
#     text = data["text"][i].strip()

#     conf = float(data["conf"][i])

#     if conf > 50 and text !="":
#         x = data["left"][i]
#         y = data["top"][i]
#         w = data["width"][i]
#         h = data["height"][i]

#         cv2.rectangle(image, (x,y), (x+w, y+h), (255, 0, 0), 2)

#         cv2.putText(
#             image,
#             text,
#             (x, y-10),
#             cv2.FONT_HERSHEY_SIMPLEX,
#             0.6,
#             (255, 0, 0),
#             2
#         )

#         print(f"{text} ({conf:.2f}%)")

# cv2.imshow("OCR Detection", image)
# cv2.waitKey(0)
# cv2.destroyAllWindows()