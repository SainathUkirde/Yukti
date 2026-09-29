/* src/components/panels/AssistantPanel.tsx
 * AI Assistant panel — local rule-based, no external LLM required.
 */
import { useState } from 'react'
import { assistantApi } from '@/api/optimizer'
import { useStore } from '@/store/useStore'
import { ProvenanceBadge } from '@/components/ui/ProvenanceBadge'

interface Message {
  role: 'user' | 'assistant'
  text: string
}

const QUICK_QUESTIONS = [
  'What is CSS and how does it work?',
  'Explain rod floating and N_rf',
  'How does viscosity change with temperature?',
  'What is SOR and what is a good target?',
  'How does the optimizer work?',
]

export function AssistantPanel() {
  const { selectedWellId } = useStore()
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', text: 'Ask me about CSS, SRP, rod floating, viscosity, optimization, or the digital twin.' }
  ])
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)

  const send = async (query: string) => {
    if (!query.trim() || pending) return
    const q = query.trim()
    setMessages((prev) => [...prev, { role: 'user', text: q }])
    setInput('')
    setPending(true)
    try {
      const res = await assistantApi.ask(q, selectedWellId ?? undefined)
      setMessages((prev) => [...prev, { role: 'assistant', text: res.answer }])
    } catch (e) {
      setMessages((prev) => [...prev, { role: 'assistant', text: 'Error: Could not reach backend.' }])
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="card h-full flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-muted uppercase tracking-wide">AI Assistant</span>
        <ProvenanceBadge tag="DEMO_RESULT" />
      </div>

      {/* Chat history */}
      <div className="flex-1 overflow-y-auto space-y-2 mb-2">
        {messages.map((m, i) => (
          <div
            key={i}
            className={m.role === 'user'
              ? 'text-right'
              : 'text-left'
            }
          >
            <div className={`inline-block max-w-[90%] px-2 py-1.5 rounded text-xs ${
              m.role === 'user'
                ? 'bg-accent/20 text-accent'
                : 'bg-surface border border-border text-text'
            }`}>
              {/* Simple markdown-ish rendering for bold */}
              {m.text.split('\n').map((line, j) => (
                <p key={j} className={j > 0 ? 'mt-1' : ''}>{line}</p>
              ))}
            </div>
          </div>
        ))}
        {pending && (
          <div className="text-left">
            <div className="inline-block px-2 py-1.5 rounded bg-surface border border-border text-xs text-muted animate-pulse">
              Thinking…
            </div>
          </div>
        )}
      </div>

      {/* Quick question chips */}
      <div className="flex flex-wrap gap-1 mb-2">
        {QUICK_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => send(q)}
            disabled={pending}
            className="text-[9px] px-1.5 py-0.5 rounded border border-border text-muted hover:border-accent hover:text-accent transition-colors"
          >
            {q.length > 30 ? q.slice(0, 30) + '…' : q}
          </button>
        ))}
      </div>

      {/* Input */}
      <form onSubmit={(e) => { e.preventDefault(); send(input) }} className="flex gap-1.5">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about CSS, SRP, viscosity…"
          className="input text-xs flex-1"
          disabled={pending}
        />
        <button type="submit" disabled={pending || !input.trim()} className="btn-primary px-3">
          →
        </button>
      </form>

      <p className="text-[9px] text-muted/50 mt-1 text-center italic">
        Rule-based assistant — no external LLM
      </p>
    </div>
  )
}
