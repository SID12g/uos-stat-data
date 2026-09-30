"""저장된 원자료·산출물에서 검토 수치와 보고서 문장을 재계산한다.

실행: python 검토_재계산.py  (numpy, pandas, scipy, pyproj, openpyxl 필요)
기존 01~07의 모든 자료 수집·회귀·그림을 다시 실행하는 프로그램은 아니다.
공간 계산 재현, 모형 가정 민감도, 정수 배치, 빈자리 정의를 독립 점검하고
검증·미래 결과는 기존 CSV에서 읽어 그 조건과 한계를 함께 기록한다.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

import e2sfca as E

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
GU = ROOT.parent / "서울시 자치구별 75세 이상 인구 대비 요양시설 정원" / "assets"
FACILITY = GU / "국민건강보험공단_장기요양기관 시설별 현황_20240716.xlsx"
EVALUATION = ROOT / "assets" / "국민건강보험공단_장기요양기관 평가 결과_20260625.csv"
GRADE = GU / "국민건강보험공단_노인장기요양보험 등급판정 현황_20240731.csv"
INPUT_NAMES = ["동별_수요.csv", "시설_공급.csv", "동별_접근성.csv", "견고한_우선동.csv",
               "시뮬레이션_greedy_우선동한정.csv", "q_표.csv", "압력효과_지역통제.csv",
               "시점외_검증.csv", "동별_미래부족석수.csv", "하락속도_상위10%_동.csv",
               "입소시설_분석범위.csv", "우선동_유지_규모.csv"]


def vacancy_table():
    """좌표 누락 시설도 포함한 서울 전체에서 순잔여·양수 빈자리를 구별한다."""
    general = pd.read_excel(FACILITY, sheet_name="일반현황", dtype={"장기요양기관코드": str})
    capacity = pd.read_excel(FACILITY, sheet_name="입소인원", dtype={"장기요양기관코드": str})
    region = general["시도 시군구 법정동명"].str.extract(r"^(\S+)\s+(\S+)")
    fallback = general["기관별 상세주소"].str.extract(r"^(\S+)\s+(\S+)")
    general["시도"] = region[0].fillna(fallback[0])
    ev = pd.read_csv(EVALUATION, encoding="cp949", dtype=str)
    ev["장기요양기관코드"] = ev["장기요양기관기호"].str.replace("-", "", regex=False)
    rating = ev.loc[ev["급여종류"].str.match(r"^0[123]\.") & ev["평가구분"].eq("2021년 정기평가"),
                    ["장기요양기관코드", "평가등급"]]
    f = (capacity.loc[capacity["기관유형코드"].isin(["A01", "A02", "A03", "A04", "A05"])]
         .groupby("장기요양기관코드", as_index=False)[["정원", "현원"]].sum()
         .merge(general[["장기요양기관코드", "시도"]], validate="one_to_one")
         .merge(rating, how="left", validate="one_to_one"))
    f = f.loc[f["시도"].eq("서울특별시")].copy()
    f["등급"] = f["평가등급"].fillna("미평가")
    f["순잔여정원"] = f["정원"] - f["현원"]
    f["양수빈자리"] = f["순잔여정원"].clip(lower=0)
    table = f.groupby("등급")[["정원", "현원", "순잔여정원", "양수빈자리"]].sum()
    table["빈자리비중"] = table["양수빈자리"] / table["양수빈자리"].sum()
    table.to_csv(OUT / "빈자리_정의별_재계산.csv")
    grades = pd.read_csv(GRADE, encoding="cp949")
    grades.columns = grades.columns.str.strip()
    g12 = grades.loc[grades["시도"].astype(str).str.strip().eq("서울"), ["1등급", "2등급"]]
    g12 = g12.apply(lambda s: pd.to_numeric(s.astype(str).str.replace(",", "", regex=False))).sum().sum()
    return table, int(g12)


def main():
    d = pd.read_csv(OUT / "동별_수요.csv", dtype={"행정동코드": str})
    f = pd.read_csv(OUT / "시설_공급.csv", dtype={"장기요양기관코드": str})
    rob = pd.read_csv(OUT / "견고한_우선동.csv", dtype={"행정동코드": str})
    saved = pd.read_csv(OUT / "동별_접근성.csv", dtype={"행정동코드": str}).set_index("행정동코드")
    seoul = d["서울"].to_numpy()
    eligible = seoul & (d[["65~74세", "75~84세", "85세 이상"]].sum(axis=1).to_numpy() >= 100)
    target = d["행정동코드"].isin(rob["행정동코드"]).to_numpy()
    demand, supply = d["D_A"].to_numpy(), f["S_occupancy_seoul_mean"].to_numpy()
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True).transform(f.lon, f.lat)
    dist = E.distance_matrix_km(d[["cx", "cy"]].to_numpy(), np.column_stack([x, y]))
    result = E.e2sfca(demand, supply, dist, 5)
    E.check_conservation(result, demand, supply)
    acc = result.accessibility
    error = np.max(np.abs(acc[seoul] * 100 - saved.loc[d.loc[seoul, "행정동코드"], "A100"]))
    assert error < 1e-8, error
    a_star = float(np.median(acc[eligible]))
    sf = f["시도"].eq("서울특별시")
    q = float(supply[sf].sum() / f.loc[sf, "정원"].sum())
    gap = float(E.shortage(acc[seoul], demand[seoul], a_star).sum())
    base = set(rob["행정동코드"])
    n_bottom = int(np.ceil(eligible.sum() * .1))
    rows, member_rows = [], []
    variants = [("주 설정", "D_A", "S_occupancy_seoul_mean", "gaussian"),
                ("구별 인정률", "D_B", "S_occupancy_seoul_mean", "gaussian"),
                ("3등급 포함", "D_A3", "S_occupancy_seoul_mean", "gaussian"),
                ("A·B=1, C~E=0.5", "D_A", "S_binary_seoul_mean", "gaussian"),
                ("품질 가중 없음", "D_A", "S_none_seoul_mean", "gaussian"),
                ("거리감쇠 없음", "D_A", "S_occupancy_seoul_mean", "uniform")]
    for name, dc, sc, decay in variants:
        sets = []
        for radius in [3, 5, 10, 15]:
            a = E.e2sfca(d[dc].to_numpy(), f[sc].to_numpy(), dist, radius, decay).accessibility
            # Same 43-smallest rule as the notebook, with stable tie ordering.
            ranked = d.loc[eligible, ["행정동코드"]].assign(A=a[eligible]).sort_values("A", kind="stable")
            sets.append(set(ranked.head(n_bottom)["행정동코드"]))
        common = set.intersection(*sets)
        rows.append({"설정": name, "네반경_공통하위동수": len(common), "원래12동_유지수": len(base & common),
                     "원래12동_제외": ", ".join(d.loc[d["행정동코드"].isin(base - common), "행정동명"])})
        for _, dong in d.loc[d["행정동코드"].isin(common)].iterrows():
            member_rows.append({"설정": name, "행정동코드": dong["행정동코드"], "행정동명": dong["행정동명"],
                                "원래12동": dong["행정동코드"] in base})
        if name == "주 설정":
            assert common == base, (common, base)
    sensitivity = pd.DataFrame(rows)
    sensitivity.to_csv(OUT / "우선동_가정민감도.csv", index=False)
    pd.DataFrame(member_rows).to_csv(OUT / "우선동_가정민감도_동목록.csv", index=False)
    candidate = d.loc[eligible].reset_index(drop=True)
    dc = E.distance_matrix_km(d[["cx", "cy"]].to_numpy(), candidate[["cx", "cy"]].to_numpy())
    opt_rows = []
    for cap in [1, 2]:
        opt = E.minimum_sites(acc, demand, dc, 50 * q, 5, a_star, target, max_per_site=cap)
        assert opt.certified, f"최적성 미확인: 후보당 {cap}곳"
        selected = candidate.loc[opt.counts > 0, ["행정동코드", "행정동명", "지역"]].copy()
        selected["시설수"] = opt.counts[opt.counts > 0]
        selected["추가정원"] = selected["시설수"] * 50
        selected.to_csv(OUT / f"최소시설_배치_후보당{cap}곳.csv", index=False)
        opt_rows.append({"후보당상한": cap, "최소시설수": opt.objective, "정원": opt.objective * 50,
                         "최적성확인": opt.certified, "최적하한": opt.lower_bound,
                         "최소목표여유": float((opt.accessibility[target] - a_star).min())})
    pd.DataFrame(opt_rows).to_csv(OUT / "최소시설_최적화비교.csv", index=False)
    # Preserve the original 26-site map and evaluate that exact placement.
    sites = pd.read_csv(OUT / "시뮬레이션_greedy_우선동한정.csv")
    indices = []
    for _, r in sites.iterrows():
        match = np.flatnonzero(candidate["행정동명"].str.split().str[-1].eq(r["행정동"]) & candidate["지역"].eq(r["지역"]))
        assert len(match) == 1
        indices.append(match[0])
    post = acc.copy()
    for k in indices:
        post = E.add_facility(post, demand, dc[:, k], 50 * q, 5)
    assert np.all(post[target] >= a_star - 1e-8)
    vacancy, all_age_g12 = vacancy_table()
    validation = pd.read_csv(OUT / "압력효과_지역통제.csv").set_index("반경(km)").loc[5]
    oot = pd.read_csv(OUT / "시점외_검증.csv").set_index("반경(km)").loc[5]
    future = pd.read_csv(OUT / "동별_미래부족석수.csv")
    q_b = pd.read_csv(OUT / "q_표.csv", index_col=0).loc["B", "occupancy"]
    improve = sf & f["등급"].isin(["C", "D", "E"])
    supply2 = supply.copy()
    supply2[improve] = f.loc[improve, "정원"] * q_b
    qa = E.e2sfca(demand, supply2, dist, 5).accessibility
    q_gain = float((supply2 - supply).sum())
    stats = {"서울계산동수": int(seoul.sum()), "서울비교동수": int(eligible.sum()), "시설수": len(f),
             "서울시설수": int(sf.sum()), "서울잠재수요": float(demand[seoul].sum()), "목표A100": a_star * 100,
             "서울q": q, "유효정원격차": gap, "정원환산하한": gap / q,
             "접근성저장값_최대오차": float(error), "배치26_전체격차": float(E.shortage(post[seoul], demand[seoul], a_star).sum()),
             "품질가중_유효증가": q_gain, "신규와품질가중_격차": float(E.shortage((qa + post - acc)[seoul], demand[seoul], a_star).sum()),
             "순잔여정원": int(vacancy["순잔여정원"].sum()), "양수빈자리": int(vacancy["양수빈자리"].sum()),
             "전체연령1_2등급": all_age_g12,
             "미래": {str(y): {"잠재수요": float(future[f"수요_{y}"].sum()), "정원환산하한": float(future[f"부족_{y}"].sum() / q)} for y in [2024, 2029, 2034]}}
    ab = int(vacancy.loc[["A", "B"], "양수빈자리"].sum())
    cde = int(vacancy.loc[["C", "D", "E"], "양수빈자리"].sum())
    unr = int(vacancy.loc["미평가", "양수빈자리"])
    geo = pd.read_csv(OUT / "입소시설_분석범위.csv")
    scale = pd.read_csv(OUT / "우선동_유지_규모.csv").set_index("기준 연도 수요")
    retained = "; ".join(f"{r['설정']} {r['원래12동_유지수']}곳" for r in rows[1:])
    sentences = {
        "01": [f"서울 {seoul.sum()}개 동과 경기·인천 {len(d)-seoul.sum()}개 읍면동을 함께 계산한다. 정원 0 시설을 제외한 E2SFCA 표본은 {len(f):,}곳(서울 {sf.sum()}곳)이며, 좌표 확보 표본 {len(geo):,}곳(서울 {geo['시도'].eq('서울특별시').sum()}곳)과 구별한다. 기준은 2024년 7월이며 현재 시설 현황을 뜻하지 않는다."],
        "02": [f"동별 연령 구조에 서울 공통 1~2등급 인정률을 곱한 잠재 중증 돌봄 지표다. 서울 65세 이상 합계는 {demand[seoul].sum():,.0f}명이다. 실제 입소·대기 수요와 같지 않으며 재가·병원 이용과 일부 3~5등급 입소자를 별도 고려해야 한다.",
               "공통 인정률은 구별 건강·신청 성향을 고정한 연령 구조 비교를 위한 선택이다. 주소 이동 교정이 입증된 것은 아니다. 기존 점검에서 구별 표준화 인정비와 정원 상관은 1~2등급 0.34(p=0.10), 4~5등급 0.62(p=0.001)였으므로 주소 이동만으로 설명하지 않는다. 구별 인정률 버전 B를 민감도로 함께 비교한다."],
        "03": [f"순잔여정원은 {stats['순잔여정원']:,}석으로 전체 연령 1~2등급 {all_age_g12:,}명 대비 {stats['순잔여정원']/all_age_g12:.1%}다. 음수를 0으로 처리한 물리적 빈자리 지표는 {stats['양수빈자리']:,}석: A·B {ab:,}석, C~E {cde:,}석, 미평가 {unr:,}석이다. A·B 빈자리는 전체 연령 인정자 100명당 {ab/all_age_g12*100:.1f}석이며 즉시 입소 가능 여부를 확인한 값은 아니다.",
               f"등급별 가동률 비는 품질·입지·비용·개원 시기 등이 섞인 탐색적 가중치다. 미평가 q는 서울 정원가중 평균 {q:.6f}를 사용한다. C~E 시설의 가중치를 B 수준으로 올리는 시나리오의 유효 정원 증가 {q_gain:.0f}석은 실제 정원 증가가 아니다."],
        "04": [f"주 설정(A·가동률 비·가우스 감쇠·5km)의 비교 대상은 {eligible.sum()}개 동이다. 잠재 인정자 100명당 유효 정원은 중앙값 {a_star*100:.1f}석, 10% 경계 {np.quantile(acc[eligible],.1)*100:.1f}석, 90% 경계 {np.quantile(acc[eligible],.9)*100:.1f}석이다.",
               f"네 반경 모두 하위 10%인 동은 주 설정 {len(base)}곳이다. 원래 {len(base)}곳 중 유지: {retained}. 미평가 q는 각 설정의 서울 평가시설 정원가중 평균(이진 가중 약 0.791)이다. 반경에 대한 견고성과 모든 가정에 대한 강건성을 구별한다. 전체 교집합 크기와 동 명단은 우선동_가정민감도 CSV를 참고한다."],
        "05": [f"5km 수요 압력의 만실 오즈비는 전체 {validation['OR(전체)']:.2f}, 시도 통제 {validation['OR(시도 통제)']:.2f}(p={validation['p(시도 통제)']:.2f}), 서울만 {validation['OR(서울만)']:.2f}(p={validation['p(서울만)']:.2f})다. 서울 동 순위는 이 자료로 뚜렷하게 검증하지 못했다. 만실 비율 68%는 검정력을 제한할 수 있으나 원인으로 확인되지 않았다.",
               f"기존 2025년 시점 외 예측에서 5km AUC는 {oot['AUC(2025)']:.3f}, 압력 추가에 따른 증가는 {oot['ΔAUC(압력 추가)']:.3f}으로 작다. 실제 입소 출발지·대기자 자료를 이용한 검증이 필요하다. 여기서는 기존 회귀 CSV를 읽었으며 회귀를 다시 적합하지 않았다."],
        "06": [f"수요와 2024년 서울 중앙값 목표를 고정한 모형상 격차 합계는 유효 정원 {gap:,.0f}석이다. 서울 평균 q={q:.6f}의 신규 시설을 가정한 물리적 정원 환산 하한은 {gap/q:,.0f}석이다. 관측된 미충족 입소 수요가 아니다.",
               f"서울 {eligible.sum()}개 동 중심점·5km·50석·동일 q·우선 {len(base)}동 목표의 정수 최적화: 후보당 1곳이면 최소 {opt_rows[0]['최소시설수']}곳({opt_rows[0]['정원']:,}석), 2곳이면 최소 {opt_rows[1]['최소시설수']}곳({opt_rows[1]['정원']:,}석)이다. 기존 greedy는 후보당 1곳 {scale.loc[2024,'한 동에 1곳']}, 2곳 {scale.loc[2024,'한 동에 2곳까지']}의 순차 배치 해이며 최소로 부르지 않는다. 기존 {len(sites)}곳 지도는 수요가중 제곱 격차를 가장 줄이는 후보 순서로 고른 배치다.",
               f"기존 26곳 배치에서 서울 전체 격차는 {stats['배치26_전체격차']:,.0f}석, 품질 가중치 개선을 더하면 {stats['신규와품질가중_격차']:,.0f}석이다. 전국 100명당 159.8석은 총유효정원÷전국 65세 이상 인정자라는 총량 비율로, 전국 동 접근성 중앙값과 비교한 것이 아니다."],
        "07": [f"인정률·공급을 2024년 수준으로 고정한 시나리오의 서울 잠재 수요는 2029년 {stats['미래']['2029']['잠재수요']:,.0f}명, 2034년 {stats['미래']['2034']['잠재수요']:,.0f}명이다. 목표와 q를 고정한 정원 환산 하한은 각각 {stats['미래']['2029']['정원환산하한']:,.0f}석, {stats['미래']['2034']['정원환산하한']:,.0f}석이다.",
               f"기존 2034년 순차 배치는 후보당 2곳에서 {scale.loc[2034,'한 동에 2곳까지']}으로 목표에 도달한 실행 가능 해이며 최소를 증명한 값이 아니다. 서울 총량 보정은 동별 순이동을 검증하지 않는다. 2019→2024 인구 역검증·동별 이동·정비사업 시나리오는 후속 과제다."],
    }
    inputs = [OUT / name for name in INPUT_NAMES] + [FACILITY, EVALUATION, GRADE, ROOT / "e2sfca.py", Path(__file__)]
    provenance = {str(p.relative_to(ROOT.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    payload = {"조건": {"주반경km": 5, "민감도반경km": [3, 5, 10, 15], "소수요제외65세인구": 100,
                        "하위동수": n_bottom, "미평가q": "각 설정의 서울 평가시설 정원가중 평균",
                        "배치시설정원": 50, "배치대상": sorted(base), "배치후보": "서울 비교 대상 동 중심점"},
               "수치": stats, "최적화": opt_rows, "민감도": rows, "문장": sentences, "입력sha256": provenance}
    (OUT / "검토_재계산.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(sensitivity.to_string(index=False))
    print(pd.DataFrame(opt_rows).to_string(index=False))
    print(f"공간 계산 재현 최대오차 {error:.2g}; 순잔여 {stats['순잔여정원']}; 양수빈자리 {stats['양수빈자리']}")
    return payload


def reviewed_sentences(stage):
    """입력의 해시가 일치할 때만 검토 문장을 반환한다. 오래된 출력은 거부한다."""
    path = OUT / "검토_재계산.json"
    if not path.exists():
        raise RuntimeError("01~07 산출물 준비 후 python 검토_재계산.py를 실행한다")
    payload = json.loads(path.read_text())
    for relative, digest in payload["입력sha256"].items():
        p = ROOT.parent / relative
        if hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"검토 산출물이 오래되었다: {relative}. python 검토_재계산.py를 다시 실행한다")
    return payload["문장"][stage]


if __name__ == "__main__":
    main()
