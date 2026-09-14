/* Everything about "you" in one place. It exists because logout was split off the
   sidebar chip (the chip used to BE the logout button), which finally gave the chip
   somewhere to navigate to. */
import { useAuth } from "../components/AuthContext";
import { useTheme } from "../components/ThemeContext";
import {
  IconLogout,
  IconMoon,
  IconSun,
} from "../components/icons";

const initials = (s: string) => s.split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase();

export default function Profile() {
  const { user, logout, enabled } = useAuth();
  const { theme, toggle } = useTheme();

  const name = user?.name || user?.email || "Admin";
  const email = user?.email || "—";

  return (
    <div className="profile">
      <div className="profile-head">
        {user?.picture
          ? <img className="profile-av" src={user.picture} alt="" />
          : <div className="profile-av">{initials(name)}</div>}
        <div style={{ minWidth: 0 }}>
          <h2>{name}</h2>
          <div className="pe">{email}</div>
        </div>
        <span className="role-chip" style={{ marginLeft: "auto", textTransform: "capitalize" }}>
          {user?.role || "admin"}
        </span>
      </div>

      <div className="card panel-pad">
        <div className="profile-rows">
          <div className="profile-row">
            <div>
              <div className="pl">Appearance</div>
              <div className="pd">Remembered on this browser.</div>
            </div>
            <div className="theme-seg">
              <button className={theme === "light" ? "on" : ""} onClick={() => theme !== "light" && toggle()}>
                <IconSun /> Light
              </button>
              <button className={theme === "dark" ? "on" : ""} onClick={() => theme !== "dark" && toggle()}>
                <IconMoon /> Dark
              </button>
            </div>
          </div>

          <div className="profile-row">
            <div><div className="pl">Role</div><div className="pd">Set by an admin in Settings &amp; Access.</div></div>
            <div className="pv" style={{ textTransform: "capitalize" }}>{user?.role || "admin"}</div>
          </div>

          <div className="profile-row">
            <div><div className="pl">Email</div><div className="pd">Your Openhouse Google account.</div></div>
            <div className="pv">{email}</div>
          </div>
        </div>
      </div>

      {/* With auth off there is no session to end, so the control would be a lie. */}
      {enabled && (
        <div className="card panel-pad">
          <div className="profile-row">
            <div><div className="pl">Sign out</div><div className="pd">Ends this session on this device.</div></div>
            <button className="btn" onClick={logout} style={{ color: "var(--coral)", borderColor: "var(--coral-soft-2)" }}>
              <IconLogout /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
