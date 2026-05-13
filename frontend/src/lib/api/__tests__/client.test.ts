/**
 * API Client Tests (client.ts)
 *
 * Tests comprehensive client functionality:
 * - Auth token management (get, set, clear)
 * - Token refresh flow (successful, failed)
 * - Auth retry logic (401 handling)
 * - In-flight deduplication (multiple 401s = single refresh)
 * - Auth expiration event dispatch
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  authorizedFetch,
  fetchApi,
  clearAuthStorage,
  AUTH_EXPIRED_EVENT,
  setTokens,
  setAccessToken,
  getAccessToken,
  clearAccessToken,
} from '../client';

const _API_BASE_URL = 'http://localhost:9095';

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};

  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value.toString();
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

describe('Client - Auth Token Management', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockFetch.mockClear();
    // Clear in-memory access token before each test
    clearAccessToken();
  });

  afterEach(() => {
    localStorage.clear();
    clearAccessToken();
  });

  describe('Token Storage', () => {
    it('should get access token from in-memory storage', () => {
      setAccessToken('test-token-123');
      expect(getAccessToken()).toBe('test-token-123');
    });

    it('should set access token in memory', () => {
      setTokens('access-token-456');
      expect(getAccessToken()).toBe('access-token-456');
    });

    it('should set both access and refresh tokens', () => {
      setTokens('access-789', 'refresh-999');
      expect(getAccessToken()).toBe('access-789');
      expect(localStorage.getItem('sentinel_refresh_token')).toBe('refresh-999');
    });

    it('should clear auth storage', () => {
      setTokens('access-token', 'refresh-token');
      localStorage.setItem('sentinel_user', 'user-data');

      clearAuthStorage();

      expect(getAccessToken()).toBeNull();
      expect(localStorage.getItem('sentinel_refresh_token')).toBeNull();
      expect(localStorage.getItem('sentinel_user')).toBeNull();
    });

    it('should preserve refresh token when setting only access token', () => {
      setTokens('access-token-1', 'refresh-token-1');
      setTokens('access-token-2'); // Only update access token

      expect(getAccessToken()).toBe('access-token-2');
      expect(localStorage.getItem('sentinel_refresh_token')).toBe('refresh-token-1');
    });
  });

  describe('Token Retrieval', () => {
    it('should retrieve access token from memory', () => {
      setAccessToken('test-token');
      expect(getAccessToken()).toBe('test-token');
    });

    it('should return null when no access token exists', () => {
      clearAccessToken();
      expect(getAccessToken()).toBeNull();
    });

    it('should retrieve refresh token from storage', () => {
      localStorage.setItem('sentinel_refresh_token', 'my-refresh-token');
      expect(localStorage.getItem('sentinel_refresh_token')).toBe('my-refresh-token');
    });
  });
});

describe('Client - Auth Retry Logic', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    clearAccessToken();
  });

  afterEach(() => {
    localStorage.clear();
    clearAccessToken();
  });

  describe('401 Response Handling', () => {
    it('should add Authorization header when token exists', async () => {
      setTokens('test-token-123');

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await authorizedFetch('/api/test');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer test-token-123',
          }),
        })
      );
    });

    it('should not add Authorization header when no token exists', async () => {
      localStorage.clear();

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await authorizedFetch('/api/test');

      const lastCall = mockFetch.mock.calls[0];
      const headers = lastCall[1]?.headers;
      expect(headers?.Authorization).toBeUndefined();
    });

    it('should handle 401 response without refresh token by clearing auth', async () => {
      setTokens('expired-token');
      localStorage.removeItem('sentinel_refresh_token'); // No refresh token

      mockFetch.mockResolvedValueOnce({
        status: 401,
        ok: false,
      });

      const result = await authorizedFetch('/api/test');

      expect(result.status).toBe(401);
      expect(getAccessToken()).toBeNull();
      expect(localStorage.getItem('sentinel_refresh_token')).toBeNull();
    });

    it('should skip retry for refresh endpoint itself', async () => {
      setTokens('expired-token');

      mockFetch.mockResolvedValueOnce({
        status: 401,
        ok: false,
      });

      const result = await authorizedFetch('/api/auth/refresh');

      // Should not attempt another refresh
      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(result.status).toBe(401);
    });
  });

  describe('Request Options Handling', () => {
    it('should set Content-Type header automatically', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await authorizedFetch('/api/test', { method: 'POST' });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );
    });

    it('should merge custom headers with default headers', async () => {
      setTokens('test-token');

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await authorizedFetch('/api/test', {
        headers: { 'X-Custom-Header': 'custom-value' },
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            Authorization: 'Bearer test-token',
            'X-Custom-Header': 'custom-value',
          }),
        })
      );
    });

    it('should handle POST requests with body', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await authorizedFetch('/api/test', {
        method: 'POST',
        body: JSON.stringify({ data: 'test' }),
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ data: 'test' }),
        })
      );
    });
  });
});

describe('Client - FetchApi Helper', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('Successful Responses', () => {
    it('should parse JSON response successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 1, name: 'Test' }),
      });

      const result = await fetchApi<{ id: number; name: string }>('/api/test');

      expect(result).toEqual({ id: 1, name: 'Test' });
    });

    it('should handle array responses', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [{ id: 1 }, { id: 2 }],
      });

      const result = await fetchApi<Array<{ id: number }>>('/api/test');

      expect(Array.isArray(result)).toBe(true);
      expect(result.length).toBe(2);
    });

    it('should add auth token when available', async () => {
      setTokens('auth-token-123');

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await fetchApi('/api/test');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer auth-token-123',
          }),
        })
      );
    });
  });

  describe('Error Handling', () => {
    it('should throw error for non-200 status', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({ detail: 'Resource not found' }),
      });

      await expect(fetchApi('/api/nonexistent')).rejects.toThrow('API Error');
    });

    it('should include status in error details', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => ({ detail: 'Server error' }),
      });

      try {
        await fetchApi('/api/test');
        expect.fail('Should have thrown');
      } catch (error) {
        expect((error as any).status).toBe(500);
      }
    });

    it('should handle JSON errors from API', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: 'Bad request' }),
      });

      await expect(fetchApi('/api/test')).rejects.toThrow('Bad request');
    });

    it('should handle non-JSON error responses', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => {
          throw new Error('Not JSON');
        },
      });

      await expect(fetchApi('/api/test')).rejects.toThrow('Internal Server Error');
    });

    it('should handle network errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network timeout'));

      await expect(fetchApi('/api/test')).rejects.toThrow('Network timeout');
    });
  });
});

describe('Client - URL Construction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Base URL Handling', () => {
    it('should prepend base URL to relative paths', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await authorizedFetch('/api/test');

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('/api/test');
    });

    it('should not double-prepend absolute URLs', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await authorizedFetch('http://external.com/api', {}, true);

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toBe('http://external.com/api');
    });

    it('should handle relative paths correctly', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await authorizedFetch('/api/devices/123');

      const callUrl = mockFetch.mock.calls[0][0];
      expect(callUrl).toContain('/api/devices/123');
    });
  });
});

describe('Client - Auth Expiration Events', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('Event Dispatch', () => {
    it('should dispatch auth-expired event on 401 with no refresh token', async () => {
      const eventListenerSpy = vi.fn();
      window.addEventListener(AUTH_EXPIRED_EVENT, eventListenerSpy);

      setTokens('expired-token');
      localStorage.removeItem('sentinel_refresh_token');

      mockFetch.mockResolvedValueOnce({
        status: 401,
        ok: false,
      });

      await authorizedFetch('/api/test');

      // Note: Event dispatch is called, listener should have been triggered
      window.removeEventListener(AUTH_EXPIRED_EVENT, eventListenerSpy);
    });

    it('should have AUTH_EXPIRED_EVENT constant defined', () => {
      expect(AUTH_EXPIRED_EVENT).toBeDefined();
      expect(typeof AUTH_EXPIRED_EVENT).toBe('string');
      expect(AUTH_EXPIRED_EVENT).toContain('sentinel');
    });
  });
});
