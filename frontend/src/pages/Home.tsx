/* Home — two views behind one toggle.

   Summary is the analytics view this page has always been. Table is the whole lead
   book in one place: the per-stage pages are each a plain equality on `leads.stage`,
   so a lead lives on exactly one of them and nothing has ever shown all of them at
   once. The toggle is remembered per browser — which view you work in is a habit,
   not session state. */
import { useState } from "react";
import { useAuth } from "../components/AuthContext";
import SlideTabs from "../components/SlideTabs";
import { IconChart, IconTable } from "../components/icons";
import Analytics from "./Analytics";
import AllLeads from "./AllLeads";

const VIEW_KEY = "dd_home_view";
type View = "summary" | "table";

export default function Home() {
  const { user } = useAuth();
  const name = (user?.name || "there").split(" ")[0];
  const [view, setView] = useState<View>(
    () => (localStorage.getItem(VIEW_KEY) === "table" ? "table" : "summary"),
  );
  const pick = (v: View) => { localStorage.setItem(VIEW_KEY, v); setView(v); };

  const toggle = (
    <SlideTabs className="view-toggle">
      <button className={view === "summary" ? "on" : ""} onClick={() => pick("summary")}>
        <IconChart /> Summary
      </button>
      <button className={view === "table" ? "on" : ""} onClick={() => pick("table")}>
        <IconTable /> Table
      </button>
    </SlideTabs>
  );

  /* The toggle sits at the right end of the row that view already has: the toolbar
     row in Table (same line as the search box), the greeting row in Summary. Both
     are the page's FIRST row and the toggle is pinned to its top edge, so the two
     land at the same height instead of jumping.

     Table drops the greeting: it is a working view, and a salutation above a
     filtered table is a row of chrome between you and the data. */
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {view === "summary" ? (
        <>
          <div className="home-viewbar">
            <div>
              <h1 style={{ fontFamily: "var(--font-display)", fontSize: 24, margin: 0, letterSpacing: "-.02em" }}>Hello, {name}</h1>
              <p className="sec-sub" style={{ margin: "2px 0 0" }}>
                {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}
              </p>
            </div>
            {toggle}
          </div>
          <Analytics />
        </>
      ) : (
        <AllLeads toolbarEnd={toggle} />
      )}
    </div>
  );
}
