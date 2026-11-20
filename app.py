"""
app.py — Le site Streamlit (Damien)

Enchaîne les 10 étapes de la section 1 en appelant les fonctions du contrat 4.3.
Lancer en local :  streamlit run app.py
Tous les textes affichés sont dans textes.py (FR / EN) et questionnaire.py.
"""

from __future__ import annotations

from datetime import date

import hashlib
import json
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analytics
import accueil_marche
import livrable_excel
import livrable_pdf
import llm
import questionnaire as qn
import regles
import scoring
import simulation
from textes import NOMS_ENVELOPPES, t

st.set_page_config(page_title="Robo-advisor", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")

ETAT_DEFAUT = {"etape": 0, "langue": "fr", "montant": 300_000, "reponses": {}, "profil_calcule": None,
               "profil_choisi": None, "enveloppe": None, "enveloppe_choisie": None,
               "delta_actions": 0, "delta_oblig": 0, "horizon_ans": None, "explication": None,
               "source_explication": None, "ter_trad": 1.5, "note_construction": None}
for cle, val in ETAT_DEFAUT.items():
    st.session_state.setdefault(cle, val)
S = st.session_state
HORIZONS = {"<2": (1, 2, 2), "2-5": (2, 5, 5), "5-8": (5, 8, 8), ">8": (8, 30, 15)}   # (min, max, défaut)


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------
def L():
    return S.langue


def pct(x, d=1):
    return t("nd", L()) if x is None else f"{x * 100:.{d}f} %"


def eur(x):
    return t("nd", L()) if x is None else f"{x:,.0f} €".replace(",", " ")


FLUX = [1, 2, 3, 5, 6, 7]   # Montant, Questionnaire, Profil, Portefeuille, Simulation, Explication


def aller(etape):
    if etape == -1:  # « Refaire le questionnaire » : on efface les réponses mais on garde le montant
        montant = S.montant
        recommencer()
        S.montant = montant
        etape = 1
    S.etape = etape


def navigation(suivant=True, retour=True, desactiver=False):
    c1, _, c2 = st.columns([1, 4, 1])
    if S.etape not in FLUX:
        return
    i = FLUX.index(S.etape)
    if retour:
        c1.button(t("retour", L()), on_click=aller, args=(0 if i == 0 else FLUX[i - 1],), width="stretch")
    if suivant:
        if i == len(FLUX) - 1:
            c2.button("Terminer" if L() == "fr" else "Finish", on_click=aller, args=(0,), type="primary",
                      width="stretch")
        else:
            c2.button(t("continuer", L()), on_click=aller, args=(FLUX[i + 1],), type="primary",
                      disabled=desactiver, width="stretch")


def _graine_reponses():
    """Graine stable tirée des réponses : un nouveau questionnaire change le choix des titres."""
    r = json.dumps(S.reponses, sort_keys=True, default=str)
    return int(hashlib.md5(r.encode()).hexdigest()[:8], 16)


@st.cache_data(show_spinner=False)
def _analyser(pf_items):
    return analytics.analyser(dict(pf_items))


@st.cache_data(show_spinner=False)
def _perf_lignes(pf_items):
    return analytics.perf_lignes(dict(pf_items))


@st.cache_data(show_spinner=False)
def _simuler(pf_items, montant, versement, horizon, cible):
    return simulation.simuler(dict(pf_items), montant, versement, horizon, cible)


def profil_num():
    return S.profil_choisi or (S.profil_calcule or {}).get("profil")


def enveloppe():
    return S.enveloppe_choisie or S.enveloppe


def portefeuille_courant():
    """
    Portefeuille avec l'ajustement du client et ses préférences durables.
    Si les contraintes sont impossibles à tenir (ex. trop d'exclusions), on retire d'abord
    l'ajustement, puis les exclusions, et on garde une note pour prévenir le client.
    """
    p = profil_num()
    r = S.reponses
    excl, esg = regles.preferences_durables(r)
    try:
        alloc = regles.ajuster_allocation(p, S.delta_actions / 100, S.delta_oblig / 100)
    except ValueError:
        alloc = None
    base = dict(horizon=r.get("horizon"), zone=r.get("zone", "Monde"), graine=_graine_reponses())
    essais = [(alloc, excl, esg, None), (None, excl, esg, "ajustement"), (None, [], esg, "exclusions"), (None, [], False, "esg")]
    for al, ex, e, perdu in essais:
        try:
            pf = regles.construire_portefeuille(p, r.get("durabilite", "aucune"), enveloppe(), allocation=al,
                                                exclusions=ex, esg=e, **base)
            S.note_construction = perdu
            return pf
        except ValueError:
            continue
    raise RuntimeError("Construction du portefeuille impossible")


def dossier_complet():
    """Regroupe tout ce qui précède pour expliquer() et les livrables (contrat 4.3)."""
    pf = portefeuille_courant()
    items = tuple(sorted(pf.items()))
    r = dict(S.reponses)
    profil = dict(S.profil_calcule)
    profil["profil_calcule"] = profil["profil"]
    profil["profil"] = profil_num()
    sim = _simuler(items, r["montant"], r.get("versement_mensuel", 0), S.horizon_ans, r.get("cible", 0))
    r_just = dict(r, _profil=profil_num(), _enveloppe=enveloppe())
    return {"date": date.today().isoformat(), "langue": L(), "reponses": r, "profil": profil,
            "enveloppe": enveloppe(), "portefeuille": pf, "indicateurs": _analyser(items),
            "simulation": sim, "horizon_ans": S.horizon_ans,
            "justifications": regles.justifier(pf, r_just, L()),
            "explication": S.explication or ""}


# ---------------------------------------------------------------------------
# En-tête (la barre latérale est masquée)
# ---------------------------------------------------------------------------
st.markdown("<style>[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'], "
            "[data-testid='collapsedControl'] {display:none;}</style>", unsafe_allow_html=True)


def recommencer():
    langue = L()
    for cle in list(S.keys()):
        del S[cle]
    for cle, val in ETAT_DEFAUT.items():
        S[cle] = val
    S.langue = langue


_FR = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 3 2'><rect width='1' height='2' fill='%23002395'/>"
       "<rect x='1' width='1' height='2' fill='%23fff'/><rect x='2' width='1' height='2' fill='%23ed2939'/></svg>")
