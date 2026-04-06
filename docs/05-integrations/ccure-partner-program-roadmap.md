---
title: "Software House Connected Partner Program Roadmap"
type: "spec"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Software House Connected Partner Program Roadmap

## Overview

This guide explains how to obtain a Software House Connected Partner Program license and integrate C•CURE 9000 with SENTINEL at your client site.

**Timeline:** 2-4 weeks from application to live integration
**Cost:** Tiered licensing based on reader count
**Benefit:** Unlock rapid SENTINEL onboarding for clients with C•CURE installations

---

## Step 1: Partner Application (1 Week)

### Prerequisites
- Your organization has a commercial relationship with clients
- You plan to integrate C•CURE with other BMS/energy systems
- Your company has technical support capability

### Application Process

1. **Visit Software House Partner Network**
   - Go to: https://softwarehouse.com/partner-network/
   - Click "Become a Partner"

2. **Submit Application**
   - Company Information
     - Legal name, address, website
     - Primary contact (name, email, phone)
     - Service focus: Integration, Consulting, VAR, etc.
   - Integration Plan
     - Describe SENTINEL platform and use case
     - Explain why C•CURE integration benefits mutual customers
     - Reference existing partners (Envoy, Milestone, HID, Oloid, etc.)
   - Technical Capability
     - List integration platforms you've built
     - Describe API experience (REST, OAuth, etc.)
     - Confirm support team availability

3. **Software House Review**
   - Partner team evaluates application (3-5 business days)
   - May request clarification or references
   - Approval or escalation to sales team

### Template Application Response

```
Company: [Your Company Name]
Primary Contact: [Name], [Title]
Email: [Email]
Phone: [Phone]

Integration Overview:
SENTINEL is an AI-powered building management system that optimizes energy
consumption, predictive maintenance, and occupancy-driven comfort in commercial
properties. We seek C•CURE 9000 integration to correlate:
- Badge access patterns with HVAC/lighting energy consumption
- Security infrastructure health with building power systems
- After-hours occupancy anomalies with energy waste detection

Market Opportunity:
South African commercial real estate increasingly deploys C•CURE for access
control. SENTINEL integration enables rapid security + energy system onboarding,
reducing client deployment time from weeks to days.

Technical References:
- Existing BMS integrations: [List Niagara, BACnet, Modbus, etc.]
- API experience: REST, OAuth, async polling, WebSocket real-time events
- Support team: 24/7 technical availability

Proposed Timeline:
- Phase 1 (Week 1-2): Development environment setup, license issuance
- Phase 2 (Week 3-4): Integration development and testing
- Phase 3 (Week 5): Pilot customer deployment
```

---

## Step 2: License Acquisition (1 Week)

### Licensing Tiers

Software House offers tiered licenses based on reader count:

| Tier | Readers | Annual Cost | Use Case |
|------|---------|-------------|----------|
| Developer | 1-10 | $0 | Development, testing (free tier) |
| Small | 11-50 | $2,000-5,000 | Small multi-site deployments |
| Medium | 51-200 | $5,000-15,000 | Regional deployments |
| Enterprise | 200+ | Custom | National/international |

### Obtaining Your License

1. **Software House Issues License GUID**
   - After approval, you receive: `SENTINEL-CCURE-GUID-xxxxx`
   - Valid for specific reader count tier
   - Tied to your company account

2. **End-User License (Per Customer)**
   - Customers purchasing SENTINEL need separate license
   - Tiered by their reader count
   - Software House tracks licenses per client

3. **victor Web Service License**
   - Separate license line item
   - Enables API access (not included in base license)
   - Cost: ~$1,000-3,000 annually depending on tier

### License Management

```
Your Account (Partner)
├─ License GUID: SENTINEL-CCURE-GUID-xxxxx
├─ Tier: Medium (51-200 readers)
├─ Valid From: Jan 1, 2026
└─ Valid To: Dec 31, 2026

Customer 1 (Client)
├─ License GUID: CCURE-CLIENT-001-xxxxx
├─ Tier: Small (25 readers)
└─ Readers: Access Control + Lighting DALI readers

Customer 2 (Client)
├─ License GUID: CCURE-CLIENT-002-xxxxx
├─ Tier: Medium (120 readers)
└─ Readers: Multi-building, 4 locations
```

