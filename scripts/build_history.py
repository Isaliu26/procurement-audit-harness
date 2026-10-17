#!/usr/bin/env python3
"""Builds outputs/history.json from hand-transcribed items (findings-analyst). Quotes are verified by verify_history.py."""
import hashlib, json, subprocess, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
A24 = "audit-completed-work-2024-25-annual.pdf"
A25 = "audit-completed-work-2025-26-q3.pdf"
PLAN = "internal-audit-plan-2025-28.pdf"
RMS = "risk-management-strategy-2024-27.pdf"
M25, D25 = "End of March 2025", "End of December 2025"

def src(f, title, as_at):
    p = ROOT/"data/committee"/f
    pages = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True).stdout).group(1))
    return {"file": f, "pages": pages, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "title": title, "as_at": as_at}

sources = [
 src(A24, "Internal Audit Plan Update Report, Appendix A (completed work)", M25),
 src(A25, "Internal Audit Plan Update Report, Appendix A (completed work)", D25),
 src(PLAN, "Internal Audit Plan 2025-2028 (Governance Committee, 29th April 2025)", "29th April 2025"),
 src(RMS, "Risk Management Strategy 2024-2027 (Governance, 12 December 2024)", "12 December 2024"),
]

def aud(f, page, asat, d, s, t, o, q):
    return dict(source_file=f, pdf_page=page, section="1) COMPLETED AUDITS", directorate=d, service=s,
                audit_title=t, opinion=o, report_as_at=asat, quote=q)
FPP = "Finance, Property and Procurement"
audits = [
 aud(A24,1,M25,"Resources",FPP,"Contract Letting","Reasonable Assurance","Finance, Property and Procurement | Contract Letting | Reasonable Assurance"),
 aud(A24,1,M25,"Resources",FPP,"Housing Benefit and Council Tax Hardship Fund","Reasonable Assurance","Finance, Property and Procurement | Housing Benefit and Council Tax Hardship Fund | Reasonable Assurance"),
 aud(A24,1,M25,"Resources",FPP,"Bank Reconciliation","Substantial Assurance","Finance, Property and Procurement | Bank Reconciliation | Substantial Assurance"),
 aud(A24,1,M25,"Resources","Transformation","Systems Security (Firewall, Antivirus, Traffic Management)","Reasonable Assurance","Transformation | Systems Security (Firewall, Antivirus, Traffic Management) | Reasonable Assurance"),
 aud(A24,1,M25,"People","Public Health","Joint Agreement Governance","Advisory - no opinion given","Joint Agreement Governance | Advisory - no opinion given"),
 aud(A24,1,M25,"Place","Communities","Public Protection Partnership – Financial Control Processes","Substantial Assurance","Public Protection Partnership – Financial Control Processes | Substantial Assurance"),
 aud(A24,1,M25,"Schools","Primary","Springfield","Substantial Assurance","Springfield | Substantial Assurance"),
 aud(A24,1,M25,"Schools","Primary","St Paul’s","Reasonable Assurance","St Paul’s | Reasonable Assurance"),
 aud(A24,1,M25,"Schools","Primary","St John and St Nicolas Federation","Reasonable Assurance","St John and St Nicolas Federation | Reasonable Assurance"),
 aud(A25,1,D25,"Resources","Strategy and Governance","Recruitment (Talent Attraction) and Retention","Reasonable Assurance","Recruitment (Talent Attraction) and Retention | Reasonable Assurance"),
 aud(A25,1,D25,"Resources",FPP,"Accounts Payable","Reasonable Assurance","Finance, Property and | Accounts Payable | Reasonable Assurance"),
 aud(A25,1,D25,"People","Children with Disabilities and SEN Teams","Personal Budgets (Direct Payments)","Limited Assurance","Children with Disabilities and SEN Teams | Personal Budgets (Direct Payments) | Limited Assurance"),
 aud(A25,1,D25,"People","Children and Family","Separated Children (UASC)","Substantial Assurance","Children and Family | Separated Children (UASC) | Substantial Assurance"),
 aud(A25,1,D25,"People","Adult Social Care","Purchase of Residential and Nursing Care Provision","Reasonable Assurance","Adult Social Care | Purchase of Residential and Nursing Care Provision | Reasonable Assurance"),
 aud(A25,1,D25,"Schools","Primary","Winchcombe","Reasonable Assurance","Winchcombe | Reasonable Assurance"),
 aud(A25,1,D25,"Schools","Primary","Curridge","Substantial Assurance","Curridge | Substantial Assurance"),
]
for i,a in enumerate(audits,1): a["id"]=f"AUD-{i:02d}"

