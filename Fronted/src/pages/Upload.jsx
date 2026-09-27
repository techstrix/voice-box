import { useRef, useState } from "react";
import { CheckCircle2, FileText, LoaderCircle, UploadCloud, X } from "lucide-react";
import "./Upload.css";

const ACCEPTED_TYPES = ".txt,.md,.pdf,.docx";

export default function Upload() {
  const [companyId, setCompanyId] = useState(
    () => localStorage.getItem("voicebox.companyId") ?? "",
  );
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef(null);

  const chooseFile = (nextFile) => {
    if (!nextFile) return;
    setFile(nextFile);
    setStatus("idle");
    setMessage("");
    setResult(null);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!file || !companyId.trim()) {
      setStatus("error");
      setMessage(!companyId.trim() ? "Enter a company ID." : "Choose a document to upload.");
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
      const response = await fetch("/api/upload", { method: "POST", body });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "The document could not be indexed.");
      }
      setResult(payload);
      setStatus("done");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not connect to the upload service.");
      setStatus("error");
    }
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setIsDragging(false);
    chooseFile(event.dataTransfer.files[0]);
  };

  return (
    <section className="upload-page">
      <header className="upload-heading">
        <p className="upload-eyebrow">KNOWLEDGE BASE</p>
        <h1>Upload documents</h1>
        <p>Index company documents so VoiceBox can answer from approved information.</p>
      </header>

      <form className="upload-form" onSubmit={handleSubmit}>
        <label className="upload-field-label" htmlFor="company-id">Company ID</label>
        <input
          id="company-id"
          className="upload-company-input"
          value={companyId}
          onChange={(event) => setCompanyId(event.target.value)}
          placeholder="e.g. acme-corp"
          autoComplete="organization"
          maxLength={63}
          required
        />

        <div
          className={`upload-dropzone${isDragging ? " is-dragging" : ""}${status === "error" ? " has-error" : ""}`}
          onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
        >
          <input
            ref={inputRef}
            className="upload-file-input"
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={(event) => chooseFile(event.target.files?.[0])}
          />
          <div className="upload-icon" aria-hidden="true">
            {status === "done" ? <CheckCircle2 size={30} /> : <UploadCloud size={30} />}
          </div>
          <div className="upload-drop-copy">
            <strong>{file ? file.name : "Drop a document here"}</strong>
            <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "TXT, MD, PDF, or DOCX · up to 10 MB"}</span>
          </div>
          <button
            className="upload-choose-button"
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={status === "uploading"}
          >
            {file ? "Change file" : "Browse files"}
          </button>
        </div>

        {file && (
          <div className="upload-selected-file">
            <FileText size={17} aria-hidden="true" />
            <span>{file.name}</span>
            <button
              type="button"
              className="upload-remove-button"
              onClick={() => { setFile(null); setStatus("idle"); setResult(null); }}
              aria-label="Remove selected file"
              disabled={status === "uploading"}
            >
              <X size={16} />
            </button>
          </div>
        )}

        <div className="upload-submit-row">
          <span className="upload-privacy-note">Documents are indexed under this company ID.</span>
          <button className="upload-submit-button" type="submit" disabled={status === "uploading"}>
            {status === "uploading" ? <LoaderCircle className="upload-spinner" size={17} /> : <UploadCloud size={17} />}
            {status === "uploading" ? "Indexing" : "Upload and index"}
          </button>
        </div>

        {status === "error" && <p className="upload-feedback is-error" role="alert">{message}</p>}
        {status === "done" && result && (
          <p className="upload-feedback is-success" role="status">
            <CheckCircle2 size={18} /> {result.filename} indexed as {result.chunks} chunks.
          </p>
        )}
      </form>
    </section>
  );
}