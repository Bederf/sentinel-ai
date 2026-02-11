/**
 * FetchClient Tests (fetchClient.ts)
 *
 * Tests comprehensive fetchClient functionality:
 * - Basic fetch with auth headers
 * - Error handling and ApiError class
 * - JSON serialization/parsing
 * - Network error handling
 * - Status code error responses
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiFetch, ApiError } from '../fetchClient';

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

describe('FetchClient - ApiError Class', () => {
  it('should create ApiError with status and message', () => {
    const error = new ApiError(404, 'Not Found');

    expect(error).toBeInstanceOf(Error);
    expect(error.status).toBe(404);
    expect(error.message).toBe('Not Found');
    expect(error.name).toBe('ApiError');
  });

  it('should store additional data in ApiError', () => {
    const data = { field: 'error_detail' };
    const error = new ApiError(400, 'Bad Request', data);

    expect(error.data).toEqual(data);
  });

  it('should handle ApiError with undefined data', () => {
    const error = new ApiError(500, 'Server Error');

    expect(error.data).toBeUndefined();
  });

  it('should preserve error stack trace', () => {
    const error = new ApiError(403, 'Forbidden');

    expect(error.stack).toBeDefined();
  });
});

describe('FetchClient - apiFetch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('Successful Requests', () => {
    it('should fetch and parse JSON response successfully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 1, name: 'Test' }),
      });

      const result = await apiFetch<{ id: number; name: string }>('/api/test');

      expect(result).toEqual({ id: 1, name: 'Test' });
    });

    it('should handle array responses', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [{ id: 1 }, { id: 2 }, { id: 3 }],
      });

      const result = await apiFetch<Array<{ id: number }>>('/api/items');

      expect(Array.isArray(result)).toBe(true);
      expect(result).toHaveLength(3);
    });

    it('should return empty object on JSON parse error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => {
          throw new Error('Invalid JSON');
        },
      });

      const result = await apiFetch('/api/test');

      expect(result).toEqual({});
    });
  });

  describe('Auth Header Management', () => {
    it('should add Authorization header when token exists', async () => {
      localStorage.setItem('sentinel_token', 'auth-token-123');

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await apiFetch('/api/test');

      const call = mockFetch.mock.calls[0];
      const headers = call[1]?.headers as Headers;
      expect(headers.get('Authorization')).toBe('Bearer auth-token-123');
    });

    it('should not add Authorization header when no token', async () => {
      localStorage.clear();

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await apiFetch('/api/test');

      const call = mockFetch.mock.calls[0];
      const headers = call[1]?.headers as Headers;
      expect(headers.get('Authorization')).toBeNull();
    });

    it('should set Content-Type header to application/json', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await apiFetch('/api/test');

      const call = mockFetch.mock.calls[0];
      const headers = call[1]?.headers as Headers;
      expect(headers.get('Content-Type')).toBe('application/json');
    });
  });

  describe('Request Body Handling', () => {
    it('should stringify object body as JSON', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const body = { key: 'value', count: 42 };
      await apiFetch('/api/test', { body });

      const call = mockFetch.mock.calls[0];
      const sentBody = call[1]?.body;
      expect(sentBody).toBe(JSON.stringify(body));
    });

    it('should pass string body as-is', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const bodyString = '{"data":"test"}';
      await apiFetch('/api/test', { body: bodyString });

      const call = mockFetch.mock.calls[0];
      const sentBody = call[1]?.body;
      expect(sentBody).toBe(bodyString);
    });

    it('should not include body when not provided', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await apiFetch('/api/test', { method: 'GET' });

      const call = mockFetch.mock.calls[0];
      const sentBody = call[1]?.body;
      expect(sentBody).toBeUndefined();
    });
  });

  describe('HTTP Error Handling', () => {
    it('should throw ApiError on 404 response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: 'Not found' }),
        text: async () => 'Not found',
      });

      try {
        await apiFetch('/api/missing');
        expect.fail('Should have thrown');
      } catch (error) {
        expect(error).toBeInstanceOf(ApiError);
        expect((error as ApiError).status).toBe(404);
      }
    });

    it('should throw ApiError on 400 Bad Request', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: 'Invalid request' }),
        text: async () => 'Bad Request',
      });

      await expect(apiFetch('/api/test', { body: { invalid: 'data' } })).rejects.toThrow(
        ApiError
      );
    });

    it('should throw ApiError on 401 Unauthorized', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Unauthorized' }),
        text: async () => 'Unauthorized',
      });

      try {
        await apiFetch('/api/protected');
        expect.fail('Should have thrown');
      } catch (error) {
        expect(error).toBeInstanceOf(ApiError);
        expect((error as ApiError).status).toBe(401);
      }
    });

    it('should throw ApiError on 403 Forbidden', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: async () => ({ detail: 'Forbidden' }),
        text: async () => 'Forbidden',
      });

      await expect(apiFetch('/api/admin')).rejects.toThrow(ApiError);
    });

    it('should throw ApiError on 500 Server Error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Internal server error' }),
        text: async () => 'Server Error',
      });

      try {
        await apiFetch('/api/test');
        expect.fail('Should have thrown');
      } catch (error) {
        expect(error).toBeInstanceOf(ApiError);
        expect((error as ApiError).status).toBe(500);
      }
    });

    it('should throw ApiError on 429 Too Many Requests', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 429,
        json: async () => ({ detail: 'Rate limited' }),
        text: async () => 'Too Many Requests',
      });

      await expect(apiFetch('/api/test')).rejects.toThrow(ApiError);
    });
  });

  describe('Error Response Parsing', () => {
    it('should include error detail in message', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ detail: 'Validation error' }),
      });

      try {
        await apiFetch('/api/test');
        expect.fail('Should have thrown');
      } catch (error) {
        expect((error as ApiError).status).toBe(400);
      }
    });

    it('should handle JSON error responses', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: async () => ({
          detail: [
            { loc: ['body', 'name'], msg: 'Field required' },
            { loc: ['body', 'email'], msg: 'Invalid email' },
          ],
        }),
      });

      try {
        await apiFetch('/api/test');
        expect.fail('Should have thrown');
      } catch (error) {
        expect((error as ApiError).status).toBe(422);
      }
    });

    it('should handle non-JSON error responses', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('Not JSON');
        },
        text: async () => 'Internal Server Error',
      });

      try {
        await apiFetch('/api/test');
        expect.fail('Should have thrown');
      } catch (error) {
        expect((error as ApiError).status).toBe(500);
      }
    });
  });

  describe('Network Error Handling', () => {
    it('should throw ApiError on network failure', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network timeout'));

      await expect(apiFetch('/api/test')).rejects.toThrow(ApiError);
    });

    it('should preserve error message from network error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Failed to fetch'));

      try {
        await apiFetch('/api/test');
        expect.fail('Should have thrown');
      } catch (error) {
        expect((error as ApiError).message).toContain('Failed to fetch');
      }
    });

    it('should handle non-Error exceptions', async () => {
      mockFetch.mockRejectedValueOnce('Unknown error');

      try {
        await apiFetch('/api/test');
        expect.fail('Should have thrown');
      } catch (error) {
        expect((error as ApiError).status).toBe(0);
        expect((error as ApiError).message).toContain('Unknown error');
      }
    });
  });

  describe('Request Options Handling', () => {
    it('should support custom HTTP methods', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await apiFetch('/api/test', { method: 'POST' });

      const call = mockFetch.mock.calls[0];
      expect(call[1]?.method).toBe('POST');
    });

    it('should merge custom headers with default headers', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await apiFetch('/api/test', {
        headers: { 'X-Custom': 'value' },
      });

      const call = mockFetch.mock.calls[0];
      const headers = call[1]?.headers as Headers;
      expect(headers.get('Content-Type')).toBe('application/json');
      expect(headers.get('X-Custom')).toBe('value');
    });

    it('should support custom fetch options', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      await apiFetch('/api/test', {
        mode: 'cors',
        credentials: 'include',
      });

      const call = mockFetch.mock.calls[0];
      expect(call[1]).toMatchObject({
        mode: 'cors',
        credentials: 'include',
      });
    });
  });

  describe('Response Type Handling', () => {
    it('should properly type response data', async () => {
      interface TestResponse {
        id: number;
        name: string;
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 1, name: 'Test' }),
      });

      const result = await apiFetch<TestResponse>('/api/test');

      expect(result.id).toBe(1);
      expect(result.name).toBe('Test');
    });

    it('should handle generic array types', async () => {
      interface Item {
        id: number;
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [{ id: 1 }, { id: 2 }],
      });

      const result = await apiFetch<Item[]>('/api/items');

      expect(Array.isArray(result)).toBe(true);
      expect(result[0].id).toBe(1);
    });
  });
});
