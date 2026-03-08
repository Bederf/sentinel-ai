/**
 * Vitest setup file
 * Runs before all tests to configure the test environment
 */

import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// Cleanup after each test
afterEach(() => {
  cleanup();
});

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver as a proper class (required by @dnd-kit/core)
class ResizeObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  constructor(_callback: ResizeObserverCallback) {}
}
global.ResizeObserver = ResizeObserverMock;

// Mock IntersectionObserver as a proper class
class IntersectionObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  root = null;
  rootMargin = '';
  thresholds = [];
  takeRecords = vi.fn().mockReturnValue([]);
  constructor(_callback: IntersectionObserverCallback, _options?: IntersectionObserverInit) {}
}
global.IntersectionObserver = IntersectionObserverMock;

// Mock EventSource for SSE testing
let mockEventSourceInstance: any = null;

class EventSourceMock {
  url: string;
  readyState: number;
  CONNECTING = 0;
  OPEN = 1;
  CLOSED = 2;

  private listeners: Map<string, Set<EventListener>> = new Map();

  onopen: ((this: EventSource, ev: Event) => any) | null = null;
  onerror: ((this: EventSource, ev: Event) => any) | null = null;
  onmessage: ((this: EventSource, ev: MessageEvent) => any) | null = null;

  constructor(url: string) {
    this.url = url;
    this.readyState = 0; // CONNECTING
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    mockEventSourceInstance = this;

    // Simulate opening connection on next tick
    Promise.resolve().then(() => {
      this.readyState = 1; // OPEN
      this.__dispatchOpen();
    });
  }

  addEventListener(type: string, listener: EventListener): void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: EventListener): void {
    if (!this.listeners.has(type)) return;
    this.listeners.get(type)!.delete(listener);
  }

  close(): void {
    this.readyState = 2; // CLOSED
    this.listeners.clear();
  }

  // Test helper methods
  __dispatchMessage(data: string): void {
    const messageEvent = new MessageEvent('message', { data });
    this.listeners.get('message')?.forEach(listener => listener(messageEvent));
    if (this.onmessage) {
      this.onmessage(messageEvent);
    }
  }

  __dispatchError(error?: Event): void {
    const errorEvent = error || new Event('error');
    this.listeners.get('error')?.forEach(listener => listener(errorEvent));
    if (this.onerror) {
      this.onerror(errorEvent);
    }
  }

  private __dispatchOpen(): void {
    const openEvent = new Event('open');
    this.listeners.get('open')?.forEach(listener => listener(openEvent));
    if (this.onopen) {
      this.onopen(openEvent);
    }
  }
}

// Override EventSource globally
(global as any).EventSource = EventSourceMock;
(global as any).__getMockEventSourceInstance = () => mockEventSourceInstance;