_GB = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 30'><clipPath id='t'><path d='M30,15 h30 v15 z v15 h-30 z h-30 v-15 z v-15 h30 z'/></clipPath>"
       "<path d='M0,0 v30 h60 v-30 z' fill='%23012169'/><path d='M0,0 L60,30 M60,0 L0,30' stroke='%23fff' stroke-width='6'/>"
       "<path d='M0,0 L60,30 M60,0 L0,30' clip-path='url(%23t)' stroke='%23C8102E' stroke-width='4'/>"
       "<path d='M30,0 v30 M0,15 h60' stroke='%23fff' stroke-width='10'/><path d='M30,0 v30 M0,15 h60' stroke='%23C8102E' stroke-width='6'/></svg>")
st.markdown(f"""<style>
.st-key-lang_fr button, .st-key-lang_en button {{width:46px;min-height:32px;padding:0;background-size:cover;
  background-position:center;border:2px solid transparent;border-radius:6px;opacity:.45;}}
.st-key-lang_fr button p, .st-key-lang_en button p {{display:none;}}
.st-key-lang_fr button {{background-image:url("{_FR}");}}
.st-key-lang_en button {{background-image:url("{_GB}");}}
.st-key-lang_{L()} button {{opacity:1;border-color:#1F3A5F;}}
</style>""", unsafe_allow_html=True)


def _choisir_langue(code):
    S.langue = code


_, c_accueil, c_fr, c_en = st.columns([8, 1.8, 0.6, 0.6])
if S.etape > 0:
    c_accueil.button("🏠 " + ("Accueil" if L() == "fr" else "Home"), on_click=aller, args=(0,),
                     key="btn_home_header", width="stretch")
c_fr.button("FR", key="lang_fr", on_click=_choisir_langue, args=("fr",))
c_en.button("EN", key="lang_en", on_click=_choisir_langue, args=("en",))

if S.etape in FLUX:
    st.title(t("titre", L()))
    st.caption("⚠️ " + t("avertissement", L()))
    st.subheader(f"{FLUX.index(S.etape) + 1}. {t('etapes', L())[S.etape]}")
    st.progress((FLUX.index(S.etape) + 1) / len(FLUX))


def perf_jour_fictive(isin, classe):
    """Performance du jour FICTIVE (démo) : stable pour une journée donnée."""
    h = int(hashlib.md5(f"{isin}{date.today().isoformat()}".encode()).hexdigest()[:8], 16)
    x = (h % 2001 - 1000) / 1000  # -1 .. 1
    c = str(classe).lower()
    vol = 0.0005 if c.startswith("mon") else 0.0015 if c.startswith("obl") else 0.009 if c.startswith("act") else 0.007
    return x * vol


def resume_accueil():
    """Données affichées dans « Mon portefeuille » une fois le questionnaire rempli (sinon None)."""
    if not S.profil_calcule:
        return None
    try:
        num = profil_num()
        cls = t("classes", L())
        alloc = {cls[k]: v * 100 for k, v in regles.poids_par_classe(portefeuille_courant()).items() if v > 0}
        pf_ = portefeuille_courant()
        u_ = regles.charger_univers()
        mt_ = S.reponses.get("montant", S.montant)
        pj_ = sum(w * perf_jour_fictive(i, u_.loc[i, "classe"]) for i, w in pf_.items())
        return {"perf_jour": (pj_ * 100, pj_ * mt_),
                "montant": S.reponses.get("montant", S.montant), "profil_num": num,
                "profil_nom": regles.PROFILS[num]["nom_en" if L() == "en" else "nom"],
                "enveloppe": NOMS_ENVELOPPES[L()][enveloppe()], "allocation": alloc}
    except Exception:
        return None


