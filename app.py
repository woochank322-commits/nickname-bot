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
    MemberJoinedEvent,
)

load_dotenv()

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN과 LINE_CHANNEL_SECRET 환경 변수를 설정해주세요.")

app = Flask(__name__)
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

STEP_1_FORM = (
    "🥀 {입장 전 인증} 🗝️\n\n"
    "*아래 내용을 복붙 후 작성해주세요.\n\n"
    "닉네임(2글자, 초성X) -\n"
    "성별(여/남) -\n"
    "나이 -\n"
    "방 경험 (유/무) -\n"
    "((유를 선택하셨을 시 경험했던 방 임티 -\n"
    "성향(돔/섭/스위치/바닐라) -\n"
    "초대자 이름 -"
)

STEP_2_GUIDE = (
    "🥀 {성별 인증} 🗝️\n\n"
    "아래에 적혀있는 인증멘트를 음성메세지로 녹음 후 보내주세요.\n\n"
    "((안녕하세요 + (닉네임) 입니다.)"
)

STEP_3_COMPLETE = (
    "🥀 {인증 완료} 🗝️\n\n"
    "- 관리자가 전달하는 닉으로 변경\n"
    "- 프본 (본인사진)으로 프사 변경\n"
    "- 완료 후 관리자 태그 후 완료 통보\n\n"
    "관리자에게 확인을 받은 후 안내를 따라주세요.\n\n"
    "• 프사에 꼭 얼굴이 나오지 않아도 됩니다.\n"
    "• Ai 사진은 금지합니다.\n"
    "• 도용은 즉시 강퇴입니다."
)

MANUAL_AUTH_REPLIES = {
    "1)": STEP_1_FORM,
    "2)": STEP_2_GUIDE,
    "3)": STEP_3_COMPLETE,
}

TENDENCY_MAP = {
    "돔": "𝒮",
    "섭": "ℳ",
    "스위치": "𝒮𝒲",
    "바닐라": "𝒱",
}

GENDER_MAP = {
    "남": "🕰️",
    "여": "🥀",
}

SUPERSCRIPT_MAP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def to_superscript(age_str: str) -> str:
    return age_str.translate(SUPERSCRIPT_MAP)


def is_valid_two_char_nickname(nickname: str) -> bool:
    return bool(re.match(r"^[가-힣a-zA-Z0-9]{2}$", nickname))


def generate_formatted_nickname(nickname: str, gender: str, age: str, tendency: str) -> str:
    tendency_symbol = TENDENCY_MAP[tendency]
    small_age = to_superscript(age)
    gender_emoji = GENDER_MAP[gender]
    return f"{tendency_symbol} · {nickname}{small_age}{gender_emoji}"


def is_completed_step1_form(text: str) -> bool:
    """1) 입장 전 인증 양식을 복사해 필수 항목을 채워 넣었는지 판별"""
    required_prefixes = [
        "닉네임",
        "성별",
        "나이",
        "방 경험",
        "성향",
        "초대자",
    ]
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for prefix in required_prefixes:
        matched_line = next((line for line in lines if line.startswith(prefix)), None)
        if not matched_line or "-" not in matched_line:
            return False
        value = matched_line.split("-", 1)[1].strip()
        if not value:
            return False

    return True


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
    return "VELVET HOUR Auto-Auth & Nickname Bot is running.", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MemberJoinedEvent)
def handle_member_joined(event):
    """신입 입장 시 1) 입장 전 인증 양식 자동 발송"""
    reply_text(event.reply_token, STEP_1_FORM)


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_text = event.message.text.strip()

    # 수동 명령어 1), 2), 3) 처리
    if user_text in MANUAL_AUTH_REPLIES:
        reply_text(event.reply_token, MANUAL_AUTH_REPLIES[user_text])
        return

    # 1) 양식을 작성해서 붙여넣으면 자동으로 2) 성별 인증 안내 발송
    if is_completed_step1_form(user_text):
        reply_text(event.reply_token, STEP_2_GUIDE)
        return

    # 닉네임 생성 코드 (예: 레오 남 20 돔 -> 𝒮 · 레오²⁰🕰️)
    parts = user_text.split()
    if len(parts) != 4:
        return

    nickname, gender, age, tendency = parts

    if gender not in GENDER_MAP or not age.isdigit() or tendency not in TENDENCY_MAP:
        return

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
