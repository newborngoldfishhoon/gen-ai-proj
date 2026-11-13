import { useMemo, useState } from 'react';
import type { Source, TaskStatus } from '../types/agent';
import {
  ArrowUpRight,
  BookOpen,
  BriefcaseBusiness,
  GraduationCap,
  Inbox,
  LoaderCircle,
  PlayCircle,
  Sparkles,
} from 'lucide-react';

export type ResourceCategory = 'Tutorials & videos' | 'Courses' | 'Jobs & applications' | 'Trending' | 'Other';
type ResourceFilter = 'All' | ResourceCategory;

interface ResourcePanelProps {
  sources: Source[];
  taskStatus?: TaskStatus;
  printable?: boolean;
  exportTarget?: boolean;
}

export function getCategory(source: Source): ResourceCategory {
  const text = `${source.title} ${source.snippet || ''} ${source.domain} ${source.url}`.toLowerCase();
  if (/\b(job|jobs|career|careers|internship|intern|apply|application|applications|hiring)\b/.test(text)) {
    return 'Jobs & applications';
  }
  if (/\b(course|courses|coursera|edx|udemy|class|curriculum|certification|training)\b/.test(text)) {
    return 'Courses';
  }
  if (/\b(youtube|youtu\.be|video|videos|tutorial|playlist|walkthrough)\b/.test(text)) {
    return 'Tutorials & videos';
  }
  if (/\b(trending|trend|latest|new release|recent|202[5-9])\b/.test(text)) {
    return 'Trending';
  }
  return 'Other';
}

const categoryStyles: Record<ResourceCategory, string> = {
  'Tutorials & videos': 'bg-violet-500/10 text-violet-200 border-violet-400/20',
  Courses: 'bg-blue-500/10 text-blue-200 border-blue-400/20',
  'Jobs & applications': 'bg-emerald-500/10 text-emerald-200 border-emerald-400/20',
  Trending: 'bg-amber-500/10 text-amber-200 border-amber-400/20',
  Other: 'bg-surface-700/60 text-surface-300 border-surface-600/40',
};

function CategoryIcon({ category }: { category: ResourceCategory }) {
  const iconProps = { size: 16, 'aria-hidden': true as const };
  if (category === 'Tutorials & videos') return <PlayCircle {...iconProps} />;
  if (category === 'Courses') return <GraduationCap {...iconProps} />;
  if (category === 'Jobs & applications') return <BriefcaseBusiness {...iconProps} />;
  if (category === 'Trending') return <Sparkles {...iconProps} />;
  return <BookOpen {...iconProps} />;
}

