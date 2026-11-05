import { useEffect, useRef, type ReactNode } from "react";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { ArrowUp, AudioLines, FileText, ImageIcon, Plus, ShieldCheck, Square, X } from "lucide-react";
import type { Attachment, SelectedRecord } from "../../types";
import { useAttachments } from "../../hooks/useAttachments";
import { acceptedFiles, MAX_ATTACHMENTS } from "../../config/uploads";
import { AttachmentList } from "../attachments/AttachmentPreview";
import { ErrorState } from "../common/ErrorState";
import { vi } from "../../i18n/vi";
import { USE_MOCK_API } from "../../api/client";
import { useDictation } from "../voice/useDictation";
import "./composer-voice.css";
export function ChatInput({
  draft,
  sessionKey,
  setDraft,
  onSend,
  onSendRecords,
  busy,
  onView,
  stopReading,
  speechControls,
  speechError,
}: {
  draft: string;
  sessionKey?: string;
  setDraft: (value: string) => void;
  onSend: (content: string, attachments: Attachment[]) => void;
  onSendRecords: (records: SelectedRecord[], text?: string) => void;
  busy: boolean;
  onView: (attachment: Attachment) => void;
  stopReading: () => void;
  speechControls?: ReactNode;
  speechError?: string;
}) {
  const files = useAttachments();
  useEffect(() => { files.reset(); }, [sessionKey, files.reset]);
  const input = useRef<HTMLTextAreaElement>(null);
  const selection = useRef({ start: 0, end: 0, draft: "" });
  const insertSpeech = (text: string) => {
    const { start, end, draft: original } = selection.current;
    const before = original.slice(0, start);
    const after = original.slice(end);
    const prefix = before && !/\s$/.test(before) ? " " : "";
    const suffix = after && !/^\s/.test(after) ? " " : "";
    const remaining = Math.max(0, 10000 - before.length - after.length - prefix.length - suffix.length);
    return remaining ? before + prefix + text.slice(0, remaining) + suffix + after : original;
  };
  const voice = useDictation(sessionKey, text => setDraft(insertSpeech(text)));
  const dictating = voice.phase !== "idle";
  const visibleDraft = dictating && voice.preview ? insertSpeech(voice.preview) : draft;
  const recordPicker = useRef<HTMLInputElement>(null);
  const xrayPicker = useRef<HTMLInputElement>(null);
  const recordMode = files.attachments.some((a) => a.type === "medical_record");
  const imageMode = files.attachments.some(a=>a.type==="xray");
  // Tệp đính kèm tự kích hoạt phân tích Clinical IE; văn bản không có tệp là chat thông thường.
  const clinical = files.attachments.length > 0;
  const disabled =
    busy || dictating ||
    files.busy ||
    files.hasErrors ||
    (!draft.trim() && !files.attachments.length);
  useEffect(() => {
    if (input.current) {
      input.current.style.height = "auto";
      input.current.style.height = `${Math.min(160, input.current.scrollHeight)}px`;
    }
  }, [visibleDraft]);
  useEffect(() => {
    if (draft) input.current?.focus();
  }, [draft]);
  const submit = () => {
    if (disabled) return;
    if (clinical) onSendRecords(files.commitRecords(), recordMode ? "" : draft.trim());
    else onSend(draft.trim(), files.commit());
    setDraft("");
    if (input.current) input.current.style.height = "auto";
  };
  const limit = dictating || busy || files.attachments.length >= MAX_ATTACHMENTS;
  return (
    <footer className="composer-area">
      <form
        className="chat-composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {files.attachments.length > 0 && (
          <AttachmentList
            attachments={files.attachments}
            onRemove={files.remove}
            onRetry={files.retry}
            onView={onView}
          />
        )}
        {files.error && <ErrorState message={files.error} />}
        <label htmlFor="chat-question" className="sr-only">
          Câu hỏi y tế
        </label>
        <textarea
          ref={input}
          id="chat-question"
          value={visibleDraft}
          readOnly={dictating}
          onChange={(e) => setDraft(e.target.value)}
          disabled={recordMode || busy || files.busy || files.hasErrors}
          placeholder={recordMode ? "Bấm Gửi để phân tích bệnh án..." : imageMode ? "Có thể thêm văn bản bệnh án để phân tích kết hợp..." : vi.placeholder}
          rows={2}
          maxLength={10000}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              submit();
            }
          }}
        />
        {dictating && <div className="composer-voice-status" role="status">
          <span aria-hidden="true" className={voice.phase === "recording" ? "voice-status-dot recording" : "voice-status-dot"} />
          {voice.phase === "recording" ? "Đang nghe · Bản nhận dạng tạm" : voice.phase === "opening" ? "Đang mở mic…" : "Đang hoàn tất nhận dạng…"}
        </div>}
        {speechError && <ErrorState message={speechError} />}
        {voice.error && <ErrorState message={voice.error} onRetry={voice.canRetry && !busy && !clinical ? () => {
          selection.current = { start: input.current?.selectionStart ?? draft.length, end: input.current?.selectionEnd ?? draft.length, draft };
          stopReading();
          voice.retry();
        } : undefined} />}
        <div className="composer-actions">
          <div className="attachment-actions">
            <Menu.Root>
              <Menu.Trigger asChild>
                <button
                  type="button"
                  className="icon-button add-attachment"
                  aria-label="Thêm tệp đính kèm"
                  title="Thêm tệp đính kèm"
                  disabled={limit}
                >
                  <Plus size={20} />
                </button>
              </Menu.Trigger>
              <Menu.Portal>
                <Menu.Content
                  className="dropdown-menu"
                  side="top"
                  sideOffset={8}
                >
                  <Menu.Item onSelect={() => recordPicker.current?.click()}>
                    <FileText size={16} />
                    {vi.medicalRecord}
                  </Menu.Item>
                  <Menu.Item onSelect={() => xrayPicker.current?.click()}>
                    <ImageIcon size={16} />
                    {vi.xray}
                  </Menu.Item>
                </Menu.Content>
              </Menu.Portal>
            </Menu.Root>
            <span className="composer-divider" />
            <button
              type="button"
              className="attachment-button"
              aria-label={vi.medicalRecord}
              title={vi.medicalRecord}
              disabled={limit}
              onClick={() => recordPicker.current?.click()}
            >
              <FileText size={17} />
              <span>{vi.medicalRecord}</span>
            </button>
            <button
              type="button"
              className="attachment-button"
              aria-label={vi.xray}
              title="Ảnh X-quang JPEG/PNG"
              disabled={limit || imageMode}
              onClick={() => xrayPicker.current?.click()}
            >
              <ImageIcon size={17} />
              <span>{vi.xray}</span>
            </button>
            <button
              type="button"
              className={`attachment-button composer-voice-button composer-voice-control${voice.phase === "recording" ? " is-recording" : ""}`}
              aria-label={voice.phase === "recording" ? "Dừng ghi âm" : "Trò chuyện bằng giọng nói"}
              title={voice.phase === "recording" ? "Dừng ghi âm" : "Ghi âm câu hỏi"}
              disabled={voice.phase !== "recording" && (dictating || busy || files.busy || files.attachments.length > 0 || USE_MOCK_API)}
              onClick={() => {
                if (voice.phase === "recording") { voice.stop(); return; }
                selection.current = { start: input.current?.selectionStart ?? draft.length, end: input.current?.selectionEnd ?? draft.length, draft };
                stopReading();
                void voice.start();
              }}
            >
              {voice.phase === "recording" ? <Square size={17} aria-hidden="true" /> : <AudioLines size={17} aria-hidden="true" />}
              <span className="composer-voice-label">{voice.phase === "recording" ? "Dừng ghi âm" : "Giọng nói"}</span>
            </button>
            {dictating && <button type="button" className="attachment-button composer-voice-control"
              aria-label="Hủy ghi âm" title="Hủy ghi âm" onClick={voice.cancel}><X aria-hidden="true" /></button>}
            {speechControls}
          </div>
          <div className="send-actions">
            <span className="enter-hint">
              {clinical
                ? "Bấm Gửi để phân tích tệp"
                : files.busy
                ? "Đang xử lý tệp…"
                : busy
                  ? "AI đang trả lời…"
                  : "Enter để gửi"}
            </span>
            <button
              type="submit"
              className="send-button"
              aria-label={vi.send}
              title={clinical
                ? "Gửi tệp để phân tích"
                : files.hasErrors ? "Vui lòng tải lại hoặc bỏ tệp lỗi" : vi.send}
              disabled={disabled}
            >
              <ArrowUp size={21} />
            </button>
          </div>
        </div>
        <input
          ref={recordPicker}
          data-testid="medical-record-input"
          className="sr-only"
          type="file"
          tabIndex={-1}
          accept={acceptedFiles("medical_record")}
          onChange={(e) => {
            if (e.target.files) files.add(e.target.files, "medical_record");
            e.target.value = "";
          }}
        />
        <input
          ref={xrayPicker}
          data-testid="xray-input"
          className="sr-only"
          type="file"
          tabIndex={-1}
          accept={acceptedFiles("xray")}
          onChange={(e) => {
            if (e.target.files) files.add(e.target.files, "xray");
            e.target.value = "";
          }}
        />
      </form>
      <div className="composer-caption">
        <span>
          <ShieldCheck size={13} />
          {USE_MOCK_API ? vi.privacy : "Bệnh án chỉ được tải lên khi bạn bấm Gửi"}
        </span>
        <span>
          {files.attachments.length
            ? `${files.attachments.length}/${MAX_ATTACHMENTS} tệp`
            : "Tối đa 2 tệp · 20 MB/tệp"}
        </span>
      </div>
      <p className="medical-disclaimer">{vi.disclaimer}</p>
    </footer>
  );
}
