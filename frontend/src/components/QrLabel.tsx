import { useMemo } from "react";
import qrcode from "qrcode-generator";
import { Button, Icon } from "./ui";
import { printAs } from "./print";
import type { ApiMaterial } from "../api/materials";

const QUIET_ZONE = 4; // modules of white border required around a QR code

/** A QR code for `value`, drawn as SVG paths (no HTML injection). Error correction M survives light wear. */
export function QrCodeSvg({ value, size = 168 }: { value: string; size?: number }) {
  const { modules, path } = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(value);
    qr.make();
    const n = qr.getModuleCount();
    let d = "";
    for (let row = 0; row < n; row++) for (let col = 0; col < n; col++) if (qr.isDark(row, col)) d += `M${col} ${row}h1v1h-1z`;
    return { modules: n, path: d };
  }, [value]);
  const side = modules + QUIET_ZONE * 2;
  return <svg viewBox={`${-QUIET_ZONE} ${-QUIET_ZONE} ${side} ${side}`} width={size} height={size} role="img" aria-label={`QR code for ${value}`} shapeRendering="crispEdges">
    <rect x={-QUIET_ZONE} y={-QUIET_ZONE} width={side} height={side} fill="#fff"/>
    <path d={path} fill="#000"/>
  </svg>;
}

/** Printable batch label. The QR code holds the batch ID, which QR Tracking looks up when scanned. */
export function QrLabelDialog({ material, onClose }: { material: ApiMaterial; onClose: () => void }) {
  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="qr-label-title">
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <div className="dialog" style={{ width: "min(460px, 100%)" }}>
      <div className="dialog-header">
        <div>
          <p className="eyebrow">Batch label</p>
          <h2 id="qr-label-title">{material.name}</h2>
          <p>Scan it on the QR Tracking page to open this batch.</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button>
      </div>
      <div className="print-label">
        <QrCodeSvg value={material.id}/>
        <div>
          <strong>{material.name}</strong>
          <span className="mono">{material.id}</span>
          <small>Lot {material.batch} · {material.unit}</small>
          <small>{material.category.name} · {material.yard.name}{material.location ? ` · Zone ${material.location.zone}` : ""}</small>
        </div>
      </div>
      <div className="dialog-actions">
        <Button type="button" variant="ghost" onClick={onClose}>Close</Button>
        <Button type="button" icon="download" onClick={() => printAs("label")}>Print label</Button>
      </div>
    </div>
  </div>;
}
