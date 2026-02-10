"""Claim Auditor — Streamlit UI.

Run with Docker (recommended):
    docker compose up streamlit

Run locally:
    streamlit run streamlit_app.py --server.port 8501

Access: http://localhost:8501
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
    page_icon="⚖️",
    layout="wide",
)

# Minimal CSS for polish
st.markdown("""
<style>
    /* Subtle improvements without overhaul */
    .block-container {
        padding-top: 2rem;
        max-width: 1400px;
    }

    /* Trust badge styling */
    .trust-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 14px;
    }
    .trust-high { background: #d1fae5; color: #065f46; }
    .trust-good { background: #dbeafe; color: #1e40af; }
    .trust-medium { background: #fef3c7; color: #92400e; }
    .trust-low { background: #fee2e2; color: #991b1b; }

    /* Cleaner headers */
    h1 { color: #0f172a; font-weight: 700; }
    h2 { color: #1e293b; font-weight: 600; margin-top: 2rem; }
    h3 { color: #334155; font-weight: 600; }

    /* Better card appearance */
    [data-testid="stExpander"] {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

VERDICT_DISPLAY_NAMES = {
    "verified": "Correct",
    "approximately_correct": "Mostly Correct",
    "misleading": "Misleading",
    "incorrect": "Incorrect",
    "unverifiable": "Cannot Verify",
}

PATTERN_ICONS = {
    "consistent_rounding_up": "🔺",
    "metric_switching": "🔄",
    "increasing_inaccuracy": "📉",
    "gaap_nongaap_shifting": "📊",
    "selective_emphasis": "🎯",
}


def get_verdict_display_name(verdict: str) -> str:
    """Convert internal verdict name to user-friendly display name."""
    return VERDICT_DISPLAY_NAMES.get(verdict, verdict.replace("_", " ").title())


@st.cache_resource
def get_session_factory():
    """Cache the session factory (engine + Session class), not the session instance."""
    settings = Settings()

    # Fix database path for Streamlit Cloud deployment
    # Make path relative to this file's location, not working directory
    if settings.database_url.startswith("sqlite:///./"):
        # Get path to this file's directory
        app_dir = Path(__file__).parent
        db_relative_path = settings.database_url.replace("sqlite:///./", "")
        db_path = app_dir / db_relative_path

        # Ensure the path exists
        if not db_path.exists():
            st.error(f"Database not found at {db_path}")
            st.info(f"Looking in: {app_dir}")
            st.info(f"Files available: {list(app_dir.glob('**/*.db'))}")
            st.stop()

        # Use absolute path
        database_url = f"sqlite:///{db_path.absolute()}"
    else:
        database_url = settings.database_url

    engine = build_engine(database_url, echo=False)
    return build_session_factory(engine)


def get_db():
    """Get a fresh database session for the current request."""
    # Check if we already have a session in st.session_state for this page load
    if 'db_session' not in st.session_state:
        st.session_state.db_session = get_session_factory()()
    return st.session_state.db_session


db = get_db()


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


def get_trust_badge_html(trust_score: float) -> str:
    """Return HTML for trust level badge."""
    if trust_score >= 80:
        return '<span class="trust-badge trust-high">High Trust</span>'
    elif trust_score >= 60:
        return '<span class="trust-badge trust-good">Good</span>'
    elif trust_score >= 40:
        return '<span class="trust-badge trust-medium">Mixed</span>'
    else:
        return '<span class="trust-badge trust-low">Low Trust</span>'


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
        # Escape dollar signs to prevent LaTeX rendering
        explanation = vf.explanation.replace('$', r'\$')
        st.markdown(f"**Explanation:** {explanation}")
        if vf.misleading_flags:
            flags = ", ".join(f.replace("_", " ") for f in vf.misleading_flags)
            st.warning(f"Flags: {flags}")

    if c.context_snippet:
        # Escape dollar signs to prevent LaTeX rendering
        context = c.context_snippet.replace('$', r'\$')
        st.caption(f'Context: "{context}"')

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


@st.dialog("Company Analysis", width="large")
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
    st.caption(f"{comp.sector} · {total} claims analyzed across earnings calls")

    col_trust, col_acc = st.columns([1, 2])
    with col_trust:
        st.metric("Trust Score", f"{trust:.0f} / 100")
        st.progress(min(trust / 100, 1.0))
        st.markdown(get_trust_badge_html(trust), unsafe_allow_html=True)
    with col_acc:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Correct", v_counts["verified"])
        c2.metric("Mostly Correct", v_counts["approximately_correct"])
        c3.metric("Misleading", v_counts["misleading"])
        c4.metric("Incorrect", v_counts["incorrect"])
        c5.metric("Cannot Verify", v_counts["unverifiable"])

    st.markdown("---")

    # ── Quarter-to-Quarter Breakdown ──────────────────────────────────
    quarter_stats = compute_quarter_stats(claims)
    if quarter_stats:
        st.markdown("### Quarter-to-Quarter Performance")

        # Summary table
        table_data = []
        for qkey, v, qtotal, qacc, qtrust, _ in quarter_stats:
            table_data.append({
                "Quarter": qkey,
                "Claims": qtotal,
                "Correct": v["verified"],
                "Mostly": v["approximately_correct"],
                "Misleading": v["misleading"],
                "Incorrect": v["incorrect"],
                "N/A": v["unverifiable"],
                "Accuracy": f"{qacc:.0%}",
                "Trust": f"{qtrust:.0f}",
            })
        st.dataframe(table_data, use_container_width=True, hide_index=True)

        # Trend indicators
        if len(quarter_stats) >= 2:
            latest_trust = quarter_stats[0][4]
            prev_trust = quarter_stats[1][4]
            delta = latest_trust - prev_trust
            if delta > 0:
                trend = "↑ Improving"
                trend_color = "green"
            elif delta < 0:
                trend = "↓ Declining"
                trend_color = "red"
            else:
                trend = "→ Stable"
                trend_color = "gray"

            st.markdown(
                f"**Recent Trend:** :{trend_color}[{trend}] — "
                f"Trust moved **{delta:+.0f}** points from {quarter_stats[1][0]} to {quarter_stats[0][0]}"
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
        st.markdown("### Systematic Discrepancy Patterns")
        st.caption("Cross-quarter analysis reveals consistent patterns in how management communicates financial performance.")
        if pattern_source == "live":
            st.info("💡 Computed on-demand — run `--step analyze` to persist patterns.")
        for p in patterns_display:
            ptype = p.pattern_type.value if hasattr(p.pattern_type, "value") else p.pattern_type
            icon = PATTERN_ICONS.get(ptype, "🔍")
            severity_pct = f"{p.severity * 100:.0f}%"
            quarters = p.affected_quarters if isinstance(p.affected_quarters, list) else []
            with st.expander(
                f"{icon} **{ptype.replace('_', ' ').title()}** — "
                f"Severity: {severity_pct} · Quarters: {', '.join(quarters)}"
            ):
                st.write(p.description)
                evidence = p.evidence if isinstance(p.evidence, list) else []
                for ev in evidence:
                    st.caption(f"→ {ev}")
        st.markdown("---")

    # ── Top Discrepancies ─────────────────────────────────────────────
    bad_claims = [
        c for c in claims
        if c.verification and c.verification.verdict in ("misleading", "incorrect")
    ]
    if bad_claims:
        st.markdown("### Material Discrepancies")
        st.caption("Claims flagged as misleading or incorrect, sorted by severity.")
        for c in bad_claims[:5]:
            vf = c.verification
            verdict_label = get_verdict_display_name(vf.verdict)
            # Escape dollar signs to prevent LaTeX rendering
            claim_preview = c.claim_text[:80].replace('$', r'\$')
            with st.expander(f'**{verdict_label}** — "{claim_preview}…" — {c.speaker}'):
                _render_claim_detail(c, vf)
        st.markdown("---")

    # ── Per-Quarter Claims ────────────────────────────────────────────
    if quarter_stats:
        st.markdown("### All Claims by Quarter")
        for qkey, v, qtotal, qacc, qtrust, qclaims in quarter_stats:
            trust_label = "High Trust" if qtrust >= 80 else "Good" if qtrust >= 60 else "Mixed" if qtrust >= 40 else "Low Trust"
            with st.expander(f"**{qkey}** — {qtotal} claims · {qacc:.0%} accuracy · Trust: {qtrust:.0f} ({trust_label})"):
                for c in qclaims:
                    vf = c.verification
                    if vf:
                        verdict_label = get_verdict_display_name(vf.verdict)
                    else:
                        verdict_label = "Pending"
                    # Escape dollar signs to prevent LaTeX rendering
                    claim_preview = c.claim_text[:100].replace('$', r'\$')
                    st.markdown(
                        f'**{verdict_label}** — "{claim_preview}"'
                    )


# ── Main App ─────────────────────────────────────────────────────────────

companies = get_companies()

if not companies:
    st.title("Claim Auditor")
    st.warning(
        "**No data found.** Run the pipeline first to analyze earnings calls:\n\n"
        "```bash\ncd backend && python -m scripts.run_pipeline\n```"
    )
    st.stop()

# ── Sidebar ──────────────────────────────────────────────────────────────

st.sidebar.title("Claim Auditor")
st.sidebar.caption("Automated verification of management claims from earnings calls")
st.sidebar.markdown("---")

view = st.sidebar.radio("Navigate", ["Dashboard", "Company Deep Dive"], label_visibility="collapsed")

if view == "Company Deep Dive":
    selected_ticker = st.sidebar.selectbox(
        "Select Company",
        options=[c.ticker for c in companies],
        format_func=lambda t: f"{t} — {next(c.name for c in companies if c.ticker == t)}",
    )
    verdict_filter = st.sidebar.multiselect(
        "Filter by verdict",
        options=["verified", "approximately_correct", "misleading", "incorrect", "unverifiable"],
        default=[],
        format_func=get_verdict_display_name,
    )

# ══════════════════════════════════════════════════════════════════════════
# DASHBOARD VIEW
# ══════════════════════════════════════════════════════════════════════════

if view == "Dashboard":
    st.title("Dashboard")
    st.caption(
        "Systematically analyzing quantitative claims from earnings call transcripts against actual financial data. "
        "Identifying discrepancies, misleading framing, and patterns of inaccurate communication."
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
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total Claims", len(all_claims))
    col2.metric("Correct", agg_v["verified"])
    col3.metric("Mostly Correct", agg_v["approximately_correct"])
    col4.metric("Misleading", agg_v["misleading"])
    col5.metric("Incorrect", agg_v["incorrect"])
    col6.metric("Cannot Verify", agg_v["unverifiable"])

    st.markdown("---")

    # Company cards
    st.subheader("Company Overview")

    # Sort by trust score descending
    company_data.sort(key=lambda x: x[4], reverse=True)

    for i in range(0, len(company_data), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(company_data):
                comp, v, total, acc, trust = company_data[i + j]
                with col:
                    # Header with trust badge
                    st.markdown(f"### {comp.ticker}")
                    st.markdown(get_trust_badge_html(trust), unsafe_allow_html=True)
                    st.caption(f"**{comp.name}** · {comp.sector}")

                    st.progress(min(trust / 100, 1.0), text=f"Trust Score: {trust:.0f}/100")

                    sub = st.columns(5)
                    sub[0].metric("Cor", v["verified"], label_visibility="visible")
                    sub[1].metric("Mst", v["approximately_correct"], label_visibility="visible")
                    sub[2].metric("Mis", v["misleading"], label_visibility="visible")
                    sub[3].metric("Inc", v["incorrect"], label_visibility="visible")
                    sub[4].metric("N/A", v["unverifiable"], label_visibility="visible")

                    # Show pattern badges on company cards
                    comp_patterns = all_patterns.get(comp.id, [])
                    if comp_patterns:
                        badges = " ".join(
                            PATTERN_ICONS.get(p.pattern_type, "🔍")
                            for p in comp_patterns
                        )
                        st.caption(f"{total} claims · {acc:.0%} accurate · Patterns: {badges}")
                    else:
                        st.caption(f"{total} claims · {acc:.0%} accurate · No patterns detected")

                    # ── "View Details" button opens popup dialog ──
                    if st.button(
                        f"View {comp.ticker} Analysis",
                        key=f"detail_{comp.id}",
                        use_container_width=True,
                    ):
                        show_company_detail(comp.id)

                    st.markdown("---")

    # ── Cross-Company Discrepancy Patterns ────────────────────────────
    all_pattern_list = [p for pats in all_patterns.values() for p in pats]
    if all_pattern_list:
        st.markdown("---")
        st.subheader("Systematic Communication Patterns")
        st.caption(
            "Recurring patterns of potentially misleading communication detected across "
            "multiple quarters. These patterns suggest systematic issues rather than isolated errors."
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
                    f"(Severity: {severity_pct}, Quarters: {quarters})"
                ):
                    st.write(p.description)
                    if p.evidence:
                        for ev in p.evidence:
                            st.caption(f"→ {ev}")

# ══════════════════════════════════════════════════════════════════════════
# COMPANY DEEP DIVE VIEW
# ══════════════════════════════════════════════════════════════════════════

elif view == "Company Deep Dive":
    company = next(c for c in companies if c.ticker == selected_ticker)
    claims = get_claims_for_company(company.id)
    v_counts, total, accuracy, trust = compute_stats(claims)

    # Header
    st.title(f"{company.ticker} — {company.name}")
    st.caption(f"{company.sector} · {total} claims analyzed across earnings calls")

    # Trust score + verdict breakdown
    col_trust, col_acc = st.columns([1, 2])
    with col_trust:
        st.metric("Trust Score", f"{trust:.0f} / 100")
        st.progress(min(trust / 100, 1.0))
        st.markdown(get_trust_badge_html(trust), unsafe_allow_html=True)
    with col_acc:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Correct", v_counts["verified"])
        c2.metric("Mostly Correct", v_counts["approximately_correct"])
        c3.metric("Misleading", v_counts["misleading"])
        c4.metric("Incorrect", v_counts["incorrect"])
        c5.metric("Cannot Verify", v_counts["unverifiable"])

    st.markdown("---")

    # ── Quarter-to-Quarter Breakdown ──────────────────────────────────
    quarter_stats = compute_quarter_stats(claims)
    if quarter_stats:
        st.subheader("Quarter-to-Quarter Performance")

        # Summary table
        table_data = []
        for qkey, v, qtotal, qacc, qtrust, _ in quarter_stats:
            table_data.append({
                "Quarter": qkey,
                "Claims": qtotal,
                "Correct": v["verified"],
                "Mostly": v["approximately_correct"],
                "Misleading": v["misleading"],
                "Incorrect": v["incorrect"],
                "N/A": v["unverifiable"],
                "Accuracy": f"{qacc:.0%}",
                "Trust": f"{qtrust:.0f}",
            })
        st.dataframe(table_data, use_container_width=True, hide_index=True)

        # Trend indicators
        if len(quarter_stats) >= 2:
            latest_trust = quarter_stats[0][4]
            prev_trust = quarter_stats[1][4]
            delta = latest_trust - prev_trust
            if delta > 0:
                trend = "↑ Improving"
                trend_color = "green"
            elif delta < 0:
                trend = "↓ Declining"
                trend_color = "red"
            else:
                trend = "→ Stable"
                trend_color = "gray"

            st.markdown(
                f"**Recent Trend:** :{trend_color}[{trend}] — "
                f"Trust moved **{delta:+.0f}** points from {quarter_stats[1][0]} to {quarter_stats[0][0]}"
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
        st.subheader("Systematic Discrepancy Patterns")
        st.caption("Cross-quarter analysis reveals consistent patterns in how management communicates financial performance.")
        if pattern_source == "live":
            st.info("💡 Computed on-demand — run `--step analyze` to persist patterns.")
        for p in patterns_display:
            ptype = p.pattern_type.value if hasattr(p.pattern_type, "value") else p.pattern_type
            icon = PATTERN_ICONS.get(ptype, "🔍")
            severity_pct = f"{p.severity * 100:.0f}%"
            quarters = p.affected_quarters if isinstance(p.affected_quarters, list) else []
            with st.expander(
                f"{icon} **{ptype.replace('_', ' ').title()}** — "
                f"Severity: {severity_pct} · Quarters: {', '.join(quarters)}"
            ):
                st.write(p.description)
                evidence = p.evidence if isinstance(p.evidence, list) else []
                for ev in evidence:
                    st.caption(f"→ {ev}")
        st.markdown("---")

    # ── Top Discrepancies ────────────────────────────────────────────
    bad_claims = [
        c for c in claims
        if c.verification and c.verification.verdict in ("misleading", "incorrect")
    ]
    if bad_claims:
        st.subheader("Material Discrepancies")
        st.caption("Claims flagged as misleading or incorrect, sorted by severity.")
        for c in bad_claims[:5]:
            vf = c.verification
            verdict_label = get_verdict_display_name(vf.verdict)
            # Escape dollar signs to prevent LaTeX rendering
            claim_preview = c.claim_text[:80].replace('$', r'\$')
            with st.expander(f'**{verdict_label}** — "{claim_preview}…" — {c.speaker}'):
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

                # Escape dollar signs to prevent LaTeX rendering
                claim_preview = c.claim_text[:90].replace('$', r'\$')

                if vf:
                    verdict_label = get_verdict_display_name(vf.verdict)
                    header = f'**{verdict_label}** — "{claim_preview}"'
                else:
                    header = f'**Pending** — "{claim_preview}"'

                with st.expander(header):
                    _render_claim_detail(c, vf, show_quarter=False)
