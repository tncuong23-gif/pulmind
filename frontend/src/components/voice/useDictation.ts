import { useEffect, useRef, useState } from "react";
import { errorMessage } from "../../api/client";
import { voiceApi } from "../../api/voiceApi";

export function useDictation(sessionKey: string | undefined, onResult: (text: string) => void) {
  const [phase, setPhase] = useState<"idle" | "opening" | "recording" | "finalizing">("idle");
  const [preview, setPreview] = useState("");
  const [error, setError] = useState("");
  const [canRetry, setCanRetry] = useState(false);
  const active = useRef<AbortController | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timeout = useRef<number | undefined>(undefined);
  const lastRecording = useRef<Blob | undefined>(undefined);
  const result = useRef(onResult);
  result.current = onResult;

  function release() {
    window.clearTimeout(timeout.current);
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
  }
  function cleanup() {
    active.current?.abort();
    active.current = null;
    if (recorder.current?.state === "recording") recorder.current.stop();
    recorder.current = null;
    release();
  }
  useEffect(() => {
    setPhase("idle");
    setPreview("");
    setError("");
    setCanRetry(false);
    lastRecording.current = undefined;
    return cleanup;
  }, [sessionKey]);

  function cancel() {
    cleanup();
    lastRecording.current = undefined;
    setPhase("idle");
    setPreview("");
    setError("");
    setCanRetry(false);
  }

  async function finish(blob: Blob, job: AbortController) {
    if (job.signal.aborted) return;
    lastRecording.current = blob;
    try {
      const { transcript } = await voiceApi.transcribe(blob, job.signal);
      if (job.signal.aborted) return;
      if (!transcript.trim()) throw new Error("Chưa nhận dạng được lời nói. Bạn có thể thử lại hoặc ghi âm mới.");
      result.current(transcript.trim());
      lastRecording.current = undefined;
      setCanRetry(false);
    } catch (e) {
      if (!job.signal.aborted) {
        setError(errorMessage(e));
        setCanRetry(Boolean(blob.size));
      }
    } finally {
      if (!job.signal.aborted) {
        active.current = null;
        setPhase("idle");
        setPreview("");
      }
    }
  }

  function retry() {
    if (active.current || !lastRecording.current) return;
    const job = new AbortController();
    active.current = job;
    setError("");
    setPhase("finalizing");
    void finish(lastRecording.current, job);
  }

  async function start() {
    if (active.current) return;
    const job = new AbortController();
    active.current = job;
    lastRecording.current = undefined;
    setCanRetry(false);
    setError("");
    setPhase("opening");
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
        throw new Error("Micro cần trình duyệt hỗ trợ thu âm và địa chỉ HTTPS hoặc localhost.");
      }
      const input = await navigator.mediaDevices.getUserMedia({ audio: {
        echoCancellation: true, noiseSuppression: true, channelCount: 1,
      } });
      if (job.signal.aborted) {
        input.getTracks().forEach(track => track.stop());
        return;
      }
      stream.current = input;
      const mimeType = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"]
        .find(type => MediaRecorder.isTypeSupported(type));
      const capture = new MediaRecorder(input, mimeType ? { mimeType, audioBitsPerSecond: 96000 } : undefined);
      recorder.current = capture;
      const chunks: Blob[] = [];
      let pending: Promise<void> | undefined;
      const snapshot = () => new Blob(chunks, { type: capture.mimeType });
      capture.ondataavailable = event => {
        if (event.data.size) chunks.push(event.data);
        if (job.signal.aborted || pending || capture.state !== "recording" || chunks.length < 2) return;
        pending = voiceApi.transcribe(snapshot(), job.signal)
          .then(({ transcript }) => {
            if (!job.signal.aborted && capture.state === "recording") setPreview(transcript.trim());
          })
          .catch(() => { /* The final recording is retried independently. */ })
          .finally(() => { pending = undefined; });
      };
      capture.onstop = async () => {
        if (job.signal.aborted) return;
        recorder.current = null;
        release();
        setPhase("finalizing");
        await pending;
        await finish(snapshot(), job);
      };
      capture.onerror = () => {
        if (job.signal.aborted) return;
        cancel();
        setError("Không thể tiếp tục thu âm. Hãy kiểm tra mic rồi thử lại.");
      };
      capture.start(2000);
      timeout.current = window.setTimeout(() => {
        if (capture.state === "recording") capture.stop();
      }, 60000);
      setPhase("recording");
    } catch (e) {
      if (!job.signal.aborted) {
        cancel();
        setError(errorMessage(e));
      }
    }
  }

  return { phase, preview, error, canRetry, start, cancel, retry, stop: () => recorder.current?.stop() };
}
