# Privacy Impact Assessment (PIA) Template

**Document Owner:** Information Security Officer
**Version:** 1.0
**Effective Date:** 2026-02-05
**Review Cadence:** Annually or when processing activities change
**FSR Reference:** Domain 4.3 -- Information Classification & Data Privacy
**Classification:** Confidential

---

## How to Use This Template

This template follows POPIA requirements and ISO 29134 (Guidelines for Privacy Impact Assessment) principles. Complete each section thoroughly before initiating any high-risk data processing activity.

**When to conduct a PIA:**
- Processing personal information of data subjects
- Cross-border data transfers outside South Africa
- Introducing new technology that processes personal information
- Significant changes to existing processing activities
- Automated decision-making affecting data subjects
- Large-scale processing or profiling

---

## Section 1: Project Description

### 1.1 Project Overview

| Field | Details |
|-------|---------|
| **PIA Reference** | PIA-YYYY-NNN |
| **Project/System Name** | [Name of project or system] |
| **Business Owner** | [Name and role] |
| **Technical Owner** | [Name and role] |
| **Date Initiated** | [YYYY-MM-DD] |
| **PIA Prepared By** | [Name and role] |
| **PIA Version** | [Version number] |

### 1.2 Purpose of Processing

Describe the purpose of the processing activity:

- **Primary purpose:** [Why is personal information being processed?]
- **Secondary purposes:** [Any additional uses of the data]
- **Business justification:** [Why this processing is necessary]

### 1.3 Scope

- **Systems involved:** [List all systems that will process the data]
- **Geographic scope:** [Where processing occurs]
- **Data subjects:** [Categories of individuals whose data is processed]
- **Timeframe:** [Duration of processing activity]

---

## Section 2: Data Inventory

### 2.1 Personal Information Categories

| Category | Description | Examples | Volume (Est.) | Sensitivity |
|----------|-------------|----------|---------------|-------------|
| Identification | Direct identifiers | Names, ID numbers, employee IDs | [Count] | High |
| Contact | Communication details | Phone numbers, email addresses | [Count] | Medium |
| Location | Physical or digital location | Building access data, desk locations | [Count] | Medium |
| Behavioural | Activity patterns | Building entry/exit times, comfort complaints | [Count] | Low-Medium |
| Technical | System data | IP addresses, device identifiers | [Count] | Low |
| [Other] | [Description] | [Examples] | [Count] | [Level] |

### 2.2 Special Personal Information

Under POPIA, special personal information requires additional protections:

| Category | Processed? | Justification |
|----------|------------|---------------|
| Religious or philosophical beliefs | Yes/No | [If yes, explain] |
| Race or ethnic origin | Yes/No | [If yes, explain] |
| Trade union membership | Yes/No | [If yes, explain] |
| Political persuasion | Yes/No | [If yes, explain] |
| Health or sex life | Yes/No | [If yes, explain] |
| Biometric information | Yes/No | [If yes, explain] |
| Criminal behaviour | Yes/No | [If yes, explain] |
| Children's information | Yes/No | [If yes, explain] |

### 2.3 Data Sources

| Source | Description | Lawful Basis |
|--------|-------------|--------------|
| [Source 1] | [How data is collected] | [Legal basis for collection] |
| [Source 2] | [How data is collected] | [Legal basis for collection] |

### 2.4 Data Retention

| Data Category | Retention Period | Justification | Destruction Method |
|---------------|------------------|---------------|--------------------|
| [Category 1] | [Period] | [Why this period] | [How destroyed] |
| [Category 2] | [Period] | [Why this period] | [How destroyed] |

---

## Section 3: Necessity and Proportionality Assessment

### 3.1 Legal Basis for Processing (POPIA Section 11)

Select the applicable lawful basis:

| Basis | Applicable? | Justification |
|-------|-------------|---------------|
| **Consent** (s11(1)(a)) | Yes/No | [Data subject has given consent] |
| **Contract** (s11(1)(b)) | Yes/No | [Necessary for contract performance] |
| **Legal obligation** (s11(1)(c)) | Yes/No | [Required by law] |
| **Legitimate interest** (s11(1)(d)) | Yes/No | [Pursuing legitimate interest, balanced against data subject rights] |
| **Public interest** (s11(1)(e)) | Yes/No | [For proper performance of public law duty] |
| **Protection of legitimate interests** (s11(1)(f)) | Yes/No | [Necessary to protect legitimate interests of data subject] |

### 3.2 Necessity Test

- [ ] Is the processing necessary for the stated purpose?
- [ ] Can the purpose be achieved with less data?
- [ ] Can the purpose be achieved with anonymised/pseudonymised data?
- [ ] Is the data retained only for as long as necessary?

### 3.3 Proportionality Test

| Factor | Assessment |
|--------|------------|
| **Benefits to organisation** | [Describe benefits] |
| **Benefits to data subjects** | [Describe benefits] |
| **Potential harm to data subjects** | [Describe potential harms] |
| **Overall proportionality** | Proportionate / Disproportionate |

---

## Section 4: Data Flow Diagram

### 4.1 Data Flow Overview

```
[Insert data flow diagram here]

Example structure:
Data Subject --> [Collection Point] --> [Processing System] --> [Storage]
                                              |
                                              v
                                     [Third Party Processor]
                                              |
                                              v
                                     [Cross-border Transfer?]
```

### 4.2 Data Flow Description

| Step | From | To | Data Elements | Transfer Method | Encryption |
|------|------|-----|--------------|-----------------|------------|
| 1 | [Source] | [Destination] | [Data types] | [Method] | Yes/No |
| 2 | [Source] | [Destination] | [Data types] | [Method] | Yes/No |

### 4.3 Cross-Border Transfers

| Recipient | Country | Data Transferred | POPIA s72 Basis | Safeguards |
|-----------|---------|------------------|-----------------|------------|
| [Recipient 1] | [Country] | [Data categories] | [Legal basis] | [Safeguards in place] |

---

## Section 5: Risk Assessment

### 5.1 Risk Identification

| Risk ID | Risk Description | Risk Category |
|---------|------------------|---------------|
| R1 | [Describe risk] | Confidentiality/Integrity/Availability |
| R2 | [Describe risk] | Confidentiality/Integrity/Availability |

### 5.2 Risk Matrix

**Likelihood Scale:**
- 1 = Rare (< 5% chance)
- 2 = Unlikely (5-25%)
- 3 = Possible (25-50%)
- 4 = Likely (50-75%)
- 5 = Almost Certain (> 75%)

**Impact Scale:**
- 1 = Negligible (Minor inconvenience to data subjects)
- 2 = Limited (Short-term distress, recoverable)
- 3 = Significant (Ongoing distress, financial loss)
- 4 = Serious (Physical harm, major financial loss)
- 5 = Critical (Threat to life, large-scale harm)

**Risk Score Matrix:**

|            | Impact 1 | Impact 2 | Impact 3 | Impact 4 | Impact 5 |
|------------|----------|----------|----------|----------|----------|
| **Like. 5** | 5 (M)    | 10 (M)   | 15 (H)   | 20 (H)   | 25 (C)   |
| **Like. 4** | 4 (L)    | 8 (M)    | 12 (H)   | 16 (H)   | 20 (H)   |
| **Like. 3** | 3 (L)    | 6 (M)    | 9 (M)    | 12 (H)   | 15 (H)   |
| **Like. 2** | 2 (L)    | 4 (L)    | 6 (M)    | 8 (M)    | 10 (M)   |
| **Like. 1** | 1 (L)    | 2 (L)    | 3 (L)    | 4 (L)    | 5 (M)    |

