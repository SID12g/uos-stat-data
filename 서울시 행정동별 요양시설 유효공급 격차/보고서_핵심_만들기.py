"""실행된 노트북(01~07)이 출력한 보고서 문장과 산출 그림으로 보고서_핵심.md를 만든다.

문장은 각 노트북의 `..._sentence = (` 칸이 print로 출력한 것을 그대로 옮긴다. 노트북을 다시 실행한 뒤 이 스크립트를 다시 돌린다.
    python 보고서_핵심_만들기.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STAGES = [
    ("① 공간 준비", "01_공간준비.ipynb",
     [("outputs/행정동_시설_지도.png", "분석 범위(서울·경기·인천)의 행정동과 입소시설 위치(점 크기: 정원)")],
     "시설 좌표는 주소 지오코딩 결과이며 3곳(서울 노원사랑요양원4, 9석)은 좌표를 얻지 못해 제외했고, 동 대표점은 인구가 아닌 경계의 기하 중심이다."),
    ("② 동별 수요 추정", "02_수요추정.ipynb",
     [("outputs/동별_수요_지도.png", "동별 추정 1~2등급 수요: 서울 공통 인정률(A), 구별 인정률(B), B÷A"),
      ("outputs/수요_주소이동_점검.png", "구별 연령표준화 인정비와 입소 정원의 관계(1~2등급 vs 대조군 4~5등급)")],
     "동별 수요는 관측값이 아니라 연령 구조 × 서울 인정률로 추정한 값이며, 65세 미만 인정자(서울 1~2등급의 5.1%)는 제외했다."),
    ("③ 공급 품질", "03_공급품질.ipynb",
     [("outputs/등급별_가동률.png", "평가등급별 입소시설 가동률(전국·서울), 부트스트랩 95% 신뢰구간")],
     "평가등급(2021~22년)과 가동률(2024년) 사이에 2~3년 시차가 있고, 미평가 시설의 빈자리는 대부분 개원 초기 충원 과정을 반영한다."),
    ("④ E2SFCA 접근성", "04_E2SFCA.ipynb",
     [("outputs/동별_접근성_지도.png", "반경 5km 기준 동별 1~2등급 100명당 유효 정원(5분위), 굵은 테두리는 하위 10% 동"),
      ("outputs/견고한_우선동_지도.png", "반경 3·5·10·15km 모두에서 하위 10%인 견고한 우선 동 12곳")],
     "거리는 직선거리라 한강변 동은 실제 이동거리를 과소평가하며(접근성 과대평가 방향), 도로망 거리는 후속 과제다."),
    ("⑤ 검증", "05_검증.ipynb",
     [("outputs/반경별_적합도.png", "반경별 수요 압력의 만실 설명력(ΔAIC, AUC)")],
     "서울 시설의 68%가 이미 만실이라 서울 안의 동별 순위는 만실 자료로 검증되지 않았고, 주소지별 입소 이용 자료나 대기자 수가 필요하다."),
    ("⑥ 부족 석수", "06_부족석수.ipynb",
     [("outputs/부족석수_지도.png", "동별 부족 석수(A* = 서울 동 중앙값)와 전국 수준 대비 접근성(%)"),
      ("outputs/시뮬레이션_전후_지도.png", "견고한 우선 동을 서울 중앙값까지: 50석 시설 26곳 추가 전후"),
      ("outputs/시뮬레이션_전후_지도_서울전체.png", "(참고) 서울 전체 동의 제곱 부족을 줄이는 순서로 배치했을 때(81곳)")],
     "필요 정원은 기준값을 2024년 서울 중앙값으로 고정한 하한이며, 후보지는 동 중심점이라 실제 부지·지가는 반영하지 않았다."),
    ("⑦ 미래 수요", "07_미래수요.ipynb",
     [("outputs/미래_부족석수_지도.png", "2034년 부족 석수와 2024년 대비 증가(파란 테두리: 하락 속도 상위 10%)"),
      ("outputs/하락속도_지도.png", "2024→2034 접근성 하락 속도, 점무늬는 최근 5년 대규모 입주 동")],
     "코호트 방식은 동 단위 전입·전출을 반영하지 못해 대규모 입주·재개발 동(상일제1·2동, 고덕2동, 위례동, 거여2동, 둔촌1동 등)의 수치는 "
     "불확실성이 크며, 인정률과 공급은 2024년 수준으로 고정했다."),
]


def sentences(notebook):
    """문장 칸(`..._sentence = (`)이 출력한 줄을 순서대로, 중복 없이 모은다."""
    seen, out = set(), []
    for cell in json.loads((ROOT / notebook).read_text())["cells"]:
        src = "".join(cell["source"])
        if cell["cell_type"] != "code" or "sentence = (" not in src or "print(" not in src:
            continue
        for o in cell.get("outputs", []):
            if o.get("output_type") == "error":
                raise RuntimeError(f"{notebook}: 문장 칸에 오류가 있다. 노트북을 다시 실행한다.")
            if o.get("output_type") == "stream":
                for line in "".join(o["text"]).strip().split("\n"):
                    line = line.strip()
                    if line and line not in seen:
                        seen.add(line)
                        out.append(line)
    assert out, f"{notebook}: 출력된 문장이 없다. 노트북을 실행한 뒤 다시 돌린다."
    return out


def main():
    md = [
        "# 서울시 행정동별 요양시설 유효공급 격차: 보고서 핵심", "",
        "초고령 사회, 서울의 의료·돌봄 인프라는 어디에 더 필요한가? 분석의 단계별 핵심 문장과 그림을 모았다. "
        "문장은 각 노트북이 계산값으로 생성해 출력한 것을 그대로 옮겼다(`python 보고서_핵심_만들기.py`로 다시 만든다). "
        "그림 경로는 이 파일 기준 상대 경로다.", "",
        "- 기준 시점: 시설 2024-07-16, 인구·등급판정 2024-07-31",
        "- 주 설정: 수요 버전 A(서울 공통 인정률), 품질 가중 q = 가동률 비, 주 반경 5km(민감도 10km), "
        "핵심 결과는 3·5·10·15km 모두 하위 10%인 12개 동", "",
    ]
    limits = []
    for title, notebook, figures, limit in STAGES:
        md += [f"## {title}", "", f"노트북: `{notebook}`", "", "### 핵심 문장", ""]
        md += [f"> {line}\n" for line in sentences(notebook)]
        md += ["### 그림", ""]
        for path, desc in figures:
            assert (ROOT / path).exists(), path
            md += [f"- `{path}`: {desc}", f"  ![{desc}]({path})"]
        md += [""]
        limits.append(f"- **{title}**: {limit}")
    md += ["## 단계별 한계", ""] + limits + [""]
    (ROOT / "보고서_핵심.md").write_text("\n".join(md), encoding="utf-8")
    print(f"보고서_핵심.md: {len(md)}줄")


if __name__ == "__main__":
    main()
