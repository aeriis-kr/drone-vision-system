# 윈도우 명령어 모음

## 설치&설정 명령어

### UV 설치
```powershell
# winget을 통한 uv 설치
winget install -e --id=astral-sh.uv
```
### PuTTY 설치
```powershell
# winget을 통한 Putty 설치
winget install -e --id=PuTTY.PuTTY
```

### FFmpeg 설치
```powershell
# winget을 통한 FFmpeg 설치
winget install -e --id Gyan.FFmpeg
```

### Git 설치
```powershell
# winget을 통한 Git 설치
winget install -e --id Git.Git
```

### VS Code 설치
```powershell
# winget을 통한 VSCode 설치
winget install -e --id Microsoft.VisualStudioCode
```

### 윈도우 방화벽 인바운드 UDP 5000 허용 (관리자 권한 실행 필요)
```powershell
# 설정
New-NetFirewallRule `
  -DisplayName "Allow UDP 5000 Inbound" `
  -Direction Inbound `
  -Protocol UDP `
  -LocalPort 5000 `
  -Action Allow

# 확인
Get-NetFirewallRule -DisplayName "Allow UDP 5000 Inbound"
```

## 예시 코드

### 간단한 코딩 YOLO 모델을 통한 object detection
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
## 모델 다운로드 명령어
```powershell
cd vision_rx
uv sync
uv run python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
uv run python -c "from ultralytics import YOLO; YOLO('yolo11n-pose.pt')"
```

## 드론 연동 명령어

### 노트북:
#### 객체 탐지
```powershell
# 객체 탐지
uv run vision-rx --port 5000
```

#### 객체 탐지 + pose
```powershell
# 객체 탐지 + pose
uv run vision-rx --port 5000 --model yolo11n-pose.pt
```

#### 객체탐지 + pose + 드론 제어
```powershell
# 객체탐지 + pose + 드론 제어
uv run vision-rx --port 5000 --control-host [드론 IP] --control-port
 5002
```

### 드론:
#### 영상전송
```powershell
# 영상전송
NO_INFERENCE=1 STREAM_HOST=[노트북 IP] make run-pose-inference-pi
```
#### 영상전송 + 제어 포트 개방
```powershell
# 영상전송 + 제어 포트 개방
AUTO_DRY_RUN=0 NO_INFERENCE=1 STREAM_HOST=[노트북 IP] make run-pose-control-pi
```