def fup(page, d, s, t, r, imp, q):
    return dict(source_file=A24, pdf_page=page, section="2) COMPLETED FOLLOW UPS", directorate=d, service=s,
                audit_title=t, opinion_report=r, opinion_implementation=imp, report_as_at=M25, quote=q)
follow_ups = [
 fup(1,"Resources",FPP,"Fixed Asset Register","Advisory – no opinion","Satisfactory","Resources/Finance, | Property and Procurement | Fixed Asset Register | Advisory – no opinion | Satisfactory"),
 fup(2,"Schools","Primary","Garland (now Burghfield Common Federation)","Weak","Unsatisfactory","Garland (now Burghfield Common Federation) | Weak | Unsatisfactory"),
 fup(2,"Schools","Primary","Westwood Farm","Limited Assurance","Satisfactory","Limited Assurance | Satisfactory | Westwood Farm"),
]
for i,a in enumerate(follow_ups,1): a["id"]=f"FUP-{i:02d}"
advisory_work = [dict(id="ADV-01", source_file=A24, pdf_page=2, section="3) COMPLETED ADVISORY REVIEWS/OTHER WORK",
   directorate="Transformation, Customer and ICT", service=None, audit_title="Transformation SWOT", report_as_at=M25,
   quote="Transformation, Customer and ICT | Transformation SWOT")]

risk_themes = [
 dict(id="RT-01", theme="Contracts & Partnerships (procurement contract and relationship management)", source_file=RMS, pdf_page=33,
      quote="Contracts & | Partnerships | Dependency on, or failure of, contractors to deliver services or products to the agreed cost and specification. Procurement contract and relationship management."),
 dict(id="RT-02", theme="Finance (financial control, fraud and corruption)", source_file=RMS, pdf_page=32,
      quote="Costs, long term financial sustainability/ reliance on finite or vulnerable funding streams. Financial control, fraud and corruption."),
 dict(id="RT-03", theme="Competition & Markets (value for money)", source_file=RMS, pdf_page=32,
      quote="Affecting the competitiveness (cost and quality) of the service and/or ability to deliver value for money and general market effectiveness."),
]

def it(prefix, f, page, rows):
    out=[]
    for i,(q,extra) in enumerate(rows,1):
        d=dict(id=f"{prefix}-{i:02d}", source_file=f, pdf_page=page, quote=q); d.update(extra); out.append(d)
    return out
def ex(prefix, rows):
    out=[]
    for i,(f,p,q,extra) in enumerate(rows,1):
        d=dict(id=f"{prefix}-{i:02d}", source_file=RMS, pdf_page=p, quote=q); d.update(extra); out.append(d)
    return out

