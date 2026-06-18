# Drone Vision System

교육용 드론 비전 시스템 레포지토리입니다.

- `pi5_tx/`: Raspberry Pi 5 카메라 캡쳐, H264 하드웨어 인코딩, UDP/RTP 전송, TCP기반 제어명령을 수신하여 mavlink 제어 실행.
- `vision_rx/`: FFmpeg 수신/디코딩, YOLO 추론, OpenCV 시각화, 제어 명령 전송.

## 교육 절차

### 1. 라즈베리파이 5 설정

라즈베리파이 SD카드를 AP 설정을 포함하여 이미징

라즈베리파이:

```bash
git clone https://github.com/aeriis-kr/drone-vision-system
cd drone-vision-system
make setup-pi
```
명령어를 실행하면 암호를 입력하라는 메세지가 표시되며 안내된 비밀번호를 입력합니다. (echo off 상태)

이 명령어는 아래 작업을 자동으로 수행합니다.
 - 시스템 패키지 업데이트
 - camera/FFmpeg/Python/uv등 프로젝트 의존성 설치,
 - system package 사용 가능한 uv 가상 환경 생성

### 2. 수신측(노트북) 설정

노트북:

윈도우 노트북은 다음 페이지를 참고하여 필요한 프로그램 설치와 프로그램 샐행 절차를 참고하세요.
[HOW_TO_SETUP_WINDOWS.md](HOW_TO_SETUP_WINDOWS.md)


```bash
make setup-rx
make run-rx
```

`make run-rx`
표시되는 송신측 명령어를 참고하여 연결 수행

```bash
STREAM_HOST=<receiver-ip> STREAM_PORT=5000 WIDTH=1280 HEIGHT=720 FPS=30 BITRATE=3000000 STREAM_FORMAT=mpegts make run-pi
```
