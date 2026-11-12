import { useRef } from "react";

export default function CameraCapture({ onCapture, label, className }) {
  const inputRef = useRef(null);

  return (
    <>
      <button
        type="button"
        className={className}
        aria-label={label}
        onPointerDown={(event) => {
          // Dismissing an alert can move the button before the click fires.
          event.stopPropagation();
        }}
        onClick={() => inputRef.current?.click()}
      >
        📷 Scatta foto
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onCapture(file);
        }}
      />
    </>
  );
}
