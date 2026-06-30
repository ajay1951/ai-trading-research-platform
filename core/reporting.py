"""
PDF Report Generation Module
Uses reportlab to create PDF summaries of financial analysis.
"""
import os
from datetime import datetime
from typing import Dict, List, Any

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.units import inch


def generate_pdf_report(analysis_result: Dict[str, Any]) -> str:
    """
    Generates a PDF report from the analysis result dictionary.
    """
    # 1. Setup file path and document
    if not os.path.exists('reports'):
        os.makedirs('reports')

    agent_results = analysis_result.get("results", {})
    symbol = agent_results.get("data", {}).get("symbol", "report")
    if not symbol: # Fallback if data agent didn't run
        symbol = agent_results.get("quant", {}).get("symbol", "report")

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{symbol.replace('/', '_')}_{timestamp_str}.pdf"
    filepath = os.path.join('reports', filename)

    doc = SimpleDocTemplate(filepath,
                            rightMargin=inch/2, leftMargin=inch/2,
                            topMargin=inch/2, bottomMargin=inch/2)

    story: List[Any] = []
    styles = getSampleStyleSheet()

    # 2. Define custom styles
    styles.add(ParagraphStyle(name='Title', fontSize=22, alignment=TA_CENTER, spaceAfter=20, textColor=colors.HexColor("#1E3A8A")))
    styles.add(ParagraphStyle(name='Header', fontSize=16, spaceAfter=12, textColor=colors.HexColor("#1F2937")))
    styles.add(ParagraphStyle(name='SubHeader', fontSize=11, spaceAfter=8, textColor=colors.HexColor("#4B5563"), fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='Signal', fontSize=28, alignment=TA_CENTER, spaceAfter=6, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='Reasoning', fontSize=10, leading=14, spaceAfter=20, alignment=TA_CENTER))
    body_style = styles['BodyText']
    body_style.fontSize = 9

    # 3. Extract data
    supervisor = agent_results.get("supervisor", {})
    quant = agent_results.get("quant", {}).get("analysis", {})
    research = agent_results.get("research", {}).get("research", {})
    risk = agent_results.get("risk", {}).get("risk_assessment", {})
    data_agent = agent_results.get("data", {}).get("data", {})

    # 4. Build Story
    # --- Header ---
    story.append(Paragraph("Financial Intelligence Report", styles['Title']))
    story.append(Paragraph(f"<b>Symbol:</b> {symbol}", styles['Header']))
    story.append(Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['SubHeader']))
    story.append(Spacer(1, 0.25*inch))

    # --- Supervisor's Final Take ---
    story.append(Paragraph("Supervisor's Final Take", styles['Header']))
    final_signal = supervisor.get('final_signal', 'N/A')
    signal_color = {"BUY": colors.green, "SELL": colors.red, "HOLD": colors.darkgoldenrod}.get(final_signal, colors.black)

    story.append(Paragraph(final_signal, ParagraphStyle(name='SignalStyle', parent=styles['Signal'], textColor=signal_color)))

    confidence = supervisor.get('final_confidence', 0)
    story.append(Paragraph(f"Confidence: {confidence*100:.1f}%", ParagraphStyle(name='Conf', parent=styles['SubHeader'], alignment=TA_CENTER)))

    reasoning = supervisor.get('reasoning', 'No reasoning provided.')
    story.append(Paragraph(f"<i>{reasoning}</i>", styles['Reasoning']))
    story.append(Spacer(1, 0.25*inch))

    # --- Quantitative Analysis ---
    story.append(Paragraph("Quantitative Analysis", styles['Header']))
    if quant:
        quant_signal = quant.get("signal", {})
        triggers = quant_signal.get("potential_triggers", [])
        story.append(Paragraph("Next Trade Signals", styles['SubHeader']))
        if triggers:
            trigger_data = [['Type', 'Value', 'Description']]
            for t in triggers[:5]:
                trigger_data.append([t.get('type'), t.get('value'), t.get('description')])
            t_table = Table(trigger_data, colWidths=[0.8*inch, 1.5*inch, 4.5*inch], hAlign='LEFT')
            t_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.darkslategray), ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0,0), (-1,0), 10), ('BACKGROUND', (0,1), (-1,-1), colors.ghostwhite),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black)
            ]))
            story.append(t_table)
        else:
            story.append(Paragraph("No potential triggers identified.", body_style))
    else:
        story.append(Paragraph("No quantitative analysis available.", body_style))
    story.append(Spacer(1, 0.25*inch))

    # --- Risk & Research ---
    col1_story, col2_story = [], []

    # --- Risk Assessment ---
    col1_story.append(Paragraph("Risk Assessment", styles['SubHeader']))
    if risk:
        risk_data = [['Metric', 'Value']]
        risk_data.append(['Risk Level', risk.get('risk_level', 'N/A')])
        risk_data.append(['Value at Risk (95%)', f"{risk.get('var', {}).get('var', 0):.2f}%"])
        risk_data.append(['Stop-Loss', f"${risk.get('trade_limits', {}).get('stop_loss', 'N/A'):,}" if isinstance(risk.get('trade_limits', {}).get('stop_loss'), (int, float)) else 'N/A'])
        risk_data.append(['Take-Profit', f"${risk.get('trade_limits', {}).get('take_profit', 'N/A'):,}" if isinstance(risk.get('trade_limits', {}).get('take_profit'), (int, float)) else 'N/A'])
        risk_table = Table(risk_data, colWidths=[1.5*inch, 1.5*inch], hAlign='LEFT')
        risk_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
        col1_story.append(risk_table)
    else:
        col1_story.append(Paragraph("No risk assessment available.", body_style))

    # --- Fundamental Research ---
    col2_story.append(Paragraph("Fundamental Research", styles['SubHeader']))
    if research:
        macro = research.get("macro_sentiment", {})
        col2_story.append(Paragraph(f"<b>News Sentiment:</b> {macro.get('overall_sentiment', 'N/A')}", body_style))
        news_items = data_agent.get("news", {}).get("news", [])
        if news_items:
            col2_story.append(Spacer(1, 0.1*inch))
            for item in news_items[:3]:
                col2_story.append(Paragraph(f"• <i>{item.get('source')}:</i> {item.get('title')[:60]}...", body_style))
    else:
        col2_story.append(Paragraph("No fundamental research available.", body_style))

    # Create a two-column layout for the last section
    two_cols_data = [[col1_story, col2_story]]
    two_cols_table = Table(two_cols_data, colWidths=[doc.width/2.0 - 10, doc.width/2.0 - 10])
    story.append(two_cols_table)

    # 5. Build the PDF
    doc.build(story)
    return filepath