def page_detail():
    import numpy as np
    fr_ = L() == "fr"
    pf = portefeuille_courant()
    items = tuple(sorted(pf.items()))
    ind = _analyser(items)
    perf = _perf_lignes(items)
    u = regles.charger_univers()
    montant = S.reponses["montant"]
    env_lignes = regles.repartition_enveloppes(pf, enveloppe(), montant)
    cls = t("classes", L())
    pj = sum(w * perf_jour_fictive(i, u.loc[i, "classe"]) for i, w in pf.items())

    def _f(x, d=1, signe=False):
        return "n/d" if x is None or pd.isna(x) else (f"{x*100:+.{d}f} %" if signe else f"{x*100:.{d}f} %")

    def _col(x):
        return "#6b7785" if x is None or pd.isna(x) else ("#12873f" if x >= 0 else "#c0392b")

    def _eur(x, signe=False):
        return (f"{x:+,.0f} €" if signe else f"{x:,.0f} €").replace(",", " ")

    def _kpi(lab, val, coul="#1B2A41"):
        return (f"<div><div style='font-size:11px;color:#6b7785'>{lab}</div>"
                f"<div style='font-size:16px;font-weight:600;color:{coul}'>{val}</div></div>")

    sh = ind["sharpe"]
    kpis = "".join([
        _kpi("1 an" if fr_ else "1y", _f(ind["perf_1a"], signe=True), _col(ind["perf_1a"])),
        _kpi("3 ans" if fr_ else "3y", _f(ind["perf_3a"], signe=True), _col(ind["perf_3a"])),
        _kpi("Volatilité" if fr_ else "Volatility", _f(ind["volatilite"])),
        _kpi("Sharpe", "n/d" if sh is None else f"{sh:.2f}"),
        _kpi("Perte max" if fr_ else "Max drawdown", _f(ind["drawdown_max"]), "#c0392b"),
        _kpi("Frais" if fr_ else "Fees", _f(ind["ter_moyen"], 2)),
    ])
    st.markdown(
        "<div style='background:#fff;border:1px solid #e3e8ee;border-radius:12px;padding:14px 16px'>"
        "<div style='display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px'>"
        f"<div><div style='font-size:12px;color:#6b7785'>{'Valeur du portefeuille' if fr_ else 'Portfolio value'}</div>"
        f"<div style='font-size:30px;font-weight:600;color:#1B2A41;line-height:1.1'>{_eur(montant)}</div>"
        f"<div style='color:{_col(pj)};font-size:13px'>{_eur(pj*montant, True)} · {pj*100:+.2f} % {'aujourd' + chr(39) + 'hui (fictif)' if fr_ else 'today (simulated)'}</div></div>"
        f"<div style='display:flex;gap:22px;flex-wrap:wrap'>{kpis}</div></div></div>", unsafe_allow_html=True)

    per = st.radio("période", ["1 an" if fr_ else "1y", "3 ans" if fr_ else "3y"], horizontal=True,
                   label_visibility="collapsed", key="per_detail")
    fin = (ind["perf_1a"] if per.startswith("1") else ind["perf_3a"]) or 0
    n = 252 if per.startswith("1") else 756
    rng = np.random.default_rng(7)
    bruit = rng.normal(0, 1, n).cumsum()
    bruit = bruit - np.linspace(0, bruit[-1], n)
    amp = (ind["volatilite"] or 0.03) * 0.25
    courbe = 100 * (1 + np.linspace(0, fin, n) + bruit / (np.abs(bruit).max() or 1) * amp)
    fig = go.Figure(go.Scatter(y=courbe, mode="lines", line=dict(color="#3E7CB1", width=2), fill="tozeroy",
                               fillcolor="rgba(62,124,177,0.08)", hovertemplate="%{y:.1f}<extra></extra>"))
    fig.update_layout(height=170, margin=dict(l=0, r=0, t=6, b=0), xaxis=dict(visible=False),
                      yaxis=dict(range=[courbe.min() * 0.99, courbe.max() * 1.01], showgrid=False))
    st.plotly_chart(fig, width="stretch", key="fig_detail_courbe")
    st.caption(("Courbe illustrative (base 100) calée sur la performance historique" if fr_ else "Illustrative curve (base 100)")
               + " · " + t("source_prix", L(), src=ind["source_prix"]))

    cols_ = ["#3E7CB1", "#12873f", "#9aa5b1", "#D85A30", "#1F3A5F", "#9CC3E6"]
    presentes = {u.loc[i, "classe"] for i in pf}
    classes_ordre = [c for c in ("monetaire", "obligations", "actions", "diversifiants", "scpi", "actif") if c in presentes]
    poids_cl = {c: sum(w for i, w in pf.items() if u.loc[i, "classe"] == c) for c in classes_ordre}
    couleur = {c: cols_[k % 6] for k, c in enumerate(classes_ordre)}
    seg = "".join(f"<div style='width:{poids_cl[c]*100:.1f}%;background:{couleur[c]}'></div>" for c in classes_ordre)
    leg = "".join(f"<span style='margin-right:14px'>{cls[c]} {poids_cl[c]*100:.0f} %</span>" for c in classes_ordre)
    st.markdown(f"<div style='display:flex;height:10px;border-radius:5px;overflow:hidden;margin:6px 0 4px'>{seg}</div>"
                f"<div style='font-size:12px;color:#6b7785;margin-bottom:10px'>{leg}</div>", unsafe_allow_html=True)

    def _sri(v):
        try:
            v = int(v)
            bg, fg = ("#E6F4EA", "#12873f") if v <= 2 else ("#FFF4DB", "#8a5a00") if v <= 4 else ("#FDE8E8", "#c0392b")
        except (TypeError, ValueError):
            return "<span style='font-size:11px;color:#6b7785'>n/d</span>"
        return f"<span style='font-size:11px;padding:2px 8px;border-radius:4px;background:{bg};color:{fg}'>{v}</span>"

    head = ("<div style='display:flex;gap:10px;font-size:11px;color:#6b7785;padding:6px 0;border-bottom:1px solid #eef1f5'>"
            f"<div style='flex:1'>{'Ligne' if fr_ else 'Holding'}</div><div style='width:60px'>{'Poids' if fr_ else 'Weight'}</div>"
            f"<div style='width:80px;text-align:right'>{'Montant' if fr_ else 'Amount'}</div><div style='width:60px;text-align:right'>{'Jour' if fr_ else 'Day'}</div>"
            f"<div style='width:62px;text-align:right'>1 {'an' if fr_ else 'y'}</div><div style='width:40px;text-align:center'>SRI</div></div>")
    blocs = ""
    for c in classes_ordre:
        ids = sorted([i for i in pf if u.loc[i, "classe"] == c], key=lambda i: -pf[i])
        mt_c = poids_cl[c] * montant
        p1_c = sum(pf[i] * (perf.loc[i, "perf_1a"] or 0) for i in ids) / poids_cl[c]
        lignes = ""
        for isin in ids:
            l = u.loc[isin]
            w = pf[isin]
            pjl = perf_jour_fictive(isin, l["classe"])
            p1, p3 = perf.loc[isin, "perf_1a"], perf.loc[isin, "perf_3a"]
            ter_ = l["ter_num"]
            ters = "" if pd.isna(ter_) or ter_ == 0 else f" · {'Frais' if fr_ else 'Fees'} {ter_*100:.2f} %"
            typ = l.get("type", "")
            try:
                cpn = float(l.get("coupon", "") or 0)
            except ValueError:
                cpn = 0.0
            if typ == "obligation":
                sous = f"{l['emetteur']} · {'zéro coupon' if cpn == 0 else f'coupon {cpn*100:.2f} %'} · {'échéance' if fr_ else 'maturity'} {l['maturite']}"
                extra = (f"<div><div style='color:#6b7785'>{'Émetteur' if fr_ else 'Issuer'}</div>{l['emetteur']}"
                         f"<div style='color:#6b7785;margin-top:4px'>{'Notation' if fr_ else 'Rating'}</div>{l['notation']}</div>"
                         f"<div><div style='color:#6b7785'>Coupon</div>{'Zéro coupon' if cpn == 0 else f'{cpn*100:.2f} %'}"
                         f"<div style='color:#6b7785;margin-top:4px'>{'Échéance' if fr_ else 'Maturity'}</div>{l['maturite']}</div>")
            elif typ == "action":
                sous = f"{l['ticker_yahoo']} · {l['secteur']} · {l['pays']}"
                extra = (f"<div><div style='color:#6b7785'>{'Secteur' if fr_ else 'Sector'}</div>{l['secteur']}"
                         f"<div style='color:#6b7785;margin-top:4px'>{'Pays' if fr_ else 'Country'}</div>{l['pays']}</div>")
            else:
                sous = f"{isin}{ters}"
                extra = ""
            lignes += (
                "<details style='border-bottom:1px solid #eef1f5'>"
                "<summary style='display:flex;align-items:center;gap:10px;padding:9px 0;cursor:pointer;list-style:none'>"
                f"<div style='flex:1;min-width:0'><div style='font-weight:600;color:#1B2A41'>{l['nom']}</div>"
                f"<div style='font-size:11px;color:#6b7785'>{sous}</div></div>"
                f"<div style='width:60px'><div style='height:5px;background:#eef1f5;border-radius:3px'><div style='width:{min(w/poids_cl[c]*100,100):.0f}%;height:5px;background:{couleur[c]};border-radius:3px'></div></div>"
                f"<div style='font-size:11px;color:#6b7785;margin-top:2px'>{w*100:.1f} %</div></div>"
                f"<div style='width:80px;text-align:right'>{_eur(w*montant)}</div>"
                f"<div style='width:60px;text-align:right;color:{_col(pjl)}'>{pjl*100:+.2f} %</div>"
                f"<div style='width:62px;text-align:right;color:{_col(p1)}'>{_f(p1, signe=True)}</div>"
                f"<div style='width:40px;text-align:center'>{_sri(l['sri'])}</div></summary>"
                "<div style='background:#F4F6F9;border-radius:8px;padding:10px 12px;margin:0 0 8px;display:flex;gap:20px;flex-wrap:wrap;font-size:12px'>"
                f"<div style='flex:2;min-width:220px;color:#4a5560'>{l['description']}</div>"
                f"<div><div style='color:#6b7785'>{'Perf. 3 ans' if fr_ else '3y perf.'}</div>{_f(p3, signe=True)}"
                f"<div style='color:#6b7785;margin-top:4px'>{'Enveloppe' if fr_ else 'Wrapper'}</div>{env_lignes[isin]}</div>"
                f"{extra}"
                f"<div><div style='color:#6b7785'>SFDR</div>{l['sfdr']}"
                f"<div style='color:#6b7785;margin-top:4px'>{'Documents' if fr_ else 'Documents'}</div><a href='{l['source']}' target='_blank'>DIC / fiche</a></div>"
                "</div></details>")
        blocs += (
            "<details style='background:#fff;border:1px solid #e3e8ee;border-radius:12px;margin:0;overflow:hidden'>"
            "<summary style='display:flex;justify-content:space-between;padding:12px 14px;cursor:pointer;background:#F7F9FB;list-style:none'>"
            f"<span style='font-weight:600;color:#1B2A41'><span style='display:inline-block;width:9px;height:9px;border-radius:50%;background:{couleur[c]};margin-right:8px'></span>{cls[c]} · {poids_cl[c]*100:.0f} %</span>"
            f"<span>{_eur(mt_c)} · <span style='color:{_col(p1_c)}'>{_f(p1_c, signe=True)}</span> ▾</span></summary>"
            f"<div style='padding:0 14px 6px'>{head}{lignes}</div></details>")
    st.markdown("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:10px;align-items:start'>"
                f"{blocs}</div>", unsafe_allow_html=True)
    st.caption("Cliquez sur une classe, puis sur une ligne, pour déplier." if fr_ else "Click a class, then a holding, to expand.")
    if ind["avertissements"]:
        with st.expander(t("avertissements", L())):
            for a_ in ind["avertissements"]:
                st.write("• " + a_)


