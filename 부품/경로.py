# -*- coding: utf-8 -*-
"""
프로젝트의 폴더 자리를 한 군데에 모은 것.

    import 경로
    경로.모델           → <프로젝트>/자료/모델
    os.path.join(경로.데이터, slug, "img")

⚠ 새 코드에 "모델" · "data" 같은 경로를 직접 적지 말고 여기 이름을 쓸 것 — 작업 폴더와 상관없이 같은 파일을 찾음.

폴더 구조
    근원/          원본 — 부품/(파이썬 OCR) · 소도구/(위키 편집 창 JS) · 영역지정/ · 툴포지/(서버)
    제작/          제작용 — 실험/ · 도구/ · 만들기/ · 시험서버/ · 문서/ · 읽은결과/ …
    자료/          data/ · dataset/ · 교정/ · 모델/ · 글꼴/ · 공유서재/
    old-hangul-ocr-toolforge/  (자동) Toolforge 판

⚠ Toolforge 묶음에서는 프로젝트를 못 찾으므로(바로 위가 `근원/` 이 아님) 작업 폴더 기준 이름("모델" · "data" …)을 씀
  — 묶음의 `app.py` 가 자기 폴더로 chdir 함.
"""
import os

_여기 = os.path.dirname(os.path.abspath(__file__))          # …/근원/부품
_위 = os.path.dirname(_여기)                                   # …/근원


def _프로젝트():
    if os.path.basename(_위) != "근원":
        return None
    r = os.path.dirname(_위)
    return r if os.path.isdir(os.path.join(r, "자료")) else None


뿌리 = _프로젝트()
묶음 = 뿌리 is None              # Toolforge 묶음처럼 떼어 낸 판에서 도는가

if not 묶음:
    근원 = os.path.join(뿌리, "근원")
    부품 = _여기
    소도구 = os.path.join(근원, "소도구")              # 소도구.js · 전사대조.js (원본 — 위키 편집 창 화면)
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

    자료 = os.path.join(뿌리, "자료")
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
실험결과 = os.path.join(결과, "실험")
