# AI 써봄 Instagram 자동 게시기

`@ai.sseobom`에 7장 카드뉴스를 월·수·금 오후 8시(KST) 자동 게시하는 프로젝트입니다.

## 동작 방식

1. GPT-5.6 Luna가 최신 AI 주제를 한 번 검색하고 7장 원고를 작성합니다.
2. Pillow 템플릿이 1080×1350 JPEG 카드 7장을 렌더링합니다.
3. GitHub Actions가 JPEG를 공개 URL로 호스팅합니다.
4. Instagram 공식 게시 API가 캐러셀을 게시합니다.
5. 성공 시 ntfy 알림을 전송하고 게시 기록을 저장합니다.

## 비용 보호

- OpenAI 조직 하드 한도: 월 $5
- 선불 잔액: $5, 자동충전 꺼짐
- 이미지 생성 모델을 사용하지 않고 템플릿 렌더링을 사용합니다.
- 게시 1회당 OpenAI 호출은 원고 생성 1회와 웹 검색 1회로 제한합니다.

## GitHub Actions 보안 값

- `OPENAI_API_KEY`
- `INSTAGRAM_ACCESS_TOKEN`
- `INSTAGRAM_USER_ID`
- `NTFY_TOPIC`

비밀 값은 저장소 파일에 커밋하지 않습니다.