# ---------------------------------------------------------------------------
# Étape 1 — Accueil
# ---------------------------------------------------------------------------
if S.etape == 0:
    accueil_marche.afficher_accueil(L(), aller, resume_accueil())

# ---------------------------------------------------------------------------
# Étape 2 — Montant
# ---------------------------------------------------------------------------
elif S.etape == 1:
    if "montant_in" not in S:
        S.montant_in = int(S.montant)
    S.montant = st.number_input(t("montant_q", L()), min_value=0, max_value=100_000_000,
                                step=10_000, key="montant_in")
    statut = scoring.verifier_montant(S.montant)
    if statut == "trop_bas":
        st.error(t("montant_bas", L()))
    elif statut == "trop_haut":
        st.warning(t("montant_haut", L()))
    navigation(desactiver=statut != "ok")

# ---------------------------------------------------------------------------
# Étape 3 — Questionnaire
# ---------------------------------------------------------------------------
elif S.etape == 2:
    r = S.reponses
    fr_ = L() == "fr"
    total_q = len(qn.QUESTIONS)
    st.caption((f"{total_q} questions, environ 10 minutes. Toutes les questions marquées d'un astérisque (*) sont obligatoires."
                if fr_ else f"{total_q} questions, about 10 minutes. Questions marked with an asterisk (*) are required."))
    # Pas de st.form : chaque réponse est gardée dans la session, donc changer de langue ne l'efface pas.
    nouvelles = {}
    n = 0
    for bloc, noms in qn.BLOCS.items():
        with st.container(border=True):
            st.markdown(f"#### {bloc}. {noms[L()]}")
            for q in [q for q in qn.QUESTIONS if q["bloc"] == bloc]:
                n += 1
                k, cle = q["id"], f"q_{q['id']}"
                precedent = r.get(k)
                obligatoire = q["type"] in ("choix", "oui_non")
                lib = f"{n}. {q[L()]}" + (" *" if obligatoire else "")
                fmt = lambda v, q=q: qn.libelle(q["id"], v, L())
                if cle not in S:                       # première fois (ou retour sur la page) : on reprend l'ancienne réponse
                    if q["type"] == "nombre":
                        S[cle] = int(precedent if precedent is not None else q["defaut"])
                    elif q["type"] == "multi":
                        S[cle] = [v for v in (precedent or [])]
                    elif precedent is not None:
                        S[cle] = precedent
                st.markdown(lib)    # libellé affiché à part : l'identité du widget (k) ne dépend pas de la langue
                if q["type"] == "nombre":
                    nouvelles[k] = st.number_input(k, label_visibility="collapsed", min_value=q["min"], max_value=q["max"], step=q.get("pas", 1), key=cle)
                elif q["type"] == "choix":
                    nouvelles[k] = st.radio(k, [o[0] for o in q["options"]], label_visibility="collapsed", index=None, key=cle, format_func=fmt)
                elif q["type"] == "multi":
                    nouvelles[k] = st.multiselect(k, [o[0] for o in q["options"]], label_visibility="collapsed", key=cle, format_func=fmt)
                else:   # oui_non / vrai_faux
                    nouvelles[k] = st.radio(k, [True, False], label_visibility="collapsed", index=None, key=cle, horizontal=True, format_func=fmt)
    envoye = st.button(t("valider_reponses", L()), type="primary", key="btn_valider_q")
    if envoye:
        manquantes = [q for q in qn.QUESTIONS if q["type"] in ("choix", "oui_non") and nouvelles.get(q["id"]) is None]
        if manquantes:
            st.error(("Il manque encore des réponses : " if fr_ else "Some answers are missing: ")
                     + " ; ".join(q[L()] for q in manquantes[:6]) + (" …" if len(manquantes) > 6 else ""))
        elif S.montant > nouvelles["patrimoine"]:
            st.error((f"Le montant que vous souhaitez investir ({eur(S.montant)}) dépasse votre patrimoine total ({eur(nouvelles['patrimoine'])}). "
                      "Vérifiez l'un des deux chiffres.") if fr_ else
                     (f"The amount you want to invest ({eur(S.montant)}) exceeds your total wealth ({eur(nouvelles['patrimoine'])}). "
                      "Please check one of the two figures."))
        else:
            nouvelles["montant"] = S.montant
            S.reponses = nouvelles
            S.profil_calcule = scoring.calculer_profil(nouvelles)
            S.profil_choisi = None
            if "profil_radio" in S:
                del S["profil_radio"]
            S.enveloppe = regles.choisir_enveloppe(nouvelles, S.profil_calcule)
            S.enveloppe_choisie = None
            S.delta_actions = S.delta_oblig = 0
            S.horizon_ans = HORIZONS[nouvelles["horizon"]][2]
            S.explication = None
            S.etape = 3
            st.rerun()
    navigation(suivant=False)

