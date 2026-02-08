"""Claim Auditor — Streamlit UI.

Run:
    streamlit run streamlit_app.py --server.port 8501
"""

import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
from sqlalchemy.orm import joinedload

from app.config import Settings
from app.database import Base, build_engine, build_session_factory
from app.engines.discrepancy_analyzer import DiscrepancyAnalyzer
from app.models.claim import ClaimModel
from app.models.company import CompanyModel
from app.models.discrepancy_pattern import DiscrepancyPatternModel
from app.models.transcript import TranscriptModel
from app.models.verification import VerificationModel
from app.repositories.claim_repo import ClaimRepository
from app.repositories.company_repo import CompanyRepository
from app.repositories.discrepancy_pattern_repo import DiscrepancyPatternRepository
from app.schemas.verification import Verdict
from app.utils.scoring import compute_stats as _compute_stats

import app.models  # noqa: F401 — register all models

# ── Setup ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Claim Auditor",
    page_icon="📊",
    layout="wide",
)

VERDICT_COLORS = {
    "verified": "#16a34a",
    "approximately_correct": "#2563eb",
    "misleading": "#d97706",
    "incorrect": "#dc2626",
    "unverifiable": "#6b7280",
}

VERDICT_ICONS = {
    "verified": "✅",
    "approximately_correct": "≈",
    "misleading": "⚠️",
    "incorrect": "❌",
    "unverifiable": "❓",
}

PATTERN_ICONS = {
    "consistent_rounding_up": "🔺",
    "metric_switching": "🔄",
    "increasing_inaccuracy": "📉",
    "gaap_nongaap_shifting": "📊",
    "selective_emphasis": "🎯",
}


@st.cache_resource
def get_db_session():
    settings = Settings()
    engine = build_engine(settings.database_url, echo=False)
    Session = build_session_factory(engine)
    return Session()


db = get_db_session()


# ── Helpers ──────────────────────────────────────────────────────────────


def get_companies():
    return db.query(CompanyModel).order_by(CompanyModel.ticker).all()


def get_claims_for_company(company_id: int):
    return (
        db.query(ClaimModel)
        .join(TranscriptModel)
        .options(
            joinedload(ClaimModel.verification),
            joinedload(ClaimModel.transcript),
        )
        .filter(TranscriptModel.company_id == company_id)
        .order_by(TranscriptModel.year.desc(), TranscriptModel.quarter.desc())
        .all()
    )


def compute_stats(claims):
    """Thin wrapper around the shared scoring utility."""
    return _compute_stats(claims)


def compute_quarter_stats(claims):
    """Group claims by quarter and compute per-quarter verdict breakdown."""
    quarter_map: dict[str, list] = {}
    for c in claims:
        key = f"Q{c.transcript.quarter} {c.transcript.year}"
        quarter_map.setdefault(key, []).append(c)

    results = []
    for qkey in sorted(quarter_map.keys(), reverse=True):
        qclaims = quarter_map[qkey]
        v, total, acc, trust = compute_stats(qclaims)
        results.append((qkey, v, total, acc, trust, qclaims))
    return results


def get_patterns_for_company(company_id: int):
    """Load persisted discrepancy patterns from DB; fall back to live analysis."""
    repo = DiscrepancyPatternRepository(db)
    return repo.get_for_company(company_id)


def get_all_patterns():
    """Load all persisted patterns grouped by company_id."""
    repo = DiscrepancyPatternRepository(db)
    return repo.get_all_grouped()


def format_value(value, unit):
    if unit == "usd_billions":
        return f"${value:.1f}B"
    if unit == "usd_millions":
        return f"${value:,.0f}M"
    if unit == "usd":
        return f"${value:.2f}"
    if unit == "percent":
        return f"{value:.1f}%"
    if unit == "basis_points":
        return f"{value:.0f} bps"
    return str(value)


