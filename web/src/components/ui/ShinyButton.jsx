// A pill button with a slow light sweeping round its edge, a faint speckle and a sheen on hover.
// Adapted from a shadcn "shiny button" for this plain Vite + React app: styles live in styles.css
// (.shiny-button), colours are CSS variables, and reduced-motion users get a still button.
export default function ShinyButton({ label, onClick, className = '', children }) {
  return (
    <button type="button" className={`shiny-button ${className}`} onClick={onClick}>
      <span>{children ?? label}</span>
    </button>
  );
}
