import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { Button } from "./ui";

const SCAN_INTERVAL_MS = 150;
const MAX_SCAN_WIDTH = 640;

function cameraError(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "Camera permission was denied. Allow camera access for this site in the browser and try again.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No camera was found on this device.";
  if (name === "NotReadableError") return "The camera is in use by another application.";
  return `The camera couldn’t be started${name ? ` (${name})` : ""}.`;
}

/** Live camera preview that decodes QR codes with jsQR and calls `onResult` once with the first value read.
 * The camera is released when a code is read, when the scanner is closed, and when it unmounts. */
export function QrScanner({ onResult, onClose }: { onResult: (text: string) => void; onClose: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;
  const [status, setStatus] = useState("Starting camera…");
  const [error, setError] = useState("");

  useEffect(() => {
    let stream: MediaStream | null = null;
    let frame = 0;
    let stopped = false;
    let lastScan = 0;
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d", { willReadFrequently: true });
    const release = () => { stopped = true; cancelAnimationFrame(frame); stream?.getTracks().forEach((t) => t.stop()); };

    const tick = (now: number) => {
      const v = video.current;
      if (stopped || !v || !context) return;
      if (now - lastScan >= SCAN_INTERVAL_MS && v.readyState >= 2 && v.videoWidth) {
        lastScan = now;
        const scale = Math.min(1, MAX_SCAN_WIDTH / v.videoWidth);
        canvas.width = Math.round(v.videoWidth * scale);
        canvas.height = Math.round(v.videoHeight * scale);
        context.drawImage(v, 0, 0, canvas.width, canvas.height);
        const image = context.getImageData(0, 0, canvas.width, canvas.height);
        const code = jsQR(image.data, image.width, image.height, { inversionAttempts: "dontInvert" });
        const text = code?.data.trim();
        if (text) {
          release();
          onResultRef.current(text);
          return;
        }
      }
      frame = requestAnimationFrame(tick);
    };

    (async () => {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        setError("Camera access needs the app to be opened at http://localhost or over HTTPS.");
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      } catch (err) {
        if (!stopped) setError(cameraError(err));
        return;
      }
      if (stopped || !video.current) { release(); return; }
      video.current.srcObject = stream;
      await video.current.play().catch(() => undefined);
      setStatus("Point the camera at a batch label");
      frame = requestAnimationFrame(tick);
    })();

    return release;
  }, []);

  return <div className="qr-scanner">
    <video ref={video} muted playsInline aria-label="Camera preview"/>
    {error ? <p role="alert">{error}</p> : <p>{status}</p>}
    <Button type="button" variant="secondary" onClick={onClose}>{error ? "Close" : "Stop camera"}</Button>
  </div>;
}
