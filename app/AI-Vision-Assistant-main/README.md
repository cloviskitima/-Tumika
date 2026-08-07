# 🤖 AI Vision Assistant

An AI-powered computer vision application that combines **YOLOv8 Object Detection** and **Tesseract OCR** to detect objects and recognize text from images.

---

## 📌 Overview

AI Vision Assistant processes an input image using two computer vision techniques:

- **Object Detection** with YOLOv8 to identify and locate objects.
- **Optical Character Recognition (OCR)** with Tesseract to extract text from the image.

The application annotates the image with bounding boxes and labels while displaying detected objects and recognized text in the terminal.

---

## ✨ Features

- 🔍 Object detection using YOLOv8
- 📝 Text recognition using Tesseract OCR
- 📦 Bounding boxes around detected objects
- 📄 Bounding boxes around detected text
- 💾 Saves the annotated output image
- ⚡ Fast and lightweight implementation

---

## 🛠️ Tech Stack

- Python
- OpenCV
- YOLOv8 (Ultralytics)
- Tesseract OCR
- NumPy

---

## 📂 Project Structure

```text
AI-Vision-Assistant/
│
├── images/
│   └── sample.jpg
│
├── output/
│   └── result.png
│
├── object_detector.py
├── text_recognition.py
├── main.py
├── requirements.txt
├── .gitignore
└── README.md
```

---

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/Aayan165/AI-Vision-Assistant.git
cd AI-Vision-Assistant
```

### 2. Create a virtual environment (Optional but recommended)

**Windows**

```bash
python -m venv venv
venv\Scripts\activate
```

**Linux / macOS**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install the required packages

```bash
pip install -r requirements.txt
```

### 4. Install Tesseract OCR

Download and install Tesseract OCR from:

https://github.com/UB-Mannheim/tesseract/wiki

After installation, update the Tesseract path in `text_recognition.py`:

```python
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

---

## ▶️ Usage

Place your image inside the `images` folder.

Example:

```text
images/
└── sample.jpg
```

Run the application:

```bash
python main.py
```

---

## 📊 Example Output

### Terminal

```text
========== OBJECTS ==========

Person (0.98)
Laptop (0.95)
Bottle (0.92)

========== TEXT ==========

FAST
University
Computer
Lab
```

### Image Output

The processed image is saved inside:

```text
output/result.png
```

The output image contains:

- 🟩 Green bounding boxes for detected objects.
- 🟦 Blue bounding boxes for recognized text.

---

## 📸 Sample Results

Example:

```
Original Image
```

<img width="1408" height="768" alt="test_1" src="https://github.com/user-attachments/assets/a808ec00-8a07-4192-bffa-bcd028721eb8" />


```
Detected Output
```

<img width="1408" height="768" alt="result" src="https://github.com/user-attachments/assets/76251e0e-a3b7-4c2a-84b6-7aeb01b1650a" />


---

## 🚀 Future Improvements

- 🎥 Real-time webcam object detection
- 📹 Video processing support
- 🔊 Text-to-Speech for detected text
- 🌐 Streamlit or Gradio web interface
- 🤖 Upgrade to newer YOLO models
- 📄 Export OCR results to PDF or CSV
- 📍 OCR only on detected regions for improved accuracy

---

## 👨‍💻 Author

**Syed Aayan Mahmood**

- GitHub: https://github.com/Aayan165

---

## 📄 License

This project is intended for educational and learning purposes.
