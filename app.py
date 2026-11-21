import os
import re
from dotenv import load_dotenv
from flask import Flask, request, abort

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
)

load_dotenv()

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN과 LINE_CHANNEL_SECRET 환경 변수를 설정해주세요.")

app = Flask(__name__)
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 성향 -> 기호 매핑
TENDENCY_MAP = {
    "돔": "𝒮",
    "섭": "ℳ",
    "스위치": "𝒮𝒲",
    "바닐라": "𝒱",
}

# 성별 -> 이모티콘 매핑
GENDER_MAP = {
    "남": "🕰️",
    "여": "🥀",
}

# 일반 숫자 -> 위첨자 작은 숫자 변환 테이블
SUPERSCRIPT_MAP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

HELP_MESSAGE = (
    "🥀 {닉네임 생성 안내} 🗝️\n\n"
    "아래 형식에 맞춰 띄어쓰기로 입력해주세요.\n"
    "형식 : 닉네임(2글자) 성별(남/여) 나이 성향\n\n"
    "• 예시 : 레오 남 20 돔\n"
    "• 결과 : 𝒮 · 레오²⁰🕰️\n\n"
    "📌 성향 기호 안내\n"
    "• 돔 : 𝒮\n"
    "• 섭 : ℳ\n"
    "• 스위치 : 𝒮𝒲\n"
    "• 바닐라 : 𝒱"
)


def to_superscript(age_str: str) -> str:
    return age_str.translate(SUPERSCRIPT_MAP)


def is_valid_two_char_nickname(nickname: str) -> bool:
    """초성(ㄱ-ㅎ)이나 모음(ㅏ-ㅣ) 단독이 아닌 완성형 한글/영문/숫자 2글자 검증"""
    return bool(re.match(r"^[가-힣a-zA-Z0-9]{2}$", nickname))


def generate_formatted_nickname(nickname: str, gender: str, age: str, tendency: str) -> str:
    tendency_symbol = TENDENCY_MAP[tendency]
    small_age = to_superscript(age)
    gender_emoji = GENDER_MAP[gender]
    return f"{tendency_symbol} · {nickname}{small_age}{gender_emoji}"


def reply_text(reply_token: str, text: str):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)],
            )
        )


@app.route("/", methods=["GET"])
def health_check():
    return "VELVET HOUR Nickname Bot is running.", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_text = event.message.text.strip()

    # 도움말 명령어
    if user_text in ("/닉네임", "!닉네임", "닉네임양식"):
        reply_text(event.reply_token, HELP_MESSAGE)
        return

    parts = user_text.split()
    if len(parts) != 4:
        return

    nickname, gender, age, tendency = parts

    # 성별, 나이(숫자 1~3자리), 성향이 모두 유효한 패턴일 때만 처리
    if gender not in GENDER_MAP or not age.isdigit() or tendency not in TENDENCY_MAP:
        return

    # 닉네임이 2글자가 아닐 경우 안내 메시지 출력
    if not is_valid_two_char_nickname(nickname):
        reply_text(
            event.reply_token,
            "⚠️ 닉네임은 초성 없이 2글자로 입력해주세요.\n(예: 레오 남 20 돔)",
        )
        return

    result = generate_formatted_nickname(nickname, gender, age, tendency)
    reply_text(event.reply_token, result)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
