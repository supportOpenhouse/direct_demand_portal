export interface OfficePitchProps {
  /** Lead's city — substituted into the pitch copy. */
  city: string;
}

/**
 * Office-visit pitch box (Q6 = No/Maybe) — gold-tinted card with English
 * bullets and a dashed-top HINGLISH section in italics.
 */
export function OfficePitch({ city }: OfficePitchProps) {
  return (
    <div className="office-pitch">
      <h4>💬 Pitch the office visit</h4>
      <ul>
        <li>
          One visit to our office = every {city} option that fits your budget — resale,
          ready-to-move and pre-launch — compared side by side.
        </li>
        <li>
          Exclusive pre-launch and off-market inventory in {city} that never reaches the portals
          — office visitors get first pick.
        </li>
        <li>
          Our closing team negotiates the price directly with the seller for you — buyers
          typically save a few lakhs.
        </li>
        <li>
          We plan your site visits from the office itself — shortlisted units, mapped route, all
          of {city} covered in one afternoon.
        </li>
      </ul>
      <div className="hinglish-label">Hinglish</div>
      <ul className="hinglish">
        <li>
          “Sir, ek baar office aa jaiye — {city} ki saari matching properties ek hi baithak mein
          dekh lenge, alag-alag chakkar nahi lagane padenge.”
        </li>
        <li>
          “Pre-launch inventory portal pe aane se pehle hi nikal jaati hai — woh options sirf
          office mein dikha sakte hain.”
        </li>
        <li>
          “Price negotiation hum khud seller se karte hain — aapke 2–3 lakh aaraam se bach
          jayenge.”
        </li>
        <li>
          “Office se hi {city} ke site visits ka poora plan bana denge — ek hi din mein 3–4 best
          options dekh lijiye.”
        </li>
      </ul>
    </div>
  );
}
