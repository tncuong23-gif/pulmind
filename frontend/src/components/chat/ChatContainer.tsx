import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { FlaskConical, Square, Volume2, VolumeX } from "lucide-react";
import { useChat } from "../../context/ChatContext";
import { USE_MOCK_API, errorMessage } from "../../api/client";
import type { Attachment, SelectedRecord } from "../../types";
import { vi } from "../../i18n/vi";
import { WelcomeScreen } from "./WelcomeScreen";
import { AssessmentPanel } from "./AssessmentPanel";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";
import { XrayViewer } from "../attachments/XrayViewer";
import { ErrorState } from "../common/ErrorState";
import { LoadingState } from "../common/LoadingState";
import { useWebMcp } from "../../hooks/useWebMcp";
import { SpeechPlayer } from "../voice/SpeechPlayer";
import { chatSpeech } from "../voice/chatSpeech";
export function ChatContainer() {
  const { conversationId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const {
    conversations,
    loadConversation,
    send,
    sendRecords,
    confirmKG,
    assessmentAction,
    busyIds,
    errors,
    retry,
    feedback,
  } = useChat();
  const [readReplies, setReadReplies] = useState(false);
  const [reading, setReading] = useState(false);
  const [speechError, setSpeechError] = useState("");
  const audio = useRef<AudioContext | undefined>(undefined);
  const player = useRef<SpeechPlayer | undefined>(undefined);
  const previousReply = useRef<{ conversationId?: string; id?: string } | undefined>(undefined);
  const awaitingReply = useRef<string | undefined>(undefined);

  function stopReading() {
    player.current?.stop();
    player.current = undefined;
    setReading(false);
  }

  function toggleReading() {
    setSpeechError("");
    if (readReplies) {
      stopReading();
      setReadReplies(false);
      return;
    }
    try {
      const context = audio.current ?? new AudioContext();
      audio.current = context;
      void context.resume().catch(() => setSpeechError("Không thể mở âm thanh. Hãy thử bật lại chế độ đọc."));
      setReadReplies(true);
    } catch (e) {
      setSpeechError(errorMessage(e));
    }
  }
  useEffect(() => () => {
    player.current?.stop();
    if (audio.current && audio.current.state !== "closed") void audio.current.close().catch(() => {});
    audio.current = undefined;
  }, []);
  useEffect(() => {
    stopReading();
    setSpeechError("");
  }, [conversationId, location.key]);
  const [draft, setDraft] = useState("");
  const [viewer, setViewer] = useState<Attachment | null>(null);
  useWebMcp(setDraft);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setDraft("");
    setLoadError("");
    setViewer(null);
    if (!conversationId) {
      setLoading(false);
      return;
    }
    let live = true;
    setLoading(true);
    loadConversation(conversationId)
      .catch((e) => {
        if (live) setLoadError(errorMessage(e));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [conversationId, loadConversation, attempt, location.key]);
  const conversation = conversationId
    ? conversations[conversationId]
    : undefined;
  const busy = (!!conversationId && busyIds.has(conversationId)) || conversation?.assessment?.status === "running";
  const reply = conversation?.messages.at(-1);
  useEffect(() => {
    if (loading || busy || !conversation || reply?.role !== "assistant") return;
    const previous = previousReply.current;
    previousReply.current = { conversationId, id: reply.id };
    const wasWaiting = awaitingReply.current === conversationId;
    if (wasWaiting) awaitingReply.current = undefined;
    if ((previous?.conversationId !== conversationId && !wasWaiting) ||
        (previous?.conversationId === conversationId && previous?.id === reply.id) ||
        !readReplies || !audio.current) return;
    const text = chatSpeech(reply.content);
    if (!text) return;
    stopReading();
    setSpeechError("");
    setReading(true);
    const next = new SpeechPlayer(() => {}, () => {}, { context: audio.current });
    player.current = next;
    next.enqueue(text);
    void next.finish().catch(e => {
      if (player.current === next) setSpeechError(errorMessage(e));
    }).finally(() => {
      if (player.current === next) {
        player.current = undefined;
        setReading(false);
      }
    });
  }, [conversationId, conversation, reply, loading, busy, readReplies]);
  const assessmentOpen = !!conversation?.assessment && !["completed", "cancelled"].includes(conversation.assessment.status);
  const onSend = (content: string, attachments: Attachment[]) => {
    const id = send(content, attachments, conversationId);
    awaitingReply.current = id;
    if (id !== conversationId) navigate(`/chat/${id}`);
  };
  const onSendRecords = (records: SelectedRecord[], text = "") => {
    const id = sendRecords(records, conversationId, text);
    awaitingReply.current = id;
    if (id !== conversationId) navigate(`/chat/${id}`);
  };
  return (
    <main className="chat-page" id="main-content">
      {USE_MOCK_API && (
        <div className="demo-notice">
          <FlaskConical size={14} />
          <span>
            <strong>{vi.mockNotice}</strong>
            <span className="demo-detail"> · {vi.demoHint}</span>
          </span>
        </div>
      )}
      <div className={`chat-scroll ${!conversationId ? "welcome-scroll" : ""}`}>
        {loading && !conversation ? (
          <LoadingState />
        ) : loadError ? (
          <div className="load-error">
            <ErrorState
              message={loadError}
              onRetry={() => setAttempt((v) => v + 1)}
            />
            <button
              className="secondary-button"
              onClick={() => navigate("/chat")}
            >
              Tạo cuộc trò chuyện mới
            </button>
          </div>
        ) : conversation ? (
          <>
          <MessageList
            messages={conversation.messages}
            busy={busy}
            error={errors[conversation.id]}
            onRetry={() => retry(conversation.id)}
            onRegenerate={(id) => retry(conversation.id, id)}
            onFeedback={(id, value) => feedback(conversation.id, id, value)}
            onView={setViewer}
            onSendKGQuestion={assessmentOpen ? undefined : text => onSend(text, [])}
            onConfirmKG={(messageId, ids) => confirmKG(conversation.id, messageId, ids)}
          />
          {conversation.assessment && <AssessmentPanel key={`${conversation.assessment.id}:${conversation.assessment.version}`} assessment={conversation.assessment} busy={busy} onAction={body => void assessmentAction(conversation.id, body)} />}
          </>
        ) : (
          <WelcomeScreen onSelect={setDraft} />
        )}
      </div>
      {!loadError && (
        <ChatInput
          sessionKey={conversationId ?? location.key}
          draft={draft}
          setDraft={setDraft}
          onSend={onSend}
          onSendRecords={onSendRecords}
          busy={busy || loading || assessmentOpen}
          onView={setViewer}
          stopReading={stopReading}
          speechError={speechError}
          speechControls={!USE_MOCK_API && <>
            <button type="button" className="attachment-button composer-voice-control"
              aria-label="Đọc câu trả lời" aria-pressed={readReplies}
              title={readReplies ? "Tắt đọc câu trả lời" : "Bật đọc câu trả lời"} onClick={toggleReading}>
              {readReplies ? <Volume2 aria-hidden="true" /> : <VolumeX aria-hidden="true" />}
              <span>Đọc trả lời</span>
            </button>
            {reading && <button type="button" className="attachment-button composer-voice-control"
              aria-label="Dừng đọc" title="Dừng đọc" onClick={stopReading}><Square aria-hidden="true" /></button>}
          </>}
        />
      )}
      <XrayViewer attachment={viewer} onClose={() => setViewer(null)} />
    </main>
  );
}
