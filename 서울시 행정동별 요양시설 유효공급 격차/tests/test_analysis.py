import hashlib
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import e2sfca as E
import config as C
import review_settings
import 검토_재계산 as audit
from validation import grade_effect_models


class SpatialTests(unittest.TestCase):
    def setUp(self):
        self.d = np.array([10., 20.])
        self.s = np.array([5., 10.])
        self.dist = np.array([[0., 1.], [1., 0.]])

    def test_invalid_inputs_fail_explicitly(self):
        for decay in ("gaussian", "uniform"):
            for radius in (0, -1, np.nan, np.inf):
                with self.subTest(decay=decay, radius=radius), self.assertRaises(ValueError):
                    E.e2sfca(self.d, self.s, self.dist, radius, decay)
        for bad in (np.nan, np.inf, -1):
            for component in ("demand", "supply", "distance"):
                d, s, dist = self.d.copy(), self.s.copy(), self.dist.copy()
                if component == "demand": d[0] = bad
                elif component == "supply": s[0] = bad
                else: dist[0, 0] = bad
                with self.subTest(component=component, bad=bad), self.assertRaises(ValueError):
                    E.e2sfca(d, s, dist, 5)
        with self.assertRaises(ValueError):
            E.e2sfca(self.d, self.s, np.zeros((1, 2)), 5)

    def test_conservation_and_increment_match_full_recalculation(self):
        r = E.e2sfca(self.d, self.s, self.dist, 5)
        self.assertAlmostEqual(np.dot(self.d, r.accessibility), self.s.sum())
        added = E.add_facility(r.accessibility, self.d, [2., 2.], 3., 5)
        full = E.e2sfca(self.d, np.r_[self.s, 3.], np.c_[self.dist, [2., 2.]], 5)
        np.testing.assert_allclose(added, full.accessibility)

    def test_unreachable_facility_does_not_create_nan_accessibility(self):
        r = E.e2sfca(self.d, self.s, np.array([[0., 20.], [1., 20.]]), 5)
        self.assertTrue(r.no_demand[1])
        self.assertTrue(np.isfinite(r.accessibility).all())
        self.assertAlmostEqual(np.dot(self.d, r.accessibility), self.s[0])

    def test_minimum_sites_matches_exhaustive_small_problem(self):
        acc = np.array([0., 0.]); target = np.array([True, True])
        result = E.minimum_sites(acc, self.d, self.dist, 20, 5, 1., target, max_per_site=2)
        feasible=[]
        for counts in itertools.product(range(3), repeat=2):
            a=acc.copy()
            for k,n in enumerate(counts):
                for _ in range(n): a=E.add_facility(a,self.d,self.dist[:,k],20,5)
            if (a>=1-1e-8).all(): feasible.append(sum(counts))
        self.assertTrue(result.certified)
        self.assertEqual(result.objective,min(feasible))


class ReviewTests(unittest.TestCase):
    def test_nonbaseline_settings_are_rejected(self):
        for key,value in (("D0_KM",10),("Q_METHOD","none"),("DEMAND_VERSION","B")):
            with self.subTest(key=key), patch.object(C,key,value), self.assertRaises(ValueError):
                review_settings.require_baseline()

    def test_changed_config_invalidates_saved_sentences(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); out=root/'outputs';out.mkdir()
            hashes={}
            for filename in ('config.py','review_settings.py','validation.py'):
                p=root/filename;p.write_text('original')
                hashes[str(p.relative_to(root.parent))]=hashlib.sha256(p.read_bytes()).hexdigest()
            (out/'검토_재계산.json').write_text(json.dumps({'입력sha256':hashes,'문장':{'05':['ok']}}))
            with patch.object(audit,'ROOT',root),patch.object(audit,'OUT',out):
                self.assertEqual(audit.reviewed_sentences('05'),['ok'])
                (root/'config.py').write_text('changed')
                with self.assertRaisesRegex(RuntimeError,'오래되었다'): audit.reviewed_sentences('05')


class ValidationTests(unittest.TestCase):
    def test_grade_removal_uses_raw_pressure(self):
        rng=np.random.default_rng(41);n=900
        grade=rng.choice(['A','B','C'],n); logcap=rng.normal(3,0.3,n)
        raw=np.exp(rng.normal(0,0.6,n));group=rng.integers(0,2,n)
        logits=-1+0.5*np.log(raw)+0.2*logcap-0.8*(grade=='C')
        data=pd.DataFrame({'만실':rng.binomial(1,1/(1+np.exp(-logits))),
                           '등급':grade,'log정원':logcap,'공동생활가정':group,'압력_정원_5':raw})
        data['압력_q_5']=raw/np.where(grade=='C',0.5,1.)
        result=grade_effect_models(data,5)
        names=result['no_grade'].model.exog_names
        self.assertIn('np.log(압력_정원_5)',names)
        self.assertFalse(any('등급' in v or '압력_q' in v for v in names))
        self.assertEqual(result['df_grade'],2)
        changed=data.copy();changed['압력_q_5']*=100
        again=grade_effect_models(changed,5)
        self.assertAlmostEqual(result['p_grade'],again['p_grade'])


if __name__ == '__main__':
    unittest.main()