export default function ResourcePanel({
  sources,
  taskStatus,
  printable = false,
  exportTarget = false,
}: ResourcePanelProps) {
  const [filter, setFilter] = useState<ResourceFilter>('All');
  const resources = useMemo(
    () => sources
      .filter((source) => /^https?:\/\//i.test(source.url))
      .map((source) => ({ source, category: getCategory(source) })),
    [sources],
  );
  const categories = ['All', ...Array.from(new Set(resources.map((item) => item.category)))] as ResourceFilter[];
  const visibleResources = filter === 'All'
    ? resources
    : resources.filter((resource) => resource.category === filter);
  const isSearching = taskStatus === 'pending' || taskStatus === 'in_progress';

  return (
    <section
      className={`${printable ? 'resource-guide report-paper space-y-5 p-6 md:p-10' : 'space-y-5 animate-fade-in'}`}
      data-pdf-export-guide={exportTarget ? '' : undefined}
    >
      <header className={`rounded-2xl border p-6 ${
        printable
          ? 'border-slate-200 bg-slate-50'
          : 'border-brand-400/20 bg-gradient-to-br from-brand-500/10 via-surface-900/80 to-surface-900'
      }`}>
        <div className="flex items-start gap-4">
          <div className={`rounded-xl border p-3 ${
            printable
              ? 'border-slate-200 bg-white text-slate-700'
              : 'border-brand-400/20 bg-brand-500/10 text-brand-200'
          }`}>
            <Sparkles size={20} />
          </div>
          <div>
            <p className={`text-xs font-semibold uppercase tracking-[0.18em] ${printable ? 'text-slate-600' : 'text-brand-200'}`}>Kickstart from today</p>
            <h2 className={`mt-1 text-xl font-bold ${printable ? 'text-slate-900' : 'text-surface-100'}`}>Useful links, ready to explore</h2>
            <p className={`mt-2 max-w-2xl text-sm leading-relaxed ${printable ? 'text-slate-700' : 'text-surface-300'}`}>
              A focused collection of tutorials, courses, opportunities, and timely resources for your research.
              Each link includes a short summary from its search result.
            </p>
          </div>
        </div>
      </header>

      {!printable && <div className="flex flex-wrap items-center gap-2">
        {categories.map((category) => (
          <button
            key={category}
            type="button"
            onClick={() => setFilter(category)}
            aria-pressed={filter === category}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
              filter === category
                ? 'border-brand-400/40 bg-brand-500/15 text-brand-100'
                : 'border-surface-700/60 bg-surface-800/50 text-surface-400 hover:text-surface-200'
            }`}
          >
            {category}
            {category === 'All' ? ` (${resources.length})` : ` (${resources.filter((item) => item.category === category).length})`}
          </button>
        ))}
        {isSearching && (
          <span className="ml-auto inline-flex items-center gap-2 text-xs text-surface-400">
            <LoaderCircle size={14} className="animate-spin" />
            Finding practical links…
          </span>
        )}
      </div>}

      {visibleResources.length === 0 ? (
        <div className={printable
          ? 'rounded-xl border border-slate-200 bg-white p-8 text-center'
          : 'glass-card p-8 text-center'}
        >
          {isSearching ? (
            <>
              <LoaderCircle size={32} className={`mx-auto mb-3 animate-spin ${printable ? 'text-blue-700' : 'text-brand-300'}`} />
              <h3 className={`text-sm font-medium ${printable ? 'text-slate-800' : 'text-surface-200'}`}>Gathering your resources</h3>
              <p className={`mt-1 text-xs ${printable ? 'text-slate-600' : 'text-surface-500'}`}>This page will fill in as the resource search completes.</p>
            </>
          ) : (
            <>
              <Inbox size={34} className={`mx-auto mb-3 ${printable ? 'text-slate-400' : 'text-surface-600'}`} />
              <h3 className={`text-sm font-medium ${printable ? 'text-slate-800' : 'text-surface-300'}`}>No resource links found</h3>
              <p className={`mt-1 text-xs ${printable ? 'text-slate-600' : 'text-surface-500'}`}>Try retrying the run to search for fresh links.</p>
            </>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {visibleResources.map(({ source, category }) => (
            <article
              key={source.id || source.url}
              className={`resource-link-card rounded-xl border p-4 transition-colors ${
                printable
                  ? 'border-slate-200 bg-white'
                  : 'border-surface-700/50 bg-surface-800/45 hover:border-surface-600/70'
              }`}
            >
              <div className="mb-3 flex items-start justify-between gap-3">
                <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${
                  printable ? 'border-slate-200 bg-slate-50 text-slate-700' : categoryStyles[category]
                }`}>
                  <CategoryIcon category={category} />
                  {category}
                </span>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`inline-flex items-center gap-1 text-xs font-medium ${
                    printable ? 'text-blue-700 hover:text-blue-900' : 'text-brand-300 hover:text-brand-200'
                  }`}
                >
                  Open link <ArrowUpRight size={13} />
                </a>
              </div>
              <h3 className={`text-sm font-semibold leading-snug ${printable ? 'text-slate-900' : 'text-surface-100'}`}>{source.title}</h3>
              <p className={`mt-2 line-clamp-2 text-xs leading-relaxed ${printable ? 'text-slate-700' : 'text-surface-300'}`}>
                {source.snippet?.trim() || 'The search result did not provide a summary for this link.'}
              </p>
              <p className={`mt-3 truncate border-t pt-2 font-mono text-[10px] ${
                printable ? 'border-slate-200 text-slate-500' : 'border-surface-700/40 text-surface-500'
              }`}>
                {source.domain}
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
