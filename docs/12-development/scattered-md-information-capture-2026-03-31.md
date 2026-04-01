---
title: "Scattered Markdown Information Capture 2026-03-31"
type: "guide"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["documentation", "migration", "archive"]
related: ["../README.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 12
---

# Scattered markdown information capture (2026-03-31)

This document captures key information from previously scattered markdown files before archiving.
Each item includes source path, intended canonical docs target, extracted title, and a short summary.

## Captured entries

| source file | canonical target | extracted title | summary |
|---|---|---|---|
| `.deployment/MCP_ENDPOINT_WHITELIST_DEPLOYMENT.md` | `docs/10-operations/deployment/` | MCP Endpoint Authentication Whitelist Deployment | Production server (`bms.aimthelaw.co.za`) is blocking MCP endpoints with HTTP 401 Authentication Required: - `/api/mcp/sse` - Claude Desktop SSE transport - `/api/mcp/openai/mcp` - ChatGPT/M365 Copilot Streamable HTTP transport |
| `INVESTOR.md` | `docs/15-business-context/` | SENTINEL BMS: Executive Summary | **AI-Powered Facilities Management Platform** **Proven ROI • Load Shedding Optimization • Interview-Ready Demo** |
| `SPRINT0_SIGNOFF.md` | `docs/15-business-context/` | Sprint 0 Hardware Integration Sign-Off | > **Status:** PENDING ON-SITE / **Version:** v27.0 / **Site:** site-002 |
| `TESTING_GUIDE.md` | `docs/15-business-context/` | Equipment Warning State Workflow - Testing Guide | **Quick Start**: 2-3 minutes to verify complete end-to-end flow |
| `backend/CIRCULAR_IMPORTS_ANALYSIS.md` | `docs/12-development/backend/` | Circular Import Analysis | **Date:** 2026-02-09 **Phase:** 67-02 Technical Debt Remediation |
| `backend/README_MCP_INTEGRATION.md` | `docs/12-development/backend/` | SIMBIOT MCP Server Integration Guide | This guide explains how to integrate SIMBIOT MCP tools with Claude Desktop and cloud Claude. |
| `backend/app/data/concept_schema.md` | `docs/12-development/backend/` | Concept Evolution CAFM - Integration Schema | This document defines the expected data formats for Concept Evolution CAFM integration with SENTINEL. |
| `backend/app/data/rag_knowledge/sentinel_system_overview.md` | `docs/12-development/backend/` | SENTINEL BMS Intelligence Platform | SENTINEL is an AI-powered Building Management System (BMS) Intelligence Platform designed for facilities management in South Africa. It combines predictive maintenance, conversational AI, and automated device control to help facility managers proactively maintain buildings and reduce operational costs. |
| `backend/app/security/SIGNATURES.md` | `docs/12-development/backend/` | Security-Relevant Function Signatures | Reference document for the SENTINEL security module. Documents all function signatures from the 9 security-relevant source files that the security module will wrap, extend, or replace. |
| `backend/app/services/.import_analysis.md` | `docs/12-development/backend/` | Import Chain Analysis | ai_optimizer.py ├─ imports claude_service (line 35) └─ does NOT import chat_tools |
| `backend/app/services/sentry_integration/sentry_ai_bridge_integration.template.md` | `docs/12-development/backend/` | PATTERNS TO ADD TO sentry_ai_bridge.py: | """ SENTRY AI Bridge Integration for Work Orders. |
| `backend/scripts/EQUIPMENT_DIAGNOSTIC_REPORT.md` | `docs/12-development/backend/` | Equipment Data Diagnostic Report | Digital Twin and equipment discovery showing only **1 device per building** instead of 50+ expected equipment items. |
| `backend/scripts/SUPABASE_SEEDING_SUMMARY.md` | `docs/12-development/backend/` | Supabase Equipment Seeding - Completion Summary | The comprehensive seeding operation to populate Supabase with all building, equipment, and zone data from JSON files has been successfully completed. **Supabase is now the PRIMARY data source** with JSON files serving as fallback only. |
| `backend/supabase/migrations/README_20250201_DEVICES_AND_DALI.md` | `docs/12-development/backend/` | Migration 20250201: BMS Devices and DALI Lighting Integration | This migration adds comprehensive support for BMS device control and refactors the DALI lighting system to integrate with the building hierarchy. |
| `compliance.md` | `docs/15-business-context/` | SENTINEL Unified Compliance Programme | Last updated: 2026-02-23 Phase 1 status: 12 items complete / Phase 2 status: 7 items complete / Phase 3 status: 5 gate items complete (3 passed, 2 pending board decision) Scope: `/opt/bms-intelligence` (SENTINEL only) |
| `frontend/DASHBOARD_INTEGRATION_COMPLETE.md` | `docs/12-development/frontend/` | Dashboard SimulationContext Integration - Complete ✅ | **Date**: 2026-02-17 **Build Status**: ✅ Success (27.86s, 829.36 kB gzipped, 0 TS errors) |
| `frontend/FINAL_TEST_STATUS.md` | `docs/12-development/frontend/` | Final Test Suite Status - Phase 6 Completion | **Date**: February 11, 2026 **Final Pass Rate**: 509/653 (78%) **Status**: Stable and production-ready |
| `frontend/OCCUPANCY_ANALYTICS_INTEGRATION_COMPLETE.md` | `docs/12-development/frontend/` | OccupancyAnalyticsPage SimulationContext Integration - Complete ✅ | **Date**: 2026-02-17 **Build Status**: ✅ Success (30.70s, 829.63 kB gzipped, 0 TS errors) |
| `frontend/OPTIMIZATION_PAGE_FIX_SUMMARY.md` | `docs/12-development/frontend/` | OptimizationPage Test Suite Fix - Session Summary | Fix OptimizationPage tests to improve frontend test pass rate from 79.7% toward 80%+. |
| `frontend/PHASE_170_01_FRONTEND_BUILD_STATUS.md` | `docs/12-development/frontend/` | Phase 170-01: Frontend Supervised Execution Loop — BUILD COMPLETE | **Status**: ✅ COMPLETE **Date**: 2026-03-23 **Compilation**: ✅ TypeScript + Vite successful |
| `frontend/SESSION_SUMMARY_2026_02_11.md` | `docs/12-development/frontend/` | Frontend Test Suite Improvement Session Summary | **Date**: February 11, 2026 **Duration**: ~2 hours **Final Pass Rate**: 513/644 (79.7%) |
| `frontend/SOLAR_DASHBOARD_INTEGRATION_COMPLETE.md` | `docs/12-development/frontend/` | SolarDashboard SimulationContext Integration - Complete ✅ | **Date**: 2026-02-17 **Build Status**: ✅ Success (36.20s, 829.81 kB gzipped, 0 TS errors) |
| `frontend/public/docs/sentinel-equipment-reference.md` | `docs/12-development/frontend/` | SENTINEL Equipment Reference | **BMS:** Siemens Desigo CC (BACnet/IP) / **Lighting:** DALI-2 (Tridonic Scenecom) |
| `frontend/src/components/PHASE_088_MODULE_GATING_INTEGRATION.md` | `docs/12-development/frontend/` | Phase 088: Frontend Module Gating Integration | **Status**: ✅ COMPLETE / **Date**: 2026-02-15 / **Build**: ✅ SUCCESS |
| `frontend/src/lib/api/SECURITY.md` | `docs/12-development/frontend/` | API Security Guidelines (Phase 75-07) | This module implements multiple layers of protection to prevent accidental exposure of authentication tokens and sensitive data in browser console logs. |
| `frontend/src/test-utils/TESTING_GUIDE.md` | `docs/12-development/frontend/` | Frontend Testing Guide | This guide documents established patterns and best practices for testing the BMS Intelligence Platform frontend. |
| `infrastructure/bcpdr/bcp-test-plan.md` | `docs/10-operations/infrastructure/` | SENTINEL Business Continuity Plan — Test Plan | **Document Owner:** SENTINEL Platform Team **Version:** 1.0 **Created:** 2026-02-04 **Review Cycle:** Annual (after each test) **Status:** Active |
| `infrastructure/bcpdr/dr-runbook.md` | `docs/10-operations/infrastructure/` | SENTINEL Disaster Recovery Runbook | **Document Owner:** SENTINEL Platform Team **Version:** 1.0 **Created:** 2026-02-04 **Classification:** CONFIDENTIAL — Contains system access details **Review Cycle:** Annual (and after each DR event) **Status:** Active |
| `infrastructure/cloudflare/README.md` | `docs/10-operations/infrastructure/` | Cloudflare WAF Rules for SENTINEL BMS Intelligence | This directory contains WAF (Web Application Firewall) rule definitions for SENTINEL web endpoints. Rules are applied via the Cloudflare Dashboard or API -- they are not automated in Docker. |
| `infrastructure/pam/access-matrix.md` | `docs/10-operations/infrastructure/` | SENTINEL Access Control Matrix | **Document:** Privileged Access Management (PAM) - Access Matrix **FSR Domain:** 4.7 - Logical Access Control **Last Updated:** 2026-02-04 **Review Cadence:** Monthly (access review), Quarterly (privileged accounts) |
| `infrastructure/scanning/README.md` | `docs/10-operations/infrastructure/` | Vulnerability Scanning Infrastructure | SENTINEL BMS Intelligence Platform - Operational vulnerability scanning for FSR domain 4.10 compliance. |
| `infrastructure/scanning/remediation-tracker.md` | `docs/10-operations/infrastructure/` | Vulnerability Remediation Tracker | SENTINEL BMS Intelligence Platform - FSR Domain 4.10 Compliance |
| `infrastructure/training/security-awareness-plan.md` | `docs/10-operations/infrastructure/` | SENTINEL Security Awareness Training Programme | **Document Owner:** SENTINEL Platform Team **Version:** 1.0 **Created:** 2026-02-04 **Review Cycle:** Annual **Status:** Active |
| `infrastructure/training/training-register.md` | `docs/10-operations/infrastructure/` | SENTINEL Security Awareness Training Register | **Document Owner:** SENTINEL Platform Team **Version:** 1.0 **Created:** 2026-02-04 **Status:** Active |
| `supabase/migrations/023_pgvector_rag_schema_DESIGN.md` | `docs/07-database/supabase/` | pgvector RAG Schema Design Documentation | **Migration:** 023_pgvector_rag_schema.sql **Phase:** 44 - Local LLM Integration (RAG System) **Database:** Supabase PostgreSQL with pgvector extension **Created:** 2026-02-01 |
| `supabase/migrations/023_pgvector_rag_schema_DIAGRAM.md` | `docs/07-database/supabase/` | pgvector RAG Schema - Entity Relationship Diagram | ┌─────────────────────────────────────────────────────────────────────────┐ │ RAG SCHEMA OVERVIEW │ └─────────────────────────────────────────────────────────────────────────┘ |
| `supabase/migrations/023_pgvector_rag_schema_QUICKSTART.md` | `docs/07-database/supabase/` | pgvector RAG Schema - Quick Start Guide | **For Developers:** Quick reference for implementing RAG services with the pgvector schema. |

| `frontend/src/components/README_ENERGY_COMPARISON.md` | `docs/12-development/frontend/` | Missing source during capture | File listed in plan but not present in working tree at execution time. |