def _render_claim_detail(c, vf, show_quarter=True):
    """Render a single claim's details inside a container."""
    quarter_label = f"Q{c.transcript.quarter} {c.transcript.year}" if show_quarter else ""

    col_a, col_b, col_c = st.columns(3)
    col_a.markdown(f"**Speaker:** {c.speaker}")
    col_b.markdown(f"**Metric:** {c.metric.replace('_', ' ').title()}")
    col_c.markdown(f"**Type:** {c.metric_type.replace('_', ' ').title()}")

    col_d, col_e, col_f = st.columns(3)
    col_d.markdown(f"**Stated:** {format_value(c.stated_value, c.unit)}")
    if vf and vf.actual_value is not None:
        col_e.markdown(f"**Actual:** {format_value(vf.actual_value, c.unit)}")
        col_f.markdown(f"**Accuracy:** {vf.accuracy_score:.1%}" if vf.accuracy_score else "")
    else:
        col_e.markdown("**Actual:** —")

    if vf:
        st.markdown(f"**Explanation:** {vf.explanation}")
        if vf.misleading_flags:
            flags = ", ".join(f.replace("_", " ") for f in vf.misleading_flags)
            st.warning(f"🏴 Flags: {flags}")

    if c.context_snippet:
        st.caption(f'📎 Context: "{c.context_snippet}"')

    meta_parts = []
    if c.comparison_period and c.comparison_period != "none":
        meta_parts.append(f"Period: {c.comparison_period.replace('_', ' ')}")
    if c.comparison_basis:
        meta_parts.append(f"Basis: {c.comparison_basis}")
    meta_parts.append("GAAP" if c.is_gaap else "Non-GAAP")
    if c.segment:
        meta_parts.append(f"Segment: {c.segment}")
    meta_parts.append(f"Confidence: {c.confidence:.0%}")
    st.caption(" · ".join(meta_parts))


# ── Company Detail Dialog ────────────────────────────────────────────────


@st.dialog("Company Detail", width="large")
def show_company_detail(company_id: int):
    """Full company analysis in a popup dialog."""
    comp = next((c for c in get_companies() if c.id == company_id), None)
    if not comp:
        st.error("Company not found.")
        return

    claims = get_claims_for_company(comp.id)
    v_counts, total, accuracy, trust = compute_stats(claims)

    # ── Header ────────────────────────────────────────────────────────
    st.markdown(f"## {comp.ticker} — {comp.name}")
    st.caption(f"{comp.sector} · {total} claims analyzed")

    col_trust, col_acc = st.columns([1, 2])
    with col_trust:
        st.metric("Trust Score", f"{trust:.0f} / 100")
        st.progress(min(trust / 100, 1.0))
    with col_acc:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("✅ Verified", v_counts["verified"])
        c2.metric("≈ Approx", v_counts["approximately_correct"])
        c3.metric("⚠️ Misleading", v_counts["misleading"])
        c4.metric("❌ Incorrect", v_counts["incorrect"])
        c5.metric("❓ N/A", v_counts["unverifiable"])

    st.markdown("---")

    # ── Quarter-to-Quarter Breakdown ──────────────────────────────────
    quarter_stats = compute_quarter_stats(claims)
    if quarter_stats:
        st.markdown("### 📅 Quarter-to-Quarter Breakdown")

        # Summary table
        table_data = []
        for qkey, v, qtotal, qacc, qtrust, _ in quarter_stats:
            table_data.append({
                "Quarter": qkey,
                "Claims": qtotal,
                "✅": v["verified"],
                "≈": v["approximately_correct"],
                "⚠️": v["misleading"],
                "❌": v["incorrect"],
                "❓": v["unverifiable"],
                "Accuracy": f"{qacc:.0%}",
                "Trust": f"{qtrust:.0f}",
            })
        st.dataframe(table_data, use_container_width=True, hide_index=True)

        # Trend indicators
        if len(quarter_stats) >= 2:
            latest_trust = quarter_stats[0][4]
            prev_trust = quarter_stats[1][4]
            delta = latest_trust - prev_trust
            trend = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
            st.markdown(
                f"**Trend:** {trend} Trust moved **{delta:+.0f}** points "
                f"from {quarter_stats[1][0]} → {quarter_stats[0][0]}"
            )

        st.markdown("---")

    # ── Discrepancy Patterns ──────────────────────────────────────────
    persisted_patterns = get_patterns_for_company(comp.id)
    if persisted_patterns:
        patterns_display = persisted_patterns
        pattern_source = "persisted"
    else:
        cbq: dict[str, list] = {}
        for c in claims:
            key = f"Q{c.transcript.quarter} {c.transcript.year}"
            cbq.setdefault(key, []).append(c)
        analyzer = DiscrepancyAnalyzer()
        patterns_display = analyzer.analyze_company(comp.id, cbq)
        pattern_source = "live"

    if patterns_display:
        st.markdown("### 🔍 Cross-Quarter Patterns Detected")
        if pattern_source == "live":
            st.caption("⚡ Computed live — run `--step analyze` to persist.")
        for p in patterns_display:
            ptype = p.pattern_type.value if hasattr(p.pattern_type, "value") else p.pattern_type
            icon = PATTERN_ICONS.get(ptype, "🔍")
            severity_pct = f"{p.severity * 100:.0f}%"
            quarters = p.affected_quarters if isinstance(p.affected_quarters, list) else []
            with st.expander(
                f"{icon} **{ptype.replace('_', ' ').title()}** — "
                f"Severity: {severity_pct} · {', '.join(quarters)}"
            ):
                st.write(p.description)
                evidence = p.evidence if isinstance(p.evidence, list) else []
                for ev in evidence:
                    st.caption(f"📎 {ev}")
        st.markdown("---")

    # ── Top Discrepancies ─────────────────────────────────────────────
    bad_claims = [
        c for c in claims
        if c.verification and c.verification.verdict in ("misleading", "incorrect")
    ]
    if bad_claims:
        st.markdown("### 🚩 Top Discrepancies")
        for c in bad_claims[:5]:
            vf = c.verification
            icon = VERDICT_ICONS.get(vf.verdict, "")
            with st.expander(f'{icon} "{c.claim_text[:80]}…" — {c.speaker}'):
                _render_claim_detail(c, vf)
        st.markdown("---")

    # ── Per-Quarter Claims ────────────────────────────────────────────
    if quarter_stats:
        st.markdown("### 📋 Claims by Quarter")
        for qkey, v, qtotal, qacc, qtrust, qclaims in quarter_stats:
            trust_icon = (
                "🟢" if qtrust >= 80 else
                "🔵" if qtrust >= 60 else
                "🟡" if qtrust >= 40 else
                "🔴"
            )
            with st.expander(f"{trust_icon} **{qkey}** — {qtotal} claims · {qacc:.0%} accuracy · Trust {qtrust:.0f}"):
                for c in qclaims:
                    vf = c.verification
                    if vf:
                        icon = VERDICT_ICONS.get(vf.verdict, "")
                        verdict_label = vf.verdict.replace("_", " ").title()
                    else:
                        icon = "⏳"
                        verdict_label = "Pending"
                    st.markdown(
                        f'{icon} **{verdict_label}** — "{c.claim_text[:100]}"'
                    )