# ---------------------------------------------------------------------------
# Étape 4 — Profil
# ---------------------------------------------------------------------------
elif S.etape == 3:
    p = S.profil_calcule
    if not p:
        S.etape = 2
        st.rerun()
    fr_ = L() == "fr"
    num = p["profil"]
    nom = regles.PROFILS[num]["nom_en" if not fr_ else "nom"]
    st.markdown(f"### {t('profil_titre', L(), nom=nom, num=num)}")
    st.write(t("profil_regle", L()))
    noms = t("notes", L())

    def _barres(v):
        return "".join(f"<span style='display:inline-block;width:22px;height:7px;border-radius:3px;margin-right:3px;"
                       f"background:{'#1F3A5F' if i < v else '#d6e4f2'}'></span>" for i in range(5))

    lignes_n = "".join(f"<tr><td style='padding:5px 12px;color:#4a5560'>{noms[k]}</td><td style='padding:5px 12px'>{_barres(v)}</td>"
                       f"<td style='padding:5px 12px;text-align:right;font-weight:600'>{v}/5</td></tr>" for k, v in p["notes"].items())
    st.markdown(f"<table style='width:100%;max-width:480px;margin:4px auto 8px;border-collapse:collapse;font-size:14px;"
                f"border:1px solid #e3e8ee;border-radius:8px'>{lignes_n}</table>", unsafe_allow_html=True)
    if p["plafonds"]:
        elems = p["plafonds"] if fr_ else [f"{noms[k]}: {v}/5" for k, v in p["notes"].items() if v < 5]
        st.markdown(f"**{t('plafonds', L())}**")
        st.markdown("<ul style='margin:2px 0 8px;padding-left:20px;line-height:1.5'>"
                    + "".join(f"<li>{x}</li>" for x in elems) + "</ul>", unsafe_allow_html=True)
    for a in p.get("alertes", []):
        st.warning(a)
    st.markdown("**" + ("Choisissez votre niveau de risque" if fr_ else "Choose your risk level") + "**")
    if "profil_radio" not in S:
        S.profil_radio = num
    S.profil_choisi = st.radio("niveau", [1, 2, 3, 4, 5], key="profil_radio", horizontal=True,
                               label_visibility="collapsed",
                               format_func=lambda n: f"{n} - {regles.PROFILS[n]['nom_en' if not fr_ else 'nom']}")
    if S.profil_choisi > num:
        st.warning(("Vous choisissez un profil plus risqué que celui recommandé (" + str(num) + "). Vous pouvez perdre plus d'argent en cas de baisse des marchés.")
                   if fr_ else ("You chose a riskier profile than the recommended one (" + str(num) + "). You may lose more if markets fall."))
    S.enveloppe = regles.choisir_enveloppe(S.reponses, S.profil_choisi)
    navigation()