impact = ex("IMP",[
 (RMS,14,"5 Critical | > 1% annual WBC budget >£2m",dict(label="Critical",score=5,financial="> 1% annual WBC budget >£2m")),
 (RMS,14,"4 Major | 0.25% - 1% annual WBC budget £500k £2M",dict(label="Major",score=4,financial="0.25% - 1% annual WBC budget £500k £2M")),
 (RMS,14,"3 Medium | 0.1% - 0.3% annual WBC budget £175k -500k",dict(label="Medium",score=3,financial="0.1% - 0.3% annual WBC budget £175k -500k")),
 (RMS,14,"2 Minor | 0.01% 0.1% of annual WBC budget £17.5k £175k",dict(label="Minor",score=2,financial="0.01% 0.1% of annual WBC budget £17.5k £175k")),
 (RMS,14,"1 Negligible | Less than 0.01% annual WBC budget £17.5k",dict(label="Negligible",score=1,financial="Less than 0.01% annual WBC budget £17.5k")),
])
likelihood = ex("LIK",[
 (RMS,15,"Risk will occur within a 12 month period 100% Certain",dict(label="Certain",score=5,probability="100%")),
 (RMS,15,"Risk is almost certain to occur within a 12 month | Almost | 70% - 99% | period | Certain",dict(label="Almost Certain",score=4,probability="70% - 99%")),
 (RMS,15,"Risk is likely to occur within a 12 month period | 30% - 69% | Likely",dict(label="Likely",score=3,probability="30% - 69%")),
 (RMS,15,"Risk is unlikely to occur within a 12 month period 2% - 29% Unlikely",dict(label="Unlikely",score=2,probability="2% - 29%")),
 (RMS,15,"Risk is very rare and highly unlikely to occur | –<2% | Rare | within a 12 month period",dict(label="Rare",score=1,probability="–<2%")),
])
matrix = ex("MTX",[
 (RMS,18,"Moderate High Extreme Extreme Extreme | 5 10 15 20 25",dict(impact_row="5 Critical",cells="Moderate(5) High(10) Extreme(15) Extreme(20) Extreme(25)")),
 (RMS,18,"Moderate High High Extreme Extreme | 4 8 12 16 20",dict(impact_row="4 Major",cells="Moderate(4) High(8) High(12) Extreme(16) Extreme(20)")),
 (RMS,18,"Low Moderate High High Extreme | 3 6 9 12 15",dict(impact_row="3 Medium",cells="Low(3) Moderate(6) High(9) High(12) Extreme(15)")),
 (RMS,18,"Low Moderate Moderate High High | 2 4 6 8 10",dict(impact_row="2 Minor",cells="Low(2) Moderate(4) Moderate(6) High(8) High(10)")),
 (RMS,18,"Low Low Low Moderate Moderate | 1 2 3 4 5",dict(impact_row="1 Negligible",cells="Low(1) Low(2) Low(3) Moderate(4) Moderate(5)")),
 (RMS,18,"1 Rare | 2 Unlikely | 3 Likely | 4 Almost Certain | 5 Certain",dict(note="likelihood axis, left to right")),
 (RMS,18,"The Council has chosen to divide the rating into bands as shown on the risk matrix below",dict(note="paragraph 5.11")),
])
bands = ex("BND",[
 (RMS,19,"Extreme | (Red) | 15 -25",dict(label="Extreme (Red)",score_range="15 -25")),
 (RMS,19,"Medium - | High | 8-12 | (Amber)",dict(label="Medium - High (Amber)",score_range="8-12")),
 (RMS,19,"Moderate | 4-6",dict(label="Moderate",score_range="4-6")),
 (RMS,19,"Low | Up to 3 | (Green)",dict(label="Low (Green)",score_range="Up to 3")),
])
appetite = ex("APP",[
 (RMS,16,"Risk levels | Averse | Cautious | Flexible | Open | Seeking",dict(note="Table 3 / 5.8 appetite levels, least to most")),
 (RMS,16,"Up to £100k | £100k - | £250k - £500k | £500k - £1m | £1m +",dict(risk_description="Financial/ Asset")),
 (RMS,16,"Following | Following | Following | Innovating, | Innovating in",dict(risk_description="Compliance (first line of each level's cell)")),
 (RMS,16,"No chance of | Little chance | Exposure of | Experimental–  | Unprecedented",dict(risk_description="Reputation (first line of each level's cell)")),
 (RMS,17,"Essential | Maintain | Encourage | Proactive | Desire to",dict(risk_description="Operational (first line of each level's cell)")),
 (RMS,17,"Financial Risk Appetite – Flexible | The Council aims to operate with a financial risk between £250k – £500k.",dict(stated_level="Flexible",para="5.10")),
 (RMS,17,"Compliance Risk Appetite – Flexible/Open",dict(stated_level="Flexible/Open",para="5.10")),
 (RMS,17,"Reputation Risk appetite – Open",dict(stated_level="Open",para="5.10")),
 (RMS,18,"Operational risk appetite – Open",dict(stated_level="Open",para="5.10")),
])
escalation = ex("ESC",[
 (RMS,19,"Add to Corporate | Risk Register and | mitigation action. | Allocate to Executive Director to | oversee and Service Director | implement agreed actions.",dict(band="Extreme (Red) 15 -25")),
 (RMS,19,"Seek assurance | that identified | controls are | effective | Allocate to Service Director to put in | place Controls Assurance.",dict(band="Medium - High (Amber) 8-12")),
 (RMS,19,"4-6 | None | Monitor risk",dict(band="Moderate 4-6")),
 (RMS,19,"Up to 3 | None | Consider at next annual review",dict(band="Low (Green) Up to 3")),
 (RMS,21,"Corporate Risk Register (CRR) | Includes risks that: | Score 9 or above",dict(figure="Figure 4")),
 (RMS,21,"Directorate Risk Register (DRR) | Includes risks that impact: | Plans overseen by the Directorate | More than one service",dict(figure="Figure 4")),
 (RMS,21,"Service (operational) Risk Register (SRR) or | Project Risks Registers (PRR) | Includes risks that impact on: | Service, team or project delivery",dict(figure="Figure 4")),
 (RMS,21,"Where risk levels are considered to be extrene (Red) on the risk matrix, the appropriate Service Director must escalate the risk to the Executive Director",dict(para="6.3")),
])
evaluation = ex("EVL",[
 (RMS,13,"Gross level – likelihood and impact without additional, specific mitigation action.",dict(para="4.1")),
 (RMS,13,"Actual level - this is the current likelihood and impact, based on mitigation action already put in place",dict(para="4.1")),
 (RMS,14,"Expected level – this is a future level of likelihood and impact based on any additional mitigation action (if any) planned",dict(para="4.1")),
 (RMS,14,"The Council evaluates its identified risks on a five-point scale on the likelihood or probability of the risk occurring (rated between rare and certain) and the impact caused should the risk occur (rated between negligible and critical).",dict(para="4.2")),
 (RMS,24,"The risk score is, therefore, based on a ‘reasonable worst case scenario’.",dict(para="7.1")),
])
scoring_method = dict(usable=True, source_file=RMS, impact_scale=impact, likelihood_scale=likelihood, matrix=matrix, bands=bands,
  appetite=appetite, escalation=escalation, evaluation_levels=evaluation,
  notes="Strategy 4.2 describes a five-point likelihood and five-point impact scale (Tables 1 and 2). Figure 1 (5x5 matrix, p18) gives a label per likelihood x impact cell; Table 4 (p19) gives bands by score with escalation and response. Figure 4 (p21) gives register membership. Records only; no score applied. Inconsistencies between these parts are in discrepancies.")

