# 옛한글 OCR — 위키문헌 소도구

한국어 위키문헌(ko.wikisource.org)의 페이지 이름공간 편집 창에서 작동하는 OCR 도구입니다.
19~20세기 한글 인쇄본을 대상으로 합니다. 그 이전의 옛한글, 한자, 숫자 등의 특수기호는 인식하지 못합니다.
브라우저 안에서 모두 작동되게 설계되어 있습니다. (스캔 파일을 서버로 보내거나 하는 과정을 거치지 않습니다. 대신 느립니다)

## 설치

[특수:내사용자문서/common.js](https://ko.wikisource.org/wiki/Special:MyPage/common.js) 에 두 줄을 넣고 저장한 뒤 새로 고침하세요.

```javascript
window.옛한글OCR자료 = "https://cdn.jsdelivr.net/gh/ysjbserver/old-hangul-ocr@v1/";
mw.loader.load(window.옛한글OCR자료 + "소도구.js");
```

## 쓰는 법

1. `페이지:…` 문서를 편집으로 엽니다.
2. 편집 상자 위의 "옛한글 OCR 로 읽기" 를 누릅니다.
3. 읽은 글이 편집 상자에 들어갑니다. 확신이 낮은 글자는 색으로 칠해 보여 줍니다
   (구문 강조를 켜 두었으면 편집 상자 위에 따로).
4. 인식한 글자가 맞는지 한 번 읽으며 점검한 후 저장해 주세요.

## 알아 두실 것

- ⚠ **꼭 눈으로 확인한 뒤 저장하세요.** 색칠되지 않은 자리에도 오류가 글자 100개에 1개 안팎 남습니다. 열 끝의 글자가 빠지는 일도 있습니다.
- 한 쪽에 20~35초 가량 소요됩니다(사용 환경에 따라 다름).
- 처음 한 번은 모델(2.4 MB)을 받느라 조금 더 걸립니다.
- 모델과 스크립트는 jsDelivr(cdn.jsdelivr.net)에서 받습니다. 받을 때 사용자의 IP 주소가 jsDelivr에 전달됩니다. 스캔 그림과 읽은 글은 전달되지 않습니다.
- 한 단·두 단·세 단 판형을 알아서 가립니다. 처음 보는 파일은 몇 쪽을 먼저 살피느라 첫 쪽이 더 오래 걸립니다.

## 사용권

[CC0 1.0](LICENSE) — 저작권을 포기합니다. 허락 없이 쓰고, 고치고, 나눠도 됩니다.
(실행할 때 받아 오는 [onnxruntime-web](https://github.com/microsoft/onnxruntime)은 이 저장소에
들어 있지 않으며 MIT 사용권을 따릅니다.)

## 문의
[사용자:Aspere] (aspere.kowiki@gmail.com / https://ko.wikisource.org/wiki/사용자토론:Aspere)