/** Opens the browser's print dialog with one print layout: a single QR label, or the dashboard report.
 * The layout is chosen by a class on <body> that the print styles in index.css key on; it is removed once
 * printing ends, so a later print (or Ctrl+P) gets the plain page again. */
export function printAs(layout: "label" | "report") {
  const name = `printing-${layout}`;
  document.body.classList.add(name);
  const done = () => { document.body.classList.remove(name); window.removeEventListener("afterprint", done); };
  window.addEventListener("afterprint", done);
  window.print();
}
