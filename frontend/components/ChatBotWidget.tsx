"use client";

/**
 * Floating multilingual chat/voice assistant (bottom-right) - a rule-based
 * FAQ bot (see lib/chatbot/intents.ts), not an LLM: it only explains what
 * this app does and points the user at the real feature. It never answers
 * an actual soil/water/crop question with invented numbers - for that, the
 * farmer fills in the real 4-step form and gets real results.
 *
 * Voice input uses the Web Speech API's SpeechRecognition (Chrome-based
 * browsers only, feature-detected - the mic button simply doesn't render
 * where it's unsupported). Voice output (reading a bot answer aloud) uses
 * SpeechSynthesis, same as the wizard's per-question voice-read buttons -
 * see lib/voice/speech.ts, shared by both.
 */

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n/I18nContext";
import { matchIntent, type ResolvedIntentId } from "@/lib/chatbot/intents";
import { isSpeechRecognitionSupported, speak, startListening } from "@/lib/voice/speech";

interface Message {
  id: number;
  from: "user" | "bot";
  text: string;
}

const SUGGESTION_INTENTS: ResolvedIntentId[] = ["identity", "capabilities", "soil", "regenScore"];

let nextId = 1;

export default function ChatBotWidget() {
  const { t, language } = useI18n();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [listening, setListening] = useState(false);
  const [micSupported, setMicSupported] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const stopListeningRef = useRef<{ stop: () => void } | null>(null);

  useEffect(() => {
    setMicSupported(isSpeechRecognitionSupported());
  }, []);

  // Seed the greeting once, on first open.
  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([{ id: nextId++, from: "bot", text: t("chatbot.intents.greeting") }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, open]);

  function respond(intentId: ResolvedIntentId) {
    const text = t(`chatbot.intents.${intentId}`);
    setMessages((previous) => [...previous, { id: nextId++, from: "bot", text }]);
  }

  function send(rawText: string) {
    const text = rawText.trim();
    if (!text) return;
    setMessages((previous) => [...previous, { id: nextId++, from: "user", text }]);
    setInput("");
    const intent = matchIntent(text, language);
    // Small delay so the bot's reply doesn't appear in the same instant as
    // the farmer's own message - reads as a reply, not an echo.
    window.setTimeout(() => respond(intent), 200);
  }

  function handleMic() {
    if (listening) {
      stopListeningRef.current?.stop();
      setListening(false);
      return;
    }
    setListening(true);
    const handle = startListening(
      language,
      (transcript) => {
        setListening(false);
        send(transcript);
      },
      () => setListening(false),
      () => setListening(false),
    );
    stopListeningRef.current = handle;
    if (!handle) setListening(false);
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 sm:bottom-6 sm:right-6">
      {open && (
        <div
          data-testid="chatbot-panel"
          className="mb-3 flex h-[70vh] max-h-[520px] w-[90vw] max-w-[380px] flex-col overflow-hidden rounded-2xl border shadow-xl"
          style={{ background: "var(--surface)", borderColor: "var(--line)" }}
          role="dialog"
          aria-label={t("chatbot.title")}
        >
          <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--line)" }}>
            <div>
              <p className="font-heading text-base font-bold text-soil-900">{t("chatbot.title")}</p>
              <p className="text-xs text-soil-700">{t("chatbot.subtitle")}</p>
            </div>
            <button
              type="button"
              data-testid="chatbot-close"
              aria-label={t("chatbot.closeAria")}
              onClick={() => setOpen(false)}
              className="icon-btn !h-8 !w-8 !text-base"
            >
              ×
            </button>
          </div>

          <div ref={listRef} data-testid="chatbot-messages" className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {messages.map((message) => (
              <div key={message.id} className={`flex ${message.from === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-snug ${
                    message.from === "user" ? "bg-crop-600 text-white" : ""
                  }`}
                  style={message.from === "bot" ? { background: "var(--surface-2)", color: "var(--ink)" } : undefined}
                >
                  <span>{message.text}</span>
                  {message.from === "bot" && (
                    <button
                      type="button"
                      aria-label={t("chatbot.speakAria")}
                      onClick={() => speak(message.text, language)}
                      className="ml-2 align-middle text-xs opacity-70"
                    >
                      🔊
                    </button>
                  )}
                </div>
              </div>
            ))}

            {messages.length <= 1 && (
              <div className="pt-1">
                <p className="mb-1.5 text-xs font-semibold text-soil-700">{t("chatbot.suggestionsTitle")}</p>
                <div className="flex flex-wrap gap-1.5">
                  {SUGGESTION_INTENTS.map((intentId) => (
                    <button
                      key={intentId}
                      type="button"
                      data-testid={`chatbot-suggestion-${intentId}`}
                      onClick={() => send(t(`chatbot.suggestions.${intentId}`))}
                      className="rounded-full border px-2.5 py-1 text-xs font-semibold"
                      style={{ borderColor: "var(--line)", color: "var(--green-900)" }}
                    >
                      {t(`chatbot.suggestions.${intentId}`)}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="border-t p-2.5" style={{ borderColor: "var(--line)" }}>
            {listening && <p className="mb-1.5 text-xs font-semibold text-crop-700">{t("chatbot.micListening")}</p>}
            <form
              className="flex items-center gap-1.5"
              onSubmit={(event) => {
                event.preventDefault();
                send(input);
              }}
            >
              <input
                data-testid="chatbot-input"
                className="text-input !min-h-0 flex-1 !py-2 !text-sm"
                placeholder={t("chatbot.inputPlaceholder")}
                value={input}
                onChange={(event) => setInput(event.target.value)}
              />
              {micSupported && (
                <button
                  type="button"
                  data-testid="chatbot-mic"
                  aria-label={t("chatbot.micAria")}
                  onClick={handleMic}
                  className={`icon-btn !h-10 !w-10 !text-base ${listening ? "animate-pulse" : ""}`}
                >
                  🎙️
                </button>
              )}
              <button
                type="submit"
                data-testid="chatbot-send"
                aria-label={t("chatbot.sendAria")}
                className="btn-primary !h-10 !flex-none !px-4 !text-sm"
              >
                ➤
              </button>
            </form>
          </div>
        </div>
      )}

      <button
        type="button"
        data-testid="chatbot-toggle"
        aria-label={open ? t("chatbot.closeAria") : t("chatbot.openAria")}
        onClick={() => setOpen((previous) => !previous)}
        className="touch-target flex h-14 w-14 items-center justify-center rounded-full text-2xl shadow-lg"
        style={{ background: "var(--green-700)", color: "#fff" }}
      >
        {open ? "×" : "💬"}
      </button>
    </div>
  );
}
