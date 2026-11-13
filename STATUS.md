# 99acres Static IP Proxy: Status and Plan

_Last updated: 2026-11-05_

Handover for any Claude session continuing this work. It records what is built, what was decided and why, and what is left. The original plan lives at the end of this file for reference.

## Read first (state on 5 Nov)

- **How to send each 99acres API call** (doc + live corrections, field map, a payload that posted,
  error codes, open questions): `docs/99acres-api.md`. The 2019 `99acres_api.docx` is out of date.
- **Make a 99acres call safely:** `droplet-backend/tools/acres_call.sh METHOD 'path' [json]` — runs ON
  the droplet (only whitelisted IP), login from `backend/.env` via SSH stdin, token never leaves the
  droplet, JWTs redacted, **writes refused unless `ALLOW_WRITE=1`**.
- **Where things stand:**

  | | |
  |---|---|
  | Token (`v21/accesstoken`) | ✅ works from 129.212.244.52 |
  | Create listing (`v21/listing`) | ✅ **proven end to end** — test listing `E95607134` posted 5 Nov (score 75), then deleted |
  | City ids | Noida **7** · Ghaziabad **9** · Gurgaon **8** (confirmed by the live listing) · Greater Noida 222 |
  | Subscription | ✅ NCR pack `Ai_Listing / GROUP43_NCR-ALL`, matched **per city** (no `City` → "no valid subscription") |
  | Delete (`deleteListings`) | ❌ **blocked** — Akamai 403 on every URL tried (v24 doc URL + 3 v21 spellings, real id). **Dashboard-only for now.** |
  | Lookups (`propertytype`, `listingstaticdata`) | ❌ 404 / 403 — ids come from the 2019 doc |
  | List existing listings | ❌ no such API — read "Manage Listings" in the dashboard |
  | Edit (`v21/listing` + `Prop_Id` + `isEdit`) | ❓ untested |
  | Photos (`PhotosData`, Cloudinary URLs, type tags) | ❓ untested — the test listing had none |

- **Rules:** never post incrementally (a thin payload may create a public listing) — only complete,
  user-approved payloads. Never print a token. Never use the droplet to scrape 99acres' website (bot
  flags would hit the whitelisted IP). Don't keep guessing blocked URLs from the whitelisted IP.