**Risk Levels:** (L) Low 1-4 | (M) Medium 5-10 | (H) High 11-16 | (C) Critical 17-25

### 5.3 Risk Assessment Table

| Risk ID | Likelihood | Impact | Score | Level | Risk Owner |
|---------|------------|--------|-------|-------|------------|
| R1 | [1-5] | [1-5] | [Score] | [L/M/H/C] | [Name] |
| R2 | [1-5] | [1-5] | [Score] | [L/M/H/C] | [Name] |

---

## Section 6: Mitigating Controls

### 6.1 Technical Controls

| Control ID | Control Description | Risk(s) Addressed | Implementation Status |
|------------|---------------------|-------------------|----------------------|
| TC1 | [Description] | R1, R2 | Implemented/Planned |
| TC2 | [Description] | R3 | Implemented/Planned |

### 6.2 Organisational Controls

| Control ID | Control Description | Risk(s) Addressed | Implementation Status |
|------------|---------------------|-------------------|----------------------|
| OC1 | [Description] | R1 | Implemented/Planned |
| OC2 | [Description] | R2 | Implemented/Planned |

### 6.3 Contractual Controls

| Control ID | Control Description | Third Party | Status |
|------------|---------------------|-------------|--------|
| CC1 | [Description] | [Provider] | In place/Required |
| CC2 | [Description] | [Provider] | In place/Required |

---

## Section 7: Residual Risk Evaluation

### 7.1 Residual Risk Assessment

After implementing mitigating controls:

| Risk ID | Original Score | Controls Applied | Residual Score | Residual Level | Acceptable? |
|---------|----------------|------------------|----------------|----------------|-------------|
| R1 | [Score] | TC1, OC1 | [Score] | [L/M/H/C] | Yes/No |
| R2 | [Score] | TC2, CC1 | [Score] | [L/M/H/C] | Yes/No |

### 7.2 Overall Residual Risk Rating

| Level | Criteria | This Assessment |
|-------|----------|-----------------|
| **LOW** | All residual risks are Low or Medium with effective controls | [ ] |
| **MEDIUM** | Some High residual risks with mitigation plans in progress | [ ] |
| **HIGH** | Critical or multiple High residual risks without adequate mitigation | [ ] |

### 7.3 Risk Acceptance

For any residual risks rated Medium or above:

| Risk ID | Residual Level | Risk Acceptance Decision | Accepted By | Date |
|---------|----------------|--------------------------|-------------|------|
| R1 | [Level] | Accept/Mitigate/Avoid/Transfer | [Name] | [Date] |

---

## Section 8: POPIA Compliance Checklist

### 8.1 Conditions for Lawful Processing

| Condition | Requirement | Status | Evidence/Notes |
|-----------|-------------|--------|----------------|
| **1. Accountability** | Organisation takes responsibility for compliance | Met/Partial/Not Met | [Evidence] |
| **2. Processing Limitation** | Processing is lawful, adequate, relevant, not excessive | Met/Partial/Not Met | [Evidence] |
| **3. Purpose Specification** | Personal information collected for specific, explicit, legitimate purpose | Met/Partial/Not Met | [Evidence] |
| **4. Further Processing Limitation** | Further processing compatible with original purpose | Met/Partial/Not Met | [Evidence] |
| **5. Information Quality** | Information is complete, accurate, not misleading, updated | Met/Partial/Not Met | [Evidence] |
| **6. Openness** | Privacy notice provided to data subjects | Met/Partial/Not Met | [Evidence] |
| **7. Security Safeguards** | Appropriate technical and organisational measures | Met/Partial/Not Met | [Evidence] |
| **8. Data Subject Participation** | Data subjects can access, correct, delete their information | Met/Partial/Not Met | [Evidence] |

