/* Dashboard — now the analytics view by default (the measurable-parameters page
   lives in Analytics.tsx). The old funnel/source/city/owner overview was retired
   once every one of its numbers was covered by Analytics. */
import { useAuth } from "../components/AuthContext";
import Analytics from "./Analytics";

export default function Dashboard() {
  const { user } = useAuth();
  const name = (user?.name || "there").split(" ")[0];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="section-head" style={{ marginBottom: 0 }}>
        <div>
          <h1 style={{ fontFamily: "'Bricolage Grotesque'", fontSize: 24, margin: 0, letterSpacing: "-.02em" }}>Hello, {name} 👋</h1>
          <p className="sec-sub" style={{ margin: "2px 0 0" }}>
            {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}
          </p>
        </div>
      </div>
      <Analytics />
    </div>
  );
}
