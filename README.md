# 옛한글 OCR — Toolforge 판

위키문헌(ko.wikisource.org)의 옛한글 스캔을 읽는 도구를 [Toolforge](https://wikitech.wikimedia.org/wiki/Help:Toolforge)에서 돌리는 묶음입니다.
모델(ONNX, CPU)은 **서버에서** 돌고, 위키문헌 편집 창의 소도구와 영역 지정 화면이 서버에 묻습니다.

| 도구 | 무엇 | 주소 |
|---|---|---|
| OCR 소도구 | 「페이지:」 편집 창에서 그 쪽 스캔을 읽어 편집 상자에 넣음 | `ocr.js` |
| 전사대조 소도구 | 이미 전사된 글을 스캔과 맞대어 틀렸을 만한 글자를 짚음 | `compare.js` |
| 영역 지정 | 스캔 위에 상자를 쳐서 그 열 · 글자만 읽음 | `area/` |

이 폴더는 프로젝트의 `python 툴포지/만들기.py` 가 만든 것입니다. **손으로 고치지 마세요.**

---

## 올리는 차례

### 처음 한 번만

1. **도구 만들기** — <https://toolsadmin.wikimedia.org/> 에 로그인 → 'Tools' → 'Create new tool'.
   이름은 **`old-hangul-ocr`**(GitHub 저장소 `old-hangul-OCR` 과 맞춤 — 만든 뒤에는 못 바꿉니다). 도구 주소가 `https://old-hangul-ocr.toolforge.org/` 가 됩니다.
2. **SSH 열쇠 등록** — PowerShell 에서 한 줄씩:
   ```
   ssh-keygen -t ed25519
   ```
   ```
   Get-Content $HOME\.ssh\id_ed25519.pub
   ```
   나온 한 줄(`ssh-ed25519 …`)을 toolsadmin 의 내 설정 → 'SSH keys' 에 붙여 넣습니다.
3. **GitHub 브랜치 만들기** — 브라우저판과 같은 공개 저장소(`ysjbserver/old-hangul-OCR`)에 **`toolforge-test` 브랜치**를 하나 만듭니다.
   GitHub Desktop 에서 'Current branch' → 'New branch' → 이름 `toolforge-test`. 이 브랜치에는 Toolforge 묶음만 둡니다
   (브라우저판 파일은 지움 — `main` · `beta-test` 의 브라우저판 · jsDelivr 주소는 그대로).
   Toolforge 판이 자리 잡으면 이 내용을 `main` 으로 옮깁니다 — 그 뒤로는 `main` 에 올리고 빌드 명령의 `--ref …` 를 뺍니다.
   ⚠ 그때도 태그 `v1`~`v3.2` 는 지우지 마세요(그 주소로 브라우저판을 쓰는 사람이 있을 수 있음).
   Toolforge 의 빌드 서비스는 공개 저장소에서만 받아 갑니다.

### 올릴 때마다

1. 프로젝트 폴더에서:
   ```
   python 툴포지/만들기.py
   ```
   (`python 브라우저판/내보내기.py` 를 돌렸다면 이미 저절로 돌았습니다.)
2. GitHub Desktop 에서 **`toolforge-test` 브랜치로 바꾼 뒤**, `old-hangul-ocr-toolforge/` 의 파일을 **전부** 저장소 폴더에 복사하고
   (같은 이름은 덮어쓰기) 커밋 · 푸시. ⚠ 다른 브랜치(`beta-test` 등)에 올리지 않게 브랜치 이름을 먼저 확인하세요.
3. Toolforge 에 들어가기 — PowerShell 에서(`<내 이름>` 은 toolsadmin 의 'Shell username'):
   ```
   ssh <내 이름>@login.toolforge.org
   ```
   ```
   become old-hangul-ocr
   ```
4. 빌드 — 몇 분 걸립니다:
   ```
   toolforge build start https://github.com/ysjbserver/old-hangul-OCR --ref toolforge-test
   ```
   끝났는지 보기(`ok` 가 나오면 됨):
   ```
   toolforge build show
   ```
5. 웹서비스 켜기 — **처음에는** start, **그다음부터는** restart:
   ```
   toolforge webservice buildservice start --mount=none
   ```
   ```
   toolforge webservice restart
   ```
6. 브라우저로 `https://old-hangul-ocr.toolforge.org/` 를 열어 첫 화면과 맨 아래 '판' 줄(모델 지문)이 새것인지 봅니다.

막혔을 때 기록 보기:
```
toolforge webservice buildservice logs -f
```
```
toolforge build logs
```

### 위키문헌에서 쓰기

`사용자:(내 이름)/common.js` 에 두 줄(첫 화면에도 같은 줄이 나옵니다):
```
mw.loader.load("https://old-hangul-ocr.toolforge.org/ocr.js");
mw.loader.load("https://old-hangul-ocr.toolforge.org/compare.js");
```
⚠ 브라우저판(jsDelivr)의 OCR 소도구 줄과 **함께 두지 마세요** — 단추가 둘 생깁니다. 하나만 남기세요.

---

## 알아 둘 것

- **자원** — 기본 0.5코어 · 512MB 로 돕니다(모델 메모리 약 70MB). 한 쪽에 몇 초~열몇 초. 쓰는 사람이 늘어 느리면:
  ```
  toolforge webservice stop
  ```
  ```
  toolforge webservice buildservice start --mount=none --cpu 1 --mem 1Gi
  ```
- **처음 보는 파일** — 판형 · 자간을 정하려고 쪽 열몇 장을 받아 봅니다(1~3분, 파일마다 처음 한 번).
  받은 스캔과 정한 값은 컨테이너의 임시 폴더에 두므로 **웹서비스를 다시 켜면 처음부터** 다시 살핍니다.
- **스캔** — 서버가 위키미디어 공용에서 1920px 썸네일을 받습니다(User-Agent 에 연락처, `step1_collect.py` 의 `CONTACT`).
- **개인정보** — 편집 상자의 글(전사대조)은 맞대는 데만 쓰고 남기지 않습니다. 접속 기록도 따로 남기지 않습니다.
- **결과** — 저장하지 않습니다. 소도구는 편집 상자에 넣기만 하고, 저장은 사람이 눈으로 보고 합니다.

## 학습 자료와 사용권

- 코드와 모델: MIT (LICENSE).
- 모델 학습에 한국지능정보사회진흥원(AI 허브)의 「옛한글 OCR」 데이터를 썼습니다 — 이 모델을 다시 나눌 때는 출처를 밝혀 주세요.

## 묶음 안

| 자리 | 무엇 |
|---|---|
| `app.py` | 서버(WSGI). gunicorn 이 `app:app` 을 띄움(`Procfile`) |
| `부품/` · `전사대조/대조.py` · `step1_collect.py` | 프로젝트의 파이썬 셈 그대로(정본) |
| `부품/onnx모델.py` | torch 대신 ONNX 로 읽는 부분 — 같은 답(확신값 차이 0.0004 미만) |
| `모델/` | `옛한글모델.onnx` · `경계검출.onnx` · `설정.json` (브라우저판과 같은 파일) |
| `정적/` | 첫 화면 · 소도구 두 개 · 영역 지정 화면 |
| `판.json` | 만든 날 · 모델 지문 — 첫 화면 맨 아래에 나옴 |

내 컴퓨터에서 먼저 돌려 보기: `python old-hangul-ocr-toolforge/app.py` → <http://localhost:8761/>
