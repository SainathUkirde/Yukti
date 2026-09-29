"""
backend/app/services/report_service.py
PDF report generation using ReportLab.
Generates a one-page well performance report with KPIs and provenance badges.
"""
import logging
import io
import os
import sys
from datetime import datetime, timezone

logger = logging.getLogger("report_service")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, ROOT)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                     TableStyle, HRFlowable)
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False
    logger.warning("ReportLab not installed — PDF reports unavailable")


def generate_well_report(state_dict: dict, opt_result: dict | None = None) -> bytes:
    """
    Generate a PDF report for a single well.
    Returns raw PDF bytes.
    """
    if not REPORTLAB_OK:
        raise RuntimeError("ReportLab not installed. Run: pip install reportlab")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             topMargin=2*cm, bottomMargin=2*cm,
                             leftMargin=2*cm, rightMargin=2*cm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title2", parent=styles["Title"],
                                  fontSize=16, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, spaceAfter=4)
    body = styles["Normal"]
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8,
                            textColor=colors.gray)

    well_id = state_dict.get("well_id", "Unknown")
    phase = state_dict.get("phase", "N/A")
    cycle = state_dict.get("cycle_number", "N/A")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    story = []

    # Header
    story.append(Paragraph("BAGHEWALA FIELD — DIGITAL TWIN WELL REPORT", title_style))
    story.append(Paragraph(f"Well: <b>{well_id}</b>  |  Generated: {now}  |  "
                            f"Phase: {phase.upper()}  |  Cycle: {cycle}", body))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 0.3*cm))

    def _val(key: str) -> str:
        v = state_dict.get(key, {})
        if isinstance(v, dict):
            return f"{v.get('value', 'N/A')} {v.get('unit', '')}".strip()
        return str(v)

    # KPI table
    story.append(Paragraph("Key Performance Indicators", h2))
    kpi_data = [
        ["Parameter", "Value", "Provenance"],
        ["Reservoir Temperature", _val("reservoir_temp_c"), "SIMULATED_LIVE"],
        ["Oil Viscosity", _val("oil_viscosity_cp"), "SIMULATED_LIVE"],
        ["Oil Rate", _val("oil_rate_m3d"), "SIMULATED_LIVE"],
        ["Water Cut", _val("water_cut_fraction"), "SIMULATED_LIVE"],
        ["Steam-Oil Ratio (SOR)", _val("sor"), "SIMULATED_LIVE"],
        ["Pump Efficiency", _val("pump_efficiency_fraction"), "SIMULATED_LIVE"],
        ["Motor Power", _val("motor_power_kw"), "SIMULATED_LIVE"],
        ["kWh/bbl", _val("kwh_per_bbl"), "SIMULATED_LIVE"],
        ["Rod Float Risk Score", _val("rod_float_risk_score"), "SIMULATED_LIVE"],
        ["Goodman Ratio", _val("goodman_ratio"), "SIMULATED_LIVE"],
        ["Active Fault", str(state_dict.get("active_fault") or "None"), "SIMULATED_LIVE"],
    ]
    kpi_table = Table(kpi_data, colWidths=[7*cm, 5*cm, 5*cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.4*cm))

    # SRP parameters
    story.append(Paragraph("SRP Configuration", h2))
    cfg = state_dict.get("config", {})
    srp_data = [
        ["Parameter", "Value"],
        ["SPM", f"{cfg.get('spm', 'N/A')} strokes/min"],
        ["Stroke Length", f"{cfg.get('stroke_length_m', 'N/A')} m"],
        ["VFD Frequency", f"{cfg.get('vfd_frequency_hz', 'N/A')} Hz"],
        ["Steam Volume (CWE)", f"{cfg.get('steam_volume_cwe_m3', 'N/A')} m³"],
        ["Soak Days", f"{cfg.get('soak_days', 'N/A')} days"],
    ]
    srp_table = Table(srp_data, colWidths=[7*cm, 10*cm])
    srp_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d5a8e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(srp_table)
    story.append(Spacer(1, 0.4*cm))

    # Optimizer recommendation (if available)
    if opt_result:
        story.append(Paragraph("Optimizer Recommendation", h2))
        rec = opt_result.get("recommended_config", {})
        deltas = opt_result.get("kpi_deltas", {})
        opt_data = [
            ["Recommended Config", "Value"],
            ["Steam Volume", f"{rec.get('steam_volume_cwe_m3', 'N/A')} m³"],
            ["Soak Days", f"{rec.get('soak_days', 'N/A')} days"],
            ["SPM", f"{rec.get('spm', 'N/A')}"],
            ["Stroke Length", f"{rec.get('stroke_length_m', 'N/A')} m"],
            ["VFD Frequency", f"{rec.get('vfd_frequency_hz', 'N/A')} Hz"],
            ["", ""],
            ["Expected KPI Delta", "Value"],
            ["Oil Rate Δ", f"+{deltas.get('oil_rate_delta_pct', 0):.1f}%"],
            ["SOR Δ", f"{deltas.get('sor_delta_pct', 0):.1f}%"],
            ["Energy Δ", f"{deltas.get('energy_delta_pct', 0):.1f}%"],
        ]
        opt_table = Table(opt_data, colWidths=[7*cm, 10*cm])
        opt_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#145a32")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 7), (-1, 7), colors.HexColor("#1a5276")),
            ("TEXTCOLOR", (0, 7), (-1, 7), colors.white),
            ("FONTNAME", (0, 7), (-1, 7), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(opt_table)
        story.append(Spacer(1, 0.4*cm))

    # Alerts
    alerts = state_dict.get("active_alerts", [])
    if alerts:
        story.append(Paragraph("Active Alerts", h2))
        for alert in alerts:
            story.append(Paragraph(f"• {alert}", body))
        story.append(Spacer(1, 0.3*cm))

    # Footer
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Paragraph(
        "YUKTI v1.0 | SYNTHETIC data — NOT validated on real field operations | "
        "Physics models: Andrade (viscosity), Marx-Langenheim (heated zone), Vogel IPR, Gibbs (wave eq)",
        small
    ))

    doc.build(story)
    return buffer.getvalue()
