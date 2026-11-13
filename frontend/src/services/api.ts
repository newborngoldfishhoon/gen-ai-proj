/**
 * API service layer — all backend communication in one place.
 */

import type {
  AgentRun,
  HealthResponse,
  RunCreatedResponse,
  RunListResponse,
  ToolCall,
  Source,
} from '../types/agent';
import { getRequestAuthHeaders } from '../lib/supabase';

const API_BASE = '/api';
const REQUEST_TIMEOUT_MS = 15_000;
const PDF_EXPORT_TIMEOUT_MS = 60_000;

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    REQUEST_TIMEOUT_MS
  );

  try {
    const authHeaders = await getRequestAuthHeaders();
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
        ...options?.headers,
      },
      ...options,
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = `Request failed with status ${response.status}`;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch {
        // ignore parse error
      }
      throw new ApiError(detail, response.status);
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) {
      throw new ApiError(
        'The backend did not respond in time. Check that it is running, then try again.',
        0
      );
    }
    throw new ApiError(
      error instanceof Error ? error.message : 'Network error',
      0
    );
  } finally {
    window.clearTimeout(timeoutId);
  }
}

/** API service methods */
export const api = {
  /** Health check */
  health(): Promise<HealthResponse> {
    return request<HealthResponse>('/health');
  },

  /** Create a new agent run */
  createRun(goal: string): Promise<RunCreatedResponse> {
    return request<RunCreatedResponse>('/runs', {
      method: 'POST',
      body: JSON.stringify({ goal }),
    });
  },

  /** Retry a failed run by creating a new run with the same goal */
  retryRun(runId: string): Promise<RunCreatedResponse> {
    return request<RunCreatedResponse>(`/runs/${runId}/retry`, {
      method: 'POST',
    });
  },

  /** List recent runs */
  listRuns(limit = 20, offset = 0): Promise<RunListResponse> {
    return request<RunListResponse>(`/runs?limit=${limit}&offset=${offset}`);
  },

  /** Get run details (includes tasks, tool calls, and sources) */
  getRun(runId: string): Promise<AgentRun> {
    return request<AgentRun>(`/runs/${runId}`);
  },

  /** Get recorded tool calls for a run */
  getRunTools(runId: string): Promise<ToolCall[]> {
    return request<ToolCall[]>(`/runs/${runId}/tools`);
  },

  /** Get recorded sources for a run */
  getRunSources(runId: string): Promise<Source[]> {
    return request<Source[]>(`/runs/${runId}/sources`);
  },

  /** Render the browser-styled report as a PDF through the backend. */
  async exportRunPdf(runId: string, html: string): Promise<Blob> {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(
      () => controller.abort(),
      PDF_EXPORT_TIMEOUT_MS,
    );
    try {
      const authHeaders = await getRequestAuthHeaders();
      const response = await fetch(`${API_BASE}/runs/${runId}/pdf`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders,
        },
        body: JSON.stringify({ html }),
        signal: controller.signal,
      });
      if (!response.ok) {
        let detail = `PDF export failed with status ${response.status}`;
        try {
          const body = await response.json();
          detail = body.detail || detail;
        } catch {
          // Keep the HTTP status message if the server response is not JSON.
        }
        throw new ApiError(detail, response.status);
      }
      if (!response.headers.get('content-type')?.includes('application/pdf')) {
        throw new ApiError('The backend did not return a PDF document.', response.status);
      }
      return await response.blob();
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (controller.signal.aborted) {
        throw new ApiError('PDF export timed out. Please try again.', 0);
      }
      throw new ApiError(
        error instanceof Error ? error.message : 'PDF export failed.',
        0,
      );
    } finally {
      window.clearTimeout(timeoutId);
    }
  },
};

export { ApiError };
export default api;
