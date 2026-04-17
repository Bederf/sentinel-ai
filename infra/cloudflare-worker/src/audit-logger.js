/**
 * Legal Compliance Audit Logger
 * Tracks all sensitive data access for attorney-client privilege protection
 */

export class AuditLogger {
  constructor(env) {
    this.database = env.MY_APP_DATABASE;
  }

  async logAccess(request, response, userId = null) {
    const url = new URL(request.url);
    const sensitiveEndpoints = ['/api/clients', '/api/cases', '/api/documents'];

    // Only log sensitive endpoints
    if (!sensitiveEndpoints.some(ep => url.pathname.startsWith(ep))) {
      return;
    }

    const auditEntry = {
      timestamp: new Date().toISOString(),
      method: request.method,
      endpoint: url.pathname,
      status: response.status,
      clientIp: request.headers.get('CF-Connecting-IP'),
      userAgent: request.headers.get('User-Agent'),
      userId: userId || this.extractUserId(request),
      country: request.cf?.country || 'unknown',
      // Attorney-client privilege marker
      privileged: url.pathname.includes('/clients/') || url.pathname.includes('/cases/'),
      // Data classification
      classification: this.getDataClassification(url.pathname)
    };

    try {
      // Store in D1 database
      await this.database.prepare(`
        INSERT INTO audit_logs
        (timestamp, method, endpoint, status, client_ip, user_id, country, privileged, classification)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).bind(
        auditEntry.timestamp,
        auditEntry.method,
        auditEntry.endpoint,
        auditEntry.status,
        auditEntry.clientIp,
        auditEntry.userId,
        auditEntry.country,
        auditEntry.privileged,
        auditEntry.classification
      ).run();

      // Alert on suspicious activity
      if (this.isSuspicious(auditEntry)) {
        await this.alertSecurity(auditEntry);
      }
    } catch (error) {
      console.error('Audit logging failed:', error);
      // Never fail the request due to logging issues
    }
  }

  extractUserId(request) {
    // Extract user ID from JWT or session
    const auth = request.headers.get('Authorization');
    if (auth && auth.startsWith('Bearer ')) {
      try {
        // Decode JWT (simplified - use proper library in production)
        const token = auth.substring(7);
        const payload = JSON.parse(atob(token.split('.')[1]));
        return payload.sub || payload.user_id;
      } catch {
        return null;
      }
    }
    return null;
  }

  getDataClassification(pathname) {
    if (pathname.includes('/clients/') || pathname.includes('/cases/')) {
      return 'LEGAL-CONFIDENTIAL';
    }
    if (pathname.includes('/documents/')) {
      return 'PRIVILEGED';
    }
    if (pathname.includes('/billing/') || pathname.includes('/invoices/')) {
      return 'FINANCIAL-SENSITIVE';
    }
    return 'INTERNAL';
  }

  isSuspicious(entry) {
    // Detect suspicious patterns
    return (
      entry.status >= 400 ||                           // Failed requests
      entry.country in ['CN', 'RU', 'KP'] ||          // High-risk countries
      entry.endpoint.includes('/export') ||            // Data export attempts
      entry.method === 'DELETE'                        // Deletion attempts
    );
  }

  async alertSecurity(entry) {
    // Send alert to security team (implement based on your notification system)
    console.warn('🚨 SECURITY ALERT:', entry);
    // Could integrate with email, Slack, or SMS alerts
  }
}

// Create the audit table in D1
const CREATE_AUDIT_TABLE = `
CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp DATETIME NOT NULL,
  method VARCHAR(10) NOT NULL,
  endpoint VARCHAR(255) NOT NULL,
  status INTEGER NOT NULL,
  client_ip VARCHAR(45),
  user_id VARCHAR(100),
  country VARCHAR(2),
  privileged BOOLEAN DEFAULT FALSE,
  classification VARCHAR(50),
  INDEX idx_timestamp (timestamp),
  INDEX idx_user_id (user_id),
  INDEX idx_privileged (privileged)
);
`;