- **Existing listing NOT made by us:** `AI P95503744` (posted 04/11/26 by a person via 99acres' app) =
  Demand Dashboard **OHNC1882**, The Hyde Park. Leave it; re-posting OHNC1882 by API → duplicate (errorCode 5).
- ❓ **"295 Credits" on every listing card.** The live card also says "Your listings credits are 295
  Credits" beside "top listings are boosted by 2.8K–6.2K credits" — so 295 looks like a per-listing
  visibility/boost allowance, NOT the cost of a listing. Confirm with 99acres (and read pack used/remaining
  in the dashboard) before planning the bulk push of ~248 properties.
- **Before a bulk push:** (1) a working API delete URL from 99acres (sold/booked homes must come down);
  (2) photo handling (do Cloudinary URLs work, which `type` tags); (3) data gaps — photos for 145 of 248,
  age + ownership per property, 2.5 BHK, Stilt parking; (4) what is already listed by hand (duplicates).

## First API listing — done (5 Nov)

`E95607134` — OHGD1609, DLF The Camellias, Sector 42 Gurgaon, 4 BHK, 7400 sqft, ₹64.8 Cr, floor
14/30. TEST values: Owntype 3 (co-op), Age 2 (5–10 yrs; possession Dec 2017 per web), furnishing
lights 6 / fans 4 / wardrobes 3, coordinates 28.4513058, 77.1006597 (Google geocode), no photos.
API answer `{"status":true,"prop_id":"E95607134","quality_score":75}`; dashboard card `AI E95607134 |
295 Credits | Posted 05/11/26 | Expiry 04/01/27 | ACTIVE`, "Gurgaon, Haryana", completion 75%.
API delete failed (Akamai 403 on 4 URLs) → **deleted by hand in the dashboard by the user, 5 Nov.**
Listing lifetime on 99acres: ~60 days (posted 05/11 → expiry 04/01).

## How to work with the user

- Give exact click paths ("Networking → Firewalls → Create Firewall") and paste-ready command blocks, one step at a time. The user asked for this explicitly after a dense, jargon-heavy answer.
- Server work is done through the **DigitalOcean browser console** (Droplet → Access → Launch Droplet Console), logged in as `root`. Local tests run in Terminal on the user's Mac.
- After each step, tell them the exact output to expect, and ask them to paste results back with secrets replaced by `xxx`.
- This is not related to the `sellerapp` repo.

## Architecture

```
Render (Singapore) / Mac / n8n
   │
   ├── 99acres calls ──► DO droplet BLR1 (Squid :31847, auth, 99acres-only) ──129.212.244.52──► 99acres API
   │
   └── everything else ── direct ──►
```

## Current state (verified)

| Item                                    | Value                                                                                                                                                                      |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DO droplet                              | `99acres-api-proxy-blr`, BLR1, Ubuntu 24.04.5 LTS, Basic $6 (1 vCPU / 1 GB)                                                                                              |
| **Reserved IP (send to 99acres)** | **129.212.244.52**                                                                                                                                                   |
| Droplet's own public IP                 | 206.189.139.59 (never whitelist this one, it changes on rebuild)                                                                                                           |
| Private IP / anchor IP                  | 10.122.0.2 / 10.47.0.5                                                                                                                                                     |
| Proxy                                   | Squid on TCP **31847**, user `acres`, password in the team password manager (never in chat or code)                                                                |
| Proxy URL format                        | `http://acres:<password>@129.212.244.52:31847`                                                                                                                           |
| DO Cloud Firewall                       | `acres-proxy-fw`, applied to the droplet by name                                                                                                                         |
| Allowed on 31847                        | `74.220.52.0/24`, `74.220.60.0/24` (Render Singapore outbound); `223.190.86.183`, `223.190.87.241` (user's Mac, ISP rotates; if it breaks use `223.190.86.0/23`) |
| Allowed on 22                           | All IPs (see the decisions section for why)                                                                                                                                |
| SSH key                                 | `~/.ssh/id_ed25519` on the user's Mac, registered in DO. Not yet backed up                                                                                               |

### Verification results

- `curl -4 icanhazip.com` on the droplet → `129.212.244.52`, before and after a reboot.
- From the Mac, through the proxy with the password → `129.212.244.52`.
- Without the password → `CONNECT tunnel failed, response 407`.
- To google.com with the password → `CONNECT tunnel failed, response 403`.
- After the firewall was created, the user reported the Mac test still passes and the security block ran ("done"). They did not paste the security block's output.

## Incident: egress lost for ~10 days (24 Oct → 3 Nov), fixed 3 Nov

- **What:** traffic left the droplet as `206.189.139.59` (its own IP), not the Reserved IP.
  99acres answered that IP with `401 {"message":"Unauthorized Client"}`.
- **Cause:** unattended-upgrades upgraded `systemd` on 24 Oct 06:58 UTC; the restart of
  systemd-networkd re-applied netplan and put the default route back on `206.189.128.1`.
  `reserved-ip-route.service` was a boot-only oneshot, so nothing re-applied the route.
- **Fix:** `reserved-ip-route.timer` (`OnBootSec=30s`, `OnUnitInactiveSec=60s`) re-runs the
  same idempotent `ip route replace` every minute; the service is now `RemainAfterExit=no`
  so the timer can re-run it. Verified: default route via `10.47.0.1`, egress
  `129.212.244.52`, timer armed. **Not yet proven:** the timer healing a route that a
  networkd restart resets (test: `ip route replace default via 206.189.128.1 dev eth0`, then
  watch `ip route show default` return to `10.47.0.1` within ~60 s).
- **Lesson:** no alert fired for 10 days — the egress cron check (plan Task 5) is not optional.

## 99acres token test (3 Nov)

Token call `POST https://www.99acres.com/99api/v21/accesstoken/qwerty?rtype=json` with
`{"username","password"}` from `backend/.env` (`ACRES_DASHBOARD_USERNAME` / `_PASSWORD`),
run ON the droplet (creds via stdin over SSH, never stored there):

| From | Answer |
|---|---|
| 206.189.139.59 (wrong IP) | `401 {"message":"Unauthorized Client","responseStatus":"UNAUTHORIZED"}` |
| 129.212.244.52 (Reserved IP) | `200 {"status":false,"expires":86400,"data":null,"message":null,"headers":null,"responseStatus":"OK"}` |

→ **The IP whitelist works.** With the first username the login was refused silently.

**With the updated username (same env key, 17 chars) → token issued** (3 Nov ~10:53 UTC):
`200 {"status": true, "accessToken": "<JWT>", "expires": 86400, "data": null, ...}`.
- ⚠️ The key is **`accessToken`** (camelCase), not the doc's `accesstoken`. Client code must read it.
- ⚠️ `expires` says 86400 s, but the JWT's own `exp` is **730 days** after `iat` (to 2 Nov 2028).
  Re-login on `errorCode` 10 / 401 regardless; don't trust either number alone.
- JWT `sub` = `7551877` (likely the 99acres profile id).
- ⚠️ **That token was printed in the 3 Nov chat** (a summary script missed the camelCase key).
  It only works from the whitelisted IP. Ask 99acres to revoke tokens issued 3 Nov ~10:53 UTC,
  and whether a new login revokes the previous token. The summary script now redacts any
  `*token*` key.

## Listing test (4 Nov) — blocked on 99acres' side

Run on the droplet (creds via SSH stdin, token never printed):

| Call | Result |
|---|---|
| `POST v21/accesstoken` | ✅ token issued |
| `POST v21/listing` with only `Res_Com/Mode/Type` (can't create anything) | `{"status":false,"error":{"errorCode":"2","errorMsg":"You do not have a valid subscription"}}` — **the endpoint is live and accepts our token; the account has no posting subscription** |
| `GET v21/propertytype`, `GET v21/listingstaticdata` | nginx **404** — gone from the 2019 doc's paths |
| same two on v22–v25 | Akamai **403 Access Denied** (unknown paths blocked at the edge) — stopped guessing |

~~Needed: an active subscription~~ — **resolved 5 Nov.** The account HAS an active pack:
`Ai_Listing | GROUP43_NCR-ALL | Common pack`, 2000 listings, valid to 2027-09-09. The pack is
matched **per city**: our 4 Nov post had no `City`, so no pack matched → errorCode 2. With
`"City":"7"` (Noida) the same post reaches form validation instead:
`errorCode 6 "Error while saving the form"`, errorDetail = Locality, Area, Latitude (map).
Same with `Credit_Allocation_Mode: SIMPLE` + `Transact_Type: 1` added.

⚠️ Only those 3 fields were reported missing — NOT the 2019 doc's long mandatory list. Adding
just them might create a real, thin public listing. **No more incremental test posts:** the next
post must be a complete, user-approved listing, with the delete path checked first.

Still needed from 99acres: the current lookup URLs / ids (age, ownership, facing, furnishing,
amenities, photo types — `v21/propertytype` and `v21/listingstaticdata` are 404) and Gurgaon's
city id. Until then the 2019 doc's static-data sample ids are the best guess.

## What was done, step by step

1. **DO account, droplet and Reserved IP** created in BLR1 and assigned to the droplet.
2. **Outbound traffic goes out over the Reserved IP.** This is a systemd oneshot unit `reserved-ip-route.service` that runs `/usr/local/sbin/reserved-ip-route`. At boot, the script reads the anchor gateway from the metadata service (`169.254.169.254/.../anchor_ipv4/gateway`) and runs `ip route replace default via $GW dev eth0`. It is enabled at boot.
3. **System updated**: `apt-get upgrade` with `--force-confold`, then a reboot. The route survived the reboot.
4. **Squid installed.** Config in `/etc/squid/squid.conf`; the original is kept as `squid.conf.orig`. Key settings:
   - `http_port 31847`
   - Login via `basic_ncsa_auth`, using `/etc/squid/passwords` (owner `proxy:proxy`, mode 640)
   - Only CONNECT requests to port 443 are allowed
   - Allowed destinations: `.99acres.com` and `icanhazip.com`; everything else is denied
   - `forwarded_for delete`, `via off`, `cache deny all`
   - A systemd drop-in `/etc/systemd/system/squid.service.d/restart.conf` sets `Restart=on-failure`, `RestartSec=5`
   - Squid is enabled at boot
5. **Hardening:**
   - fail2ban with an `[sshd]` jail (`backend = systemd`)
   - `/etc/ssh/sshd_config.d/00-hardening.conf` sets `PasswordAuthentication no` and `KbdInteractiveAuthentication no`. The `00-` prefix matters because sshd uses the first value it reads, and DO's `50-cloud-init.conf` can turn password login back on.
   - unattended-upgrades checked to be enabled
6. **DO Cloud Firewall** created with the rules in the table above. Outbound rules are left at the defaults.

## Decisions and reasoning (where we departed from the original plan)

- **Region BLR1, not Singapore, even though Render is in Singapore.** Each 99acres call crosses between Singapore and India once whichever region the droplet is in, so latency is about the same. An Indian source IP is less likely to trip geo or bot rules on an Indian portal. Laptops in India get a shorter path. Reserved IPs only work inside their region, so every future recovery droplet must also be in BLR1.
  - Note: `www.99acres.com` sits behind Akamai (edgekey), with an edge in New Delhi. The real API host is still unknown.
- **systemd unit instead of editing netplan** for the Reserved IP route. It reads the gateway at every boot, so a droplet rebuilt from a snapshot fixes its own route, and there's no risk of locking yourself out with a bad netplan file. Caveat: running `netplan apply` resets the route, so run `systemctl restart reserved-ip-route` afterwards.
- **`icanhazip.com` is allowed through Squid.** The original plan's startup IP check could never pass under a 99acres-only rule. It's one harmless extra domain.
- **No separate `ops` user. Root logs in with the key only** (`PermitRootLogin` stays at Ubuntu's default, `prohibit-password`). The user works through the DO browser console, which logs in as root.
- **Port 22 left open to all IPs.** The DO browser console connects over SSH from DigitalOcean's own IP ranges, so limiting 22 to the user's IPs would break it. Key-only login plus fail2ban covers it.
- **No ufw; the DO Cloud Firewall is the only IP filter.** One place to maintain, with a clickable UI. Two copies of the IP list would drift.
- **Port 31847 instead of 3128**, to cut down on automated proxy scanning.
- **Known gap: the proxy password is sent unencrypted** between Render and the droplet (standard proxy Basic auth). The 99acres traffic itself stays encrypted end to end. The firewall allowlist is the main protection; rotate the password if in doubt. Optional future fix: Squid `https_port` with a certificate. Python `requests`/urllib3 and Node `https-proxy-agent` support `https://` proxy URLs.
- **Render's outbound IP ranges are shared** with other Render customers in Singapore. The allowlist narrows who can reach the proxy, and the password does the rest.

## Pending

### Immediate (user)

- [ ] **Email 99acres** asking them to whitelist `129.212.244.52`. Status unknown, so ask the user. Questions to include:
  - The exact API base URL / hostname
  - Sandbox, production, or both?
  - Rate limits and bulk upload limits
  - How tokens expire and refresh
  - Can we add a backup IP later?
- [ ] Back up `~/.ssh/id_ed25519` (the private key) to the company password manager.
- [ ] Record the droplet, IPs, port and proxy credentials in the team password manager. The password should already be there; confirm.
- [ ] Confirm the DO account is on the company email and card, and decide who else gets DO access.

### When 99acres replies (Phase 3)

- [ ] If the API host is **not** under `.99acres.com`, add it to the Squid config. Otherwise every call gets a Squid 403 that looks like a whitelist failure. See the commands below.
- [ ] Store the 99acres API credentials in the team secrets store and Render environment variables, never in code, Sheets or chat.
- [ ] Make a first test call through the proxy and save the response as proof the whitelist works.

### Code (Phase 4): needs the user's uploader codebase

- [ ] Render environment variables (an Environment Group is fine):
  - `DROPLET_STATIC_IP=129.212.244.52`, `DROPLET_SQUID_PORT=31847`, `DROPLET_SQUID_USERNAME=acres`, `DROPLET_SQUID_PASSWORD=<pw>` — the app builds the proxy URL from these (`acres_client.proxy_url`), and `DROPLET_STATIC_IP` is also the egress the health check/cron expect
  - the 99acres keys
- [ ] One dedicated 99acres client that uses the proxy; nothing else in the app should. Never set global `HTTP_PROXY`/`HTTPS_PROXY`.
  - Python: a `requests.Session` with `trust_env = False` and `proxies = {"https": <proxy URL>}`
  - Node axios: `httpsAgent: new HttpsProxyAgent(url)` plus `proxy: false`
  - Native fetch: undici `ProxyAgent` as the `dispatcher`
  - n8n: set the proxy on the HTTP Request node only
- [ ] Startup check: `GET https://icanhazip.com` through the proxy must equal `DROPLET_STATIC_IP`, or the app fails loudly.
- [ ] Timeouts and retries with backoff. Log which listing failed and why.
- [ ] A per-listing upload log (listing ID, payload hash, 99acres response, timestamp) so retries don't create duplicates.
- [ ] Laptop runs: use an SSH tunnel instead of adding home IPs to the firewall: `ssh -N -L 3128:localhost:31847 root@129.212.244.52`, then set `DROPLET_STATIC_IP=localhost` and `DROPLET_SQUID_PORT=3128` locally (`/v1/acres/health` will then report an egress mismatch, because it compares the egress with `DROPLET_STATIC_IP` — expected in tunnel mode).

### Monitoring and maintenance (Phase 5)

- [ ] **Health check: a Render cron job** every ~5 minutes that does the icanhazip check through the proxy and posts to Slack on failure. Recommended over UptimeRobot or DO Uptime because it runs from the real source IPs, tests the proxy, login and Reserved IP routing together, and needs no extra firewall openings.
- [ ] DO Monitoring alert policies: CPU above 80%, memory above 85%, disk above 80%. Check the metrics agent is installed; it's the monitoring checkbox at droplet creation.
- [ ] Confirm `/etc/logrotate.d/squid` exists (it ships with the Ubuntu package).
- [ ] Add the DO tag `acres-proxy` to the droplet and switch the firewall to apply **by tag**, so a recovery droplet inherits it automatically.
- [ ] Take a snapshot now that setup is final. Optionally turn on weekly backups (about $1.20/month).
- [ ] **Recovery runbook** (try it once):

  1. Create a droplet from the snapshot in **BLR1**, with tag `acres-proxy`.
  2. Move the Reserved IP to it.
  3. `systemctl restart reserved-ip-route` (it also runs at boot).
  4. `curl -4 icanhazip.com` must print `129.212.244.52`.

  No whitelist change is needed.
- [ ] Rotate the proxy password on a schedule, and right away when someone's access changes.

### "Done when" checklist

- [X] The droplet egresses as the Reserved IP, including after a reboot
- [X] Requests without auth, or to non-99acres sites, are refused
- [ ] A test listing uploads from Render and from a laptop through the proxy
- [ ] Alerts fire when Squid is stopped on purpose
- [ ] The recovery runbook has been tried once

## Common operations (run in the Droplet Console as root)

Add an allowed destination domain (example: the API is on `api.example.com`):

```
sed -i 's/^acl acres  dstdomain .99acres.com$/acl acres  dstdomain .99acres.com .example.com/' /etc/squid/squid.conf
squid -k parse 2>&1 | tail -2 && systemctl restart squid && systemctl is-active squid
```

Rotate the proxy password (then update the password manager and Render's `DROPLET_SQUID_PASSWORD`):

```
PASS=$(openssl rand -hex 24); echo "$PASS" | htpasswd -i /etc/squid/passwords acres
systemctl restart squid && echo "NEW PROXY PASSWORD: $PASS"
```

Add an allowed source IP: DO website → Networking → Firewalls → `acres-proxy-fw` → edit the TCP 31847 rule → add it to Sources.

Check health:

```
curl -4 icanhazip.com                 # must be 129.212.244.52
systemctl is-active squid reserved-ip-route fail2ban
tail -n 20 /var/log/squid/access.log
```

Reading test errors: `CONNECT tunnel failed, response 403/407` comes from Squid (blocked or no login). A plain HTTP 403 means the tunnel opened and 99acres' CDN refused the request. A timeout usually means the firewall is blocking your source IP.

## Reference

- Original plan: "99acres Static IP Proxy — Setup To-Do" (2026-10-22), five phases: droplet + Reserved IP, lock-down proxy, whitelisting, wire uploader, monitoring.
- [DigitalOcean — Send outbound traffic over a Reserved IP](https://docs.digitalocean.com/products/networking/reserved-ips/how-to/outbound-traffic)
- [DigitalOcean — Reserved IPs pricing](https://docs.digitalocean.com/products/networking/reserved-ips/details/pricing)
