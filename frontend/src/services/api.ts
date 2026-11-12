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

const API_BASE = '/api';

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

  try {
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
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
    throw new ApiError(
      error instanceof Error ? error.message : 'Network error',
      0
    );
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
};

export { ApiError };
export default api;
