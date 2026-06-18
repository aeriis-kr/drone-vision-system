# 윈도우 명령어 모음

## 설치&설정 명령어

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

### 프로젝트 클론
```powershell
git clone https://github.com/aeriis-kr/drone-vision-system
```

## 모델 다운로드 명령어
```powershell
cd drone-vision-system/vision_rx
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
