import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export default function StatusBanner() {
  const { data, isError, error, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: 1,
  });

  if (isLoading) {
    return <p className="text-xs text-muted">Connecting to API…</p>;
  }

  if (isError) {
    return (
      <p className="text-xs text-red-400">
        API offline — start uvicorn on :8787 ({(error as Error).message})
      </p>
    );
  }

  if (!data) return null;

  const dirs = data.traces_dirs?.length ? data.traces_dirs.join(" · ") : data.traces_dir;

  return (
    <p className="text-xs text-muted truncate" title={dirs}>
      {data.schema_ready ? "DB ready" : "JSONL only"} · traces: {dirs}
    </p>
  );
}
