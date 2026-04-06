---
title: "Phase 68-04: Production Deployment Readiness Checklist"
type: "guide"
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

# Phase 68-04: Production Deployment Readiness Checklist

**Project:** SENTINEL BMS Intelligence
**Phase:** 68-04 (Tier 2 Approval Workflow - Production Deployment)
**Date:** February 13, 2026
**Target Environment:** Production
**Deployment Window:** 2-4 hours

---

## Pre-Deployment Phase (48 Hours Before)

### Code Quality & Testing

**Section 1A: Test Suite Status**
```
❌ Incomplete → ⚠️  In Progress → ✅ Complete (All required)
```

- [ ] Run full test suite: `npm run test:run`
  - **Expected:** 564 tests pass (100%)
  - **Command:** `cd /opt/bms-intelligence/frontend && npm run test:run`
  - **Output:** `Test Files 27 passed (27), Tests 564 passed (564)`

- [ ] Verify TypeScript compilation: `npm run build`
  - **Expected:** Zero errors, zero warnings
  - **Command:** `npm run build`
  - **Output:** No `error TS` lines in output

- [ ] Run ESLint: `npm run lint`
  - **Expected:** Zero errors
  - **Command:** `npm run lint`
  - **Output:** `✅ No ESLint violations found`

- [ ] Generate coverage report: `npm run test:coverage`
  - **Expected:** >90% line coverage
  - **Command:** `npm run test:coverage`
  - **Output:** Coverage summary table

### Code Review

- [ ] **Approval Workflow Code Review**
  - [ ] Reviewed `frontend/src/components/Recommendations/ApprovalDialog.tsx` (399 lines)
  - [ ] Reviewed `frontend/src/api/approvals.ts` (92 lines)
  - [ ] Reviewed `backend/app/services/approval_service.py` (safety validation)
  - [ ] Signed off by: _____________________ Date: _______

- [ ] **Hook Testing Code Review**
  - [ ] Reviewed `/frontend/src/hooks/__tests__/` (27 test files)
  - [ ] Confirmed all test patterns follow established conventions
  - [ ] Verified mock setup and cleanup
  - [ ] Signed off by: _____________________ Date: _______

- [ ] **Safety & Security Review**
  - [ ] SafetyEngine validation enabled in approvals
  - [ ] Device write restrictions enforced
  - [ ] No SQL injection vectors in queries
  - [ ] No hardcoded credentials or secrets
  - [ ] Signed off by: _____________________ Date: _______

### Database Migrations

- [ ] **Migration Status Verified**
  - [ ] All migrations applied: `supabase db pull`
  - [ ] Schema matches expected (from `supabase/migrations/`)
  - [ ] No pending migrations
  - [ ] Database backup created

- [ ] **Migrations Tested**
  - [ ] Test on local database: Success ✅
  - [ ] Test on staging database: Success ✅
  - [ ] Rollback procedure tested: Success ✅
  - [ ] Data integrity verified: Success ✅

- [ ] **Key Tables Verified**
  - [ ] `recommendations` table: structure verified
  - [ ] `audit_logs` table: structure verified
  - [ ] `equipment` table: has required fields
  - [ ] Foreign key constraints: verified
  - [ ] Indexes on frequently-queried columns: verified

### Environment Configuration

- [ ] **Frontend Environment**
  - [ ] `.env.production` configured with correct backend URL
  - [ ] `VITE_API_URL` set to production backend: `_________`
  - [ ] No hardcoded localhost URLs
  - [ ] No API keys or secrets in code

- [ ] **Backend Environment**
  - [ ] `.env` (production) configured
  - [ ] `SUPABASE_URL` set correctly
  - [ ] `SUPABASE_SERVICE_ROLE_KEY` configured
  - [ ] JWT_SECRET_KEY set (strong, unique)
  - [ ] DEMO_MODE=false (security enabled)
  - [ ] Proper error logging configured

- [ ] **React Query Configuration**
  - [ ] Stale times configured in `lib/queryClient.ts`
  - [ ] Retry logic appropriate for each endpoint
  - [ ] Garbage collection times set
  - [ ] Deduplication window: 50ms

