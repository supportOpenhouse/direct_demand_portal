/* Diwali decor window, by the viewer's own computer clock (local time),
   6–10 Nov 2026 inclusive. Outside it every festive element is simply not
   rendered — so fireworks.webp is never even downloaded — and the app looks
   normal. Mirrors Direct_Inventory and CP-Inventory-Portal (same dates, same
   assets). Diwali moves each year: update FROM/TO, or delete this file, its
   isFestive() call sites and the "festive" block at the end of styles/app.css. */
const FROM = new Date(2026, 10, 6);   // 6 Nov 2026 00:00 local (months are 0-based)
const TO = new Date(2026, 10, 11);    // 11 Nov 00:00 local — exclusive, so 10 Nov is the last day

/* Evaluated per render, not once at load: a tab left open past midnight on the
   10th drops the decor on its next re-render. */
export const isFestive = (now: Date = new Date()): boolean => now >= FROM && now < TO;
