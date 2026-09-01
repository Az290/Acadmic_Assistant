"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import { api, ApiError } from "@/lib/api";

type LearningQuiz = { question: string; options: string[]; correctIndex: number; explanation: string };
type LearningSection = {
  title: string;
  body: string[];
  projectExample: string;
  why: string;
  alternatives?: ({ name: string; useWhen: string; whyNotHere: string } | string)[];
};
type LearningModule = {
  id: string;
  eyebrow: string;
  title: string;
  summary: string;
  duration: string;
  sections: LearningSection[];
  quiz: LearningQuiz[];
  learningObjectives?: string[];
  keyTerms?: string[];
  codeWalkthroughs?: { path: string; title: string; explanation: string }[];
  pitfalls?: string[];
  exercise?: string;
  track?: string;
  level?: "foundation" | "junior" | "junior-plus" | "intermediate";
  prerequisites?: string[];
  lab?: { title: string; steps: string[]; deliverable: string; acceptanceCriteria: string[] };
  interviewQuestions?: string[];
};

type QuizAnswers = Record<string, Record<number, number>>;

export default function AiLearningHub() {
  const { user } = useAuth();
  const storageKey = `nova-ai-learning:${user?.id ?? "guest"}`;
  const [modules, setModules] = useState<LearningModule[]>([]);
  const [contentError, setContentError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState("");
  const [selectedTrack, setSelectedTrack] = useState("all");
  const [completed, setCompleted] = useState<string[]>([]);
  const [answers, setAnswers] = useState<QuizAnswers>({});
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    api.get<LearningModule[]>("/v1/internal-learning/modules")
      .then((loaded) => {
        setModules(loaded);
        setActiveId((current) => current || loaded[0]?.id || "");
      })
      .catch((error) => setContentError(error instanceof ApiError ? error.detail : "Không tải được khóa học nội bộ."));
  }, []);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? "{}") as { completed?: string[]; answers?: QuizAnswers };
      Promise.resolve().then(() => {
        setCompleted(saved.completed ?? []);
        setAnswers(saved.answers ?? {});
        setHydrated(true);
      });
    } catch {
      Promise.resolve().then(() => setHydrated(true));
    }
  }, [storageKey]);

  useEffect(() => {
    if (!hydrated) return;
    localStorage.setItem(storageKey, JSON.stringify({ completed, answers }));
  }, [answers, completed, hydrated, storageKey]);

  const active = modules.find((module) => module.id === activeId) ?? modules[0];
  const tracks = useMemo(() => Array.from(new Set(modules.map((module) => module.track ?? "Academic Assistant"))), [modules]);
  const visibleModules = selectedTrack === "all" ? modules : modules.filter((module) => (module.track ?? "Academic Assistant") === selectedTrack);
  const totalMinutes = useMemo(() => modules.reduce((sum, module) => sum + Number.parseInt(module.duration, 10), 0), [modules]);
  const progress = modules.length ? Math.round((completed.length / modules.length) * 100) : 0;

  if (contentError) {
    return <div className="card"><h1 className="text-lg font-bold">Không có quyền truy cập</h1><p className="mt-2 text-sm text-slate-600">{contentError}</p></div>;
  }
  if (!active) return <div className="card text-sm text-slate-500">Đang tải khóa học nội bộ…</div>;

  const activeAnswers = answers[active.id] ?? {};
  const answeredCount = Object.keys(activeAnswers).length;
  const score = active.quiz.reduce((total, question, index) => total + (activeAnswers[index] === question.correctIndex ? 1 : 0), 0);

  function chooseAnswer(questionIndex: number, answerIndex: number) {
    setAnswers((current) => ({ ...current, [active.id]: { ...(current[active.id] ?? {}), [questionIndex]: answerIndex } }));
  }

  function completeModule() {
    if (answeredCount !== active.quiz.length) return;
    setCompleted((current) => current.includes(active.id) ? current : [...current, active.id]);
  }

  function askNova() {
    window.dispatchEvent(new CustomEvent("ask-nova", {
      detail: { question: `Tôi đang học chương “${active.title}” trong Learning Hub. Hãy giải thích sâu hơn nội dung chương này bằng ví dụ từ chính dự án Academic Assistant.`, tab: "RAG_QUESTION" },
    }));
  }

  return (
    <div className="learning-page pb-16">
      <section className="relative overflow-hidden rounded-[20px] px-6 py-7 text-white shadow-[0_18px_42px_rgba(21,53,85,.22)] sm:px-8" style={{ background: "linear-gradient(112deg, #102745, #183b5b 58%, #286779)" }}>
        <div className="relative z-10 max-w-3xl">
          <div className="text-[11px] font-bold uppercase tracking-[.16em] text-sky-200">Nova Learning Lab</div>
          <h1 className="mt-2 text-[28px] font-extrabold tracking-[-.03em] sm:text-[34px]">Hiểu AI qua chính hệ thống bạn đang xây</h1>
          <p className="mt-3 max-w-2xl text-[14px] leading-6 text-slate-200">Một lộ trình thực hành từ AI cơ bản đến Agentic RAG, personalization, evaluation và production safety. Mỗi khái niệm đều được soi lại bằng kiến trúc Academic Assistant.</p>
          <div className="mt-5 flex flex-wrap gap-2 text-[11.5px]">
            <span className="rounded-full border border-white/20 bg-white/10 px-3 py-1.5">{modules.length} chương</span>
            <span className="rounded-full border border-white/20 bg-white/10 px-3 py-1.5">~{totalMinutes} phút</span>
            <span className="rounded-full border border-white/20 bg-white/10 px-3 py-1.5">{modules.reduce((sum, module) => sum + module.quiz.length, 0)} câu quiz</span>
          </div>
        </div>
        <div className="absolute -right-12 -top-20 h-72 w-72 rounded-full border border-cyan-200/10 shadow-[0_0_0_42px_rgba(125,211,252,.035),0_0_0_86px_rgba(125,211,252,.025)]" />
      </section>

      <div className="mt-5 grid gap-5 xl:grid-cols-[285px_minmax(0,1fr)]">
        <aside className="self-start xl:sticky xl:top-4">
          <div className="card xl:max-h-[calc(100vh-2rem)] xl:overflow-y-auto">
            <div className="flex items-end justify-between">
              <div><div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Tiến độ</div><div className="mt-1 text-[24px] font-extrabold text-[#173b64]">{progress}%</div></div>
              <div className="text-[11.5px] text-slate-500">{completed.length}/{modules.length} chương</div>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-[#3976c7] transition-all" style={{ width: `${progress}%` }} /></div>
            <label className="mt-4 grid gap-1 text-[11px] font-semibold text-slate-500">
              Lộ trình
              <select className="w-full min-w-0 rounded-lg border px-2.5 py-2 text-[11.5px] font-normal text-slate-700" value={selectedTrack} onChange={(event) => {
                const nextTrack = event.target.value;
                setSelectedTrack(nextTrack);
                const first = nextTrack === "all" ? modules[0] : modules.find((module) => (module.track ?? "Academic Assistant") === nextTrack);
                if (first) setActiveId(first.id);
              }}>
                <option value="all">Tất cả chương</option>
                {tracks.map((track) => <option key={track} value={track}>{track}</option>)}
              </select>
            </label>
            <nav className="mt-5 grid gap-1.5" aria-label="Mục lục khóa học">
              {visibleModules.map((module, index) => {
                const selected = module.id === active.id;
                const done = completed.includes(module.id);
                return (
                  <button key={module.id} onClick={() => setActiveId(module.id)} className="flex min-w-0 items-start gap-3 rounded-xl px-3 py-2.5 text-left transition-colors" style={{ background: selected ? "var(--accent-bg)" : "transparent", color: selected ? "var(--accent-ink)" : "var(--ink)" }}>
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-[10px] font-bold" style={{ background: done ? "var(--teal-bg)" : selected ? "var(--accent)" : "#eef2f7", color: done ? "var(--teal)" : selected ? "white" : "var(--ink-soft)" }}>{done ? "✓" : index + 1}</span>
                    <span className="min-w-0"><span className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400">{module.eyebrow}</span><span className="mt-0.5 block text-[12.5px] font-semibold leading-4">{module.title}</span></span>
                  </button>
                );
              })}
            </nav>
          </div>
        </aside>

        <main className="min-w-0">
          <article className="card !p-0">
            <header className="border-b px-5 py-5 sm:px-7" style={{ borderColor: "var(--border)" }}>
              <div className="flex flex-wrap items-center justify-between gap-3"><span className="rounded-full px-3 py-1 text-[10.5px] font-bold uppercase tracking-wider" style={{ background: "var(--accent-bg)", color: "var(--accent)" }}>{active.eyebrow}</span><span className="text-[11.5px] text-slate-500">{active.duration}</span></div>
              <div className="mt-3 flex flex-wrap gap-2 text-[10.5px] text-slate-500">
                <span>{active.track ?? "Academic Assistant"}</span>
                {active.level && <><span>•</span><span className="uppercase">{active.level}</span></>}
              </div>
              <h2 className="mt-3 text-[24px] font-extrabold tracking-[-.025em] text-[#173b64]">{active.title}</h2>
              <p className="mt-2 text-[13.5px] leading-6 text-slate-600">{active.summary}</p>
              {(active.learningObjectives || active.keyTerms) && (
                <div className="mt-5 grid gap-3 md:grid-cols-[1.35fr_1fr]">
                  {active.learningObjectives && (
                    <div className="rounded-xl border border-white/80 bg-white/70 p-4 shadow-sm">
                      <div className="text-[10.5px] font-bold uppercase tracking-[.12em] text-[#3976c7]">Sau chương này bro sẽ</div>
                      <ul className="mt-2 space-y-1.5 text-[12px] leading-5 text-slate-700">
                        {active.learningObjectives.map((objective) => <li key={objective} className="flex gap-2"><span className="text-[var(--teal)]">✓</span><span>{objective}</span></li>)}
                      </ul>
                    </div>
                  )}
                  {active.keyTerms && (
                    <div className="rounded-xl border border-white/80 bg-white/70 p-4 shadow-sm">
                      <div className="text-[10.5px] font-bold uppercase tracking-[.12em] text-slate-500">Thuật ngữ trọng tâm</div>
                      <div className="mt-2 flex flex-wrap gap-1.5">{active.keyTerms.map((term) => <span key={term} className="rounded-md bg-slate-100 px-2 py-1 font-mono text-[10.5px] text-slate-700">{term}</span>)}</div>
                    </div>
                  )}
                </div>
              )}
              {active.prerequisites && active.prerequisites.length > 0 && <p className="mt-3 text-[11.5px] text-slate-500"><strong>Cần biết trước:</strong> {active.prerequisites.join(" · ")}</p>}
            </header>

            <div className="space-y-8 px-5 py-6 sm:px-7">
              {active.sections.map((section, index) => (
                <section key={section.title}>
                  <div className="flex items-center gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-[#173b64] text-[11px] font-bold text-white">{index + 1}</span><h3 className="text-[17px] font-bold text-slate-900">{section.title}</h3></div>
                  <div className="mt-4 space-y-3 pl-0 text-[13.5px] leading-6 text-slate-700 sm:pl-10">{section.body.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}</div>
                  <div className="mt-4 grid gap-3 sm:ml-10 md:grid-cols-2">
                    <div className="rounded-xl border p-4" style={{ borderColor: "#cfe0f2", background: "#f2f7fd" }}><div className="text-[11px] font-bold uppercase tracking-wider text-[#3976c7]">Trong dự án này</div><p className="mt-2 text-[12.5px] leading-5 text-slate-700">{section.projectExample}</p></div>
                    <div className="rounded-xl border p-4" style={{ borderColor: "#cce9e4", background: "var(--teal-bg)" }}><div className="text-[11px] font-bold uppercase tracking-wider text-[var(--teal)]">Vì sao chọn cách này?</div><p className="mt-2 text-[12.5px] leading-5 text-slate-700">{section.why}</p></div>
                  </div>
                  {section.alternatives && <div className="mt-4 overflow-x-auto sm:ml-10"><table className="w-full min-w-[620px] overflow-hidden rounded-xl text-left text-[12px]"><thead><tr><th className="px-3 py-2.5">Giải pháp khác</th><th className="px-3 py-2.5">Nên dùng khi</th><th className="px-3 py-2.5">Vì sao chưa dùng ở đây</th></tr></thead><tbody>{section.alternatives.map((item) => {
                    const normalized = typeof item === "string" ? { name: item, useWhen: "Khi bài toán phù hợp với ưu điểm của giải pháp này.", whyNotHere: "Cần benchmark và nhu cầu thực tế trước khi tăng độ phức tạp." } : item;
                    return <tr key={normalized.name} className="border-t" style={{ borderColor: "var(--border)" }}><td className="px-3 py-3 font-semibold text-slate-900">{normalized.name}</td><td className="px-3 py-3 text-slate-600">{normalized.useWhen}</td><td className="px-3 py-3 text-slate-600">{normalized.whyNotHere}</td></tr>;
                  })}</tbody></table></div>}
                </section>
              ))}

              {active.codeWalkthroughs && (
                <section>
                  <div className="text-[11px] font-bold uppercase tracking-[.13em] text-[#3976c7]">Đọc code thật trong dự án</div>
                  <h3 className="mt-1 text-[18px] font-bold text-slate-900">Từ lý thuyết tới implementation</h3>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {active.codeWalkthroughs.map((item) => (
                      <div key={item.path} className="min-w-0 rounded-xl border p-4" style={{ borderColor: "var(--border)", background: "var(--panel-soft)" }}>
                        <div className="text-[12.5px] font-bold text-[#173b64]">{item.title}</div>
                        <code className="mt-1 block break-all text-[10.5px] text-[#3976c7]">{item.path}</code>
                        <p className="mt-2 text-[12px] leading-5 text-slate-600">{item.explanation}</p>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {(active.pitfalls || active.exercise) && (
                <section className="grid gap-3 md:grid-cols-2">
                  {active.pitfalls && (
                    <div className="rounded-xl border p-4" style={{ borderColor: "#f0d6ac", background: "var(--amber-bg)" }}>
                      <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--amber-ink)]">Bẫy thiết kế thường gặp</div>
                      <ul className="mt-2 space-y-2 text-[12px] leading-5 text-slate-700">{active.pitfalls.map((pitfall) => <li key={pitfall} className="flex gap-2"><span className="text-[var(--amber)]">!</span><span>{pitfall}</span></li>)}</ul>
                    </div>
                  )}
                  {active.exercise && (
                    <div className="rounded-xl border p-4" style={{ borderColor: "#cce9e4", background: "var(--teal-bg)" }}>
                      <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--teal)]">Bài thực hành</div>
                      <p className="mt-2 text-[12.5px] leading-5 text-slate-700">{active.exercise}</p>
                      <button onClick={askNova} className="mt-3 text-[11.5px] font-bold text-[var(--teal-ink)] underline underline-offset-2">Làm bài này cùng Nova →</button>
                    </div>
                  )}
                </section>
              )}

              {active.lab && (
                <section className="rounded-2xl border p-5 sm:p-6" style={{ borderColor: "#b9d4ee", background: "#f6faff" }}>
                  <div className="text-[11px] font-bold uppercase tracking-[.13em] text-[#3976c7]">Hands-on lab</div>
                  <h3 className="mt-1 text-[18px] font-bold text-slate-900">{active.lab.title}</h3>
                  <ol className="mt-4 space-y-2 text-[12.5px] leading-5 text-slate-700">{active.lab.steps.map((step, index) => <li key={step} className="flex gap-3"><span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[#3976c7] text-[9px] font-bold text-white">{index + 1}</span><span>{step}</span></li>)}</ol>
                  <div className="mt-4 rounded-xl bg-white p-4 shadow-sm"><div className="text-[11px] font-bold text-slate-500">ARTIFACT ĐƯA VÀO PORTFOLIO</div><p className="mt-1 text-[12.5px] text-slate-700">{active.lab.deliverable}</p><div className="mt-3 text-[11px] font-bold text-slate-500">DEFINITION OF DONE</div><ul className="mt-1 space-y-1 text-[11.8px] text-slate-600">{active.lab.acceptanceCriteria.map((criterion) => <li key={criterion}>✓ {criterion}</li>)}</ul></div>
                  <button onClick={askNova} className="mt-4 text-[12px] font-bold text-[#245ca8] underline underline-offset-2">Nhờ Nova hướng dẫn lab này →</button>
                </section>
              )}

              {active.interviewQuestions && (
                <section className="rounded-2xl bg-[#142f50] p-5 text-white sm:p-6">
                  <div className="text-[11px] font-bold uppercase tracking-[.13em] text-sky-200">Interview checkpoint</div>
                  <h3 className="mt-1 text-[18px] font-bold">Bro phải tự trả lời được</h3>
                  <ol className="mt-4 space-y-3 text-[12.5px] leading-5 text-slate-200">{active.interviewQuestions.map((question, index) => <li key={question}><span className="mr-2 font-bold text-sky-300">{index + 1}.</span>{question}</li>)}</ol>
                </section>
              )}

              <section className="rounded-2xl border p-5 sm:p-6" style={{ borderColor: "#c7d9eb", background: "linear-gradient(145deg,#f7fbff,#eef5fc)" }}>
                <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-[11px] font-bold uppercase tracking-[.13em] text-[#3976c7]">Kiểm tra nhanh</div><h3 className="mt-1 text-[18px] font-bold">Quiz cuối chương</h3></div>{answeredCount === active.quiz.length && <span className="rounded-full bg-white px-3 py-1.5 text-[11.5px] font-bold text-[#173b64] shadow-sm">{score}/{active.quiz.length} đúng</span>}</div>
                <div className="mt-5 space-y-6">
                  {active.quiz.map((question, questionIndex) => {
                    const selected = activeAnswers[questionIndex];
                    const answered = selected !== undefined;
                    return <div key={question.question}><div className="text-[13.5px] font-bold leading-5">Câu {questionIndex + 1}. {question.question}</div><div className="mt-3 grid gap-2">{question.options.map((option, optionIndex) => {
                      const isSelected = selected === optionIndex;
                      const isCorrect = answered && optionIndex === question.correctIndex;
                      const isWrong = answered && isSelected && !isCorrect;
                      return <button key={option} disabled={answered} onClick={() => chooseAnswer(questionIndex, optionIndex)} className="rounded-xl border px-4 py-3 text-left text-[12.5px] transition-colors disabled:cursor-default" style={{ borderColor: isCorrect ? "#78c9bb" : isWrong ? "#e7a3a3" : "var(--border-strong)", background: isCorrect ? "var(--teal-bg)" : isWrong ? "var(--red-bg)" : "white", color: isWrong ? "var(--red-ink)" : "var(--ink)" }}>{String.fromCharCode(65 + optionIndex)}. {option}</button>;
                    })}</div>{answered && <div className="mt-2 rounded-lg px-3 py-2 text-[11.8px] leading-5" style={{ background: selected === question.correctIndex ? "var(--teal-bg)" : "var(--amber-bg)", color: selected === question.correctIndex ? "var(--teal-ink)" : "var(--amber-ink)" }}>{selected === question.correctIndex ? "Chính xác. " : "Chưa đúng. "}{question.explanation}</div>}</div>;
                  })}
                </div>
              </section>

              <div className="flex flex-col justify-between gap-3 border-t pt-5 sm:flex-row" style={{ borderColor: "var(--border)" }}>
                <button onClick={askNova} className="btn rounded-lg border px-4 py-2.5 text-[12.5px] font-semibold" style={{ borderColor: "var(--border-strong)", color: "var(--accent)" }}>Hỏi Nova về chương này</button>
                <button onClick={completeModule} disabled={answeredCount !== active.quiz.length || completed.includes(active.id)} className="btn btn-primary rounded-lg px-5 py-2.5 text-[12.5px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{completed.includes(active.id) ? "Đã hoàn thành ✓" : answeredCount !== active.quiz.length ? "Trả lời đủ quiz để hoàn thành" : "Hoàn thành chương"}</button>
              </div>
            </div>
          </article>
        </main>
      </div>
    </div>
  );
}