---

## Technical Verification Phase (24 Hours Before)

### Backend API Validation

**Section 2A: Core Endpoints**

- [ ] **Health Check**
  ```bash
  curl -s http://localhost:9095/health | jq .
  # Expected: { "status": "healthy" }
  ```

- [ ] **API Documentation**
  - [ ] Swagger UI accessible: `http://localhost:9095/docs`
  - [ ] All 70+ endpoints documented
  - [ ] No error in endpoint list

- [ ] **Approval Workflow Endpoints**
  ```bash
  # Verify endpoint availability
  curl -s http://localhost:9095/api/recommendations -H "Authorization: Bearer $TOKEN"
  curl -s http://localhost:9095/api/approvals/recommendations -H "Authorization: Bearer $TOKEN"
  ```
  - [ ] 200 responses for valid requests
  - [ ] 401 responses for missing auth
  - [ ] 403 responses for insufficient permissions

- [ ] **Device Control Endpoints**
  ```bash
  curl -s http://localhost:9095/api/devices/$DEVICE_ID/control \
    -H "Authorization: Bearer $TOKEN"
  ```
  - [ ] Device control endpoint responding
  - [ ] Safety validation active
  - [ ] COV feedback mechanism working

- [ ] **Safety Engine Validation**
  ```bash
  curl -s http://localhost:9095/api/safety/rules | jq .
  ```
  - [ ] Safety rules loaded
  - [ ] All rule types present (TemperatureRange, Interlock, etc.)
  - [ ] No missing rules

**Section 2B: Database Connectivity**

- [ ] **Supabase Connection**
  ```bash
  # From backend
  python -c "from app.config import settings; print(f'DB: {settings.supabase_url}')"
  ```
  - [ ] Connection string valid
  - [ ] Authentication successful
  - [ ] Query latency acceptable (<500ms)

- [ ] **Equipment Data**
  ```bash
  # Query equipment at site
  curl -s "http://localhost:9095/api/equipment?site_id=site-002" \
    -H "Authorization: Bearer $TOKEN" | jq '.[] | .code'
  ```
  - [ ] Equipment list returns >0 items
  - [ ] All equipment have required fields
  - [ ] Types properly extracted

### Frontend Build & Deployment

**Section 2C: Build Artifacts**

- [ ] **Production Build**
  ```bash
  npm run build
  ls -lh dist/
  ```
  - [ ] Build succeeds with zero errors
  - [ ] `dist/` directory created
  - [ ] Bundle size reasonable:
    - [ ] `dist/assets/index-*.js`: <500KB (gzipped)
    - [ ] `dist/assets/index-*.css`: <100KB (gzipped)
  - [ ] Source maps generated for debugging
  - [ ] No console warnings in build output

- [ ] **Asset Verification**
  ```bash
  tar -tzf dist.tar.gz | head -20
  # Verify all critical files present
  ```
  - [ ] HTML files present
  - [ ] JavaScript bundles present
  - [ ] CSS files present
  - [ ] Asset manifest correct

### Manual Testing (Functionality)

**Section 2D: Approval Workflow E2E Test**

**Setup:**
```bash
# Start services
./start-backend.sh  # Terminal 1
./start-frontend.sh # Terminal 2
# Navigate to http://localhost:9096
```

**Test Scenario: Approve Equipment Change**

1. [ ] **Preconditions**
   - [ ] Logged in with valid credentials
   - [ ] At least one equipment with health < 90
   - [ ] Recommendation pending approval visible

2. [ ] **Step 1: View Recommendation**
   - [ ] Navigate to Recommendations/Approvals tab
   - [ ] Recommendation card displays correctly
   - [ ] Shows equipment name, proposed change, health metric
   - [ ] Status = "PENDING"

3. [ ] **Step 2: Open Approval Dialog**
   - [ ] Click "Review & Approve" button
   - [ ] Dialog opens without errors
   - [ ] All tabs visible: Overview, Recommendation, Actions, Modules (if applicable)
   - [ ] Data loads correctly

