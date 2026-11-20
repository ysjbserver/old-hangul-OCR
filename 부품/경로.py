# -*- coding: utf-8 -*-
"""
프로젝트의 폴더 자리를 한 군데에 모은 것.

    import 경로
    경로.모델           → <자료>/모델
    os.path.join(경로.데이터, slug, "img")

⚠ 자료 폴더는 프로젝트 밖 — `자료기본`(C 드라이브 SSD — 11-17 HDD 에서 옮김). 다른 자리면 환경변수 `OCR_DATA`. 문서의 `자료/…` 는 이 폴더를 뜻함.

⚠ 새 코드에 "모델" · "data" 같은 경로를 직접 적지 말고 여기 이름을 쓸 것 — 작업 폴더와 상관없이 같은 파일을 찾음.

폴더 구조
    근원/          원본 — 부품/(파이썬 OCR) · 소도구/(위키 편집 창 JS) · 영역지정/ · 툴포지/(서버)
    제작/          제작용 — 실험/ · 도구/ · 만들기/ · 시험서버/ · 문서/ · 읽은결과/ …
    old-hangul-ocr-toolforge/  (자동) Toolforge 판
    (프로젝트 밖) C:\\OCR 자료\\   data/ · dataset/ · 교정/ · 모델/ · 글꼴/ · 공유서재/ · 한자자료/(AI Hub 에서 뽑은 것 — 남에게 넘기면 안 됨)

⚠ Toolforge 묶음에서는 작업 폴더 기준 이름("모델" · "data" …)을 씀 — 묶음 `app.py` 가 자기 폴더로 chdir 함.
"""
import os

_여기 = os.path.dirname(os.path.abspath(__file__))          # …/근원/부품
_위 = os.path.dirname(_여기)                                   # …/근원
자료기본 = r"C:\OCR 자료"                                      # 자료 폴더(프로젝트 밖)


def _프로젝트():
    if os.path.basename(_위) != "근원":
        return None
    r = os.path.dirname(_위)
    return r if os.path.isdir(os.path.join(r, "제작")) else None


def _자료자리(뿌리):
    """환경변수 `OCR_DATA` → `자료기본` → (그 폴더가 없으면) 옛 자리 <프로젝트>/자료."""
    옛 = os.path.join(뿌리, "자료")
    자리 = os.environ.get("OCR_DATA") or 자료기본
    return 자리 if os.path.isdir(자리) or not os.path.isdir(옛) else 옛


뿌리 = _프로젝트()
묶음 = 뿌리 is None              # Toolforge 묶음처럼 떼어 낸 판에서 도는가

if not 묶음:
    근원 = os.path.join(뿌리, "근원")
    부품 = _여기
    소도구 = os.path.join(근원, "소도구")              # 소도구.js · 전사대조.js
    영역지정 = os.path.join(근원, "영역지정")
    툴포지 = os.path.join(근원, "툴포지")

    제작 = os.path.join(뿌리, "제작")
    도구 = os.path.join(제작, "도구")
    실험 = os.path.join(제작, "실험")
    만들기 = os.path.join(제작, "만들기")
    내보낸것 = os.path.join(만들기, "내보낸것")         # 내보내기.py 가 만드는 .onnx · 설정.json · 문헌설정.json
    시험서버 = os.path.join(제작, "시험서버")           # 소도구시험.html · 서버.py (위키 없이 시험)
    전사대조 = os.path.join(제작, "전사대조")
    문서 = os.path.join(제작, "문서")
    결과 = os.path.join(제작, "읽은결과")

    자료 = _자료자리(뿌리)
    툴포지판 = os.path.join(뿌리, "old-hangul-ocr-toolforge")   # (자동) Toolforge 판
    학습상태 = os.path.join(뿌리, "학습상태.txt")
else:
    뿌리 = 자료 = ""
    결과 = "읽은결과"

모델 = os.path.join(자료, "모델")
데이터 = os.path.join(자료, "data")          # data/<문헌>/img · text
데이터셋 = os.path.join(자료, "dataset")     # dataset/labels.tsv · img/
교정 = os.path.join(자료, "교정")
글꼴 = os.path.join(자료, "글꼴")
공유서재 = os.path.join(자료, "공유서재")
한자자료 = os.path.join(자료, "한자자료")    # AI Hub 에서 뽑은 그림 묶음(.npy) — 남에게 넘기면 안 됨
실험결과 = os.path.join(결과, "실험")
# (2026-11-16) 실험(`실험12`)이 학습마다 만들고 지우는 글자 그림(수십만 ~ 200만 장)을 둘 자리 — 자료 폴더(D: HDD)에 두면 학습이
#   그림을 하나씩 읽느라 시간 넘게 걸림(HDD 무작위 읽기 초당 150건 남짓). SSD 의 로컬 폴더(동기화 안 되는 LOCALAPPDATA).
#   환경변수 `OCR_생성그림` 으로 바꿈 · "끔" 이면 예전처럼 dataset/img. 사람 라벨 그림(dataset/img)은 그대로.
_생성 = os.environ.get("OCR_생성그림")
생성그림 = ("" if 묶음 or _생성 == "끔" else
            _생성 or os.path.join(os.environ.get("LOCALAPPDATA") or 자료, "옛한글OCR", "생성그림"))
