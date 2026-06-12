export default function Stub({ title }: { title: string }) {
  return (
    <div className="card">
      <div className="empty" style={{ padding: 48 }}>
        <div style={{ fontSize: 26, marginBottom: 6 }}>🚧</div>
        <div style={{ fontWeight: 600, color: "var(--ink-2)" }}>{title} is coming soon</div>
        <div style={{ fontSize: 12.5, marginTop: 4 }}>
          This phase ships Live Inventory and Supply Pipeline — the rest of the prototype follows.
        </div>
      </div>
    </div>
  );
}
