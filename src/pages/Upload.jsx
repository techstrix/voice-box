import { useState, useRef } from "react";
import { UploadCloud, CheckCircle2 } from "lucide-react";
import "./Upload.css";

export default function Upload() {
  const [status, setStatus] = useState("idle"); // idle | uploading | done
  const inputRef = useRef(null);

  const handleFiles = (e) => {
    if (!e.target.files.length) return;
    setStatus("uploading");
    // REPLACE: real upload call goes here
    setTimeout(() => setStatus("done"), 2200);
  };

  return (
    <>
      <h1>Upload</h1>
      <p style={{ color: "var(--text-muted)" }}>Add a document to index.</p>

      <label className="upload-dropzone">
        <div className={`upload-icon ${status === "uploading" ? "is-uploading" : ""}`}>
          {status === "done" ? <CheckCircle2 size={40} /> : <UploadCloud size={40} />}
        </div>
        <span>{status === "uploading" ? "Uploading…" : status === "done" ? "Uploaded" : "Choose a file"}</span>
        <input
          ref={inputRef}
          type="file"
          onChange={handleFiles}
          style={{ position: "absolute", width: 1, height: 1, opacity: 0 }}
        />
      </label>

      {/* Real no-JS fallback — see Step 7 */}
      <noscript>
        <form action="/api/upload" method="post" encType="multipart/form-data">
          <input type="file" name="file" />
          <button type="submit">Upload</button>
        </form>
      </noscript>
    </>
  );
}