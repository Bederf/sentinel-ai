# SENTINEL Outstanding TODOs Summary

## 🔍 Current Status: 155+ Outstanding Items

This document summarizes the key outstanding tasks from TODO.md as of 2026-03-16.

## 🚀 High Priority Projects

### 1. OEM Manual Scraping Service
**Status:** Assessed, not yet built
**Priority:** HIGH
**Outstanding Tasks:**
- [ ] Create bounded module under `backend/app/oem_scraper/`
- [ ] Add API routes for vendor config, crawl start, crawl jobs
- [ ] Add crawler services (fetch, parse, link classifier, download, dedupe, metadata, vendor profiles)
- [ ] Add Playwright fallback service
- [ ] Add vendor metadata tables
- [ ] Implement HTTP-first crawl with httpx + BeautifulSoup
- [ ] Add robots.txt handling, rate limiting, domain boundaries
- [ ] Implement deduplication logic
- [ ] Phase 1: HTTP-first crawler + PDF download + provenance + API
- [ ] Phase 2: Vendor profiles + JS fallback + page snapshots

### 2. Maintenance Records Ingestion Pipeline
**Status:** Designed, not yet built
**Priority:** HIGH
**Blocking:** Need answers about MRI Concept Evolution access
**Outstanding Tasks:**
- [ ] Get answers about SQL Server access, export paths, API integrations
- [ ] Build OCR-first pipeline for scanned worksheets
- [ ] Implement metadata extraction (20+ fields)
- [ ] Add document classification
- [ ] Implement equipment/site linking
- [ ] Build hybrid retrieval system
- [ ] Create intake modes (manual upload, batch import, Concept connector)

### 3. AEGIS Agent Operationalization
**Status:** IN PROGRESS - Agent active in supervised shadow mode
**Priority:** HIGH
**Outstanding Tasks:**
- [ ] Complete Phase 0A (14 consecutive simulation days, no blockers)
- [ ] Complete Phase 0B (14 consecutive live-read days, no blockers)
- [ ] Maintain zero unresolved tripwires older than 24h
- [ ] Meet approval SLA target (avg_response_time_s < 300)
- [ ] Finalize Phase 1 evidence pack
- [ ] Run controlled Modbus lab write and COV readback validation
- [ ] Get change window + rollback plan approved

### 4. Domain Migration: bms.aimthelaw.co.za → sentinel-ai.co.za
**Status:** Plan Created, Awaiting Execution
**Priority:** CRITICAL
**Blocking:** Need to verify backend port (9095 vs 9097)
**Outstanding Tasks:**
- [ ] Create backups of all configuration files
- [ ] Verify backend port
- [ ] DNS preparation in Cloudflare Dashboard
- [ ] Update backend CORS settings
- [ ] Update frontend configuration
- [ ] Update Cloudflare Tunnel configuration
- [ ] Deploy backend changes
- [ ] Rebuild and deploy frontend
- [ ] Update Cloudflare Tunnel
- [ ] Set up 301 redirects for old domain
- [ ] Test and verify new domain
- [ ] Monitor and cleanup after 30 days

## 📊 Medium Priority Projects

### 5. Supabase Performance Optimization
**Status:** COMPLETE - All 4 phases done
**Priority:** MEDIUM-HIGH
**Completed:**
- ✅ Phase 1: Critical Indexes (142 tables, 34+ indexes)
- ✅ Phase 2: Query Optimization (SELECT * → column selection)
- ✅ Phase 3: Caching Layer (Redis cache for buildings, equipment, alerts, predictions)
- ✅ Phase 4: Monitoring & Archival (Grafana dashboard, slow query logging)

### 6. Security & Compliance
**Status:** Phase 1 Complete, Phases 2-3 Outstanding
**Priority:** MEDIUM-HIGH
**Outstanding Tasks:**
- [ ] Complete Phase 2 controls implementation
- [ ] Complete Phase 3 assurance (internal audit, tabletop, closure report)
- [ ] Run monthly architecture + compliance review
- [ ] Commission independent security audit
- [ ] Configure SIEM alerting rules
- [ ] Complete FSR Questionnaire
- [ ] Compile evidence package

### 7. Digital Twin Builder
**Status:** Infrastructure Complete, Validation Pending
**Priority:** MEDIUM
**Blocking:** Need real Site 002 floor plan PDF
**Outstanding Tasks:**
- [ ] Obtain real Site 002 (Sandton City) floor plan PDF
- [ ] Test Claude extraction on sanitized schematic
- [ ] Calculate extraction accuracy (target: 85%+)
- [ ] Verify re-identification
- [ ] Create demo pipeline
- [ ] Performance benchmark (< 30 seconds)
- [ ] Test with various formats
- [ ] Document findings
- [ ] Phase B: Build DXF Parser
- [ ] Integration with SIMBIOT Wizard

### 8. Dashboard Card Merging System
**Status:** Plan Ready
**Priority:** MEDIUM
**Outstanding Tasks:**
- [ ] Implement merge detection (500ms hover gesture)
- [ ] Add visual indicators (pulsing borders, icons)
- [ ] Create MergedKPICard component
- [ ] Create MergedSectionCard component
- [ ] Add persistence to backend
- [ ] Implement unmerge logic
- [ ] Add comprehensive tests

