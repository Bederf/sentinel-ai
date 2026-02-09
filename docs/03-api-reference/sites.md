
## Province Requirement

`POST /api/sites` requires `region` (province). If omitted or blank, the API returns 400.

## Automatic Municipal Tariff Setup

When a site is created (Supabase enabled), the system auto-seeds:
- A default municipal tariff schedule based on `region`
- A municipal account for electricity billing

This ensures municipal billing is usable immediately after onboarding.
