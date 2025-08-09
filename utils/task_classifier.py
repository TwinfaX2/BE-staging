# utils/task_classifier.py

# 기본 작업 목록 정의
default_mechanical_tasks = [
    "CABINET ASSY", "BURNER ASSY(TMS)", "WET TANK ASSY(TMS)", "3-WAY VALVE ASSY",
    "N2 LINE ASSY", "N2 TUBE ASSY", "CDA LINE ASSY", "CDA TUBE ASSY", "BCW LINE ASSY",
    "PCW LINE ASSY", "O2 LINE ASSY", "LNG LINE ASSY", "WASTE GAS LINE ASSY",
    "COOLING UNIT(TMS)", "REACTOR ASSY(TMS)", "HEATING JACKET", "CIR LINE TUBING",
    "설비 CLEANING", "자주검사"
]

default_electrical_tasks = [
    "판넬 제작 작업", "케비넷 준비 작업(덕트, 철거작업)",
    "판넬 취부 및 선분리", "내, 외부 작업", "탱크 작업", "판넬 작업", "탱크 도킹 후 결선 작업", "검수"
]

default_inspection_tasks = [
    "LNG/Util", "LNG", "Chamber", "I/O 체크, 가동 검사, 전장 마무리"
]

default_finishing_tasks = [
    "캐비넷 커버 장착", "상부 마무리", "HOOK-UP 준비 및 포장"
]

# 모델별 기구 작업 목록 (기본 값 외에 모델별 특수 작업 처리)
model_mechanical_tasks = {
    "GALLANT-A": default_mechanical_tasks,
    "GAIA-I DUAL": default_mechanical_tasks,
    "GAIA-I": default_mechanical_tasks,
    "DRAGON": default_mechanical_tasks,
    "DRAGON DUAL": default_mechanical_tasks,
    "GAIA-II": default_mechanical_tasks,
    "SWS-I": [
        "CABINET ASSY", "BURNER ASSY(TMS)", "WET TANK ASSY(TMS)", "3-WAY VALVE ASSY",
        "N2 LINE ASSY", "N2 TUBE ASSY", "BCW LINE ASSY", "WASTE GAS LINE ASSY",
        "COOLING UNIT(TMS)", "REACTOR ASSY(TMS)", "HEATING JACKET", "CIR LINE TUBING",
        "설비 CLEANING", "자주검사", "CDA TUBE ASSY"
    ],
    "GAIA-P DUAL": [
        "CABINET ASSY", "BURNER ASSY(TMS)", "WET TANK ASSY(TMS)", "3-WAY VALVE ASSY",
        "N2 LINE ASSY", "N2 TUBE ASSY", "CDA LINE ASSY", "CDA TUBE ASSY", "BCW LINE ASSY",
        "PCW LINE ASSY", "WASTE GAS LINE ASSY", "COOLING UNIT(TMS)", "REACTOR ASSY(TMS)",
        "HEATING JACKET", "CIR LINE TUBING", "설비 CLEANING", "자주검사"
    ],
    "GAIA-P": [
        "CABINET ASSY", "BURNER ASSY(TMS)", "WET TANK ASSY(TMS)", "3-WAY VALVE ASSY",
        "N2 LINE ASSY", "N2 TUBE ASSY", "CDA LINE ASSY", "CDA TUBE ASSY", "BCW LINE ASSY",
        "PCW LINE ASSY", "WASTE GAS LINE ASSY", "COOLING UNIT(TMS)", "REACTOR ASSY(TMS)",
        "HEATING JACKET", "CIR LINE TUBING", "설비 CLEANING", "자주검사"
    ],
    "IVAS": [
        "CABINET ASSY", "BURNER ASSY(TMS)", "WET TANK ASSY(TMS)", "3-WAY VALVE ASSY",
        "N2 LINE ASSY", "N2 TUBE ASSY", "CDA LINE ASSY", "CDA TUBE ASSY", "BCW LINE ASSY",
        "PCW LINE ASSY", "O2 LINE ASSY", "LNG LINE ASSY", "WASTE GAS LINE ASSY",
        "COOLING UNIT(TMS)", "REACTOR ASSY(TMS)", "HEATING JACKET", "CIR LINE TUBING",
        "설비 CLEANING", "자주검사"
    ]
}

def get_mechanical_tasks(model_name):
    """
    주어진 모델 이름에 해당하는 기구 작업 목록을 반환합니다.
    모델 이름을 대문자로 변환한 후 사전에 있는 목록을 검색합니다.
    만약 해당 모델이 없으면 기본 기구 작업 목록을 반환합니다.
    """
    return model_mechanical_tasks.get(model_name.upper(), default_mechanical_tasks)

def classify_task(content, model_name):
    """
    주어진 작업(content)을 모델(model_name)에 따라 분류합니다.
    
    1. DRAGON, DRAGON DUAL, SWS-I 모델의 경우,
       해당 모델의 기구 작업 목록에 포함되어 있으면 '기구'로 분류합니다.
    2. TMS 관련 작업(tms_tasks)이 있을 경우,
       다른 모델에서는 'TMS_반제품'으로 분류합니다.
    3. 그 외 기본적으로 기구 작업, 전장, 검사, 마무리, 기타로 분류합니다.
    """
    model_name = model_name.upper()
    tms_tasks = ["BURNER ASSY(TMS)", "WET TANK ASSY(TMS)", "COOLING UNIT(TMS)", "REACTOR ASSY(TMS)"]
    
    # DRAGON, DRAGON DUAL, SWS-I 모델에서는 TMS 작업도 기구 작업으로 분류
    if model_name in ["DRAGON", "DRAGON DUAL", "SWS-I"]:
        if content in get_mechanical_tasks(model_name):
            return "기구"
    
    # TMS 관련 항목 처리
    if content in tms_tasks and model_name not in ["DRAGON", "DRAGON DUAL", "SWS-I"]:
        return "TMS_반제품"
    # 기본적으로 모델별 기구 작업 목록에 포함된 항목은 '기구'
    elif content in get_mechanical_tasks(model_name):
        return "기구"
    # 전기 작업으로 분류
    elif content in default_electrical_tasks:
        return "전장"
    # 검사 작업으로 분류
    elif content in default_inspection_tasks:
        return "검사"
    # 마무리 작업으로 분류
    elif content in default_finishing_tasks:
        return "마무리"
    # 위 조건에 해당하지 않으면 '기타' 처리
    return "기타"