## 🎨 Low Priority / Future Enhancements

### 9. Document Management System
**Status:** MVP Complete, Phases 2-6 Outstanding
**Priority:** LOW
**Outstanding Tasks:**
- [ ] Document List UI
- [ ] Delete Documents functionality
- [ ] Download Originals
- [ ] Metadata Editing
- [ ] Bulk Upload
- [ ] OCR for Scanned PDFs
- [ ] Document Versioning
- [ ] Auto-Metadata Extraction
- [ ] Auto-Tagging
- [ ] Duplicate Detection
- [ ] Content Summarization
- [ ] Organization-Level Docs
- [ ] Role-Based Access
- [ ] Audit Trail
- [ ] Search Analytics
- [ ] Semantic Search Improvements

### 10. Recommendation Pipeline Fixes
**Status:** Partial
**Priority:** LOW
**Outstanding Tasks:**
- [ ] Investigate why ai_optimization recs stopped
- [ ] Ensure optimization analysis runs on schedule
- [ ] Wire AIRecommendationEngine into background scheduler
- [ ] Surface financial recs on finance pages only
- [ ] Add source badges to recommendation cards

### 11. Voice Chat Upgrade
**Status:** Core STT/TTS Complete, Realtime Upgrade Outstanding
**Priority:** LOW
**Outstanding Tasks:**
- [ ] Phase 1: Whisper STT + Existing Chat + TTS
- [ ] Phase 2: WebRTC Realtime API with OpenAI speech-to-speech

### 12. Infrastructure Audit
**Status:** Partial
**Priority:** LOW
**Outstanding Tasks:**
- [ ] Add model routing metrics
- [ ] Add runner metrics
- [ ] Add token/cost tracking
- [ ] Set up Grafana queries and alerts
- [ ] Create eval packs per product area
- [ ] Add scorers and CI split
- [ ] Add failure injection switches
- [ ] Define performance targets
- [ ] Run load tests with k6

## 🏗️ Building Onboarding (Your Request)

**This is what you asked about - setting up fresh SENTINEL instances for new buildings**

### Current State
- ✅ Architectural principles established (SENTINEL-Site separation)
- ✅ Supabase consolidation complete (JSON fallbacks removed)
- ✅ Clean separation via SIMBIOT boundary
- ✅ Building operating lifecycle documented

### What's Needed for New Building Onboarding
1. **Fresh Instance Setup Script**
   - Git pull fresh SENTINEL instance
   - Install dependencies
   - Seed new Supabase instance
   - Configure for new building

2. **BMS Connection Wizard**
   - Connect to building's BMS
   - Discover equipment
   - Map to SENTINEL standards
   - Validate connectivity

3. **Onboarding Documentation**
   - Step-by-step guide for new installations
   - Checklist for commissioning
   - Troubleshooting guide

4. **Deployment Automation**
   - Single command to set up new instance
   - Configuration templates
   - Validation scripts

### Next Steps for Building Onboarding
This would be a great candidate for a new GSD edge phase. Would you like me to:
1. Create a new phase for building onboarding automation
2. Document the current manual process
3. Create scripts to automate the setup
4. Something else specific to your needs?

## 📁 Documentation Status

### Complete Documentation
- ✅ SENTINEL-Site Separation Principle
- ✅ Architecture Principles
- ✅ Building Operating Lifecycle
- ✅ SIMBIOT Concept Connector
- ✅ Supabase Performance Runbook
- ✅ Security & Compliance Documentation

### Outstanding Documentation
- [ ] Building Onboarding Guide
- [ ] 3D Model Creation Guide
- [ ] Troubleshooting Runbook
- [ ] Digital Twin Builder Documentation
- [ ] OEM Scraper Architecture
- [ ] Maintenance Records Pipeline

## 🔧 Technical Debt Summary

### High Priority Debt
1. **MCP Supabase Transaction Timeout Bug** - DML operations silently fail
2. **OEM Scraper Not Built** - Blocking document intake
3. **AEGIS Phase 0 Incomplete** - Blocking autonomous operations
4. **Domain Migration Blocked** - Need port verification

### Medium Priority Debt
1. **Digital Twin Validation Pending** - Need real floor plans
2. **Dashboard Card Merging Not Implemented** - UX enhancement
3. **Document Management Phases 2-6** - Feature completeness

### Low Priority Debt
1. **Voice Chat Realtime Upgrade** - Nice-to-have
2. **Infrastructure Audit Enhancements** - Monitoring improvements
3. **Recommendation Pipeline Tweaks** - Polish

## 🎯 Recommendation

Based on your request about setting up fresh instances for new buildings, I recommend creating a **New Building Onboarding GSD Edge Phase** that would include:

1. **Automated Setup Script** - Single command deployment
2. **Supabase Seeding** - Fresh database with building templates
3. **BMS Connection Wizard** - Guided onboarding
4. **Configuration Templates** - Quick start for common building types
5. **Validation Checklist** - Ensure everything works before handoff

Would you like me to create this phase and the associated documentation/scripts?