# ---------------------------------------------------------------------------
# Étape 6 — Portefeuille
# ---------------------------------------------------------------------------
elif S.etape == 5:
    p = profil_num()
    lim = regles.PROFILS[p]
    with st.expander(t("ajuster", L())):
        c1, c2 = st.columns(2)
        da = c1.slider(t("delta_actions", L()), -10, 10, S.delta_actions)
        do = c2.slider(t("delta_oblig", L()), -10, 10, S.delta_oblig)
        st.caption(t("ajust_monetaire", L()))
        try:
            regles.ajuster_allocation(p, da / 100, do / 100)
            ok = True
        except ValueError as e:
            st.error(t("ajust_refuse", L(), raison=e))
            ok = False
        if ok and (da, do) != (S.delta_actions, S.delta_oblig):
            ancien = (S.delta_actions, S.delta_oblig)
            S.delta_actions, S.delta_oblig = da, do
            ind_test = _analyser(tuple(sorted(portefeuille_courant().items())))
            if ind_test["volatilite"] is not None and ind_test["volatilite"] > lim["vol_max"] and da > 0:
                st.error(t("vol_depassee", L(), vol=pct(ind_test["volatilite"]), max=pct(lim["vol_max"])))
                S.delta_actions, S.delta_oblig = ancien
    if S.note_construction:
        st.info({"ajustement": "Votre ajustement n'a pas pu être appliqué avec vos préférences : portefeuille de référence conservé.",
                 "exclusions": "Vos exclusions sectorielles rendent le portefeuille impossible à construire : elles n'ont pas été appliquées.",
                 "esg": "Le filtre ESG n'a pas pu être appliqué."}[S.note_construction])
    page_detail()
    navigation()

