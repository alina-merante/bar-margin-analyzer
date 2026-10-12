import { useEffect, useRef } from "react";

const VARIANT_ICONS = {
  error: "⛔",
  warning: "⚠️",
  success: "✅",
};

export function attachAlertDismissalHandlers(element, eventTarget, onClose) {
  function handlePointerDown(event) {
    if (!element.contains(event.target)) onClose();
  }

  function handleKeyDown(event) {
    if (event.key === "Escape") onClose();
  }

  eventTarget.addEventListener("pointerdown", handlePointerDown);
  eventTarget.addEventListener("keydown", handleKeyDown);

  return () => {
    eventTarget.removeEventListener("pointerdown", handlePointerDown);
    eventTarget.removeEventListener("keydown", handleKeyDown);
  };
}

export default function AlertBanner({
  variant = "error",
  title,
  children,
  onClose,
  className = "",
}) {
  const bannerRef = useRef(null);
  const safeVariant = VARIANT_ICONS[variant] ? variant : "error";
  const role = safeVariant === "success" ? "status" : "alert";

  useEffect(() => {
    if (!onClose || !bannerRef.current) return undefined;
    return attachAlertDismissalHandlers(bannerRef.current, document, onClose);
  }, [onClose]);

  return (
    <div
      ref={bannerRef}
      className={`alert-banner alert-banner--${safeVariant} ${className}`.trim()}
      role={role}
    >
      <span className="alert-banner__icon" aria-hidden="true">
        {VARIANT_ICONS[safeVariant]}
      </span>

      <div className="alert-banner__content">
        {title ? <p className="alert-banner__title">{title}</p> : null}
        <div className="alert-banner__message">{children}</div>
      </div>

      {onClose ? (
        <button
          type="button"
          className="alert-banner__close"
          aria-label="Chiudi messaggio"
          onClick={onClose}
        >
          ×
        </button>
      ) : null}
    </div>
  );
}
