import { useRef, useState } from "react";
import { CheckCircle2, LoaderCircle, Mic, Phone, Square, UploadCloud } from "lucide-react";
import "./Upload.css";

const ACCEPTED_AUDIO = ".wav,.mp3,.m4a,.flac,.ogg,.opus,.webm";

export default function CallTester() {
  const [companyId, setCompanyId] = useState(
    () => localStorage.getItem("voicebox.companyId") ?? "",
  );
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState(null);
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const fileInputRef = useRef(null);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        const ext = blob.type.includes("mp4") ? "m4a" : "webm";
        setFile(new File([blob], `recording.${ext}`, { type: blob.type }));
        setStatus("idle");
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      setStatus("error");
      setMessage("Microphone access was denied. Upload an audio file instead.");
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!companyId.trim()) {
      setStatus("error");
      setMessage("Enter a company ID.");
      return;
    }
    if (!file) {
      setStatus("error");
      setMessage("Record or choose an audio clip first.");
      return;
    }
    setStatus("uploading");
    setMessage("");
    setResult(null);
    localStorage.setItem("voicebox.companyId", companyId.trim());

    const body = new FormData();
    body.append("company_id", companyId.trim());
    body.append("file", file);
    try {
      const response = await fetch("/api/voice-turn", { method: "POST", body });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "The voice turn failed.");
      }
      setResult(payload);
      setStatus("done");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not reach the voice service.");
      setStatus("error");
    }
  };

  return (
    <section className="upload-page">
      <header className="upload-heading">
        <p className="upload-eyebrow">VOICE LOOP</p>
        <h1>Test a call</h1>
        <p>Speak a question and hear what a caller on the phone would hear.</p>
      </header>

      <form className="upload-form" onSubmit={handleSubmit}>
        <label className="upload-field-label" htmlFor="call-company-id">Company ID</label>
        <input
          id="call-company-id"
          className="upload-company-input"
          value={companyId}
          onChange={(event) => setCompanyId(event.target.value)}
          placeholder="e.g. acme-corp"
          autoComplete="organization"
          maxLength={63}
          required
        />

        <div className="upload-submit-row">
          {!recording ? (
            <button className="upload-choose-button" type="button" onClick={startRecording}>
              <Mic size={17} /> Record question
            </button>
          ) : (
            <button className="upload-choose-button" type="button" onClick={stopRecording}>
              <Square size={17} /> Stop
            </button>
          )}
          <button
            className="upload-choose-button"
            type="button"
            onClick={() => fileInputRef.current?.click()}
          >
            <UploadCloud size={17} /> {file ? "Change file" : "Upload audio"}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_AUDIO}
            hidden
            onChange={(event) => {
              const next = event.target.files?.[0];
              if (next) {
                setFile(next);
                setStatus("idle");
                setResult(null);
              }
            }}
          />
        </div>

        {file && (
          <p className="upload-privacy-note">
            <Phone size={14} aria-hidden="true" /> {file.name} ({(file.size / 1024).toFixed(1)} KB)
          </p>
        )}

        <div className="upload-submit-row">
          <span className="upload-privacy-note">Runs STT → RAG → LLM → TTS.</span>
          <button className="upload-submit-button" type="submit" disabled={status === "uploading"}>
            {status === "uploading" ? <LoaderCircle className="upload-spinner" size={17} /> : <Phone size={17} />}
            {status === "uploading" ? "Answering" : "Ask"}
          </button>
        </div>

        {status === "error" && <p className="upload-feedback is-error" role="alert">{message}</p>}
        {status === "done" && result && (
          <div role="status">
            <p className="upload-feedback is-success">
              <CheckCircle2 size={18} /> Turn complete.
            </p>
            <p><strong>You said:</strong> {result.transcript || "—"}</p>
            <p><strong>VoiceBox:</strong> {result.answer || "—"}</p>
            {result.audio_url && (
              <audio controls src={result.audio_url} style={{ width: "100%", marginTop: "0.5rem" }} />
            )}
          </div>
        )}
      </form>
    </section>
  );
}