# ---------------------------------------------------------------------------
# Détail du portefeuille (depuis l'accueil)
# ---------------------------------------------------------------------------
elif S.etape == 11:
    st.button("← " + ("Retour à l'accueil" if L() == "fr" else "Back to home"), on_click=aller, args=(0,), key="btn_detail_home")
    st.markdown(f"## {'Détail de mon portefeuille' if L() == 'fr' else 'My portfolio details'}")
    if not S.profil_calcule:
        st.info("Complétez d'abord le questionnaire." if L() == "fr" else "Complete the questionnaire first.")
    else:
        page_detail()
        c1, c2 = st.columns(2)
        c1.button("Simulation", on_click=aller, args=(6,), width="stretch", key="btn_det_sim")
        c2.button("Mes documents" if L() == "fr" else "My documents", on_click=aller, args=(12,), width="stretch", key="btn_det_doc")

elif S.etape == 6:
    r = S.reponses
    fr_ = L() == "fr"
    mini, maxi, _ = HORIZONS.get(r.get("horizon"), (1, 30, 10))
    cs1, cs2, _ = st.columns([1, 1, 1])
    S.horizon_ans = cs1.slider(t("horizon_sim", L()), mini, maxi, int(S.horizon_ans or maxi))
    S.ter_trad = cs2.slider("Frais d'une gestion traditionnelle (% par an)" if fr_ else "Traditional management fees (% p.a.)",
                            0.5, 3.0, float(S.ter_trad), 0.1)
    pf = portefeuille_courant()
    items = tuple(sorted(pf.items()))
    with st.spinner("Monte Carlo…"):
        sim = _simuler(items, r["montant"], r.get("versement_mensuel", 0), S.horizon_ans, r.get("cible", 0))
    ind = _analyser(items)
    h = sim["hypotheses"]
    versement = r.get("versement_mensuel", 0)
    brut = h["rendement_portefeuille"] + ind["ter_moyen"]
    trad = [r["montant"]]
    for an in range(1, S.horizon_ans + 1):
        trad.append(simulation.impact_frais(r["montant"], versement, an, brut, ind["ter_moyen"],
                                            S.ter_trad / 100)["capital_traditionnel"])
    debut = pd.Timestamp.today().normalize()
    dates = [debut + pd.DateOffset(years=an) for an in range(S.horizon_ans + 1)]
    fmt_eur = "%{y:,.0f} €"
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=sim["p90"], name=t("favorable", L()), line=dict(width=1, color="#2E7D32"),
                             hovertemplate=fmt_eur))
    fig.add_trace(go.Scatter(x=dates, y=sim["p10"], name=t("defavorable", L()), fill="tonexty",
                             fillcolor="rgba(46,125,50,0.12)", line=dict(width=1, color="#C62828"), hovertemplate=fmt_eur))
    fig.add_trace(go.Scatter(x=dates, y=sim["p50"], name=t("central", L()), line=dict(width=3, color="#1F3A5F"),
                             hovertemplate=fmt_eur))
    fig.add_trace(go.Scatter(x=dates, y=trad, name=("Gestion traditionnelle" if fr_ else "Traditional management")
                             + f" ({S.ter_trad:.1f} %)", line=dict(width=2, color="#D85A30"), hovertemplate=fmt_eur))
    fig.add_trace(go.Scatter(x=dates, y=sim["capital_verse"], name=t("verse", L()),
                             line=dict(dash="dot", color="#9AA5B1"), hovertemplate=fmt_eur))
    if r.get("cible"):
        fig.add_hline(y=r["cible"], line_dash="dot", line_color="#E65100",
                      annotation_text=("Objectif" if fr_ else "Target"), annotation_position="top left")
    fig.update_layout(height=480, margin=dict(t=10, b=10, l=0, r=0), hovermode="x unified",
                      xaxis=dict(tickformat="%Y", dtick="M12" if S.horizon_ans <= 15 else "M24", showgrid=False),
                      yaxis=dict(tickformat=",.0f", ticksuffix=" €", gridcolor="#eef1f5"),
                      legend=dict(orientation="h", y=-0.12))
    st.plotly_chart(fig, width="stretch")
    imp = simulation.impact_frais(r["montant"], versement, S.horizon_ans, brut, ind["ter_moyen"], S.ter_trad / 100)
    m = st.columns(5)
    m[0].metric(t("defavorable", L()), eur(sim["p10"][-1]))
    m[1].metric(t("central", L()), eur(sim["p50"][-1]))
    m[2].metric(t("favorable", L()), eur(sim["p90"][-1]))
    m[3].metric("Avec nos frais" if fr_ else "With our fees", eur(imp["capital_portefeuille"]))
    m[4].metric("Gestion traditionnelle" if fr_ else "Traditional", eur(imp["capital_traditionnel"]),
                delta=("−" if imp["ecart"] >= 0 else "+") + eur(abs(imp["ecart"])), delta_color="inverse")
    if sim["proba_cible"] is not None:
        st.metric(t("proba", L(), cible=eur(r["cible"])), pct(sim["proba_cible"], 0))
    else:
        st.caption(t("pas_cible", L()))
    with st.expander(t("hypotheses", L())):
        st.write(t("hyp_texte", L(), mu=pct(h["rendement_portefeuille"]), vol=pct(h["volatilite_portefeuille"]),
                   n=f"{h['trajectoires']:,}".replace(",", " "), src=h["source"], corr=h["methode_correlation"]))
        st.caption("Les frais de la gestion traditionnelle sont une valeur de démonstration." if fr_ else
                   "Traditional fees are a demo value.")
    navigation()