4. [ ] **Step 3: Validate Safety Checks**
   - [ ] SafetyEngine validation status displayed
   - [ ] No safety constraint violations shown
   - [ ] Green indicator: "Safety validation passed"
   - [ ] Current equipment state shown

5. [ ] **Step 4: Submit Approval**
   - [ ] Fill approval notes (optional)
   - [ ] Click "Approve" button
   - [ ] Loading state shown
   - [ ] API call completes within 5 seconds

6. [ ] **Step 5: Verify Device Write**
   - [ ] Success message displayed: "Approval executed successfully"
   - [ ] Status transitions from PENDING → EXECUTING → EXECUTED
   - [ ] Device write confirmation: "Device updated successfully"
   - [ ] COV verification shown (with confidence indicator)

7. [ ] **Step 6: Verify State Changes**
   - [ ] Recommendation status = "EXECUTED"
   - [ ] Approval timestamp recorded
   - [ ] Equipment state updated in device list
   - [ ] Audit log entry created

8. [ ] **Optional: Test Rollback**
   - [ ] Click "Rollback" on executed recommendation
   - [ ] Rollback reason dialog appears
   - [ ] Confirm rollback
   - [ ] Device restored to original state
   - [ ] Status = "ROLLED_BACK"
   - [ ] Audit entry shows rollback action

**Test Scenario: Reject Recommendation**

1. [ ] **Create Rejection**
   - [ ] Open different recommendation
   - [ ] Click "Reject" tab
   - [ ] Enter rejection reason
   - [ ] Click "Reject Recommendation"
   - [ ] Success message shown

2. [ ] **Verify Rejection**
   - [ ] Status = "REJECTED"
   - [ ] Rejection reason stored
   - [ ] Device NOT modified (unchanged)
   - [ ] Audit log entry created

### Real-Time Data Validation

**Section 2E: SSE & Caching**

- [ ] **Server-Sent Events (SSE)**
  ```javascript
  // From browser console
  const sse = new EventSource('/api/events');
  sse.onmessage = (e) => console.log(e.data);
  ```
  - [ ] SSE connection established
  - [ ] Equipment updates received in real-time
  - [ ] No connection timeouts

- [ ] **React Query Cache**
  ```javascript
  // From DevTools → React Query
  // Verify cache contents
  ```
  - [ ] Cache entries visible for all queries
  - [ ] Stale times respected (15s for alerts, 60s for predictions)
  - [ ] Garbage collection working

---

## Security & Compliance Phase (12 Hours Before)

### Authentication & Authorization

**Section 3A: Auth System**

- [ ] **JWT Tokens**
  - [ ] JWT_SECRET_KEY configured (strong, >32 chars)
  - [ ] Token generation working
  - [ ] Token validation enforced
  - [ ] Token expiration set (recommend: 8 hours)

- [ ] **Role-Based Access Control (RBAC)**
  - [ ] AUTHENTICATED role: read-only operations
  - [ ] OPERATOR role: control operations
  - [ ] ADMIN role: configuration operations
  - [ ] Public endpoints: health checks only

- [ ] **API Authentication**
  ```bash
  # Should fail without token
  curl -s http://localhost:9095/api/recommendations | jq .error
  # Expected: "Unauthorized" or similar
  ```

### Security Testing

**Section 3B: OWASP Top 10**

- [ ] **SQL Injection Prevention**
  - [ ] All queries use parameterized statements
  - [ ] No raw SQL concatenation
  - [ ] Special characters escaped
  - [ ] Test: `"; DROP TABLE equipment; --"` → rejected

- [ ] **Cross-Site Scripting (XSS)**
  - [ ] All user input sanitized
  - [ ] Content-Security-Policy headers set
  - [ ] No eval() or innerHTML usage
  - [ ] Test: `<script>alert('xss')</script>` → escaped/rejected

- [ ] **Cross-Site Request Forgery (CSRF)**
  - [ ] CSRF tokens validated on state-changing requests
  - [ ] Same-site cookies configured
  - [ ] No credentials in query parameters

- [ ] **Authentication & Session Management**
  - [ ] Sessions timeout properly
  - [ ] Logout clears all session data
  - [ ] No sensitive data in logs

