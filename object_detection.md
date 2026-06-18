# 객체 탐지를 위한 간단한 코딩

### 1. UV 설치
```powershell
# winget을 통한 uv 설치
winget install -e --id=astral-sh.uv
```

### 2. VS Code 설치
```powershell
# winget을 통한 VSCode 설치
winget install -e --id Microsoft.VisualStudioCode
```

## 3. 파워쉘 재실행

## 4. uv 프로젝트 생성
```powershell
uv init object_detection
cd object_detection
uv add opencv-python ultralytics
code .
```

## 5. YOLO 모델을 통한 객체 탐지
```python
import cv2
from ultralytics import YOLO

def main():
    model = YOLO("yolo11n.pt”)
    # 웹캠 열기: 기본 웹캠은 0, 외장 웹캠은 1 또는 2일 수 있음
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        print("웹캠을 열 수 없습니다.")
        return
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    print("YOLO 웹캠 감지를 시작합니다. 종료하려면 q 키를 누르세요.")

    while True:
        ret, frame = cap.read()
        
        if not ret:
            print("프레임을 읽을 수 없습니다.")
            break
        
        results = model(
            frame,
            conf=0.4,
            imgsz=640,
            verbose=False
        )
        
        annotated_frame = results[0].plot()
        cv2.imshow("YOLO Object Detection - Webcam", annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
```
