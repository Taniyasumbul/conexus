"""Seed clause bank with expert-style labels.

Each entry is a *template family* (family id used for grouped train/test splits so
the ML classifier is evaluated on wording it has not seen).

Labelling guideline (see docs/ANNOTATION_GUIDELINES.md):
  requires_human = True  -> the clause creates exposure an SME cannot price or
                            reverse (uncapped liability, one-sided indemnity for the
                            other party's negligence, transfer of background IP,
                            exclusivity / non-compete, strict liability for data
                            breaches, unlimited audits). Must go to a human.
  redlinable     = True  -> commercially off-market but has a standard fallback
                            position the agent may propose autonomously.
"""
from __future__ import annotations

# (family, clause_type, level, requires_human, redlinable, heading, [variants])
BANK: list[tuple[str, str, str, bool, bool, str, list[str]]] = [
    # ---------------- payment terms ----------------
    ("pay_std", "payment_terms", "low", False, False, "Payment Terms", [
        "{customer} shall pay all undisputed invoices within thirty (30) days of the invoice date.",
        "Invoices are payable net 30 days from receipt. Late amounts accrue interest at 1% per month.",
        "Fees are invoiced annually in advance and are due within 30 days of the date of invoice.",
    ]),
    ("pay_long", "payment_terms", "high", False, True, "Payment Terms", [
        "{customer} shall pay undisputed invoices within one hundred and twenty (120) days of receipt of a correct invoice.",
        "Payment shall be made net 90 days following {customer}'s acceptance of the Services, at {customer}'s sole discretion.",
        "All invoices shall be settled within 90 days of month end; {customer} may withhold payment pending internal approvals.",
    ]),
    ("pay_mid", "payment_terms", "medium", False, True, "Payment Terms", [
        "{customer} will pay each invoice within sixty (60) days of receipt.",
        "Invoices are payable net 45 days; no late payment interest shall apply.",
    ]),
    # ---------------- liability ----------------
    ("liab_cap", "liability_cap", "low", False, False, "Limitation of Liability", [
        "Except for breach of confidentiality, each party's aggregate liability under this Agreement shall not exceed the fees paid or payable in the twelve (12) months preceding the claim.",
        "In no event shall either party be liable for indirect or consequential damages, and each party's total liability is capped at the amounts paid under this Agreement in the prior 12 months.",
        "The total cumulative liability of either party arising out of this Agreement shall be limited to one times (1x) the annual fees.",
    ]),
    ("liab_unl", "liability_cap", "high", True, True, "Limitation of Liability", [
        "{vendor}'s liability under this Agreement shall be unlimited, and nothing herein shall limit {customer}'s recovery of any losses.",
        "The limitations of liability set out herein shall not apply to {vendor}. {vendor} shall be liable for all direct, indirect and consequential losses without limit.",
        "{vendor}'s aggregate liability shall not exceed ten (10) times the total contract value, and the exclusion of consequential damages shall apply only to {customer}.",
    ]),
    # ---------------- indemnity ----------------
    ("ind_mutual", "indemnification", "low", False, False, "Indemnification", [
        "Each party shall indemnify the other against third-party claims to the extent arising from its own gross negligence or wilful misconduct.",
        "{vendor} shall defend {customer} against third-party claims alleging that the Software infringes a patent or copyright, subject to the liability cap.",
    ]),
    ("ind_broad", "indemnification", "high", True, False, "Indemnification", [
        "{vendor} shall indemnify, defend and hold harmless {customer} from any and all claims, losses and expenses of whatever nature, including those arising from {customer}'s own negligence.",
        "{vendor} agrees to indemnify {customer} and its affiliates against all losses howsoever arising in connection with this Agreement, without limitation and regardless of fault.",
        "{vendor} shall hold {customer} harmless from any and all liabilities, including penalties and fines, regardless of whether caused by {vendor}.",
    ]),
    # ---------------- IP ----------------
    ("ip_vendor", "ip_ownership", "low", False, False, "Intellectual Property", [
        "{vendor} retains all right, title and interest in the Software and any improvements. {customer} receives a non-exclusive licence for the Term.",
        "All intellectual property rights in the platform remain with {vendor}. {customer} owns its Customer Data.",
    ]),
    ("ip_assign", "ip_ownership", "high", True, False, "Intellectual Property", [
        "All intellectual property created or used in performing the Services, including {vendor}'s pre-existing materials, shall vest in and be assigned to {customer}.",
        "{vendor} hereby assigns to {customer} all right, title and interest in any software, tools, know-how and background IP used to deliver the Services.",
        "Any modifications, derivative works or improvements to the platform made during the Term shall be the exclusive property of {customer}.",
    ]),
    # ---------------- confidentiality ----------------
    ("conf_std", "confidentiality", "low", False, False, "Confidentiality", [
        "Each party shall protect the other's Confidential Information with reasonable care for a period of three (3) years following disclosure.",
        "The receiving party shall use Confidential Information solely to perform this Agreement and shall not disclose it except to personnel with a need to know.",
    ]),
    ("conf_one", "confidentiality", "medium", False, True, "Confidentiality", [
        "{vendor} shall keep all information received from {customer} confidential in perpetuity. {customer} shall have no confidentiality obligations.",
        "Confidentiality obligations shall bind {vendor} only and shall survive indefinitely.",
    ]),
    # ---------------- termination ----------------
    ("term_cause", "termination", "low", False, False, "Termination", [
        "Either party may terminate this Agreement for material breach that remains uncured thirty (30) days after written notice.",
        "This Agreement may be terminated by either party upon insolvency of the other or uncured material breach.",
    ]),
    ("term_conv", "termination", "high", False, True, "Termination", [
        "{customer} may terminate this Agreement for convenience at any time on seven (7) days' notice, and {vendor} shall refund all prepaid fees in full.",
        "{customer} may terminate at any time without cause and without liability; no fees shall be payable for the remainder of the Term.",
    ]),
    # ---------------- auto renewal ----------------
    ("ren_std", "auto_renewal", "low", False, False, "Renewal", [
        "This Agreement renews for successive one-year terms unless either party gives thirty (30) days' notice of non-renewal.",
        "The subscription will automatically renew for 12 months unless cancelled at least 30 days before the renewal date.",
    ]),
    ("ren_price", "auto_renewal", "medium", False, True, "Renewal", [
        "Upon renewal, fees shall remain fixed at the initial rates for a period of five (5) years.",
        "The Agreement renews automatically and {vendor} may not increase prices on any renewal.",
    ]),
    # ---------------- governing law ----------------
    ("law_home", "governing_law", "low", False, False, "Governing Law", [
        "This Agreement is governed by the laws of India and the courts at New Delhi shall have exclusive jurisdiction.",
        "This Agreement shall be governed by Indian law, and disputes shall be resolved by arbitration seated in Delhi.",
    ]),
    ("law_foreign", "governing_law", "medium", False, True, "Governing Law", [
        "This Agreement is governed by the laws of the State of New York, and the courts of New York shall have exclusive jurisdiction.",
        "This Agreement shall be governed by the laws of England and Wales; the English courts shall have exclusive jurisdiction.",
        "Disputes shall be finally settled under the rules of the Singapore International Arbitration Centre, seated in Singapore.",
    ]),
    # ---------------- warranty ----------------
    ("war_std", "warranty", "low", False, False, "Warranties", [
        "{vendor} warrants that the Services will perform materially in accordance with the Documentation. The sole remedy for breach is re-performance or a pro-rata refund.",
        "{vendor} shall use commercially reasonable efforts to make the Services available 99.5% of the time, excluding scheduled maintenance.",
    ]),
    ("war_abs", "warranty", "high", False, True, "Warranties", [
        "{vendor} guarantees 100% uptime and that the Services will be error-free. Any failure shall entitle {customer} to service credits of 50% of annual fees per incident.",
        "{vendor} warrants that the Services are fit for every purpose for which {customer} may use them.",
    ]),
    # ---------------- non-compete / exclusivity ----------------
    ("nc_none", "non_compete", "low", False, False, "Non-Solicitation", [
        "During the Term, neither party shall knowingly solicit for employment the other party's employees directly involved in the Services.",
    ]),
    ("nc_excl", "non_compete", "high", True, False, "Exclusivity", [
        "During the Term and for two (2) years thereafter, {vendor} shall not provide similar services to any competitor of {customer}.",
        "{vendor} grants {customer} exclusivity in the {customer}'s industry and shall not license the platform to any other company in that sector.",
        "{vendor} shall not, for a period of three years, develop or market any product that competes with {customer}'s business.",
    ]),
    # ---------------- data protection ----------------
    ("dp_std", "data_protection", "low", False, False, "Data Protection", [
        "{vendor} shall process personal data only on documented instructions and implement appropriate technical and organisational measures in line with the DPDP Act, 2023.",
        "Each party shall comply with applicable data protection law. {vendor} shall notify {customer} of any personal data breach without undue delay.",
    ]),
    ("dp_strict", "data_protection", "high", True, False, "Data Protection", [
        "{vendor} shall be strictly liable for any data breach, howsoever caused, and shall bear all regulatory fines imposed on {customer}.",
        "{customer} and its auditors may audit {vendor}'s systems, premises and records at any time without notice and at {vendor}'s cost.",
    ]),
    # ---------------- assignment ----------------
    ("asg_mutual", "assignment", "low", False, False, "Assignment", [
        "Neither party may assign this Agreement without the other's prior written consent, except to a successor in a merger or acquisition.",
    ]),
    ("asg_one", "assignment", "medium", False, True, "Assignment", [
        "{customer} may assign this Agreement freely to any third party. {vendor} may not assign or subcontract any obligation without consent.",
    ]),
    # ---------------- price / other ----------------
    ("price", "price", "low", False, False, "Fees", [
        "{customer} shall pay {vendor} an annual subscription fee of {price} for {seats} user seats.",
        "The total annual fees for the Services are {price}, covering {seats} named users.",
    ]),
    ("misc", "other", "low", False, False, "General", [
        "This Agreement constitutes the entire agreement between the parties and supersedes all prior understandings.",
        "Notices shall be in writing and delivered by email to the addresses set out above.",
        "If any provision is held invalid, the remainder of this Agreement shall continue in full force.",
    ]),
]

# Paraphrase noise so the ML component cannot simply memorise exact strings.
PREFIXES = ["", "Notwithstanding anything to the contrary, ", "Subject to the terms hereof, ", "For the avoidance of doubt, "]
SUFFIXES = ["", " This clause shall survive termination.", " The parties acknowledge this term was negotiated."]
