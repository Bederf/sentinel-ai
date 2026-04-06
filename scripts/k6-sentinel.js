import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = 'http://localhost:9095';
const SITE_ID = 'd73a5a5f-6de5-4081-8c46-411954013156';

// Single login at start - token reused across all VUs
const ACCESS_TOKEN = __ENV.ACCESS_TOKEN || '';

export const options = {
  stages: [
    { duration: '30s', target: 5 },
    { duration: '1m', target: 5 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    'http_req_failed{name:auth}': [],  // informational only
    'http_req_failed{name:api}': ['rate<0.05'],
    'http_req_duration{name:api}': ['p(95)<500'],
  },
};

export default function () {
  const headers = {
    'Authorization': `Bearer ${ACCESS_TOKEN}`,
    'Content-Type': 'application/json',
  };

  const r1 = http.get(`${BASE}/api/sites`, { headers, tags: { name: 'api' } });
  check(r1, { 'sites 200': (r) => r.status === 200 });

  const r2 = http.get(`${BASE}/api/buildings/${SITE_ID}/equipment`, { headers, tags: { name: 'api' } });
  check(r2, { 'equipment 200': (r) => r.status === 200 });

  const r3 = http.get(`${BASE}/api/digital-twin/stub-config?site_code=site-002&site_name=Sandton`, { headers, tags: { name: 'api' } });
  check(r3, { 'stub 200': (r) => r.status === 200 });

  const r4 = http.get(`${BASE}/api/cockpit/decision/S002`, { headers, tags: { name: 'api' } });
  check(r4, { 'cockpit 200/404': (r) => r.status === 200 || r.status === 404 });

  sleep(1);
}