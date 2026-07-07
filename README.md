# PDF & 오디오 도구

PDF 분할, 오디오 변환·분할을 한 번에 처리하는 데스크톱 앱입니다.  
NotebookLM, Google Drive 등 파일 용량 제한이 있는 서비스에 올리기 전 처리에 유용합니다.

---

## 다운로드

→ [최신 버전 다운로드](https://github.com/jiyeonvis/media_splitter/releases/latest)

| 운영체제 | 파일 |
| --- | --- |
| Windows | `media_splitter_windows.zip` 압축 해제 → `media_splitter.exe` 실행 |
| macOS | `media_splitter_mac.zip` 압축 해제 → `media_splitter` 실행 |

---

## 기능 소개

### 탭 1 — PDF 용량 분할

용량이 큰 PDF를 지정한 크기 이하로 자동 분할합니다.  
예: 500MB PDF → 200MB 이하 파일 3개로 분할

- **최대 크기** 설정 (기본값: 200MB)
- **🔍 스캔** 버튼으로 분할이 필요한 파일 목록 미리 확인 가능
- 분할된 파일명: `원본파일명_part1.pdf`, `_part2.pdf` …

### 탭 2 — PDF 페이지 분할

PDF를 지정한 페이지 수 단위로 분할합니다.  
예: 300페이지 PDF → 50페이지씩 6개 파일로 분할

- **페이지 수** 설정 (기본값: 50페이지)

### 탭 3 — 오디오 → m4a 변환

mp3, wav, aac, flac, ogg, wma 등 다양한 오디오 파일을 m4a(AAC)로 변환합니다.

- **비트레이트** 선택: 64k / 96k / 128k / 192k / 256k (기본값: 128k)
  - 64k: 음성 통화 수준, 인터뷰 녹음에 충분
  - 128k: 대부분의 용도에 무난한 기본값
  - 256k: 고음질
- 이미 m4a인 파일은 자동으로 건너뜀
- 한글·공백이 포함된 파일명도 정상 처리

### 탭 4 — 오디오 용량 분할

오디오 파일을 지정한 용량 이하로 분할합니다.  
예: 300MB wav 파일 → 100MB 이하 파일 3개로 분할

- **최대 크기** 설정 (기본값: 100MB)
- 분할된 파일명: `원본파일명_part1.wav`, `_part2.wav` …

---

## 공통 기능

- **폴더 선택**: 폴더 안의 파일 전체를 한꺼번에 처리
- **파일 선택**: 특정 파일만 골라서 처리
- **하위 폴더 포함**: 체크하면 하위 폴더의 파일도 모두 처리
- **하위 폴더 구조 유지**: 출력 폴더에 원본과 동일한 폴더 구조로 저장
- **원본 삭제**: 처리 완료 후 원본 파일 자동 삭제
- **⏹ 강제중단**: 처리 중 언제든 중단 가능 (확인 팝업 후 중단)

---

## 처음 실행할 때 보안 경고 해제

### Windows

"Windows가 PC를 보호했습니다" 창이 뜨면:

1. **추가 정보** 클릭
2. **실행** 클릭

### macOS

"개발자를 확인할 수 없습니다" 창이 뜨거나 실행이 안 되면 터미널에서 아래 명령을 한 번 실행하세요.

```bash
xattr -rd com.apple.quarantine ~/Downloads/pdf_splitter
```

이후 정상 실행됩니다.

---

## 개발 환경에서 실행하기

```bash
pip3.13 install pymupdf pyqt6
python3.13 media_splitter.py
```

## 실행 파일 직접 빌드하기

```bash
pip install pymupdf pyqt6 pyinstaller

# macOS
pyinstaller --onedir --windowed --icon=icon.icns -y --add-binary "ffmpeg:." media_splitter.py

# Windows
pyinstaller --onefile --windowed --icon=icon.ico -y --add-binary "ffmpeg.exe;." media_splitter.py
```
