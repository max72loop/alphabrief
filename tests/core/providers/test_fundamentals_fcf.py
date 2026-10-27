"""FCF : `freeCashFlow` de FMP d'abord, jamais OCF seul (2026-10-27).

IREN, exercice clos le 30/06/2026 : FMP laisse `investmentsInPropertyPlantAndEquipment`
à 0 et met le capex (−4,33 Md$) dans `capitalExpenditure`. L'ancien calcul
(OCF + investmentsInPPE) donnait +2,10 Md$ — le flux d'exploitation seul — pour
un FCF réel de −2,23 Md$, et un FCF yield de +18,9 % au lieu d'environ −20 %.
"""
from unittest.mock import patch

import pytest

from core.providers import fundamentals_yf

_IREN_CF = {
    "date": "2026-06-30",
    "netCashProvidedByOperatingActivities": 2_100_418_000,
    "investmentsInPropertyPlantAndEquipment": 0,
    "capitalExpenditure": -4_333_087_000,
    "freeCashFlow": -2_232_669_000,
}


def _fmp(cf_row):
    def fake(endpoint, params=None, cache=True):
        if endpoint == "cash-flow-statement":
            return [cf_row]
        if endpoint == "profile":
            return [{"marketCap": 11_114_733_669}]
        if endpoint == "income-statement":
            return [{"revenue": 500_000_000}]
        return []
    return fake


def _fcf(cf_row):
    with patch.object(fundamentals_yf, "fmp_get", side_effect=_fmp(cf_row)), \
         patch.object(fundamentals_yf, "_complete_from_yf", return_value=None):
        out = fundamentals_yf.fetch_core_fundamentals("IREN")
    return out["financials"]["fcf_absolute"], out["valuation"]["fcf_yield_ttm"]


def test_free_cash_flow_fmp_prime():
    fcf, fy = _fcf(_IREN_CF)
    assert fcf == -2_232_669_000
    assert fy == pytest.approx(-20.09, abs=0.01)     # −2,233 / 11,115 Md$


def test_repli_sur_capital_expenditure():
    row = {k: v for k, v in _IREN_CF.items() if k != "freeCashFlow"}
    fcf, _ = _fcf(row)
    assert fcf == 2_100_418_000 - 4_333_087_000      # OCF + capitalExpenditure, pas OCF + 0


def test_dernier_repli_sur_l_ancien_champ():
    row = {"date": "2026-06-30", "netCashProvidedByOperatingActivities": 100, "investmentsInPropertyPlantAndEquipment": -40}
    fcf, _ = _fcf(row)
    assert fcf == 60
