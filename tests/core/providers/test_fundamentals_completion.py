"""Complétion yfinance des fondamentaux + coupe-circuit FMP.

Ces deux mécanismes n'avaient aucun test alors qu'ils portent désormais
l'essentiel des données de scoring : depuis que le plan FMP est épuisé
(HTTP 429 « Limit Reach » sur tous les endpoints), yfinance n'est plus un
secours mais la source réelle.

Aucun accès réseau : le bundle yfinance est injecté.
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.providers import fmp_client
from core.providers import fundamentals_yf as F


# ─────────────────────────────────────────────
# Outillage
# ─────────────────────────────────────────────

def _stmt(rows: dict, n_cols: int = 4) -> pd.DataFrame:
    """États financiers au format yfinance : colonnes du plus récent au plus
    ancien, ce qui est aussi la convention des listes FMP."""
    cols = [pd.Timestamp(f"202{5-i}-09-30") for i in range(n_cols)]
    return pd.DataFrame(rows, index=cols).T


@pytest.fixture
def bundle(monkeypatch):
    """Injecte un bundle yfinance et renvoie le dict pour le personnaliser."""
    data = {
        "info": {
            "totalRevenue": 1000.0,
            "freeCashflow": 200.0,
            "operatingCashflow": 250.0,
            "netIncomeToCommon": 150.0,
            "marketCap": 8000.0,
            "totalDebt": 300.0,
            "totalCash": 100.0,
            "ebitda": 400.0,
            "payoutRatio": 0.25,
            "sector": "Technology",
            "industry": "Software",
        },
        "income": _stmt({
            "Total Revenue": [1000.0, 900.0, 800.0, 700.0],
            "Gross Profit": [500.0, 430.0, 380.0, 330.0],
            "Operating Income": [300.0, 260.0, 230.0, 200.0],
            "Net Income": [150.0, 130.0, 115.0, 100.0],
            "Interest Expense": [10.0, 9.0, 8.0, 7.0],
            "Diluted Average Shares": [90.0, 95.0, 98.0, 100.0],
        }),
        "balance": _stmt({
            "Total Assets": [2000.0, 1800.0, 1600.0, 1400.0],
            "Current Assets": [800.0, 700.0, 600.0, 500.0],
            "Current Liabilities": [400.0, 380.0, 350.0, 300.0],
            "Retained Earnings": [600.0, 500.0, 400.0, 300.0],
            "Total Liabilities Net Minority Interest": [900.0, 850.0, 800.0, 750.0],
        }),
        "cash": _stmt({"Operating Cash Flow": [250.0, 220.0, 200.0, 180.0]}),
    }
    monkeypatch.setattr(F, "_yf_bundle", lambda ticker: data)
    return data


# ─────────────────────────────────────────────
# Complétion — les champs qui manquaient vraiment
# ─────────────────────────────────────────────

class TestChampsManquants:
    """Les 14 champs absents de 29 à 32 cartes sur 39 au 2026-09-02."""

    def test_tresorerie(self, bundle):
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)
        fin, val = out["financials"], out["valuation"]
        assert fin["fcf_absolute"] == 200.0
        assert fin["net_income"] == 150.0
        assert fin["fcf_margin"] == pytest.approx(20.0)      # 200/1000
        assert val["fcf_yield_ttm"] == pytest.approx(2.5)     # 200/8000
        assert val["price_to_ocf"] == pytest.approx(32.0)     # 8000/250

    def test_levier_utilise_la_dette_nette(self, bundle):
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)
        # (300 - 100) / 400
        assert out["financials"]["net_debt_to_ebitda"] == pytest.approx(0.5)

    def test_couverture_interets(self, bundle):
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)
        assert out["financials"]["interest_coverage"] == pytest.approx(30.0)  # 300/10

    def test_composites(self, bundle):
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)
        fin = out["financials"]
        # marge brute 50 % aujourd'hui contre 47,5 % il y a deux exercices
        assert fin["gross_margin_trend"] == pytest.approx(2.5)
        # actions diluées 90 contre 100 il y a trois ans → relution
        assert fin["share_dilution_3y"] == pytest.approx(-10.0)
        # (150 - 250) / 2000
        assert fin["accruals_ratio"] == pytest.approx(-5.0)
        assert fin["altman_z"] is not None and fin["altman_z"] > 0
        assert fin["payout_ratio"] == pytest.approx(25.0)


class TestSeriesDeRevenus:
    """0,45 du pilier Croissance tient au seul CAGR 3 ans."""

    def test_cagr_sur_trois_ans(self, bundle):
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)
        # 700 → 1000 en 3 ans = 12,62 %/an
        assert out["financials"]["revenue_cagr_3y"] == pytest.approx(12.624, abs=1e-2)

    def test_taux_annuels_du_plus_ancien_au_plus_recent(self, bundle):
        """Convention FMP : la liste est ordonnée du plus ancien au plus récent.
        L'inverser fausserait `compute_growth_trend_score`, qui lit une pente."""
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)
        yoy = out["financials"]["revenue_yoy_rates"]
        assert len(yoy) == 3
        assert yoy == pytest.approx([14.2857, 12.5, 11.1111], abs=1e-3)
        assert yoy[0] > yoy[-1]  # croissance qui décélère, ordre chronologique

    def test_repli_deux_ans_si_historique_court(self, bundle, monkeypatch):
        """Trois exercices publiés : on annualise sur 2 ans plutôt que de rendre
        None, sans quoi le pilier Croissance retombe à 50 neutre."""
        bundle["income"] = _stmt({"Total Revenue": [1000.0, 900.0, 800.0]}, n_cols=3)
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)
        assert out["financials"]["revenue_cagr_3y"] == pytest.approx(11.803, abs=1e-2)


