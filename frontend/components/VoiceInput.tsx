"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";

type VoiceState = "idle" | "recording" | "transcribing" | "error";

interface VoiceInputProps {
  onTranscriptionComplete: (text: string) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * VoiceInput - Microphone input component sử dụng Web MediaRecorder API
 * để record audio và gửi lên backend để Whisper transcription.
 *
 * Trạng thái:
 * - idle: Sẵn sàng ghi âm
 * - recording: Đang ghi âm
 * - transcribing: Đang chuyển speech -> text
 * - error: Có lỗi xảy ra
 */
export default function VoiceInput({ onTranscriptionComplete, disabled = false, className = "" }: VoiceInputProps) {
  const [state, setState] = useState<VoiceState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const mountedRef = useRef(true);
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleReset = useCallback((delay: number) => {
    if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
    resetTimerRef.current = setTimeout(() => {
      if (!mountedRef.current) return;
      setState("idle");
      setErrorMessage(null);
    }, delay);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (resetTimerRef.current) clearTimeout(resetTimerRef.current);

      const recorder = mediaRecorderRef.current;
      mediaRecorderRef.current = null;
      audioChunksRef.current = [];
      if (recorder) {
        // Đóng panel làm VoiceInput unmount. Hủy callbacks TRƯỚC khi
        // dừng recorder để onstop không gửi một request transcription
        // sau khi giao diện đã biến mất.
        recorder.ondataavailable = null;
        recorder.onstop = null;
        recorder.onerror = null;
        if (recorder.state !== "inactive") {
          try {
            recorder.stop();
          } catch {
            // Recorder có thể vừa tự chuyển inactive giữa hai dòng.
          }
        }
        recorder.stream.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  const stopRecording = useCallback(async () => {
    if (!mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") {
      return;
    }

    const recorder = mediaRecorderRef.current;
    // Không stop MediaStream ngay ở đây. Chrome cần stream còn sống
    // đến khi phát xong dataavailable/onstop để flush phần audio cuối.
    try {
      recorder.requestData();
      recorder.stop();
    } catch (err) {
      console.error("Unable to stop MediaRecorder safely:", err);
      recorder.stream.getTracks().forEach((track) => track.stop());
      mediaRecorderRef.current = null;
      if (mountedRef.current) {
        setErrorMessage("Không thể kết thúc ghi âm, vui lòng thử lại.");
        setState("error");
        scheduleReset(3000);
      }
    }
  }, [scheduleReset]);

  const sendAudioToBackend = useCallback(
    async (audioBlob: Blob) => {
      if (!mountedRef.current || audioBlob.size === 0) return;
      setState("transcribing");
      setErrorMessage(null);

      try {
        const formData = new FormData();
        formData.append("file", audioBlob, "recording.webm");

        const response = await api.post<{ text: string; language: string; duration: number }>(
          "/v1/voice/transcribe",
          formData
        );

        if (!mountedRef.current) return;
        if (response.text && response.text.trim()) {
          onTranscriptionComplete(response.text.trim());
          setState("idle");
        } else {
          setErrorMessage("Không nhận diện được giọng nói, vui lòng thử lại.");
          setState("error");
          // Reset về idle sau 2 giây nếu có lỗi
          scheduleReset(2000);
        }
      } catch (err) {
        if (!mountedRef.current) return;
        console.error("Transcription error:", err);
        if (err instanceof ApiError) {
          setErrorMessage(err.detail);
        } else {
          setErrorMessage("Lỗi khi chuyển giọng nói thành văn bản.");
        }
        setState("error");
        // Reset về idle sau 3 giây nếu có lỗi
        scheduleReset(3000);
      }
    },
    [onTranscriptionComplete, scheduleReset]
  );

  const startRecording = useCallback(async () => {
    setErrorMessage(null);

    try {
      // Request microphone permission
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      // Người dùng có thể đóng Nova trong lúc hộp thoại cấp quyền mic
      // vẫn đang mở. Không tạo recorder cho component đã unmount.
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      // Create MediaRecorder with preferred mime type
      let mimeType = "audio/webm;codecs=opus";
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = "audio/webm";
        if (!MediaRecorder.isTypeSupported(mimeType)) {
          mimeType = "audio/mp4";
          if (!MediaRecorder.isTypeSupported(mimeType)) {
            mimeType = "";
          }
        }
      }

      const mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, {
          type: mimeType || "audio/webm",
        });

        // Clean up
        stream.getTracks().forEach((track) => track.stop());
        mediaRecorderRef.current = null;
        audioChunksRef.current = [];

        // Send to backend for transcription
        if (mountedRef.current && audioBlob.size > 0) {
          void sendAudioToBackend(audioBlob);
        }
      };

      mediaRecorder.onerror = (event) => {
        console.error("MediaRecorder error:", event);
        stream.getTracks().forEach((track) => track.stop());
        mediaRecorderRef.current = null;
        if (!mountedRef.current) return;
        setErrorMessage("Lỗi khi ghi âm, vui lòng thử lại.");
        setState("error");
        scheduleReset(3000);
      };

      // Start recording
      mediaRecorder.start(1000); // Collect data every second
      setState("recording");
    } catch (err) {
      if (!mountedRef.current) return;
      console.error("Microphone access error:", err);

      if (err instanceof DOMException) {
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
          setErrorMessage("Vui lòng cho phép truy cập microphone.");
        } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
          setErrorMessage("Không tìm thấy microphone.");
        } else {
          setErrorMessage("Không thể truy cập microphone.");
        }
      } else {
        setErrorMessage("Lỗi khi bắt đầu ghi âm.");
      }

      setState("error");
      scheduleReset(3000);
    }
  }, [scheduleReset, sendAudioToBackend]);

  const handleClick = useCallback(() => {
    if (disabled) return;

    if (state === "idle" || state === "error") {
      startRecording();
    } else if (state === "recording") {
      stopRecording();
    }
    // If transcribing, do nothing (wait for completion)
  }, [disabled, state, startRecording, stopRecording]);

  // Determine button icon and style based on state
  const getButtonContent = () => {
    switch (state) {
      case "recording":
        return (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
        );
      case "transcribing":
        return (
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="animate-pulse"
          >
            <circle cx="12" cy="12" r="10" opacity="0.3" />
            <path d="M12 6v6l4 2" />
          </svg>
        );
      case "error":
        return (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        );
      default:
        return (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" y1="19" x2="12" y2="23" />
            <line x1="8" y1="23" x2="16" y2="23" />
          </svg>
        );
    }
  };

  const isRecording = state === "recording";

  return (
    <div className={`relative ${className}`}>
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled || state === "transcribing"}
        className={`
          flex h-10 w-10 items-center justify-center rounded-lg
          transition-all duration-200 ease-out
          ${
            isRecording
              ? "animate-pulse bg-red-500 text-white shadow-lg shadow-red-200"
              : state === "error"
                ? "bg-orange-100 text-orange-600"
                : state === "transcribing"
                  ? "bg-blue-50 text-blue-400 cursor-wait"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-800"
          }
          ${disabled ? "opacity-50 cursor-not-allowed" : ""}
        `}
        title={
          state === "recording"
            ? "Dừng ghi âm"
            : state === "transcribing"
              ? "Đang xử lý..."
              : state === "error"
                ? errorMessage || "Lỗi"
                : "Ghi âm câu hỏi"
        }
        aria-label={
          state === "recording"
            ? "Dừng ghi âm"
            : state === "transcribing"
              ? "Đang xử lý giọng nói"
              : "Bắt đầu ghi âm"
        }
      >
        {getButtonContent()}
      </button>

      {/* Error tooltip */}
      {state === "error" && errorMessage && (
        <div className="absolute bottom-full left-1/2 mb-2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-red-600 px-3 py-1.5 text-xs text-white shadow-lg">
          {errorMessage}
          <div className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-red-600" />
        </div>
      )}
    </div>
  );
}
