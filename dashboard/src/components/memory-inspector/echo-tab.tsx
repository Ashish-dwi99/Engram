"use client";

import type { Memory } from "@/lib/types/memory";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-medium text-gray-700 mb-2">{title}</h4>
      {children}
    </div>
  );
}

function TagList({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item, i) => (
        <span
          key={i}
          className="inline-flex rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-700"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function StringList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="text-sm text-gray-600 leading-relaxed">
          {item}
        </li>
      ))}
    </ul>
  );
}

export function EchoTab({ memory }: { memory: Memory }) {
  const meta = memory.metadata || {};
  const depth = meta.echo_depth || "none";
  const paraphrases = meta.echo_paraphrases || [];
  const keywords = meta.echo_keywords || [];
  const implications = meta.echo_implications || [];
  const questions = meta.echo_questions || [];
  const importance = meta.echo_importance;

  const hasEchoData =
    paraphrases.length > 0 ||
    keywords.length > 0 ||
    implications.length > 0 ||
    questions.length > 0;

  return (
    <div className="space-y-5">
      {/* Echo depth badge */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-gray-500">Echo Depth</span>
        <span className="inline-flex rounded-full bg-purple-50 px-2.5 py-0.5 text-xs font-medium text-purple-700 ring-1 ring-purple-200 capitalize">
          {depth}
        </span>
        {importance !== undefined && (
          <>
            <span className="text-xs text-gray-500 ml-2">Importance</span>
            <div className="flex items-center gap-1.5">
              <div className="w-16 h-1.5 rounded-full bg-gray-100">
                <div
                  className="h-1.5 rounded-full bg-purple-500"
                  style={{ width: `${(importance as number) * 100}%` }}
                />
              </div>
              <span className="text-xs text-gray-500">
                {((importance as number) * 100).toFixed(0)}%
              </span>
            </div>
          </>
        )}
      </div>

      {!hasEchoData && (
        <p className="text-sm text-gray-400">No echo encoding data available.</p>
      )}

      {paraphrases.length > 0 && (
        <Section title="Paraphrases">
          <StringList items={paraphrases} />
        </Section>
      )}

      {keywords.length > 0 && (
        <Section title="Keywords">
          <TagList items={keywords} />
        </Section>
      )}

      {implications.length > 0 && (
        <Section title="Implications">
          <StringList items={implications} />
        </Section>
      )}

      {questions.length > 0 && (
        <Section title="Questions">
          <StringList items={questions} />
        </Section>
      )}
    </div>
  );
}
