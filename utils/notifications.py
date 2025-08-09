import ssl
import smtplib
import certifi
import logging
import json
import pytz
import requests
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText 
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication

from config.settings import (
    EMAIL_ADDRESS, EMAIL_PASS, RECEIVER_EMAIL,
    SMTP_SERVER, SMTP_PORT,
    KAKAO_REST_API_KEY,
    KAKAO_REFRESH_TOKEN
)

# 카카오토큰 갱신 함수 (변경 없음)
def refresh_access_token():
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": KAKAO_REST_API_KEY,
        "refresh_token": KAKAO_REFRESH_TOKEN
    }
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        token_info = response.json()
        if "access_token" in token_info:
            new_access_token = token_info["access_token"]
            logging.info(f"✅ 새 액세스 토큰: {new_access_token}")
            return new_access_token
        else:
            logging.error(f"❌ 토큰 갱신 실패: {token_info}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ [네트워크 오류] 토큰 갱신 실패: {e}")
        return None

# 이메일 발송 함수
def send_occurrence_email(subject, body_text, graph_files=None, dashboard_file=None):
    context = ssl.create_default_context(cafile=certifi.where())
    context.minimum_version = ssl.TLSVersion.TLSv1_2  # TLS 1.2 강제
    context.maximum_version = ssl.TLSVersion.TLSv1_2  # TLS 1.3까지 허용
    msg = MIMEMultipart('mixed')
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "html", _charset="utf-8"))

    # 📎 그래프 이미지 첨부
    if graph_files:
        for graph_file in graph_files:
            try:
                with open(graph_file, 'rb') as f:
                    img = MIMEImage(f.read())
                    img.add_header('Content-Disposition', 'attachment', filename=graph_file)
                    msg.attach(img)
                logging.info(f"✅ 그래프 파일 첨부 완료: {graph_file}")
            except Exception as e:
                logging.error(f"❌ [첨부 오류] 그래프 파일 {graph_file}: {e}")

    # 📎 대시보드 HTML 첨부
    if dashboard_file:
        try:
            with open(dashboard_file, 'rb') as f:
                html_attachment = MIMEApplication(f.read(), _subtype="html")
                html_attachment.add_header('Content-Disposition', 'attachment', filename=dashboard_file)
                msg.attach(html_attachment)
            logging.info(f"📄 HTML 대시보드 파일 첨부 완료: {dashboard_file}")
        except Exception as e:
            logging.error(f"❌ [이메일 첨부 오류] HTML 대시보드: {e}")

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASS)
            server.send_message(msg)
        logging.info(f"📧 이메일 발송 완료: {RECEIVER_EMAIL}")
    except Exception as e:
        logging.error(f"❌ [이메일 발송 실패]: {e}")

# 카카오톡 메시지 전송 (변경 없음)
def send_kakao_message(text, access_token=None):
    if not access_token:
        logging.error("❌ [Kakao] access_token 누락")
        return False

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": text,
            "link": {"web_url": "", "mobile_web_url": ""}
        }, ensure_ascii=False)
    }
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        logging.info(f"✅ 카카오톡 메시지 전송 성공")
        return True
    except Exception as e:
        logging.error(f"❌ [카카오톡 메시지 전송 실패]: {e}")
        return False

# NaN/OT 요약 카카오 메시지 발송 (변경 없음)
def send_nan_alert_to_kakao(all_results):
    if not all_results:
        logging.warning("[카카오] 전송할 데이터 없음")
        return

    total_nan = sum(stats["nan_count"] for result in all_results for stats in result[4].values())
    total_ot = sum(stats["ot_count"] for result in all_results for stats in result[4].values())
    kst = pytz.timezone("Asia/Seoul")
    execution_time = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

    text = (
        f"📢 PDA Overtime 및 NaN 체크 결과\n"
        f"📅 실행 시간: {execution_time} (KST)\n"
        f"📊 총 {len(all_results)}건 처리\n"
        f"⚠️ 누락(NaN): {total_nan} 건\n"
        f"⏳ 오버타임: {total_ot} 건\n"
        f"👇 대시보드에서 상세 내용 확인하세요!"
    )

    access_token = refresh_access_token()
    if not access_token:
        logging.error("❌ [카카오] 액세스 토큰 발급 실패")
        return

    send_kakao_message(text, access_token)