"""등급 정보가 압력 변수에 남지 않는 시설 만실 검정."""

import numpy as np
import statsmodels.formula.api as smf
from scipy.stats import chi2
from sklearn.metrics import roc_auc_score


def grade_effect_models(data, radius, outcome="만실"):
    """일반 정원 기준 압력으로 등급·압력의 추가 설명력을 각각 비교한다.

    압력_q는 등급별 q를 이미 포함하므로 등급을 제거하는 축소 모형에는 쓰지 않는다.
    반환 모델은 같은 관측치를 사용한다. 결측·비유한 압력은 조용히 제외하지 않는다.
    """
    pressure = f"압력_정원_{radius}"
    if (not np.isfinite(data[pressure]).all() or (data[pressure] <= 0).any()
            or not np.isfinite(data["log정원"]).all()
            or data[[outcome, "등급", "공동생활가정"]].isna().any().any()):
        raise ValueError("검증 표본의 반응·등급·규모·압력에 결측 또는 잘못된 값이 있다")
    core = "log정원 + 공동생활가정"
    press = f"np.log({pressure})"
    full = smf.logit(f"{outcome} ~ 등급 + {core} + {press}", data=data).fit(disp=False)
    no_grade = smf.logit(f"{outcome} ~ {core} + {press}", data=data).fit(disp=False)
    no_press = smf.logit(f"{outcome} ~ 등급 + {core}", data=data).fit(disp=False)
    result = {"full": full, "no_grade": no_grade, "no_press": no_press}
    for label, model in list(result.items()):
        if not model.mle_retvals["converged"]:
            raise RuntimeError(f"{label} 로지스틱 회귀가 수렴하지 않았다")
        result[f"auc_{label}"] = roc_auc_score(data[outcome], model.predict(data))
    for label, reduced in (("grade", no_grade), ("press", no_press)):
        lr = 2 * (full.llf - reduced.llf)
        df = int(full.df_model - reduced.df_model)
        result[f"lr_{label}"], result[f"df_{label}"] = lr, df
        result[f"p_{label}"] = chi2.sf(lr, df)
    return result