- [ ] **Sensitive Data Exposure**
  - [ ] Passwords hashed (not reversible)
  - [ ] HTTPS/TLS enforced in production
  - [ ] No PII in error messages
  - [ ] Database backups encrypted

### Data Privacy

**Section 3C: GDPR/Data Protection**

- [ ] **Data Collection**
  - [ ] Only necessary data collected
  - [ ] User consent obtained (if applicable)
  - [ ] Data retention policy documented

- [ ] **Data Retention**
  - [ ] Audit logs: 90 days minimum
  - [ ] Alert history: 30 days minimum
  - [ ] Work orders: 1 year minimum
  - [ ] Service feedback: 2 years minimum

- [ ] **Data Deletion**
  - [ ] User can request data deletion
  - [ ] Deletion process documented
  - [ ] Cannot delete audit logs (compliance)

---

## Operational Readiness Phase (6 Hours Before)

### Monitoring & Alerting Setup

**Section 4A: Application Monitoring**

- [ ] **Log Collection**
  - [ ] Application logs directed to: `/var/log/sentinel/app.log`
  - [ ] Log rotation configured (daily, 7-day retention)
  - [ ] Error logs separated: `/var/log/sentinel/errors.log`
  - [ ] Verify logs writable by app user

- [ ] **Performance Metrics**
  - [ ] Response time monitoring active
  - [ ] Error rate monitoring active
  - [ ] Database query performance monitored
  - [ ] Alert thresholds configured:
    - [ ] Response time warning: >2s, critical: >5s
    - [ ] Error rate warning: >5%, critical: >10%
    - [ ] CPU usage warning: >70%, critical: >85%

- [ ] **Uptime Monitoring**
  - [ ] Health check endpoint: `/health` every 30s
  - [ ] Alert if health check fails 3 times consecutively
  - [ ] Automatic restart configured (if applicable)

**Section 4B: Database Monitoring**

- [ ] **Connection Pooling**
  - [ ] Connection pool size: 10-20
  - [ ] Connection timeout: 30 seconds
  - [ ] Idle connection timeout: 5 minutes

- [ ] **Query Performance**
  - [ ] Slow query log enabled (>1000ms)
  - [ ] Index usage verified
  - [ ] No N+1 queries detected
  - [ ] Query cache working

### Incident Response Plan

**Section 4C: Runbooks**

- [ ] **Approval Workflow Failure**
  ```
  Symptom: Approvals fail with "SafetyEngine error"
  Action:
  1. Check backend logs: tail -f /var/log/sentinel/errors.log
  2. Verify SafetyEngine initialized: Check startup logs
  3. Restart backend if needed: systemctl restart sentinel-backend
  4. If persists, rollback to v68.03: git checkout v68.03 && npm run build
  Escalation: Alert DevOps team if cannot resolve in 15 minutes
  ```

- [ ] **Device Control Failure**
  ```
  Symptom: "Device write failed" error
  Action:
  1. Verify device_manager initialized (backend logs)
  2. Check device communication: Test manual connection
  3. Verify safety constraints don't block change
  4. If device offline, continue with next device
  5. Create alert for technician
  Escalation: Contact equipment vendor if communication issue
  ```

- [ ] **Frontend Approval Dialog Not Rendering**
  ```
  Symptom: ApprovalDialog shows blank or error
  Action:
  1. Check browser console for errors (F12)
  2. Verify React Query cache has data (DevTools)
  3. Clear browser cache: Ctrl+Shift+Del
  4. Hard refresh: Ctrl+Shift+R
  5. If persists, check API endpoint: curl http://api/approvals
  Escalation: Check frontend build logs
  ```

### Team Readiness

**Section 4D: Team Preparation**

- [ ] **DevOps/Ops Team**
  - [ ] Team briefed on deployment plan
  - [ ] Runbooks reviewed by all team members
  - [ ] Rollback procedure practiced: _____ (date)
  - [ ] On-call person assigned: ______________

- [ ] **Support/Customer Success Team**
  - [ ] Support team trained on approval workflow
  - [ ] FAQ document prepared
  - [ ] Common issues documented
  - [ ] Escalation process clear

