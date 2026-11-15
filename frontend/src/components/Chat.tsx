import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { streamChat, type ChatTurn } from '../api'

export type ChatState = {
  messages: ChatTurn[]
  streaming: boolean
  error: string | null
  send: (text: string) => void
  stop: () => void
  retry: () => void
}

// Lives in the modal so the conversation survives switching tabs and ends when the modal closes.
export function useChat(siteId: string, twinId: string | null): ChatState {
  const [messages, setMessages] = useState<ChatTurn[]>([])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const history = useRef<ChatTurn[]>([])
  const twin = useRef(twinId)
  const abort = useRef<AbortController | null>(null)
  twin.current = twinId

  const publish = useCallback((next: ChatTurn[]) => {
    history.current = next
    setMessages(next)
  }, [])

  const run = useCallback(
    async (turns: ChatTurn[]) => {
      const controller = new AbortController()
      abort.current = controller
      setError(null)
      setStreaming(true)
      publish([...turns, { role: 'assistant', content: '' }])
      try {
        await streamChat(
          { siteId, twinId: twin.current, messages: turns },
          (text) => {
            const last = history.current[history.current.length - 1]
            publish([...history.current.slice(0, -1), { ...last, content: last.content + text }])
          },
          controller.signal,
        )
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'The assistant did not answer.')
      } finally {
        const last = history.current[history.current.length - 1]
        if (last?.role === 'assistant' && !last.content) publish(history.current.slice(0, -1))
        if (abort.current === controller) {
          abort.current = null
          setStreaming(false)
        }
      }
    },
    [siteId, publish],
  )

  useEffect(() => () => abort.current?.abort(), [])

  const send = useCallback(
    (text: string) => {
      const question = text.trim()
      if (!question || abort.current) return
      void run([...history.current, { role: 'user', content: question }])
    },
    [run],
  )

  const stop = useCallback(() => abort.current?.abort(), [])

  const retry = useCallback(() => {
    const last = history.current[history.current.length - 1]
    if (last?.role === 'user' && !abort.current) void run(history.current)
  }, [run])

  return { messages, streaming, error, send, stop, retry }
}

function inline(text: string, key: number): ReactNode {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
      <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong>
    ) : (
      <Fragment key={`${key}-${i}`}>{part}</Fragment>
    ),
  )
}

// Paragraphs, bullet lists and **bold** are all the model is asked to use. Lists may follow a sentence without a blank line.
function Answer({ text }: { text: string }) {
  const bullet = /^\s*[-*•]\s+/
  const blocks: { list: boolean; lines: string[] }[] = []
  for (const line of text.split('\n')) {
    if (!line.trim()) {
      blocks.push({ list: false, lines: [] })
      continue
    }
    const list = bullet.test(line)
    const last = blocks[blocks.length - 1]
    if (last && last.lines.length && last.list === list) last.lines.push(line)
    else if (last && !last.lines.length) Object.assign(last, { list, lines: [line] })
    else blocks.push({ list, lines: [line] })
  }
  return (
    <>
      {blocks
        .filter((b) => b.lines.length)
        .map((b, i) =>
          b.list ? (
            <ul key={i}>
              {b.lines.map((l, j) => (
                <li key={j}>{inline(l.replace(bullet, ''), j)}</li>
              ))}
            </ul>
          ) : (
            <p key={i}>{inline(b.lines.join(' '), i)}</p>
          ),
        )}
    </>
  )
}

export default function Chat({
  moonName,
  suggestions,
  chat,
}: {
  moonName: string
  suggestions: string[]
  chat: ChatState
}) {
  const { messages, streaming, error, send, stop, retry } = chat
  const [draft, setDraft] = useState('')
  const scroller = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)
  const input = useRef<HTMLTextAreaElement>(null)

  useLayoutEffect(() => {
    const el = scroller.current
    if (el && pinned.current) el.scrollTop = el.scrollHeight
  }, [messages, error])

  useEffect(() => {
    input.current?.focus()
  }, [])

  const submit = () => {
    if (!draft.trim() || streaming) return
    pinned.current = true
    send(draft)
    setDraft('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  const last = messages[messages.length - 1]
  const waiting = streaming && last?.role === 'assistant' && !last.content

  return (
    <section className="chat" aria-label={`Ask about ${moonName}`}>
      <div
        className="chat-scroll"
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
        }}
      >
        {messages.length === 0 ? (
          <div className="chat-intro">
            <h3>Ask about {moonName}</h3>
            <p>Terrain, temperature, minerals, access, protection status. Answers come from the data for this place and its five Earth matches.</p>
            <ul className="chat-ideas">
              {suggestions.map((s) => (
                <li key={s}>
                  <button type="button" onClick={() => send(s)}>
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <ol className="chat-log" aria-live="polite">
            {messages.map((m, i) => (
              <li key={i} className="msg" data-role={m.role}>
                {m.role === 'user' ? <p>{m.content}</p> : m.content ? <Answer text={m.content} /> : null}
              </li>
            ))}
            {waiting && (
              <li className="msg typing" data-role="assistant" aria-label="Thinking">
                <span />
                <span />
                <span />
              </li>
            )}
          </ol>
        )}
        {error && (
          <div className="chat-error" role="alert">
            <span>{error}</span>
            {last?.role === 'user' && (
              <button type="button" onClick={retry}>
                Try again
              </button>
            )}
          </div>
        )}
      </div>

      <form
        className="chat-form"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <textarea
          ref={input}
          rows={1}
          value={draft}
          maxLength={2000}
          placeholder="Ask a question"
          aria-label="Your question"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
        {streaming ? (
          <button type="button" className="chat-stop" onClick={stop}>
            Stop
          </button>
        ) : (
          <button type="submit" className="chat-send" disabled={!draft.trim()}>
            Send
          </button>
        )}
      </form>
    </section>
  )
}
