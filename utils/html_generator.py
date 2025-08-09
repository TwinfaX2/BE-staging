# utils/html_generator.py
import pandas as pd
from datetime import datetime, date
import pytz
import logging
from utils.data_processing import format_hours
from utils.logger import setup_logging
from utils.uploader import upload_to_drive  # Drive 업로드 함수 (연동)

setup_logging()

def generate_html_from_content(html_content, output_filename="index.html"):
    """
    주어진 HTML 컨텐츠로 스타일이 적용된 HTML 파일을 생성하고,
    생성된 파일을 Google Drive에 업로드한 후, 파일 경로(또는 URL)를 반환합니다.
    """
    styled_html = f"""
    <html>
    <head>
      <meta charset="UTF-8">
      <title>PDA Dashboard</title>
      <style>
        body {{ font-family: 'NanumGothic', sans-serif; font-size: 12px; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        details {{ margin-bottom: 10px; }}
        summary {{ cursor: pointer; font-weight: bold; color: #333; }}
        details[open] summary {{ color: #0056b3; }}
        details > *:not(summary) {{ display: block; margin-left: 20px; }}
        ul {{ margin: 5px 0; padding-left: 20px; }}
        p {{ margin: 5px 0; }}
        hr {{ margin: 20px 0; }}
        a {{ color: #0056b3; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        img {{ max-width: 100%; height: auto; }}
      </style>
    </head>
    <body>{html_content}</body></html>
    """
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(styled_html)
        logging.info(f"HTML 파일 생성 완료: {output_filename}")
        # 파일 업로드: 업로드된 URL을 반환하도록 함
        html_link = upload_to_drive(output_filename)
        if html_link:
            logging.info(f"HTML 업로드 완료, 링크: {html_link}")
        return output_filename, html_link
    except Exception as e:
        logging.error(f"HTML 생성 오류: {e}")
        return None, None