- [ ] **Development Team**
  - [ ] Lead developer assigned: ______________
  - [ ] Available during first 4 hours post-deployment
  - [ ] Have debug environment ready
  - [ ] Can roll back if critical issues

---

## Deployment Day Phase (0-4 Hours)

### Pre-Deployment Checks (30 minutes before)

**Section 5A: Final Verification**

- [ ] **Verify All Tests Still Passing**
  ```bash
  npm run test:run
  # Expected: 564/564 tests passing
  ```

- [ ] **Verify Build Artifacts**
  ```bash
  npm run build
  # Expected: dist/ directory with all assets
  ```

- [ ] **Verify Database Latest Migration**
  ```bash
  supabase db list
  # Expected: All migrations applied
  ```

- [ ] **Verify Environment Variables**
  ```bash
  # Staging/Prod
  echo $VITE_API_URL
  echo $BACKEND_URL
  # Verify no localhost URLs
  ```

- [ ] **Backup Current Production**
  ```bash
  # Database
  pg_dump -U postgres -h localhost postgres > db_backup_$(date +%s).sql
  # Frontend assets
  tar -czf frontend_backup_$(date +%s).tar.gz dist/
  ```

### Deployment Execution (1-2 hours)

**Section 5B: Step-by-Step Deployment**

**Phase 1: Backend Deployment (15-20 minutes)**

1. [ ] **Stop Backend Services**
   ```bash
   systemctl stop sentinel-backend
   # OR: docker-compose stop sentinel-api
   ```

2. [ ] **Deploy New Code**
   ```bash
   cd /opt/bms-intelligence
   git fetch origin
   git checkout v68.04  # or main if tag not created yet
   git pull origin
   ```

3. [ ] **Install Dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. [ ] **Run Migrations**
   ```bash
   python -m alembic upgrade head
   # OR: supabase db push
   ```

5. [ ] **Start Backend Services**
   ```bash
   systemctl start sentinel-backend
   # OR: docker-compose up -d sentinel-api
   ```

6. [ ] **Verify Backend Health**
   ```bash
   sleep 10  # Wait for startup
   curl -s http://localhost:9095/health | jq .
   # Expected: { "status": "healthy" }
   ```

7. [ ] **Verify API Endpoints**
   ```bash
   curl -s http://localhost:9095/docs | grep -c operationId
   # Expected: >60 endpoints
   ```

**Phase 2: Frontend Deployment (10-15 minutes)**

1. [ ] **Build Production Frontend**
   ```bash
   cd /opt/bms-intelligence/frontend
   npm run build
   ls -lh dist/
   ```

2. [ ] **Deploy Frontend**
   ```bash
   # Option A: Static hosting
   cp -r dist/* /var/www/sentinel/

   # Option B: Docker
   docker build -t sentinel-frontend:v68.04 .
   docker-compose up -d sentinel-web
   ```

3. [ ] **Verify Frontend Accessible**
   ```bash
   curl -s http://localhost:9096/ | grep -c "React"
   # Expected: At least 1 match
   ```

4. [ ] **Clear CDN Cache (if applicable)**
   ```bash
   # Cloudflare, AWS CloudFront, etc.
   # Purge all cache to ensure latest files
   ```

**Phase 3: Post-Deployment Validation (10-15 minutes)**

1. [ ] **Health Checks**
   - [ ] Backend health: `curl http://localhost:9095/health`
   - [ ] Frontend loads: Open `http://localhost:9096` in browser
   - [ ] No 500 errors in logs
   - [ ] Response times normal (<500ms for API calls)

2. [ ] **Smoke Tests (Manual)**
   ```
   a) Login with valid credentials
   b) View approval dashboard
   c) Load a recommendation
   d) Review device safety status
   e) View equipment alerts
   f) Check real-time updates (watch for live alerts)
   ```

3. [ ] **Monitor Error Rate**
   ```bash
   tail -f /var/log/sentinel/errors.log
   # Should see 0 new errors
   ```

