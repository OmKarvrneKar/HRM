import io
import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

LOGO_PATH = Path(__file__).resolve().parent.parent.parent / "frontend" / "static" / "img" / "ai_samrat_logo.jpeg"


class SalaryPDFService:
    """Generates professional, enterprise-standard AI Samrat PDF Salary Slips."""

    @classmethod
    def generate_payslip_pdf(cls, slip: dict) -> io.BytesIO:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        
        # Custom Typography Styles
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0f2942")
        )
        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475569")
        )
        section_style = ParagraphStyle(
            "SectionHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#0f2942")
        )
        cell_bold = ParagraphStyle(
            "CellBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#1e293b")
        )
        cell_norm = ParagraphStyle(
            "CellNorm",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#334155")
        )
        cell_right = ParagraphStyle(
            "CellRight",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            alignment=2,
            textColor=colors.HexColor("#0f172a")
        )
        cell_right_bold = ParagraphStyle(
            "CellRightBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            alignment=2,
            textColor=colors.HexColor("#0f172a")
        )
        footer_style = ParagraphStyle(
            "DocFooter",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            leading=10,
            alignment=1,
            textColor=colors.HexColor("#64748b")
        )

        story = []

        # 1. Header with Logo & Company Title
        header_data = []
        company_info = [
            Paragraph("AI SAMRAT PVT LTD", title_style),
            Paragraph("Official Human Resource Management & Payroll Operations", subtitle_style),
            Paragraph("CIN: U72900KA2021PTC145620 &bull; Corporate Headquarters, Bengaluru, Karnataka, India", subtitle_style),
        ]
        
        logo_elem = None
        if LOGO_PATH.exists():
            try:
                logo_elem = Image(str(LOGO_PATH), width=1.1 * inch, height=0.65 * inch)
            except Exception:
                logo_elem = Paragraph("<b>AI SAMRAT</b>", title_style)
        else:
            logo_elem = Paragraph("<b>AI SAMRAT</b>", title_style)

        header_table = Table(
            [[logo_elem, company_info]],
            colWidths=[1.3 * inch, 6.0 * inch]
        )
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 6))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0f2942"), spaceAfter=10))

        # 2. Statement Title & Period Bar
        month_name = slip.get("month_name", "Monthly Statement")
        slip_id = slip.get("slip_id", "N/A")
        period_data = [
            [
                Paragraph(f"<b>PAYSLIP FOR {month_name.upper()}</b>", section_style),
                Paragraph(f"<b>Slip Ref:</b> {slip_id}", cell_right),
            ]
        ]
        period_table = Table(period_data, colWidths=[4.5 * inch, 2.8 * inch])
        period_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(period_table)
        story.append(Spacer(1, 10))

        # 3. Employee Summary Information Grid
        emp_id = slip.get("employee_id", "-")
        full_name = slip.get("full_name", "-")
        dept = slip.get("department", "-")
        desig = slip.get("designation", "-")
        joining = slip.get("joining_date", "-")
        bank = slip.get("bank_name", "-")
        acc = slip.get("account_number", "-")
        pan = slip.get("pan_number", "-")
        uan = slip.get("uan_number", "-")
        pf_num = slip.get("pf_number", "-")
        days_worked = slip.get("days_worked", 22)
        total_days = slip.get("total_working_days", 22)
        pay_date = slip.get("payment_date", "-")

        info_grid = [
            [
                Paragraph("<b>Employee Name:</b>", cell_bold), Paragraph(full_name, cell_norm),
                Paragraph("<b>Employee ID:</b>", cell_bold), Paragraph(emp_id, cell_norm),
            ],
            [
                Paragraph("<b>Department:</b>", cell_bold), Paragraph(dept, cell_norm),
                Paragraph("<b>Designation:</b>", cell_bold), Paragraph(desig, cell_norm),
            ],
            [
                Paragraph("<b>Joining Date:</b>", cell_bold), Paragraph(joining, cell_norm),
                Paragraph("<b>Payment Date:</b>", cell_bold), Paragraph(pay_date, cell_norm),
            ],
            [
                Paragraph("<b>Bank Name:</b>", cell_bold), Paragraph(bank, cell_norm),
                Paragraph("<b>Bank Account:</b>", cell_bold), Paragraph(acc, cell_norm),
            ],
            [
                Paragraph("<b>PAN Number:</b>", cell_bold), Paragraph(pan, cell_norm),
                Paragraph("<b>UAN / PF No:</b>", cell_bold), Paragraph(f"{uan} / {pf_num}", cell_norm),
            ],
            [
                Paragraph("<b>Working Days:</b>", cell_bold), Paragraph(f"{days_worked} of {total_days}", cell_norm),
                Paragraph("<b>Payment Mode:</b>", cell_bold), Paragraph("Direct NEFT / Bank Transfer", cell_norm),
            ],
        ]
        info_table = Table(info_grid, colWidths=[1.3 * inch, 2.35 * inch, 1.3 * inch, 2.35 * inch])
        info_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#f1f5f9")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 12))

        # 4. Earnings and Deductions Table
        earnings = slip.get("earnings_breakdown", {})
        deductions = slip.get("deductions_breakdown", {})

        earning_rows = [
            ("Basic Salary", earnings.get("basic_salary", 0)),
            ("House Rent Allowance (HRA)", earnings.get("hra", 0)),
            ("Conveyance Allowance", earnings.get("conveyance_allowance", 0)),
            ("Medical Allowance", earnings.get("medical_allowance", 0)),
            ("Special / Flexi Allowance", earnings.get("special_allowance", 0)),
        ]

        deduction_rows = [
            ("Provident Fund (Employee EPF)", deductions.get("provident_fund", 0)),
            ("Professional Tax (PT)", deductions.get("professional_tax", 0)),
            ("Income Tax (TDS)", deductions.get("tds_tax", 0)),
            ("", ""),
            ("", ""),
        ]

        salary_table_data = [
            [
                Paragraph("<b>EARNINGS COMPONENT</b>", cell_bold),
                Paragraph("<b>AMOUNT (INR)</b>", cell_right_bold),
                Paragraph("<b>DEDUCTIONS</b>", cell_bold),
                Paragraph("<b>AMOUNT (INR)</b>", cell_right_bold),
            ]
        ]

        for (e_name, e_val), (d_name, d_val) in zip(earning_rows, deduction_rows):
            e_val_str = f"{e_val:,.2f}" if isinstance(e_val, (int, float)) else ""
            d_val_str = f"{d_val:,.2f}" if isinstance(d_val, (int, float)) else ""
            salary_table_data.append([
                Paragraph(e_name, cell_norm),
                Paragraph(e_val_str, cell_right),
                Paragraph(d_name, cell_norm),
                Paragraph(d_val_str, cell_right),
            ])

        gross_val = slip.get("gross_earnings", 0)
        tot_ded_val = slip.get("total_deductions", 0)

        salary_table_data.append([
            Paragraph("<b>Total Gross Earnings</b>", cell_bold),
            Paragraph(f"<b>{gross_val:,.2f}</b>", cell_right_bold),
            Paragraph("<b>Total Deductions</b>", cell_bold),
            Paragraph(f"<b>{tot_ded_val:,.2f}</b>", cell_right_bold),
        ])

        salary_table = Table(
            salary_table_data,
            colWidths=[2.3 * inch, 1.35 * inch, 2.3 * inch, 1.35 * inch]
        )
        salary_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#0f2942")),
        ]))
        story.append(salary_table)
        story.append(Spacer(1, 10))

        # 5. Net Salary Highlights Box (AI Samrat Corporate Blue Palette)
        net_val = slip.get("net_salary", 0)
        net_words = slip.get("net_salary_words", "")

        net_data = [
            [
                Paragraph("<b>NET TAKE-HOME PAY</b>", ParagraphStyle(
                    "NetLabel", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, textColor=colors.HexColor("#002b80")
                )),
                Paragraph(f"<b>INR {net_val:,.2f}</b>", ParagraphStyle(
                    "NetVal", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=14, alignment=2, textColor=colors.HexColor("#0056d6")
                ))
            ],
            [
                Paragraph(f"<b>Amount in Words:</b> {net_words}", cell_norm),
                Paragraph(f"Ref: {slip.get('transaction_ref', 'N/A')}", cell_right)
            ]
        ]
        net_table = Table(net_data, colWidths=[4.8 * inch, 2.5 * inch])
        net_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f7ff")),
            ("BOX", (0, 0), (-1, -1), 1.25, colors.HexColor("#0056d6")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(net_table)
        story.append(Spacer(1, 14))

        # 6. Sign-off and Verification Footer
        signoff_data = [
            [
                Paragraph("<b>Prepared By:</b><br/>HR Payroll Automated Engine", cell_norm),
                Paragraph("<b>Verified By:</b><br/>Senior HR Generalist", cell_norm),
                Paragraph("<b>Authorized Signatory:</b><br/>Director, AI Samrat Pvt Ltd", cell_norm),
            ]
        ]
        signoff_table = Table(signoff_data, colWidths=[2.43 * inch, 2.43 * inch, 2.44 * inch])
        signoff_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(signoff_table)
        story.append(Spacer(1, 16))

        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=6))
        story.append(Paragraph(
            "This is a confidential computer-generated payroll document issued by AI Samrat Pvt Ltd. "
            "No physical signature is required. For inquiries regarding tax deductions or allowance structure, "
            "please contact HR Operations.",
            footer_style
        ))

        doc.build(story)
        buffer.seek(0)
        return buffer
