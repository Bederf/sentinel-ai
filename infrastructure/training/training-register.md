# SENTINEL Security Awareness Training Register

**Document Owner:** SENTINEL Platform Team
**Version:** 1.0
**Created:** 2026-02-04
**Status:** Active

---

## 1. Training Completion Register

Track all personnel training completions. Each row represents one module completion by one person.

### Current Training Period: 2026

| Name | Role | Module | Completion Date | Next Due | Sign-off | Notes |
|------|------|--------|----------------|----------|----------|-------|
| _[Template row]_ | Developer/Operator/Admin | Module 1-5 | YYYY-MM-DD | YYYY-MM-DD | Yes/No | _Initial/Renewal_ |

---

## 2. How to Record Training Completion

### For the trainee:

1. Complete all required module documentation review
2. Complete any module-specific activities (code review checklist, procedure walkthrough)
3. Notify the training coordinator
4. Sign the acknowledgment: "I have read, understood, and agree to comply with the security policies and procedures covered in this training module."

### For the training coordinator:

1. Verify the trainee has completed all required activities
2. Add a new row to the register above with:
   - Full name of trainee
   - Role (Developer, Operator, Administrator, Contractor)
   - Module number and name
   - Completion date (YYYY-MM-DD)
   - Next due date (completion date + 365 days)
   - Sign-off status (Yes after acknowledgment received)
3. Keep a copy of the signed acknowledgment (digital or physical)

---

## 3. Annual Renewal Process

### Timeline

| Month | Activity |
|-------|----------|
| **January** | Training coordinator sends renewal notices for Q1 |
| **February** | First reminder for overdue renewals |
| **March** | Escalation for 60-day overdue personnel |
| **Quarterly** | Compliance report generated |
| **December** | Annual programme review and content update |

### Renewal Steps

1. Training coordinator identifies personnel with training due within 30 days
2. Send renewal notice with module list and deadline
3. Trainee reviews updated module content (may have changed since last year)
4. Trainee completes acknowledgment
5. Coordinator updates register with new completion and next-due dates
6. Coordinator archives previous period records

---

## 4. New Personnel Onboarding Checklist

### First 5 Working Days

| Day | Activity | Module | Sign-off |
|-----|----------|--------|----------|
| Day 1 | System access provisioning | N/A | IT Admin |
| Day 1 | Security awareness introduction | Module 1: Information Security Fundamentals | Trainee |
| Day 2 | Privacy and data protection | Module 4: Privacy and Data Protection | Trainee |
| Day 3 | Role-specific training | Module 2 (Dev) / Module 3 (Ops) | Trainee |
| Day 4 | BMS/OT security (if applicable) | Module 5: BMS/OT Security | Trainee |
| Day 5 | Onboarding completion review | All assigned modules | Line Manager |

### Onboarding Verification

- [ ] All required modules completed
- [ ] Acknowledgments signed
- [ ] Register updated
- [ ] Access permissions match role
- [ ] MFA configured and tested
- [ ] SSH key provisioned (if applicable)
- [ ] Emergency contacts provided

---

## 5. Compliance Metrics

### Quarterly Report Template

**Period:** Q_ 2026
**Report Date:** YYYY-MM-DD
**Prepared By:** [Training Coordinator]

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| **Total personnel requiring training** | _ | N/A | - |
| **Training completion rate** | _% | 100% | PASS/FAIL |
| **Overdue training items** | _ | 0 | PASS/FAIL |
| **New personnel onboarded this quarter** | _ | N/A | - |
| **Onboarding completed within 5 days** | _% | 100% | PASS/FAIL |
| **Quarterly briefing attendance** | _% | 90% | PASS/FAIL |

### Completion by Module

| Module | Required | Completed | Rate | Overdue |
|--------|----------|-----------|------|---------|
| Module 1: Information Security Fundamentals | _ | _ | _% | _ |
| Module 2: Secure Development Practices | _ | _ | _% | _ |
| Module 3: Operational Security | _ | _ | _% | _ |
| Module 4: Privacy and Data Protection | _ | _ | _% | _ |
| Module 5: BMS/OT Security | _ | _ | _% | _ |

---

## 6. Historical Archive

Training records from previous periods are archived below or in a separate file for long-term retention.

### 2025 Training Period

_No records — programme established 2026._

---

## 7. FSR Audit Evidence

This register serves as evidence for:

- **FSR Domain 4.4:** Human Resource Security — security awareness training
- **POPIA Compliance:** Privacy training for personnel handling personal information
- **ISO 27001 A.6.3:** Information security awareness, education and training

For FSR submission, export this register along with:
- `infrastructure/training/security-awareness-plan.md` — programme description
- Individual acknowledgment records (digital sign-offs)
- Quarterly compliance reports

---

*Register maintained by SENTINEL Training Coordinator. Updated after each training completion.*
