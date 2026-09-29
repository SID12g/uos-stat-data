"""E2SFCA(Enhanced Two-Step Floating Catchment Area) 공통 함수.

입소시설뿐 아니라 재가(주야간보호)·의료(요양병원) 층에도 쓰도록 공급·수요·반경을 인자로 받는다.

    1단계(시설 쪽): R_j = S_j / Σ_{d_ij ≤ d0} D_i · W(d_ij)
    2단계(동 쪽):   A_i = Σ_{d_ij ≤ d0} R_j · W(d_ij)

보존 성질: 반경 안 수요가 있는 시설만 보면 Σ_i D_i · A_i = Σ_j S_j 이다.
"""
from dataclasses import dataclass

import numpy as np

_EXP_HALF = np.exp(-0.5)


def gaussian_decay(dist_km, d0_km):
    """W(d) = [exp(-½(d/d0)²) - exp(-½)] / [1 - exp(-½)] (d ≤ d0), 그 밖에는 0. W(0) = 1, W(d0) = 0."""
    d = np.asarray(dist_km, dtype=float)
    w = (np.exp(-0.5 * (d / d0_km) ** 2) - _EXP_HALF) / (1 - _EXP_HALF)
    return np.where(d <= d0_km, w, 0.0)


def uniform_decay(dist_km, d0_km):
    """거리감쇠 없는 원래 2SFCA: 반경 안이면 1."""
    return (np.asarray(dist_km, dtype=float) <= d0_km).astype(float)


DECAY_FUNCTIONS = {"gaussian": gaussian_decay, "uniform": uniform_decay}


def distance_matrix_km(demand_xy, supply_xy):
    """평면 좌표(미터, 예: EPSG:5179) 사이의 직선거리 행렬(km). 행: 수요 지점, 열: 공급 지점."""
    a = np.asarray(demand_xy, dtype=float)
    b = np.asarray(supply_xy, dtype=float)
    diff = a[:, None, :] - b[None, :, :]
    return np.sqrt((diff ** 2).sum(axis=2)) / 1_000


@dataclass
class E2SFCAResult:
    accessibility: np.ndarray  # A_i, 수요 1단위당 유효 공급
    supply_ratio: np.ndarray  # R_j, 시설 공급 ÷ 반경 안 가중 수요 (반경 안 수요가 0이면 nan)
    weighted_demand: np.ndarray  # 시설별 Σ_i D_i · W(d_ij)
    no_demand: np.ndarray  # 반경 안 수요가 0인 시설(bool)


def e2sfca(demand, supply, dist_km, d0_km, decay="gaussian"):
    """E2SFCA를 계산한다.

    demand: (n,) 수요 D_i, supply: (m,) 공급 S_j, dist_km: (n, m) 거리 행렬(km),
    d0_km: 반경, decay: "gaussian" | "uniform" 또는 (dist, d0) → 가중치 함수.
    """
    demand = np.asarray(demand, dtype=float)
    supply = np.asarray(supply, dtype=float)
    assert dist_km.shape == (len(demand), len(supply))
    assert (demand >= 0).all() and (supply >= 0).all()

    decay_fn = DECAY_FUNCTIONS[decay] if isinstance(decay, str) else decay
    w = decay_fn(dist_km, d0_km)

    weighted_demand = demand @ w  # (m,)
    no_demand = weighted_demand <= 0
    ratio = np.full(len(supply), np.nan)
    ratio[~no_demand] = supply[~no_demand] / weighted_demand[~no_demand]

    accessibility = w[:, ~no_demand] @ ratio[~no_demand]  # (n,)
    return E2SFCAResult(accessibility, ratio, weighted_demand, no_demand)


def check_conservation(result, demand, supply, rtol=1e-9):
    """Σ_i D_i · A_i = Σ_{반경 안 수요가 있는 j} S_j 를 확인하고 두 값을 돌려준다."""
    lhs = float(np.dot(demand, result.accessibility))
    rhs = float(np.asarray(supply, dtype=float)[~result.no_demand].sum())
    assert np.isclose(lhs, rhs, rtol=rtol), (lhs, rhs)
    return lhs, rhs


