import React, { useState } from 'react';
import { Send, Sparkles } from 'lucide-react';

interface GoalInputProps {
  onSubmit: (goal: string) => void;
  isLoading: boolean;
}

const EXAMPLE_GOALS = [
  'Research five software engineering internships suitable for a second-year BTech student with Python and web development skills. Find the eligibility requirements, application deadlines, company details, and application links. Compare the opportunities and create a report with sources.',
  'Research the top 5 programming languages for AI development and compare their strengths with live documentation sources',
  'Compare microservices vs monolithic architecture costs for a 50k DAU SaaS startup, calculating infrastructure estimates',
  'Develop a go-to-market content strategy for launching a new developer tooling product',
];

export default function GoalInput({ onSubmit, isLoading }: GoalInputProps) {
  const [goal, setGoal] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = goal.trim();

    if (!trimmed) {
      setError('Please enter a goal for the agent.');
      return;
    }
    if (trimmed.length > 2000) {
      setError('Goal must be 2000 characters or fewer.');
      return;
    }

    setError('');
    onSubmit(trimmed);
  };

  const handleExampleClick = (example: string) => {
    setGoal(example);
    setError('');
  };

  return (
    <div className="glass-card p-6 md:p-8 animate-fade-in">
      <form onSubmit={handleSubmit}>
        <div className="flex items-center gap-2 mb-4">
          <Sparkles size={20} className="text-brand-400" />
          <h2 className="text-lg font-semibold text-surface-100">
            What would you like the agent to accomplish?
          </h2>
        </div>

        <textarea
          id="goal-input"
          value={goal}
          onChange={(e) => {
            setGoal(e.target.value);
            if (error) setError('');
          }}
          placeholder="Describe your goal in detail. The agent will create a plan and execute it step by step..."
          className="input-field min-h-[120px] mb-1 font-normal text-[15px] leading-relaxed"
          disabled={isLoading}
          maxLength={2000}
        />

        <div className="flex items-center justify-between mb-4">
          <span className="text-xs text-surface-500">
            {goal.length}/2000 characters
          </span>
          {error && (
            <span className="text-xs text-red-400">{error}</span>
          )}
        </div>

        <button
          id="run-agent-btn"
          type="submit"
          disabled={isLoading || !goal.trim()}
          className="btn-primary w-full text-base"
        >
          {isLoading ? (
            <>
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" className="opacity-75" />
              </svg>
              Agent Working...
            </>
          ) : (
            <>
              <Send size={18} />
              Run Agent
            </>
          )}
        </button>
      </form>

      {/* Example goals */}
      <div className="mt-6 pt-5 border-t border-surface-700/50">
        <p className="text-xs font-medium text-surface-500 uppercase tracking-wider mb-3">
          Example goals
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {EXAMPLE_GOALS.map((example, i) => (
            <button
              key={i}
              id={`example-goal-${i}`}
              onClick={() => handleExampleClick(example)}
              disabled={isLoading}
              className="text-left text-sm text-surface-400 hover:text-surface-200 p-3 rounded-lg
                         hover:bg-surface-700/30 transition-all duration-200 border border-transparent
                         hover:border-surface-600/30 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