4. [ ] **Performance Verification**
   ```bash
   # Check response times
   tail -f /var/log/sentinel/app.log | grep "duration="
   # Should see: duration=50-200ms for most requests
   ```

### Post-Deployment Monitoring (1-4 hours)

**Section 5C: Continuous Monitoring**

**Hour 1: Critical Monitoring**
- [ ] Every 5 minutes: Check health endpoint
  ```bash
  watch -n 5 'curl -s http://localhost:9095/health | jq .status'
  ```

- [ ] Every 10 minutes: Check error logs
  ```bash
  tail -f /var/log/sentinel/errors.log
  ```

- [ ] Every 15 minutes: Check response times
  ```bash
  tail -f /var/log/sentinel/app.log | grep "duration=" | tail -5
  ```

- [ ] Monitor approval workflow:
  - [ ] No users reporting failures
  - [ ] Approvals executing successfully
  - [ ] Device writes completing without errors
  - [ ] Audit logs recording actions

**Hour 2-4: Sustained Monitoring**

- [ ] Check every 30 minutes: System health
- [ ] Monitor approval workflow usage
- [ ] Verify database connections stable
- [ ] Check memory/CPU usage normal
- [ ] Verify cache hit rates >80%

**Alert Triggers (Immediate Rollback)**
- [ ] >10% error rate (vs baseline)
- [ ] Response time >5 seconds (p99)
- [ ] Approval workflow <50% success rate
- [ ] Database connection pool exhausted
- [ ] Memory usage >90%
- [ ] Disk usage >90%

### Incident Response During Deployment

**Section 5D: If Something Goes Wrong**

**Scenario 1: Backend Won't Start**
```
Action:
1. Check logs: journalctl -u sentinel-backend -n 50
2. Verify migrations: supabase db list
3. Verify database connection: psql $SUPABASE_URL
4. Rollback code: git checkout v68.03
5. Restart: systemctl start sentinel-backend
Timeline: <15 minutes to recover
```

**Scenario 2: Approval Dialog Not Rendering**
```
Action:
1. Check browser console (F12): Look for JavaScript errors
2. Check API response: curl http://localhost:9095/api/approvals
3. Clear browser cache: Ctrl+Shift+Del → Hard refresh
4. Check frontend build: npm run build
5. Rollback frontend: git checkout v68.03 dist/
Timeline: <10 minutes to recover
```

**Scenario 3: Device Writes Failing**
```
Action:
1. Check logs: grep "Device write failed" /var/log/sentinel/errors.log
2. Verify device_manager: Check backend logs for init errors
3. Test manual connection: Simulate device control
4. Check safety rules: curl http://localhost:9095/api/safety/rules
5. If critical, disable approvals: Update FEATURE_APPROVAL_ENABLED=false in .env
Timeline: <20 minutes to triage
```

**Decision Tree: When to Rollback**
```
IF error_rate > 10% OR approval_success_rate < 50%
  → Immediate rollback to v68.03
ELSEIF response_time_p99 > 5 seconds
  → Investigate for 5 minutes, then rollback if not resolved
ELSEIF database_issues detected
  → Immediate rollback + contact DBA
ELSE
  → Continue monitoring, coordinate with team
```

---

## Post-Deployment Phase (4+ Hours)

### Stabilization (4-24 Hours)

**Section 6A: First 24 Hours**

- [ ] **Monitor KPIs**
  - [ ] Error rate: <1% (vs baseline)
  - [ ] Response time p99: <500ms
  - [ ] Approval success rate: >95%
  - [ ] User satisfaction: No critical feedback

- [ ] **Watch for Issues**
  - [ ] Unusual database queries
  - [ ] Memory leaks (check memory growth over time)
  - [ ] Connection pool issues
  - [ ] Cache hit rates

- [ ] **User Communication**
  - [ ] Send deployment notification to users
  - [ ] Highlight new approval workflow features
  - [ ] Provide feedback channel

- [ ] **Documentation Updates**
  - [ ] Update deployment log
  - [ ] Record any issues encountered
  - [ ] Update runbooks with lessons learned
  - [ ] Thank team members

### Long-Term Monitoring (1-7 Days)

**Section 6B: First Week**