def shortage(accessibility, demand, a_star):
    """부족 석수_i = max(0, A* − A_i) × D_i (공급 단위)."""
    return np.maximum(0.0, a_star - np.asarray(accessibility)) * np.asarray(demand, dtype=float)


def add_facility(accessibility, demand, dist_new_km, supply_new, d0_km, decay="gaussian"):
    """가상 시설 하나를 더한 뒤의 A_i.

    기존 시설의 R_j는 자기 공급과 반경 안 수요로만 정해지므로 새 시설이 생겨도 변하지 않는다.
    따라서 A_i' = A_i + R_new · W(d_i,new) 로 전체를 다시 계산한 것과 정확히 같다.
    """
    decay_fn = DECAY_FUNCTIONS[decay] if isinstance(decay, str) else decay
    w = decay_fn(np.asarray(dist_new_km, dtype=float), d0_km)
    weighted = float(np.dot(demand, w))
    if weighted <= 0:
        return np.asarray(accessibility, dtype=float).copy()
    return np.asarray(accessibility, dtype=float) + supply_new / weighted * w


def shortfall_objective(accessibility, demand, a_star, objective="linear"):
    """부족 지표 합계. linear: Σ D_i (A* − A_i)₊ (부족 석수 합계), squared: Σ D_i (A* − A_i)₊² (심한 부족에 더 큰 가중)."""
    gap = np.maximum(0.0, a_star - np.asarray(accessibility))
    power = {"linear": 1, "squared": 2}[objective]
    return float((np.asarray(demand, dtype=float) * gap ** power).sum())


def greedy_sites(accessibility, demand, dist_candidates_km, supply_new, d0_km, a_star, target, n_sites=None,
                 decay="gaussian", objective="squared", unique=True, stop=None, max_sites=500, max_per_site=None):
    """부족 지표(target 동)를 가장 많이 줄이는 후보지를 하나씩 고른다.

    objective="linear"는 부족 석수 합계를 쓴다. 보존 성질 때문에 새 시설은 Σ D·A를 정확히 자기 유효 정원만큼 늘리므로,
    반경 안 동이 모두 기준 미달로 남는 후보지는 감소량이 새 유효 정원과 같아져 동점이 많이 생긴다.
    objective="squared"는 더 심하게 부족한 동을 먼저 채우는 형평 기준으로 동점이 거의 없다.
    unique=True면 후보지마다 한 번만 쓴다(max_per_site=1과 같다). max_per_site를 주면 후보지마다 그 횟수까지 쓴다.
    n_sites개를 고르거나, stop(A_i)가 True가 될 때까지 고른다.
    dist_candidates_km: (n 동, k 후보) 거리 행렬. target: 합계를 셀 동(bool, 예: 서울 동).
    반환: [(후보 번호, 추가 후 목표 지표, 감소량, 같은 값의 동점 후보 수)], 최종 A_i
    """
    assert (n_sites is None) != (stop is None), "n_sites와 stop 중 하나만 준다"
    acc = np.asarray(accessibility, dtype=float).copy()
    demand = np.asarray(demand, dtype=float)
    current = shortfall_objective(acc[target], demand[target], a_star, objective)
    if max_per_site is None:
        max_per_site = 1 if unique else np.inf
    used = np.zeros(dist_candidates_km.shape[1])
    available = used < max_per_site
    chosen = []
    while (len(chosen) < n_sites) if n_sites is not None else not stop(acc):
        if len(chosen) >= max_sites or not available.any():
            raise RuntimeError(f"후보지 {len(chosen)}곳을 추가해도 정지 조건을 만족하지 못했다")
        totals = np.full(dist_candidates_km.shape[1], np.inf)
        accs = {}
        for k in np.flatnonzero(available):
            new_acc = add_facility(acc, demand, dist_candidates_km[:, k], supply_new, d0_km, decay)
            totals[k] = shortfall_objective(new_acc[target], demand[target], a_star, objective)
            accs[k] = new_acc
        k = int(np.argmin(totals))
        ties = int((totals <= totals[k] + 1e-9 * max(1.0, abs(totals[k]))).sum())
        chosen.append((k, totals[k], current - totals[k], ties))
        current, acc = totals[k], accs[k]
        used[k] += 1
        available = used < max_per_site
    return chosen, acc