C=lambda f,p,q: dict(source_file=f,pdf_page=p,quote=q)
discrepancies = [
 dict(id="DIS-01", kind="internal_inconsistency", description="Paragraph 4.3 numbers the impact levels Negligible (1), Minor (2), Medium (2), Major (4), Critical (5); Table 1 numbers Medium as 3.",
  evidence=[C(RMS,14,"Negligible (1), Minor (2), Medium (2), Major (4), or Critical impact(5)"), C(RMS,14,"3 Medium | 0.1% - 0.3% annual WBC budget £175k -500k")]),
 dict(id="DIS-02", kind="internal_inconsistency", description="Table 1 financial ranges overlap between levels 3 and 4 (0.1% - 0.3% vs 0.25% - 1%); the printed £ ranges (£175k -500k, £500k £2M) abut at £500k.",
  evidence=[C(RMS,14,"0.1% - 0.3% annual WBC budget £175k -500k"), C(RMS,14,"0.25% - 1% annual WBC budget £500k £2M")]),
 dict(id="DIS-03", kind="internal_inconsistency", description="Table 2 probability bands: level 5 is 100% and level 4 is 70% - 99% (values between 99% and 100% unassigned); level 1 is printed '–<2%' against level 2 '2% - 29%'; 29% to 30% likewise adjacent.",
  evidence=[C(RMS,15,"Risk will occur within a 12 month period 100% Certain"), C(RMS,15,"Risk is almost certain to occur within a 12 month | Almost | 70% - 99% | period | Certain"), C(RMS,15,"Risk is unlikely to occur within a 12 month period 2% - 29% Unlikely")]),
 dict(id="DIS-04", kind="internal_inconsistency", description="Band name differs: the matrix labels scores 8-12 'High' while Table 4 names that band 'Medium - High (Amber)'. Table 4 'Extreme (Red)' vs matrix 'Extreme'.",
  evidence=[C(RMS,18,"Moderate High High Extreme Extreme | 4 8 12 16 20"), C(RMS,19,"Medium - | High | 8-12 | (Amber)")]),
 dict(id="DIS-05", kind="internal_inconsistency", description="Escalation threshold for the Corporate Risk Register: Table 4 adds risks to the CRR at Extreme (15 -25); Figure 4 states the CRR includes risks that score 9 or above (9 and 12 sit in the 8-12 band).",
  evidence=[C(RMS,19,"Add to Corporate | Risk Register and | mitigation action."), C(RMS,19,"Extreme | (Red) | 15 -25"), C(RMS,21,"Corporate Risk Register (CRR) | Includes risks that: | Score 9 or above")]),
 dict(id="DIS-06", kind="internal_inconsistency", description="Committee naming: Figure 4 names a 'Governance and Ethics Committee' for six-monthly review; elsewhere the strategy refers to the 'Governance Committee'.",
  evidence=[C(RMS,21,"Six monthly - | Governance and | Ethics Committee"), C(RMS,22,"Governance Committee")]),
 dict(id="DIS-07", kind="internal_inconsistency", description="Section 6.3 states an Extreme (Red) risk is escalated for discussion at Directorate level to decide Directorate or Corporate Risk Register; Table 4 states Extreme risks are added to the Corporate Risk Register.",
  evidence=[C(RMS,21,"so that consideration can be given as to whether the risk should be moved to the Directorate Risk Register or the Corporate Risk Register."), C(RMS,19,"Add to Corporate | Risk Register and | mitigation action.")]),
 dict(id="DIS-08", kind="opinion_label_inconsistency", description="Follow-up table of the End of March 2025 report records the report opinion as 'Weak' for one school and 'Limited Assurance' for another; the completed audits table uses Assurance labels.",
  evidence=[C(A24,2,"Garland (now Burghfield Common Federation) | Weak | Unsatisfactory"), C(A24,2,"Limited Assurance | Satisfactory | Westwood Farm")]),
 dict(id="DIS-09", kind="opinion_label_inconsistency", description="Advisory opinion is printed 'Advisory - no opinion given' (hyphen) in table 1 and 'Advisory – no opinion' (en dash) in table 2 of the same report.",
  evidence=[C(A24,1,"Joint Agreement Governance | Advisory - no opinion given"), C(A24,1,"Fixed Asset Register | Advisory – no opinion | Satisfactory")]),
 dict(id="DIS-10", kind="internal_inconsistency", description="Internal Audit Plan states the 3-year resource is 'sufficient' (4.7) and 'approximately in line with' the planned days (5.8).",
  evidence=[C(PLAN,3,"The plan over the three-year period shows the level of resource is sufficient to meet the planned programme of work."), C(PLAN,5,"The plan over the three-year period shows the level of resource is approximately in line with the number of days in the planned programme of work.")]),
 dict(id="DIS-11", kind="internal_inconsistency", description="Strategy paragraph number 4.3 is used twice on page 28 (risk-aware culture; effective corporate approach).",
  evidence=[C(RMS,28,"4.3 The assessment that the culture of the organisation is ‘risk aware’"), C(RMS,28,"4.3 An effective corporate approach to risk management will:")]),
]
gaps = [
 dict(id="GAP-01", what="Agreed audit actions/recommendations with due dates and status (open/overdue) are not in the papers; only follow-up implementation-progress opinions (recorded under follow_ups).", looked_in=[A24,A25,PLAN,RMS]),
 dict(id="GAP-02", what="Strategic / Corporate Risk Register not public: strategy states risk is reported as a Part II (confidential information) report to the Governance Committee.", looked_in=[RMS,PLAN], evidence=C(RMS,28,"risk is reported as a Part II (confidential information) report to the Governance Committee")),
 dict(id="GAP-03", what="Audit plan appendices A-F (Charter, Strategy, Protocol, Plan 2025 to 2028 with key risks and risk levels, Anti-Fraud Work Plan, Quality and Improvement Programme) are listed but not included.", looked_in=[PLAN], evidence=C(PLAN,6,"Appendix D - Internal Audit Plan 2025 to 2028")),
 dict(id="GAP-04", what="Definitions of each assurance opinion label (Substantial, Reasonable, Limited, Weak, Satisfactory, Unsatisfactory, Advisory) are not given; the NOTE only says how an opinion is derived.", looked_in=[A24,A25,PLAN]),
 dict(id="GAP-05", what="Follow-up status of open recommendations: the End of December 2025 report records follow-ups as 'None'; no recommendation-level status in any paper.", looked_in=[A24,A25]),
 dict(id="GAP-06", what="No audit of procurement-card or purchasing-card spend, or other purchasing spend beyond Contract Letting and Accounts Payable, appears in the completed-work tables.", looked_in=[A24,A25,PLAN]),
 dict(id="GAP-07", what="Table 1 impact scale cells for 'Personal', 'Assets', 'Reputation' and 'Compliance' columns are not recorded item-by-item; only the label and financial column per level are quoted (plain text separates the columns).", looked_in=[RMS]),
]
for g in gaps:
    if "evidence" in g: pass
plan_statements = [
 dict(id="PLN-01", source_file=PLAN, pdf_page=5, quote="The plan analyses the different areas of the Council’s activity that Internal Audit have determined need to be audited after carrying out a risk assessment process."),
 dict(id="PLN-02", source_file=PLAN, pdf_page=5, quote="The key risks involved in that area."),
 dict(id="PLN-03", source_file=PLAN, pdf_page=5, quote="The level of risk associated with the audit area/function, as assessed by Internal Audit."),
 dict(id="PLN-04", source_file=PLAN, pdf_page=3, quote="The plan analyses the different areas of the Council’s activity that Internal Audit have risk assessed as needing to be audited over a three-year timeframe."),
]
h = dict(sources=sources, audits=audits, follow_ups=follow_ups, advisory_work=advisory_work, agreed_actions=[], risk_themes=risk_themes,
         scoring_method=scoring_method, discrepancies=discrepancies, gaps=gaps, audit_plan_statements=plan_statements)
(ROOT/"outputs/history.json").write_text(json.dumps(h, indent=1, ensure_ascii=False))