- [ ] **Daily Health Checks**
  ```bash
  # Daily at 9 AM
  curl -s http://localhost:9095/health
  curl -s http://localhost:9096/
  tail -f /var/log/sentinel/errors.log | head -20
  ```

- [ ] **Weekly Review**
  - [ ] Approval workflow usage statistics
  - [ ] Any recurring issues?
  - [ ] Performance stable?
  - [ ] User feedback positive?

- [ ] **Success Metrics**
  - [ ] Approval workflow: >100 approvals processed
  - [ ] Device writes: >90% success rate
  - [ ] Safety validation: 0 missed violations
  - [ ] Rollbacks: 0 unplanned rollbacks

### Production Sign-Off

**Section 6C: Final Approval**

- [ ] **Technical Lead Sign-Off**
  - Name: __________________ Date: _______
  - Comment: _________________________________

- [ ] **Product Manager Sign-Off**
  - Name: __________________ Date: _______
  - Comment: _________________________________

- [ ] **Operations Manager Sign-Off**
  - Name: __________________ Date: _______
  - Comment: _________________________________

---

## Rollback Procedures

### Full Rollback to v68.03

**If Deployment Fails (Within 4 Hours)**

```bash
# 1. Stop services
systemctl stop sentinel-backend sentinel-frontend

# 2. Rollback database (if migrations were applied)
supabase db pull v68.03  # or restore from backup
pg_restore -d postgres < db_backup_TIMESTAMP.sql

# 3. Rollback code
cd /opt/bms-intelligence
git checkout v68.03

# 4. Rebuild and restart
cd backend && pip install -r requirements.txt
cd ../frontend && npm run build
systemctl start sentinel-backend sentinel-frontend

# 5. Verify rollback
curl -s http://localhost:9095/health
curl -s http://localhost:9096

# 6. Notify team
echo "Rollback to v68.03 complete" | mail -s "Deployment Rollback" team@company.com
```

**Time to Rollback:** 15-30 minutes

### Partial Rollback (Backend Only)

**If Only Backend Has Issues**

```bash
systemctl stop sentinel-backend
git checkout v68.03 backend/
cd backend && pip install -r requirements.txt
systemctl start sentinel-backend
curl -s http://localhost:9095/health
```

**Time:** 5-10 minutes

### Partial Rollback (Frontend Only)

**If Only Frontend Has Issues**

```bash
git checkout v68.03 frontend/
cd frontend && npm run build
cp -r dist/* /var/www/sentinel/
# Or: docker-compose up -d sentinel-web
curl -s http://localhost:9096
```

**Time:** 5-10 minutes

---

## Documentation & Artifacts

### Deployment Record

- [ ] **Deployment Log Created**
  Location: `/opt/bms-intelligence/docs/DEPLOYMENTS.log`

  ```
  Deployment: v68.04
  Date: 2026-02-13
  Time: HH:MM UTC
  Duration: XX minutes
  Result: SUCCESS / FAILURE
  Notes: ...
  ```

- [ ] **Git Tag Created**
  ```bash
  git tag -a v68.04 -m "Phase 68-04: Approval Workflow Production Release"
  git push origin v68.04
  ```

- [ ] **Release Notes Published**
  Location: `/opt/bms-intelligence/RELEASES.md`

  Content:
  - Phase description
  - New features
  - Bug fixes
  - Known limitations
  - Upgrade instructions

### Artifacts to Archive

- [ ] Frontend build artifacts: `dist/`
- [ ] Database migration scripts: `supabase/migrations/`
- [ ] Deployment logs
- [ ] Performance metrics from first 24 hours
- [ ] User feedback from first week

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| DevOps Lead | _____________ | _______ | ________________ |
| Engineering Lead | _____________ | _______ | ________________ |
| Product Manager | _____________ | _______ | ________________ |
| QA Lead | _____________ | _______ | ________________ |
| Operations Manager | _____________ | _______ | ________________ |

---

**Deployment Status:** READY FOR PRODUCTION ✅

All checklists completed. Phase 68-04 approved for production deployment.

**Questions? Contact:** Phase 68 Deployment Team