class TestNonRegression:
    def test_ne_remplace_jamais_une_valeur_existante(self, bundle):
        """FMP garde autorité partout où il a répondu."""
        out = F._empty_payload()
        out["financials"]["fcf_margin"] = 99.0
        out["valuation"]["pe_ttm"] = 42.0
        F._complete_from_yf("TEST", out)
        assert out["financials"]["fcf_margin"] == 99.0
        assert out["valuation"]["pe_ttm"] == 42.0

    def test_idempotent(self, bundle):
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)
        first = dict(out["financials"])
        F._complete_from_yf("TEST", out)
        assert out["financials"] == first

    def test_bundle_vide_ne_leve_pas(self, monkeypatch):
        monkeypatch.setattr(F, "_yf_bundle",
                            lambda t: {"info": {}, "income": None, "balance": None, "cash": None})
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)  # ne doit pas lever
        assert out["financials"]["fcf_margin"] is None

    def test_etat_financier_absent_ne_bloque_pas_les_autres_champs(self, bundle):
        """Un état manquant dégrade le résultat, il ne l'annule pas."""
        bundle["balance"] = None
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)
        assert out["financials"]["accruals_ratio"] is None   # dépend du bilan
        assert out["financials"]["altman_z"] is None
        assert out["financials"]["fcf_margin"] == pytest.approx(20.0)  # intact

    def test_altman_ignore_pour_les_banques(self, bundle):
        bundle["info"]["sector"] = "Financial Services"
        bundle["info"]["industry"] = "Banks — Regional"
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)
        assert out["financials"]["altman_z"] is None

    def test_source_marquee(self, bundle):
        out = F._empty_payload()
        F._complete_from_yf("TEST", out)
        assert "yf" in out["source"]


# ─────────────────────────────────────────────
# Coupe-circuit FMP
# ─────────────────────────────────────────────

class TestCoupeCircuitFMP:
    def setup_method(self):
        fmp_client.reset_plan_breaker()

    def teardown_method(self):
        fmp_client.reset_plan_breaker()

    def test_distingue_quota_de_plan_et_rafale(self):
        assert fmp_client._looks_like_plan_limit(
            '{"Error Message": "Limit Reach . Please upgrade your plan"}')
        assert fmp_client._looks_like_plan_limit("You have exceeded your rate limit")
        # Un 429 de rafale ne doit PAS ouvrir le circuit : le backoff a du sens.
        assert not fmp_client._looks_like_plan_limit("Too Many Requests")
        assert not fmp_client._looks_like_plan_limit("")

    def test_court_circuit_apres_declenchement(self, monkeypatch):
        calls = {"n": 0}

        class Resp:
            status_code = 429
            text = '{"Error Message": "Limit Reach . Please upgrade your plan"}'
            headers: dict = {}

        def fake_get(*a, **k):
            calls["n"] += 1
            return Resp()

        monkeypatch.setattr(fmp_client.requests, "get", fake_get)
        monkeypatch.setattr(fmp_client, "_cache", {})

        assert fmp_client.fmp_get("profile", {"symbol": "AAPL"}) is None
        assert calls["n"] == 1                    # une seule tentative, pas quatre
        assert fmp_client.plan_exhausted()

        # Appel suivant : plus aucune requête réseau.
        assert fmp_client.fmp_get("income-statement", {"symbol": "MSFT"}) is None
        assert calls["n"] == 1

    def test_reset_referme_le_circuit(self):
        fmp_client._trip_plan_breaker("profile", "AAPL")
        assert fmp_client.plan_exhausted()
        fmp_client.reset_plan_breaker()
        assert not fmp_client.plan_exhausted()