# ── Main App ─────────────────────────────────────────────────────────────

companies = get_companies()

if not companies:
    st.title("📊 Claim Auditor")
    st.warning(
        "No data found. Run the pipeline first:\n\n"
        "```bash\ncd backend && python -m scripts.run_pipeline\n```"
    )
    st.stop()

# ── Sidebar ──────────────────────────────────────────────────────────────

st.sidebar.title("📊 Claim Auditor")
st.sidebar.markdown("---")

view = st.sidebar.radio("View", ["Dashboard", "Company Deep Dive"])

if view == "Company Deep Dive":
    selected_ticker = st.sidebar.selectbox(
        "Company",
        options=[c.ticker for c in companies],
        format_func=lambda t: f"{t} — {next(c.name for c in companies if c.ticker == t)}",
    )
    verdict_filter = st.sidebar.multiselect(
        "Filter by verdict",
        options=["verified", "approximately_correct", "misleading", "incorrect", "unverifiable"],
        default=[],
        format_func=lambda v: f"{VERDICT_ICONS.get(v, '')} {v.replace('_', ' ').title()}",
    )

# ══════════════════════════════════════════════════════════════════════════
# DASHBOARD VIEW
# ══════════════════════════════════════════════════════════════════════════

if view == "Dashboard":
    st.title("📊 Claim Auditor — Dashboard")
    st.caption(
        "Analyzing management claims from earnings calls against actual financial data. "
        "Flagging discrepancies and misleading framing."
    )

    # Aggregate stats across all companies
    all_claims = []
    company_data = []
    all_patterns = get_all_patterns()  # {company_id: [DiscrepancyPatternModel]}
    for comp in companies:
        claims = get_claims_for_company(comp.id)
        all_claims.extend(claims)
        v, total, acc, trust = compute_stats(claims)
        company_data.append((comp, v, total, acc, trust))

    agg_v = {e.value: 0 for e in Verdict}
    for _, v, _, _, _ in company_data:
        for k in agg_v:
            agg_v[k] += v.get(k, 0)

    # Top-level metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Claims", len(all_claims))
    col2.metric("✅ Verified", agg_v["verified"])
    col3.metric("≈ Approx Correct", agg_v["approximately_correct"])
    col4.metric("⚠️ Misleading", agg_v["misleading"])
    col5.metric("❌ Incorrect", agg_v["incorrect"])

    st.markdown("---")

    # Company cards
    st.subheader("Companies")

    # Sort by trust score descending
    company_data.sort(key=lambda x: x[4], reverse=True)

    for i in range(0, len(company_data), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(company_data):
                comp, v, total, acc, trust = company_data[i + j]
                with col:
                    trust_color = (
                        "🟢" if trust >= 80 else
                        "🔵" if trust >= 60 else
                        "🟡" if trust >= 40 else
                        "🔴"
                    )
                    st.markdown(
                        f"### {comp.ticker} {trust_color}\n"
                        f"**{comp.name}** · {comp.sector}"
                    )
                    st.progress(min(trust / 100, 1.0), text=f"Trust: {trust:.0f}/100")

                    sub = st.columns(5)
                    sub[0].metric("✅", v["verified"], label_visibility="visible")
                    sub[1].metric("≈", v["approximately_correct"], label_visibility="visible")
                    sub[2].metric("⚠️", v["misleading"], label_visibility="visible")
                    sub[3].metric("❌", v["incorrect"], label_visibility="visible")
                    sub[4].metric("❓", v["unverifiable"], label_visibility="visible")

                    # Show pattern badges on company cards
                    comp_patterns = all_patterns.get(comp.id, [])
                    if comp_patterns:
                        badges = " ".join(
                            PATTERN_ICONS.get(p.pattern_type, "🔍")
                            for p in comp_patterns
                        )
                        st.caption(f"{total} claims · {acc:.0%} accuracy · Patterns: {badges}")
                    else:
                        st.caption(f"{total} claims · {acc:.0%} accuracy · ✨ No patterns")

                    # ── "View Details" button opens popup dialog ──
                    if st.button(
                        f"🔍 View {comp.ticker} Details",
                        key=f"detail_{comp.id}",
                        use_container_width=True,
                    ):
                        show_company_detail(comp.id)

                    st.markdown("---")

    # ── Cross-Company Discrepancy Patterns ────────────────────────────
    all_pattern_list = [p for pats in all_patterns.values() for p in pats]
    if all_pattern_list:
        st.markdown("---")
        st.subheader("🔍 Cross-Quarter Discrepancy Patterns")
        st.caption(
            "Systematic patterns of misleading communication detected across "
            "multiple earnings calls for each company."
        )

        # Summary counters by pattern type
        type_counts: dict[str, int] = {}
        for p in all_pattern_list:
            label = p.pattern_type.replace("_", " ").title()
            type_counts[label] = type_counts.get(label, 0) + 1

        pcols = st.columns(min(len(type_counts), 5))
        for idx, (ptype, cnt) in enumerate(sorted(type_counts.items())):
            icon = PATTERN_ICONS.get(ptype.lower().replace(" ", "_"), "🔍")
            pcols[idx % len(pcols)].metric(f"{icon} {ptype}", cnt)

        st.markdown("")

        # Detailed patterns per company
        for comp in companies:
            comp_pats = all_patterns.get(comp.id, [])
            if not comp_pats:
                continue
            for p in comp_pats:
                icon = PATTERN_ICONS.get(p.pattern_type, "🔍")
                label = p.pattern_type.replace("_", " ").title()
                severity_pct = f"{p.severity * 100:.0f}%"
                quarters = ", ".join(p.affected_quarters) if p.affected_quarters else "—"
                with st.expander(
                    f"{icon} **{comp.ticker}** — {label} "
                    f"(severity: {severity_pct}, quarters: {quarters})"
                ):
                    st.write(p.description)
                    if p.evidence:
                        for ev in p.evidence:
                            st.caption(f"📎 {ev}")

# ══════════════════════════════════════════════════════════════════════════
# COMPANY DEEP DIVE VIEW
# ══════════════════════════════════════════════════════════════════════════

elif view == "Company Deep Dive":
    company = next(c for c in companies if c.ticker == selected_ticker)
    claims = get_claims_for_company(company.id)
    v_counts, total, accuracy, trust = compute_stats(claims)

    # Header
    st.title(f"{company.ticker} — {company.name}")
    st.caption(f"{company.sector} · {total} claims analyzed")

    # Trust score + verdict breakdown
    col_trust, col_acc = st.columns([1, 2])
    with col_trust:
        st.metric("Trust Score", f"{trust:.0f} / 100")
        st.progress(min(trust / 100, 1.0))
    with col_acc:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("✅ Verified", v_counts["verified"])
        c2.metric("≈ Approx", v_counts["approximately_correct"])
        c3.metric("⚠️ Misleading", v_counts["misleading"])
        c4.metric("❌ Incorrect", v_counts["incorrect"])
        c5.metric("❓ N/A", v_counts["unverifiable"])

    st.markdown("---")

    # ── Quarter-to-Quarter Breakdown ──────────────────────────────────
    quarter_stats = compute_quarter_stats(claims)
    if quarter_stats:
        st.subheader("📅 Quarter-to-Quarter Breakdown")

        # Summary table
        table_data = []
        for qkey, v, qtotal, qacc, qtrust, _ in quarter_stats:
            table_data.append({
                "Quarter": qkey,
                "Claims": qtotal,
                "✅": v["verified"],
                "≈": v["approximately_correct"],
                "⚠️": v["misleading"],
                "❌": v["incorrect"],
                "❓": v["unverifiable"],
                "Accuracy": f"{qacc:.0%}",
                "Trust": f"{qtrust:.0f}",
            })
        st.dataframe(table_data, use_container_width=True, hide_index=True)

        # Trend indicators
        if len(quarter_stats) >= 2:
            latest_trust = quarter_stats[0][4]
            prev_trust = quarter_stats[1][4]
            delta = latest_trust - prev_trust
            trend = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
            st.markdown(
                f"**Trend:** {trend} Trust moved **{delta:+.0f}** points "
                f"from {quarter_stats[1][0]} → {quarter_stats[0][0]}"
            )

        st.markdown("---")

    # ── Cross-quarter discrepancy patterns ───────────────────────────
    persisted_patterns = get_patterns_for_company(company.id)
    if persisted_patterns:
        patterns_display = persisted_patterns
        pattern_source = "persisted"
    else:
        cbq: dict[str, list] = {}
        for c in claims:
            key = f"Q{c.transcript.quarter} {c.transcript.year}"
            cbq.setdefault(key, []).append(c)
        analyzer = DiscrepancyAnalyzer()
        patterns_display = analyzer.analyze_company(company.id, cbq)
        pattern_source = "live"

    if patterns_display:
        st.subheader("🔍 Cross-Quarter Patterns Detected")
        if pattern_source == "live":
            st.caption("⚡ Computed live — run `--step analyze` to persist.")
        for p in patterns_display:
            ptype = p.pattern_type.value if hasattr(p.pattern_type, "value") else p.pattern_type
            icon = PATTERN_ICONS.get(ptype, "🔍")
            severity_pct = f"{p.severity * 100:.0f}%"
            quarters = p.affected_quarters if isinstance(p.affected_quarters, list) else []
            with st.expander(
                f"{icon} **{ptype.replace('_', ' ').title()}** — "
                f"Severity: {severity_pct} · {', '.join(quarters)}"
            ):
                st.write(p.description)
                evidence = p.evidence if isinstance(p.evidence, list) else []
                for ev in evidence:
                    st.caption(f"📎 {ev}")
        st.markdown("---")

    # ── Top Discrepancies ────────────────────────────────────────────
    bad_claims = [
        c for c in claims
        if c.verification and c.verification.verdict in ("misleading", "incorrect")
    ]
    if bad_claims:
        st.subheader("🚩 Top Discrepancies")
        for c in bad_claims[:5]:
            vf = c.verification
            icon = VERDICT_ICONS.get(vf.verdict, "")
            with st.expander(f'{icon} "{c.claim_text[:80]}…" — {c.speaker}'):
                _render_claim_detail(c, vf)
        st.markdown("---")

    # ── All Claims Table ─────────────────────────────────────────────
    st.subheader("All Claims")

    # Apply verdict filter
    filtered = claims
    if verdict_filter:
        filtered = [
            c for c in claims
            if c.verification and c.verification.verdict in verdict_filter
        ]

    if not filtered:
        st.info("No claims match the selected filters.")
    else:
        # Group by quarter for better navigation
        quarter_groups: dict[str, list] = {}
        for c in filtered:
            key = f"Q{c.transcript.quarter} {c.transcript.year}"
            quarter_groups.setdefault(key, []).append(c)

        for qkey in sorted(quarter_groups.keys(), reverse=True):
            st.markdown(f"#### {qkey}")
            for c in quarter_groups[qkey]:
                vf = c.verification

                if vf:
                    icon = VERDICT_ICONS.get(vf.verdict, "")
                    verdict_label = vf.verdict.replace("_", " ").title()
                    header = f'{icon} **{verdict_label}** — "{c.claim_text[:90]}"'
                else:
                    header = f'⏳ Pending — "{c.claim_text[:90]}"'

                with st.expander(header):
                    _render_claim_detail(c, vf, show_quarter=False)