### 8.2 Cross-Border Transfer Compliance (Section 72)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Transfer only to countries with adequate protection | Compliant/N/A | [Evidence] |
| Binding corporate rules in place | Compliant/N/A | [Evidence] |
| Data subject consent obtained | Compliant/N/A | [Evidence] |
| Transfer necessary for contract performance | Compliant/N/A | [Evidence] |
| Transfer for benefit of data subject | Compliant/N/A | [Evidence] |

### 8.3 Operator Requirements (Section 21)

If using third-party processors:

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Written contract in place | Yes/No | [Reference] |
| Security measures specified | Yes/No | [Reference] |
| Breach notification requirements | Yes/No | [Reference] |
| Return/deletion on termination | Yes/No | [Reference] |

---

## Section 9: Recommendations

### 9.1 Required Actions (Before Processing)

| Action | Priority | Responsible | Target Date | Status |
|--------|----------|-------------|-------------|--------|
| [Action 1] | High/Medium/Low | [Name] | [Date] | Pending/Complete |
| [Action 2] | High/Medium/Low | [Name] | [Date] | Pending/Complete |

### 9.2 Recommendations (To Improve Privacy)

| Recommendation | Rationale | Implementation Cost |
|----------------|-----------|---------------------|
| [Recommendation 1] | [Why this improves privacy] | Low/Medium/High |
| [Recommendation 2] | [Why this improves privacy] | Low/Medium/High |

### 9.3 Conditions for Approval

Processing may proceed only if:

- [ ] All required actions are completed
- [ ] Residual risk is acceptable to the risk owner
- [ ] All POPIA conditions are met
- [ ] Sign-off obtained from Information Security Officer

---

## Section 10: Sign-off and Review Schedule

### 10.1 PIA Sign-off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| **Business Owner** | [Name] | _____________ | [Date] |
| **Technical Owner** | [Name] | _____________ | [Date] |
| **Information Security Officer** | [Name] | _____________ | [Date] |
| **Data Protection Officer** (if applicable) | [Name] | _____________ | [Date] |

### 10.2 Approval Decision

| Decision | Date | Approved By |
|----------|------|-------------|
| [ ] **Approved** - Processing may proceed | [Date] | [Name] |
| [ ] **Approved with conditions** - Processing may proceed after completing required actions | [Date] | [Name] |
| [ ] **Not approved** - Processing must not proceed until issues resolved | [Date] | [Name] |

### 10.3 Review Schedule

| Review Type | Frequency | Next Review Date |
|-------------|-----------|------------------|
| Annual PIA review | 12 months | [Date] |
| Triggered review (on change) | As needed | N/A |
| Compliance audit | Annually | [Date] |

**Triggers for immediate review:**
- Change in processing purpose or scope
- New data categories collected
- New third-party processors
- Security incident or breach
- Change in legal requirements
- Significant increase in data volume

---

## Appendices

### Appendix A: Data Flow Diagram

[Insert detailed data flow diagram]

### Appendix B: Privacy Notice

[Reference or include the privacy notice provided to data subjects]

### Appendix C: Consent Records

[Reference consent capture mechanism and sample consent text]

### Appendix D: Third-Party Agreements

[List relevant DPAs and operator agreements]

### Appendix E: Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | [Date] | [Author] | Initial PIA |
| 1.1 | [Date] | [Author] | [Changes made] |

---

## References

| Document | Location |
|----------|----------|
| POPIA (Protection of Personal Information Act, 2013) | Government Gazette |
| ISO 29134:2017 (Guidelines for Privacy Impact Assessment) | ISO |
| SENTINEL Data Privacy Policy | `docs/08-security/data-privacy-policy.md` |
| SENTINEL Consent and Privacy Controls | `docs/08-security/consent-and-privacy.md` |
| SENTINEL Third-Party Security Register | `docs/08-security/third-party-security-register.md` |
| SENTINEL Information Classification Policy | `docs/08-security/information-classification-policy.md` |

---

*This template is maintained by the Information Security Officer. PIAs must be completed before initiating any high-risk data processing activity and reviewed annually.*
