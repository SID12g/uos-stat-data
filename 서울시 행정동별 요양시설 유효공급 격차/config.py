"""서울시 행정동별 요양시설 유효공급 격차 분석의 공통 설정.

경로, 기준 시점, 분석 파라미터를 한곳에 모은다. 민감도 분석은 이 파일의 값만 바꿔서 한다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets"
OUTPUT_DIR = ROOT / "outputs"

# 기존 자치구 분석의 원자료를 그대로 쓴다(복사하지 않음).
# 저장소 루트의 .env(.gitignore 대상)에서 KOSIS_API_KEY 등을 읽는다. 키 값은 출력하지 않는다.
load_dotenv(ROOT.parent / ".env")

GU_ANALYSIS_DIR = ROOT.parent / "서울시 자치구별 75세 이상 인구 대비 요양시설 정원"
FACILITY_FILE = GU_ANALYSIS_DIR / "assets" / "국민건강보험공단_장기요양기관 시설별 현황_20240716.xlsx"
GRADE_FILE = GU_ANALYSIS_DIR / "assets" / "국민건강보험공단_노인장기요양보험 등급판정 현황_20240731.csv"

# ---------------------------------------------------------------- 기준 시점
POPULATION_YEAR_MONTH = ("2024", "07")  # 주민등록 인구 2024-07-31
ADM_BOUNDARY_VERSION = "ver20240701"  # vuski/admdongkor 행정동 경계
ADM_BOUNDARY_URL = (
    "https://raw.githubusercontent.com/vuski/admdongkor/master/"
    f"{ADM_BOUNDARY_VERSION}/HangJeongDong_{ADM_BOUNDARY_VERSION}.geojson"
)

# ---------------------------------------------------------------- 공간
CRS = "EPSG:5179"
SIDO_CODES = {"11": "서울특별시", "28": "인천광역시", "41": "경기도"}
BUFFER_KM = None  # None: 경기·인천 전체를 분석 범위로 둔다(2단계 계산이라 서울 경계에서 2 × 최대 d0까지 필요)
NEIGHBOR_SIDO_CODES = ["51", "43", "44"]  # 범위 밖 인접 육지(강원·충북·충남): 경계 효과 assert용

# ---------------------------------------------------------------- 공급
RESIDENTIAL_CODES = ["A01", "A02", "A03", "A04", "A05"]  # 입소시설(기존 자치구 분석과 동일)
DAYCARE_CODES = ["B03", "C03"]  # 주야간보호(재가 층, 후속 과제)
KAKAO_API_KEY_ENV = "KAKAO_REST_API_KEY"

# ---------------------------------------------------------------- 분석 파라미터(1단계 이후)
AGE_GROUPS = {"65~74세": (65, 74), "75~84세": (75, 84), "85세 이상": (85, None)}
DEMAND_VERSION = "A"  # "A": 서울 공통 인정률, "B": 구별 인정률
INCLUDE_GRADE3 = False  # 민감도: 3등급 포함 수요
EVAL_FILE = ASSET_DIR / "국민건강보험공단_장기요양기관 평가 결과_20260625.csv"
EVAL_URL = (
    "https://www.data.go.kr/cmm/cmm/fileDownload.do"
    "?atchFileId=FILE_000000003665176&fileDetailSn=1&insertDataPrcus=N"
)
EVAL_CYCLE = "2021년 정기평가"  # 기준 시점(2024-07)에 유효한 입소시설 평가
Q_METHOD = "occupancy"  # "occupancy" | "regression" | "binary" | "none"
UNRATED_Q = "seoul_mean"  # 미평가 시설: "seoul_mean" | "separate" | "rating2025"
N_BOOTSTRAP = 2000
D0_KM = 5
D0_SENSITIVITY_KM = [3, 5, 10, 15]
VERIFY_SAMPLE_KM = 10  # 검증 표본: 서울 + 서울 경계 10km 안 시설
MIN_POP65 = 100  # 65세 이상 인구가 이보다 적은 동은 하위 목록·분위·지도 색칠에서 제외(재건축 등)
DECAY = "gaussian"  # W(d) = [exp(-½(d/d0)²) - exp(-½)] / [1 - exp(-½)]

# ---------------------------------------------------------------- 미래 수요(6단계)
KOSIS_API_KEY_ENV = "KOSIS_API_KEY"
FUTURE_YEARS = [2029, 2034]
BASE_YEAR = 2024


def kosis_key():
    key = os.environ.get(KOSIS_API_KEY_ENV)
    if not key:
        raise RuntimeError(f"환경변수 {KOSIS_API_KEY_ENV}가 없다. 저장소 루트 .env에 넣는다.")
    return key
