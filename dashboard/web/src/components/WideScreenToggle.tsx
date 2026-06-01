import { useLayout } from "../context/LayoutContext";

type Props = {
  className?: string;
};

export default function WideScreenToggle({ className = "" }: Props) {
  const { wideScreen, toggleWideScreen } = useLayout();

  return (
    <button
      type="button"
      onClick={toggleWideScreen}
      title={wideScreen ? "Use standard width" : "Use full browser width"}
      className={`px-3 py-1.5 rounded text-xs font-medium border ${
        wideScreen
          ? "border-accent/50 bg-accent/20 text-accent"
          : "border-slate-700/50 text-muted hover:text-white"
      } ${className}`}
    >
      {wideScreen ? "Standard width" : "Wide screen"}
    </button>
  );
}