---

## Step 3: Development Environment Setup (1 Week)

### Option A: Software House Test Lab Access

**Best For:** Rapid prototyping before customer deployment

1. **Request Test Environment Access**
   - Email: partners@softwarehouse.com
   - Provide: Company name, primary contact, license GUID
   - Receive: Test C•CURE instance credentials

2. **Test Lab Details**
   - URL: https://ccure-test.softwarehouse.com/
   - Pre-populated with sample data (100+ badges, 20 doors, 5 controllers)
   - Reset daily (don't rely for long-term testing)
   - Operator account: `test_partner` (password provided)

3. **Documentation**
   - victor API documentation: https://softwarehouse.com/developers/
   - Sample cURL requests
   - Authentication examples
   - Rate limits: 1000 requests/hour

### Option B: Local C•CURE Instance (Recommended for Production)

**Best For:** Full control, accurate testing with customer-like setup

1. **Request VMware/Hyper-V Appliance**
   - Contact: Software House sales
   - Delivery: C•CURE 9000 virtual machine image
   - Requirements: 4GB RAM, 50GB disk, Windows Server 2019+

2. **Installation Steps**
   - Deploy VM from image
   - Configure IIS for victor Web Service
   - Create Operator account with "SYSTEM ALL" permission
   - Configure sample data (import sample database backup)

3. **Backup Credentials**
   ```
   C•CURE Admin Login:
   - Username: ccure_admin
   - Password: [Set during installation]

   victor API Service:
   - URL: https://localhost:6443/api/
   - Operator: sentinel_operator
   - Password: [Create in UI]
   ```

### victor Web Service Configuration

1. **IIS Setup**
   - victor service runs on port 6443 (HTTPS)
   - Self-signed cert OK for testing (ignore cert warnings)
   - Windows authentication or API key fallback

2. **Test Connectivity**
   ```bash
   # Test victor API endpoint
   curl -k -X GET https://ccure-test.softwarehouse.com/api/system/info \
     -H "Authorization: Bearer <token>"

   # Expected response:
   {
     "manufacturer": "Software House",
     "model": "C•CURE 9000",
     "version": "2.90",
     "deployed_date": "2024-01-15"
   }
   ```

3. **Token Acquisition**
   ```bash
   # POST to obtain JWT token
   curl -k -X POST https://ccure-test.softwarehouse.com/api/auth/token \
     -H "Content-Type: application/json" \
     -d '{
       "license_guid": "SENTINEL-CCURE-GUID-xxxxx",
       "username": "sentinel_operator",
       "password": "your_password"
     }'

   # Response:
   {
     "token": "eyJhbGc...",
     "expires_in": 3600
   }
   ```

---

## Step 4: Integration Development (1-2 Weeks)

### Code Setup

1. **Create CCure Adapter**
   ```python
   # backend/app/services/ccure/ccure_adapter.py

   class CCureAdapter(DeviceAdapter):
       def __init__(self, api_url, license_guid, username, password):
           self.api_url = api_url
           self.license_guid = license_guid
           self.token = None

       async def _authenticate(self):
           """Obtain JWT token from victor API"""
           response = await self.client.post(
               f"{self.api_url}/auth/token",
               json={
                   "license_guid": self.license_guid,
                   "username": self.username,
                   "password": self.password
               }
           )
           self.token = response.json()["token"]

       async def get_badge_events(self, since: datetime):
           """Fetch badge events since timestamp"""
           response = await self.client.get(
               f"{self.api_url}/access-events",
               headers={"Authorization": f"Bearer {self.token}"},
               params={"since": since.isoformat()}
           )
           return response.json()
   ```

2. **Test Against Test Lab**
   ```bash
   cd backend

   # Set environment variables
   export CCURE_API_URL="https://ccure-test.softwarehouse.com/api/"
   export CCURE_LICENSE_GUID="SENTINEL-CCURE-GUID-xxxxx"
   export CCURE_USERNAME="test_partner"
   export CCURE_PASSWORD="test_password"

   # Run integration test
   pytest tests/services/ccure/test_integration.py -v
   ```

3. **Validate Data Mapping**
   - Confirm personnel data maps to SENTINEL models
   - Verify controller health status sync
   - Test anomaly detection with sample badge events

### Certification Testing

1. **Test Scenarios**
   ```
   [ ] Badge entry/exit event capture
   [ ] Door status polling (open, locked, fault)
   [ ] Controller heartbeat monitoring
   [ ] Anti-passback zone occupancy
   [ ] Permission revocation sync
   [ ] Controller offline detection
   [ ] Error handling (API timeout, credential revoked, etc.)
   ```

2. **Performance Testing**
   ```
   [ ] 1000+ badge events per day processed
   [ ] <100ms latency per API call
   [ ] Polling interval 60 seconds (no performance impact)
   [ ] Memory footprint <100MB for adapter
   ```

3. **Security Testing**
   ```
   [ ] API credentials encrypted in .env
   [ ] JWT token rotation every hour
   [ ] No sensitive data logged to console
   [ ] HTTPS certificate verification enforced
   [ ] Cross-origin access controls validated
   ```

---

## Step 5: Production Certification (1 Week)

### Certification Checklist

**Document Submission:**
- [ ] Integration architecture diagram
- [ ] API call sequence documentation
- [ ] Data mapping specification (C•CURE ↔ SENTINEL)
- [ ] Error handling procedures
- [ ] Security practices (credential storage, encryption)
- [ ] Performance benchmarks
- [ ] Test results (all scenarios passed)

**Code Review:**
- [ ] Software House reviews integration code
- [ ] No unauthorized API calls (only documented endpoints)
- [ ] No credential hardcoding
- [ ] Proper error handling and logging

**Customer Pilot (Optional):**
- [ ] Deploy at 1-2 friendly customers
- [ ] 30-day pilot period
- [ ] Gather feedback and metrics
- [ ] Document any issues and resolutions

### Certification Approval

Once approved, you receive:
```
✅ Integration Certification Document
✅ Production License (multi-customer use)
✅ Technical Support Agreement (Software House)
✅ Marketing Co-op Approval (list on Software House partner directory)
```

---

## Step 6: Customer Deployment (1-2 Days Per Customer)

### Pre-Deployment Checklist

**Customer Preparation:**
- [ ] C•CURE 9000 v2.90+ deployed and operational
- [ ] Operator account created with "SYSTEM ALL" permission
- [ ] Sample data loaded (for training)
- [ ] Network connectivity to SENTINEL platform
- [ ] API credentials (username/password) prepared

**SENTINEL Preparation:**
- [ ] Production environment deployed
- [ ] C•CURE adapter configured with customer endpoint
- [ ] Credentials stored in .env (encrypted)
- [ ] Demo mode disabled
- [ ] Live mode enabled
- [ ] Database migrations applied

### Deployment Steps

1. **Connection Verification** (30 min)
   ```bash
   # Test C•CURE connectivity
   curl -X GET \
     -H "Authorization: Bearer $TOKEN" \
     https://ccure.customer.com/api/system/info

   # Should return: C•CURE system info
   ```

2. **Data Sync Validation** (30 min)
   ```bash
   # Verify badge events flowing
   GET /api/security/events/recent?limit=10

   # Verify controller status
   GET /api/security/ccure/controllers

   # Verify occupancy
   GET /api/security/occupancy/real-time
   ```

3. **Anomaly Detection Test** (30 min)
   - Trigger after-hours access (use test badge)
   - Verify anomaly detected in dashboard
   - Check cross-system correlations working

4. **Dashboard Training** (1 hour)
   - Show C•CURE status card (live vs. demo)
   - Explain anomaly types and severity
   - Walk through recommendations
   - Demonstrate ROI calculations

5. **Go-Live** (30 min)
   - Enable production badges
   - Configure alert thresholds
   - Set notification channels (email, Slack, etc.)
   - Handoff to customer operations team

---

## Customer Onboarding Template Email

```
Subject: SENTINEL Security Module + C•CURE 9000 Integration Ready

Hi [Customer Name],

Your SENTINEL platform has been successfully integrated with your C•CURE 9000
access control system. You now have:

✅ Real-time badge event monitoring
✅ After-hours activity anomaly detection
✅ Security equipment health tracking
✅ Occupancy-driven energy optimization

Key Features:

1. After-Hours Anomaly Detection
   Correlates badge access with HVAC/lighting activation outside business hours,
   identifying energy waste and security risks. Estimated 15-20% energy savings
   through occupancy-driven control.

2. Security Equipment Health Monitoring
   Tracks controller status, tamper events, and network health. Predicts
   maintenance needs before failures occur.

3. Occupancy-Driven Recommendations
   Uses badge data to recommend HVAC setpoint and lighting adjustments in
   real-time, balancing comfort and efficiency.

Dashboard Location:
  http://your-domain/dashboard/security

Support:
  - Technical Issues: [Support Email]
  - Operational Questions: [Your Company]
  - C•CURE Specific: Software House Support

Next Steps:
1. Review sample anomalies in dashboard
2. Customize alert thresholds for your building
3. Set up notification channels (email, Slack, etc.)
4. Schedule monthly review meeting

Questions? Feel free to reach out!

Best regards,
[Your Company]
```

---

## Troubleshooting Deployment Issues

### Issue: "Invalid License GUID"
**Solution:**
```bash
# Verify GUID matches exactly
export CCURE_LICENSE_GUID="SENTINEL-CCURE-GUID-xxxxx"

# Check license is active (not expired)
curl -X GET \
  -H "Authorization: Bearer $TOKEN" \
  https://ccure.customer.com/api/license/status
```

### Issue: "Authentication Failed - Operator Permission Denied"
**Solution:**
- C•CURE admin: User → sentinel_operator → Permissions → Check "SYSTEM ALL"
- Verify operator can read: Badges, Events, Controllers, Zones
- Test credentials in C•CURE UI before SENTINEL integration

### Issue: "API Rate Limit Exceeded"
**Solution:**
- Increase polling interval (60 sec → 120 sec)
- Implement request batching
- Contact Software House for rate limit increase

### Issue: "Certificate Verification Failed" (HTTPS)
**Solution:**
```python
# If customer uses self-signed cert in dev:
adapter = CCureAdapter(
    api_url=...,
    verify_ssl=False  # Only for development!
)

# In production: Get signed certificate from customer
```

---

## Reference Timeline

```
Week 1:  Application submitted → Partner approval
Week 2:  License issued → Development environment access
Week 3:  Integration development (CCureAdapter)
Week 4:  Testing in lab environment
Week 5:  Certification submission → Software House review
Week 6:  Certification approved → Production ready
Week 7:  Customer deployment
Week 8:  Go-live support
```

---

## Key Contacts

**Software House Partner Program:**
- Email: partners@softwarehouse.com
- Phone: +1-800-xxx-xxxx
- Partner Portal: https://partners.softwarehouse.com/

**Technical Support:**
- Bug Reports: support@softwarehouse.com
- API Questions: developers@softwarehouse.com
- Implementation Help: integration-support@softwarehouse.com

**Your Support Team:**
- [Your Company Technical Support Email]
- [Your Company Support Phone]
- [Your Company Support Portal]

---

## Additional Resources

- **Software House Documentation:** https://docs.softwarehouse.com/ccure-9000/
- **victor API Reference:** https://softwarehouse.com/developers/api-reference/
- **Partner Directory:** https://softwarehouse.com/partner-network/partners/
- **Integration Examples:** https://github.com/SoftwareHouse/ccure-integrations/

---

*Last Updated: Phase 58.2*
*For Phase 58.3 (Live API) Updates: Check this document Q2 2026*
