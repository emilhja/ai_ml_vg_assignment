import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type SessionSummary } from "../api";

type Props = {
  session: SessionSummary;
  compact?: boolean;
};

export default function SessionTitleEditor({ session, compact = false }: Props) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(session.display_name ?? "");

  useEffect(() => {
    setDraft(session.display_name ?? "");
  }, [session.display_name, session.session_id]);

  const mutation = useMutation({
    mutationFn: (name: string | null) => api.renameSession(session.session_id, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      queryClient.invalidateQueries({ queryKey: ["session", session.session_id] });
      setEditing(false);
    },
  });

  const save = () => {
    const trimmed = draft.trim();
    const next = trimmed || null;
    const current = session.display_name?.trim() || null;
    if (next === current) {
      setEditing(false);
      return;
    }
    mutation.mutate(next);
  };

  const title = session.display_name?.trim() || "Untitled session";

  if (editing) {
    return (
      <div className={compact ? "space-y-1" : "space-y-2"}>
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") save();
            if (e.key === "Escape") {
              setDraft(session.display_name ?? "");
              setEditing(false);
            }
          }}
          maxLength={120}
          autoFocus
          className="w-full max-w-md bg-panel border border-violet-500/50 rounded px-2 py-1 text-white text-sm"
          placeholder="Session name"
        />
        <div className="flex gap-2">
          <button
            type="button"
            onClick={save}
            disabled={mutation.isPending}
            className="text-xs px-2 py-1 rounded bg-accent/30 text-accent hover:bg-accent/40"
          >
            Save
          </button>
          <button
            type="button"
            onClick={() => {
              setDraft(session.display_name ?? "");
              setEditing(false);
            }}
            className="text-xs px-2 py-1 rounded text-muted hover:text-white"
          >
            Cancel
          </button>
        </div>
        {mutation.isError && (
          <p className="text-xs text-red-400">{(mutation.error as Error).message}</p>
        )}
      </div>
    );
  }

  return (
    <div className={compact ? "" : "space-y-1"}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className={`font-semibold text-white ${compact ? "text-base" : "text-lg"}`}>{title}</h2>
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-xs text-muted hover:text-accent"
          title="Rename session"
        >
          Rename
        </button>
      </div>
      <p className="text-xs text-muted font-mono">ID: {session.session_id}</p>
    </div>
  );
}
