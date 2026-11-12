/**
 * TypeScript types mirroring the backend API schemas for Phase 2.
 */

export type RunStatus = 'planning' | 'running' | 'completed' | 'failed';
export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'failed';
export type ToolCallStatus = 'pending' | 'running' | 'completed' | 'failed';
export type ExtractionStatus = 'snippet_only' | 'extracted' | 'failed';

export interface ToolCall {
  id: string;
  run_id: string;
  task_id: string;
  tool_name: string;
  arguments: string;
  status: ToolCallStatus;
  result_summary: string | null;
  result_data: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface Source {
  id: string;
  run_id: string;
  task_id: string | null;
  tool_call_id: string | null;
  title: string;
  url: string;
  domain: string;
  snippet: string | null;
  extracted_content: string | null;
  extraction_status: ExtractionStatus;
  created_at: string;
}

export interface AgentTask {
  id: string;
  run_id: string;
  title: string;
  description: string;
  order_index: number;
  status: TaskStatus;
  result: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  tool_calls?: ToolCall[];
}

export interface AgentRun {
  id: string;
  goal: string;
  status: RunStatus;
  final_report: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  tasks: AgentTask[];
  tool_calls: ToolCall[];
  sources: Source[];
}

export interface RunListItem {
  id: string;
  goal: string;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  task_count: number;
  completed_task_count: number;
  tool_call_count?: number;
  source_count?: number;
}

export interface RunListResponse {
  runs: RunListItem[];
  total: number;
}

export interface RunCreatedResponse {
  id: string;
  status: string;
  message: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}
