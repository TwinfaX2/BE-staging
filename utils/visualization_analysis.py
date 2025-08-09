# utils/visualization_analysis.py

import os
import re
import logging
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.dates as mdates
import pandas as pd
from datetime import timedelta
from matplotlib.patches import Patch

from config.settings import FONT_PATHS
from utils.task_classifier import classify_task
from utils.data_processing import get_avg_time_mapping, format_hours
from utils.logger import setup_logging

# 로깅 초기화
setup_logging()

def setup_fonts():
    """
    FONT_PATHS 중 실제 존재하는 경로의 NanumGothic 폰트를 matplotlib에 적용합니다.
    """
    font_path = next((p for p in FONT_PATHS if os.path.exists(p)), None)
    if font_path:
        logging.info(f"NanumGothic 폰트 적용: {font_path}")
        prop = fm.FontProperties(fname=font_path)
        plt.rc('font', family=prop.get_name())
    else:
        logging.warning("NanumGothic 폰트 미발견, 기본 폰트 사용")
    plt.rcParams['axes.unicode_minus'] = False

def sanitize_filename(s: str) -> str:
    """
    파일명에 안전하지 않은 문자가 들어가면 _ 로 치환합니다.
    """
    return re.sub(r'[^0-9A-Za-z_]', '_', s)

def generate_and_save_graph(task_total_time: pd.DataFrame, order_no: str, model_name: str) -> str:
    """
    작업별 워킹데이 소요시간 수평 막대그래프 생성.
    라벨에 평균 작업시간(format_hours)을 함께 표시합니다.
    """
    setup_fonts()
    avg_map = get_avg_time_mapping(model_name)

    fig, ax = plt.subplots(figsize=(12, 8))
    bars = ax.barh(
        task_total_time['내용'],
        task_total_time['워킹데이 소요 시간'],
        color='skyblue'
    )

    # y축 라벨에 평균시간 표시
    yticks = []
    for task in task_total_time['내용']:
        if task in avg_map:
            yticks.append(f"{task} (평균: {format_hours(avg_map[task])})")
        else:
            yticks.append(task)
    ax.set_yticks(range(len(yticks)))
    ax.set_yticklabels(yticks, fontsize=10, fontweight='bold', color='blue')

    # 막대 위에 실제 소요시간 텍스트 표시
    for bar in bars:
        w = bar.get_width()
        txt = format_hours(w)
        ax.text(w + 0.2, bar.get_y() + bar.get_height()/2, txt, va='center', ha='left')

    ax.set_xlim(0, max(bar.get_width() for bar in bars) + 1)
    ax.set_xlabel("Working Hours")
    ax.set_title(f"{order_no} — {model_name}", fontsize=14)
    plt.tight_layout()

    fname = f"Total_Working_Hours_{order_no}_{model_name}.png"
    fname = sanitize_filename(fname)
    plt.savefig(fname, bbox_inches='tight')
    plt.close()
    logging.info(f"Working Hours 그래프 생성: {fname}")
    return fname

def generate_legend_chart(task_total_time: pd.DataFrame, order_no: str, model_name: str) -> str:
    """
    작업 분류별 총 소요시간 파이 차트의 범례 형태로 표시.
    범례에 총합과 카테고리별, 작업별(평균 포함) 정보를 나열합니다.
    """
    setup_fonts()
    avg_map = get_avg_time_mapping(model_name)

    # 분류 컬럼 추가 및 정렬
    task_total_time['작업 분류'] = task_total_time['내용'].apply(lambda x: classify_task(x, model_name))
    df_sorted = task_total_time.sort_values(['작업 분류', '워킹데이 소요 시간'], ascending=[True, False])

    # 카테고리별 합계
    cat_totals = df_sorted.groupby('작업 분류')['워킹데이 소요 시간'].sum()
    total = cat_totals.sum()

    # 컬러 맵 (필요시 config로 이동 가능)
    category_colors = {
        "기구": "blue",
        "TMS_반제품": "cyan",
        "전장": "orange",
        "검사": "green",
        "마무리": "red",
        "기타": "gray"
    }

    legend_elements = [
        Patch(facecolor='black', label=f"총 소요시간: {format_hours(total)}")
    ]
    for cat, color in category_colors.items():
        if cat in cat_totals:
            ct = cat_totals[cat]
            legend_elements.append(Patch(facecolor=color, label=f"{cat}: {format_hours(ct)}"))
            # 작업별 상세
            for _, row in df_sorted[df_sorted['작업 분류'] == cat].iterrows():
                task = row['내용']
                dur_str = format_hours(row['워킹데이 소요 시간'])
                avg_str = f" (평균: {format_hours(avg_map[task])})" if task in avg_map else ""
                legend_elements.append(
                    Patch(facecolor='white', edgecolor=color,
                          label=f"  {task}: {dur_str}{avg_str}")
                )

    plt.figure(figsize=(8, len(legend_elements)*0.3))
    legend = plt.legend(handles=legend_elements, loc='center', frameon=False, fontsize=10,
                        title=f"{order_no} — {model_name}")
    plt.axis('off')
    plt.title(f"Legend Chart", fontsize=12)
    plt.tight_layout()

    fname = f"Legend_Chart_{order_no}_{model_name}.png"
    fname = sanitize_filename(fname)
    plt.savefig(fname, bbox_inches='tight')
    plt.close()
    logging.info(f"Legend 차트 생성: {fname}")
    return fname

def generate_and_save_graph_wd(task_total_time: pd.DataFrame, df: pd.DataFrame, order_no: str, model_name: str) -> str:
    """
    WD 차트: 각 작업별 시작·완료 시간 추세를 선 그래프로 표시.
    각 작업별로 오버랩 시 시간 오프셋 적용.
    """
    setup_fonts()
    df_valid = df.dropna(subset=['시작 시간', '완료 시간'])
    plt.figure(figsize=(16, 10))
    colors = plt.cm.tab20.colors
    offset = pd.Timedelta(hours=1)

    for idx, task in enumerate(task_total_time['내용']):
        grp = df_valid[df_valid['내용'] == task].sort_values('시작 시간')
        if grp.empty:
            continue
        dur_str = format_hours(task_total_time.loc[task_total_time['내용'] == task, '워킹데이 소요 시간'].iloc[0])
        for i, (_, row) in enumerate(grp.iterrows()):
            st = row['시작 시간'] + i*offset
            et = row['완료 시간'] + i*offset
            plt.plot([st, et], [idx, idx], color=colors[idx % len(colors)], linewidth=3, marker='o')
        plt.text(grp['완료 시간'].max() + pd.Timedelta(hours=2), idx, dur_str, va='center')

    ax = plt.gca()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    plt.xticks(rotation=45)
    plt.yticks(range(len(task_total_time['내용'])), task_total_time['내용'])
    plt.xlabel("Date")
    plt.ylabel("Tasks")
    plt.title(f"WD Chart — {order_no} — {model_name}")
    plt.grid(axis='x', linestyle='--', alpha=0.7)
    plt.tight_layout()

    fname = f"WD_Working_Hours_{order_no}_{model_name}.png"
    fname = sanitize_filename(fname)
    plt.savefig(fname, bbox_inches='tight')
    plt.close()
    logging.info(f"WD 차트 생성: {fname}")
    return fname