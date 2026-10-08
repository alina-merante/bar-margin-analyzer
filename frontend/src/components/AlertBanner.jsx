const VARIANT_ICONS = {
  error: "⛔",
  warning: "⚠️",
  success: "✅",
};

export default function AlertBanner({
  variant = "error",
  title,
  children,
  onClose,
  className = "",
}) {
  const safeVariant = VARIANT_ICONS[variant] ? variant : "error";
  const role = safeVariant === "success" ? "status" : "alert";

  return (
    <div
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
