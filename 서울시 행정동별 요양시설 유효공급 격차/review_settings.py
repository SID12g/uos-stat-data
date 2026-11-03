"""2024년 기본 설정의 검토 보고서가 다른 시나리오와 섞이지 않게 한다."""

from pathlib import Path

import config as C

# 보고서의 목표·대상·미래 연도 문장도 이 기준에 맞춰져 있다.
# config.py는 노트북 민감도 분석에 사용하되, 그 결과를 이 보고서로 덮어쓰지 않는다.
BASELINE = {
    "POPULATION_YEAR_MONTH": ("2024", "07"),
    "ADM_BOUNDARY_VERSION": "ver20240701",
    "CRS": "EPSG:5179",
    "SIDO_CODES": {"11": "서울특별시", "28": "인천광역시", "41": "경기도"},
    "NEIGHBOR_SIDO_CODES": ["51", "43", "44"],
    "RESIDENTIAL_CODES": ["A01", "A02", "A03", "A04", "A05"],
    "AGE_GROUPS": {"65~74세": (65, 74), "75~84세": (75, 84), "85세 이상": (85, None)},
    "BUFFER_KM": None,
    "DEMAND_VERSION": "A",
    "INCLUDE_GRADE3": False,
    "EVAL_CYCLE": "2021년 정기평가",
    "Q_METHOD": "occupancy",
    "UNRATED_Q": "seoul_mean",
    "D0_KM": 5,
    "D0_SENSITIVITY_KM": [3, 5, 10, 15],
    "VERIFY_SAMPLE_KM": 10,
    "MIN_POP65": 100,
    "DECAY": "gaussian",
    "BASE_YEAR": 2024,
    "FUTURE_YEARS": [2029, 2034],
}


def require_baseline():
    differences = [f"{key}={getattr(C, key)!r} (기준 {value!r})"
                   for key, value in BASELINE.items() if getattr(C, key) != value]
    root = Path(__file__).resolve().parent
    gu = root.parent / "서울시 자치구별 75세 이상 인구 대비 요양시설 정원"
    paths = {"ASSET_DIR": root / "assets", "OUTPUT_DIR": root / "outputs",
             "FACILITY_FILE": gu / "assets" / "국민건강보험공단_장기요양기관 시설별 현황_20240716.xlsx",
             "GRADE_FILE": gu / "assets" / "국민건강보험공단_노인장기요양보험 등급판정 현황_20240731.csv",
             "EVAL_FILE": root / "assets" / "국민건강보험공단_장기요양기관 평가 결과_20260625.csv"}
    differences += [f"{key}: 기본 입력 경로와 다름" for key, value in paths.items()
                    if getattr(C, key).resolve() != value.resolve()]
    if differences:
        raise ValueError("검토 보고서는 2024년 기본 설정 전용이다. 설정을 복원하거나 "
                         "별도 시나리오 보고서를 생성한다: " + "; ".join(differences))