# ---------------------------------------------------------------------------
# Étape 8 — Explication
# ---------------------------------------------------------------------------
elif S.etape == 7:
    import re
    fr_ = L() == "fr"
    d = dossier_complet()
    st.markdown(f"### {t('explication_titre', L())}")
    if S.explication is None:
        with st.spinner("…"):
            S.explication = llm.expliquer(d)
            S.source_explication = llm.derniere_source
    plan_b = str(S.source_explication or "").lower().startswith("plan b")
    if not plan_b and S.explication:
        with st.container(border=True):
            st.markdown(S.explication)
    phrases = d["justifications"]
    if phrases:
        st.info(phrases[0])
    cartes = ""
    autres = []
    for ph in phrases[1:]:
        mt = re.match(r"^(.*?) \(([\d.,]+\s?%)\)\s?:\s?(.*)$", ph, re.S)
        if not mt:
            autres.append(ph)
            continue
        nom_, poids_, txt_ = mt.groups()
        cartes += ("<div style='border:1px solid #e3e8ee;border-radius:10px;padding:10px 12px;background:#fff'>"
                   f"<div style='display:flex;justify-content:space-between;gap:8px'><b style='color:#1B2A41'>{nom_}</b>"
                   f"<span style='font-size:12px;padding:2px 8px;border-radius:6px;background:#EAF2FB;color:#1F3A5F;white-space:nowrap'>{poids_}</span></div>"
                   f"<div style='font-size:13px;color:#4a5560;margin-top:4px'>{txt_}</div></div>")
    if cartes:
        st.markdown("**" + ("Pourquoi ces lignes ?" if fr_ else "Why these holdings?") + "**")
        st.markdown("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px'>"
                    + cartes + "</div>", unsafe_allow_html=True)
    for ph in autres:
        st.write("• " + ph)
    st.caption("Les performances passées ne préjugent pas des performances futures ; les simulations ne sont pas une garantie."
               if fr_ else "Past performance does not predict future results; simulations are not a guarantee.")
    if not plan_b and st.button("Régénérer l'explication" if fr_ else "Regenerate"):
        S.explication = None
        st.rerun()
    navigation()

# ---------------------------------------------------------------------------
# Documents (depuis l'accueil)
# ---------------------------------------------------------------------------
elif S.etape == 12:
    fr_ = L() == "fr"
    st.button("← " + ("Retour à l'accueil" if fr_ else "Back to home"), on_click=aller, args=(0,), key="btn_doc_home")
    st.markdown(f"## {'Mes documents' if fr_ else 'My documents'}")
    if not S.profil_calcule:
        st.info("Complétez d'abord le questionnaire pour générer vos documents." if fr_ else
                "Complete the questionnaire first.")
        st.button("Commencer" if fr_ else "Start", on_click=aller, args=(1,), type="primary", key="btn_doc_start")
    else:
        d = dossier_complet()
        if not d["explication"]:
            d["explication"] = llm.plan_b(d)
        chemin_xl = livrable_excel.generer_excel(d)
        chemin_pdf = livrable_pdf.generer_pdf(d)
        c1, c2 = st.columns(2)
        with c1.container(border=True):
            st.markdown("#### 📊 " + ("Fichier Excel" if fr_ else "Excel file"))
            st.caption("Votre portefeuille ligne par ligne, avec les indicateurs et la simulation."
                       if fr_ else "Your portfolio line by line, with indicators and simulation.")
            with open(chemin_xl, "rb") as f:
                st.download_button(t("telech_excel", L()), f.read(), file_name=os.path.basename(chemin_xl),
                                   width="stretch", key="dl_excel")
        with c2.container(border=True):
            st.markdown("#### 📄 " + ("Déclaration d'adéquation (PDF)" if fr_ else "Suitability statement (PDF)"))
            st.caption("Votre profil, l'enveloppe, le portefeuille et les justifications, à conserver."
                       if fr_ else "Your profile, wrapper, portfolio and rationale.")
            with open(chemin_pdf, "rb") as f:
                st.download_button(t("telech_pdf", L()), f.read(), file_name=os.path.basename(chemin_pdf),
                                   mime="application/pdf", width="stretch", key="dl_pdf")