def build_combined_email_body(all_results, nan_tasks_link=None, nan_total_link=None):
    """
    all_results 데이터를 바탕으로 통합 HTML 이메일 본문을 생성합니다.
    여기에는 실행 정보, 요약 테이블, 그래프 링크 등이 포함됩니다.
    """
    kst = pytz.timezone("Asia/Seoul")
    execution_time = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
    year, week_num, _ = date.today().isocalendar()
    dashboard_link = "https://rainbow-haupia-cd8290.netlify.app"
    
    def render_progress_bar(percent, total, label):
        try:
            if percent is None or not isinstance(percent, (int, float)) or pd.isna(percent):
                percent = 0.0
            if total is None or not isinstance(total, int):
                total = 0
            completed = round((percent / 100) * total)
        except Exception as e:
            logging.error(f"⚠️ 진행률 렌더링 오류: percent={percent}, total={total}, label={label}, 오류={e}")
            return "❌ 계산불가"

        tooltip = f"{label} 완료: {completed} / {total}건"
        if percent == 100:
            return f'<span title="{tooltip}" style="font-size: 16px;">✅</span>'
        else:
            return (f'<div style="width: 100%; background-color: #e0e0e0; height: 12px; border-radius: 3px;">'
                    f'<div style="width: {percent}%; background-color: orange; height: 100%; border-radius: 3px;" title="{tooltip}"></div></div>'
                    f'<span style="font-size: 12px;">{percent:.1f}%</span>')

    lines = [
        '<div style="text-align: center; margin-bottom: 20px;">'
        '<img src="https://rainbow-haupia-cd8290.netlify.app/GST_banner.jpg" alt="Build up GST Banner" style="max-width: 100%; height: auto;">'
        '</div>',
        f"<h1>PDA Dashboard - {year}년 {week_num}주차</h1>",
        f'<h3>📌 [알림] PDA Overtime 및 NaN 체크 결과 (총 {len(all_results)}건 처리)</h3>',
        f'<p>📅 실행 시간: {execution_time} (KST)</p>',
        f'<p>📊 대시보드에서 상세 내용 확인하세요! (<a href="{dashboard_link}">대시보드 바로가기</a>)</p>',
        '<h4>요약 테이블</h4>',
        '<table border="1" style="border-collapse: collapse; width: 95%; font-size: 13px;">',
        '<tr style="background-color: #f2f2f2;">',
        '<th>Order</th><th>모델명</th><th>기구협력사</th><th>전장협력사</th><th>총 작업 수</th>',
        '<th>기구 NaN</th><th>기구 OT</th><th>기구 진행률</th>',
        '<th>전장 NaN</th><th>전장 OT</th><th>전장 진행률</th>',
        '<th>TMS NaN</th><th>TMS OT</th><th>TMS 진행률</th>',
        '</tr>'
    ]
    
    # 결과 테이블 생성
    for order_no, model_name, mech_partner, elec_partner, occurrence_stats, partner_stats, links, spreadsheet_url, progress_summary in all_results:
        total_tasks = sum(stats["total_count"] for stats in occurrence_stats.values())
        prog = progress_summary or {"기구": 0, "전장": 0, "TMS_반제품": 0}
        prog_mech = prog.get("기구", 0)
        prog_elec = prog.get("전장", 0)
        prog_tms = prog.get("TMS_반제품", 0)
        mech_stats = partner_stats.get("mech", {})
        elec_stats = partner_stats.get("elec", {})
        tms_stats = occurrence_stats.get("TMS_반제품", {})
        mech_nan = mech_stats.get("nan_count", 0)
        mech_ot = mech_stats.get("ot_count", 0)
        mech_total = mech_stats.get("total_count", 0)
        elec_nan = elec_stats.get("nan_count", 0)
        elec_ot = elec_stats.get("ot_count", 0)
        elec_total = elec_stats.get("total_count", 0)
        tms_nan = tms_stats.get("nan_count", 0)
        tms_ot = tms_stats.get("ot_count", 0)
        tms_total = tms_stats.get("total_count", 0)
        
        lines.append(f'''
        <tr><td>{order_no}</td><td>{model_name}</td><td>{mech_partner}</td><td>{elec_partner}</td><td>{total_tasks}</td>
        <td{' style="color: red; font-weight: bold;"' if mech_nan > 0 else ""}>{mech_nan}</td>
        <td{' style="color: red; font-weight: bold;"' if mech_ot > 0 else ""}>{mech_ot}</td>
        <td>{render_progress_bar(prog_mech, mech_total, "기구")}</td>
        <td{' style="color: red; font-weight: bold;"' if elec_nan > 0 else ""}>{elec_nan}</td>
        <td{' style="color: red; font-weight: bold;"' if elec_ot > 0 else ""}>{elec_ot}</td>
        <td>{render_progress_bar(prog_elec, elec_total, "전장")}</td>
        <td{' style="color: red; font-weight: bold;"' if tms_nan > 0 else ""}>{tms_nan}</td>
        <td{' style="color: red; font-weight: bold;"' if tms_ot > 0 else ""}>{tms_ot}</td>
        <td>{render_progress_bar(prog_tms, tms_total, "TMS")}</td></tr>
        ''')
    
    lines.append('</table><br>')
    if nan_tasks_link or nan_total_link:
        lines.append('<h4>NaN 발생 비율 그래프</h4>')
        if nan_tasks_link:
            lines.append(f'<p>작업 수 대비 NaN 비율: <a href="{nan_tasks_link}">그래프 보기</a></p>')
        if nan_total_link:
            lines.append(f'<p>전체 NaN 건수 대비 비율: <a href="{nan_total_link}">그래프 보기</a></p>')
        lines.append('<br>')
    
    # 세부 결과 (details) 생성
    for order_no, model_name, mech_partner, elec_partner, occurrence_stats, partner_stats, links, spreadsheet_url, _ in all_results:
        lines.append(f'<details><summary><strong>📍 Order: {order_no}, 모델명: {model_name}</strong></summary>')
        lines.append(f'<p>🏭 기구협력사: {mech_partner}, ⚡ 전장협력사: {elec_partner}</p>')
        lines.append(f'<p>📋 <strong>모델 스프레드시트</strong>: <a href="{spreadsheet_url}">바로가기</a></p>')
        lines.append(f'<p>📊 대시보드 링크: <a href="{dashboard_link}">대시보드 바로가기</a></p>')
        lines.append(f'<p>📊 그래프 링크:</p><ul>'
                     f'<li>Working Hours: <a href="{links["working_hours"]}">바로가기</a></li>'
                     f'<li>Legend Chart: <a href="{links["legend"]}">바로가기</a></li>'
                     f'<li>WD Chart: <a href="{links["wd"]}">바로가기</a></li></ul>')
        for category in ["기구", "TMS_반제품", "전장", "검사", "마무리", "기타"]:
            stats = occurrence_stats.get(category, {"total_count": 0, "nan_count": 0, "ot_count": 0, "nan_tasks": [], "ot_task_details": []})
            total_count = stats["total_count"]
            lines.append(f'<p><b>🔹 {category} 작업</b><br> - 전체 작업 수: {total_count} 건<br>')
            nan_count = stats["nan_count"]
            nan_ratio = (nan_count / total_count) * 100 if total_count > 0 else 0
            lines.append(f' <span{" style=\"color: red;\"" if nan_count > 0 else ""}>⚠️ 누락(NaN): {nan_count} 건 (비율: {nan_ratio:.2f}%)</span><br>')
            if nan_count > 0:
                lines.append(''.join(f'   - {task}<br>' for task in stats["nan_tasks"]))
            ot_count = stats["ot_count"]
            ot_ratio = (ot_count / total_count) * 100 if total_count > 0 else 0
            lines.append(f' <span{" style=\"color: red;\"" if ot_count > 0 else ""}>⏳ 오버타임: {ot_count} 건 (비율: {ot_ratio:.2f}%)</span><br>')
            if ot_count > 0:
                lines.append(''.join(f'   - {task} {format_hours(hours)}<br>' for task, hours in stats["ot_task_details"]))
            lines.append('</p>')
        lines.append('</details><hr>')
    return '\n'.join(lines)