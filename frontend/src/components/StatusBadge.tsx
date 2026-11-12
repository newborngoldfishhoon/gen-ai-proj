import React from 'react';
import type { RunStatus, TaskStatus } from '../types/agent';
import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  Zap,
} from 'lucide-react';

interface StatusBadgeProps {
  status: RunStatus | TaskStatus;
  size?: 'sm' | 'md';
}

const statusConfig: Record<
  string,
  { label: string; className: string; Icon: React.ElementType }
> = {
  planning: {
    label: 'Planning',
    className: 'bg-amber-500/15 text-amber-400 border border-amber-500/20',
    Icon: Zap,
  },
  pending: {
    label: 'Pending',
    className: 'bg-surface-600/30 text-surface-400 border border-surface-500/20',
    Icon: Clock,
  },
  running: {
    label: 'Running',
    className: 'bg-blue-500/15 text-blue-400 border border-blue-500/20',
    Icon: Loader2,
  },
  in_progress: {
    label: 'In Progress',
    className: 'bg-blue-500/15 text-blue-400 border border-blue-500/20',
    Icon: Loader2,
  },
  completed: {
    label: 'Completed',
    className: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20',
    Icon: CheckCircle2,
  },
  failed: {
    label: 'Failed',
    className: 'bg-red-500/15 text-red-400 border border-red-500/20',
    Icon: XCircle,
  },
};

export default function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.pending;
  const { label, className, Icon } = config;
  const isAnimated = status === 'running' || status === 'in_progress' || status === 'planning';

  return (
    <span
      className={`status-badge ${className} ${size === 'sm' ? 'text-[10px] px-2 py-0.5' : ''}`}
    >
      <Icon
        size={size === 'sm' ? 10 : 12}
        className={isAnimated ? 'animate-spin' : ''}
      />
      {label}
    </span>
  );
}
