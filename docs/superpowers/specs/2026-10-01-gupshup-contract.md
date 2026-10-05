# Gupshup WhatsApp contract (docs-verified reference)

Task 0 of the WhatsApp template-campaigns build. Researched **1 Oct 2026** from the official docs
only. No Gupshup API was called. **Where this file and the plan/spec disagree, this file wins**
(product owner's rule: adapt to Gupshup).

**Confidence labels**
- **Confirmed by doc**: a quote or JSON example below says it.
- **Conflict**: two official pages disagree. Both are quoted, and the code must accept both.
- **Inferred**: follows from documented facts but no page states it outright. Verify on first real traffic.
- **Not documented**: no official page found. Do not build on it.

**Method.** Gupshup's docs are ReadMe sites, and every page has a raw-markdown twin at `<page-url>.md`.
All Gupshup quotes come from those raw files, character for character, apart from markdown escapes
(`\_` written as `_`). Meta quotes come from `developers.facebook.com/documentation/...<page>.md`.
Support articles come from the Zendesk help-center JSON for the same article id. The open-source
code cited in section X1 is **not** official; it only corroborates what real traffic looks like.

---

## Sources (cited below by ID; every ID is a link)

| ID | Page | updatedAt |
|---|---|---|
| [G1](https://docs.gupshup.io/docs/template-messages) | Template messages (self-serve guide) | 2025-11-04 |
| [G2](https://docs.gupshup.io/reference/sending-text-template) | API ref: Text template send | 2025-11-03 |
| [G3](https://docs.gupshup.io/reference/postback-text-support) | API ref: Postback Text Support | 2025-11-03 |
| [G4](https://docs.gupshup.io/docs/message-events) | V2 Message events (self-serve) | 2025-11-03 |
| [G5](https://partner-docs.gupshup.io/docs/message-events) | Message events (partner docs, v2) | 2025-06-16 |
| [G6](https://docs.gupshup.io/docs/what-is-an-inbound-message) | Understanding Inbound Message | 2025-11-03 |
| [G7](https://docs.gupshup.io/docs/text) | Inbound: Text (incl. quick-reply button click) | 2025-11-03 |
| [G8](https://docs.gupshup.io/docs/interactive-messages) | Interactive Messages | 2025-11-04 |
| [G9](https://docs.gupshup.io/docs/subscriptions-and-notifications) | Subscriptions and notifications | 2025-11-03 |
| [G10](https://docs.gupshup.io/docs/webhooks-2) | Webhooks (dashboard tab) | 2026-07-29 |
| [G11](https://docs.gupshup.io/docs/what-is-a-webhook) | Webhook Key Points | 2025-11-03 |
| [G12](https://docs.gupshup.io/docs/user-event) | User events | 2025-11-03 |
| [G13](https://docs.gupshup.io/docs/error-and-status-messages) | Error Codes (same table at [partner](https://partner-docs.gupshup.io/docs/error-codes), 2026-06-26) | 2026-06-29 |
| [G14](https://docs.gupshup.io/reference/session-text-message) | API ref: session Text (`/wa/api/v1/msg`) | 2025-11-03 |
| [G15](https://docs.gupshup.io/reference/get-all-templates-for-an-app) | API ref: Get all templates for an app | 2025-11-03 |
| [G16](https://docs.gupshup.io/docs/system-events) | System events (template/account events) | 2025-11-04 |
| [G17](https://partner-docs.gupshup.io/reference/setsubscription-api-v3) | Partner API: Set subscription for an app | 2026-08-12 |
| [G18](https://partner-docs.gupshup.io/docs/events) | V3 Events | 2026-07-01 |
| [G19](https://partner-docs.gupshup.io/docs/pmp-events-1) | PMP Events (v2, after 1 Jul 2025) | 2025-06-11 |
| [G20](https://partner-docs.gupshup.io/docs/bsuid) | BSUID (contains the v2 `preference-event`) | 2026-09-03 |
| [G21](https://partner-docs.gupshup.io/docs/whatsapp-passthrough-apis-for-partners) | Passthrough (v3) APIs | 2026-07-21 |
| [G22](https://partner-docs.gupshup.io/docs/partner-rate-limits) | Partner Rate Limits | 2025-09-17 |
| [G23](https://partner-docs.gupshup.io/docs/marketing-messages-lite-mm-lite-api) | MM Lite API | 2026-01-29 |
| [G24](https://partner-docs.gupshup.io/docs/whatsapp-messages) | WhatsApp Messages (status table) | 2025-02-14 |
| [S1](https://support.gupshup.io/hc/en-us/articles/35183519921689) | Sunset of Optin Optout service | edited 2026-03-02 |
| [S2](https://support.gupshup.io/hc/en-us/articles/34057158742297) | /sm endpoints End of Life | edited 2025-06-13 |
| [S3](https://support.gupshup.io/hc/en-us/articles/42866242419609) | Gupshup Technical and Policy Updates 2025 | edited 2025-07-23 |
| [S4](https://support.gupshup.io/hc/en-us/articles/360012076319) | How many messages per second can I send? | edited 2022-02-11 |
| [S5](https://support.gupshup.io/hc/en-us/articles/43104565835673) | Meta Updates and Announcements 2025 | edited 2025-05-22 |
| [S6](https://support.gupshup.io/hc/en-us/articles/22857657759769) | FAQs: Template Pacing | edited 2023-09-11 |
| [S7](https://support.gupshup.io/hc/en-us/articles/53429741481113) | Why don't message and template counts match? | edited 2025-12-17 |
| [S8](https://support.gupshup.io/hc/en-us/articles/360014321199) | v1 to v2 migration | edited 2020-06-05 |
| [S9](https://support.gupshup.io/hc/en-us/articles/4413210201625) | Dial number vs WhatsApp ID mismatch | edited 2023-04-25 |
| [M1](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes) | Meta: Error codes | (no date shown) |
| [M2](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits) | Meta: Messaging Limits | (no date shown) |
| [M3](https://developers.facebook.com/documentation/business-messaging/whatsapp/throughput) | Meta: Throughput | (no date shown) |
| [M4](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/user_preferences) | Meta: user_preferences webhook | (no date shown) |
| [M5](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/button) | Meta: Button messages webhook | (no date shown) |
| [M6](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/marketing-templates) | Meta: Marketing templates (stop/resume) | (no date shown) |
| [M7](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/marketing-templates/per-user-limits) | Meta: Per-user marketing limits | (no date shown) |
| [M8](https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in) | Meta: Get opt-in | (no date shown) |
| [M9](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/status) | Meta: Status messages webhook | (no date shown) |
| [X1](https://github.com/glific/glific/tree/master/lib/glific_web/providers/gupshup) | **Not official.** Glific (open-source, runs on Gupshup v2 callbacks), last commits 2026-07-23 / 2026-09-03 | n/a |

---

## 0. The ten rules every task must follow

1. **Receipts are keyed by `payload.gsId`, then `payload.id`.** For `sent`, `delivered`, `read` and async
   `failed` events, `payload.id` is the **WhatsApp** message id and `payload.gsId` is the id the send
   API returned. Today's `payload["id"]` match is a **live bug** (§3, Delta 1).
2. **`gsId` can be missing**: on any event that arrives more than a week after the send, and in the
   docs' own MM Lite example. Store the WhatsApp id from the `enqueued` event
   (`payload.payload.whatsappMessageId`) and fall back to matching `payload.id` against it (§3.4).
3. **A 2xx from the send API means "submitted", not "sent".** Most per-recipient failures (not on
   WhatsApp, opted out, marketing cap, template paused) arrive later as `failed` **callbacks** (§1.8, §3.5).
4. **`sent`, `delivered` and `read` events must be switched on for the template app.** Only `enqueued`
   and `failed` are on by default (§4).
5. **The template app's webhook must use payload version 2** (Gupshup format). Our parser cannot read v3,
   which uses Meta's envelope (§5).
6. **A template quick-reply tap**: the button text is in `payload.payload.text` and
   `payload.payload.type == "button"`. The outer `payload.type` is `"quick_reply"` on one Gupshup page
   and `"text"` on another, so accept both (§6).
7. **The tap's `context.gsId` is the `messageId` of the template being answered**, which gives exact
   attribution. `context.id` is that template's WhatsApp id (§6.4).
8. **Neither Gupshup nor WhatsApp processes a typed "STOP".** Meta's opt-out is the user's
   "Offers and announcements → Stop" control. It produces a `preference-event` callback, and later
   marketing sends fail with **131050** (§7).
9. **Opt-in is not checked by Gupshup any more.** The opt-in APIs are sunset, and apps created after
   1 Aug 2025 don't support them. Don't call them (§2).
10. **The messaging limit is Meta's**: unique users over a **moving 24 h**, shared by every number in
    the business portfolio, with tiers 250 → 2,000 → 10k → 100k → unlimited. Gupshup's raw API ceiling
    is 20 msg/s (§9).

---

## 1. Template send API

### 1.1 Endpoint, method, headers. **Confirmed by doc**

[G1](https://docs.gupshup.io/docs/template-messages):

> | Header       | Value                             |
> | :----------- | :-------------------------------- |
> | Content-Type | application/x-www-form-urlencoded |
> | Apikey       | Your Gupshup account API key      |

The endpoint is `https://api.gupshup.io/wa/api/v1/template/msg`, and every sample uses `POST`.
[S2](https://support.gupshup.io/hc/en-us/articles/34057158742297) adds: *"Instead of
https://api.gupshup.io/sm/api/v1/template/msg , please switch to
https://api.gupshup.io/wa/api/v1/template/msg"*. `/sm` is dead; the plan already uses `/wa`.

Session messages (the existing `gupshup_send`) go to `POST https://api.gupshup.io/wa/api/v1/msg`
([G14](https://docs.gupshup.io/reference/session-text-message)). That is the same platform with
different fields.

### 1.2 Form fields. **Conflict on `src.name`; otherwise Confirmed**

[G2](https://docs.gupshup.io/reference/sending-text-template) (table):

> | Parameter     | Type   | Required | Description                                          | Example                          |
> | ------------- | ------ | -------- | ---------------------------------------------------- | -------------------------------- |
> | source        | string | Yes      | Sender WhatsApp Number                               | 919163xxxxx3                     |
> | src.name      | string | Yes      | App name that the source number belongs to           | DemoApp                          |
> | destination   | string | Yes      | Receiver WhatsApp Number                             | 917839xxxxx3                     |
> | template      | object | Yes      | Contains template id and list of template parameters | See below for detailed structure |
> | postbackTexts | array  | No       | List of objects containing postback text details     | See below for detailed structure |
> | channel       | string | No       | Messaging Platform Name                              | whatsapp                         |

The same page's OpenAPI block lists only `"required": ["source", "destination", "template"]`. It leaves
out `src.name`, and the [G1](https://docs.gupshup.io/docs/template-messages) text sample omits both
`channel` and `src.name`. **Always send all of `channel=whatsapp`, `source`, `destination`, `src.name` and `template`.**
The plan does this, and every source accepts it. The session API returns
`{ "message": "Invalid App Details", "status": "error" }` with HTTP 400
([G14](https://docs.gupshup.io/reference/session-text-message)). **Inferred**: a wrong `src.name`/`source`
pair on the template API fails the same way.

`source` ([G1](https://docs.gupshup.io/docs/template-messages)): *"Your registered WhatsApp Business API
phone number. The number must be in E. 164 format."*, sample `917834811114`. `destination`: *"User's phone
number."*, sample `919876543210`. Every self-serve sample uses digits only, without `+`. **Confirmed by doc
(examples).** One partner-style page, [G3](https://docs.gupshup.io/reference/postback-text-support), shows
`+1234567890`. Send digits only, exactly as the plan's `"91" + phone10` does.

App names ([quickstart](https://docs.gupshup.io/docs/quickstart-create-and-configure-access-api)): *"The app
name should be a minimum of six characters long and cannot contain any space or special characters."*

### 1.3 The `template` field: JSON shape, what `id` is, how `params` map. **Confirmed by doc**

[G1](https://docs.gupshup.io/docs/template-messages):

> `template` | object | See template object description | `{"id": "c6aecef6-bcb0-4fb1-8100-28c094e3bc6b","params": ["Agent","Local Address","Tracking code"]}`
>
> `id` — Unique identifier for a template. Use this API to get all template details for an app.
>
> `params` — Array of placeholders/variables in the template in the order of occurrence.

The `params` items are strings: in [G2](https://docs.gupshup.io/reference/sending-text-template) the
OpenAPI declares `"params": {"type": "array", ... "items": {"type": "string"}}`.

**`id` is Gupshup's template UUID.** It is not the template name and not Meta's id.
[G15](https://docs.gupshup.io/reference/get-all-templates-for-an-app) lists one object per template
(OpenAPI properties, condensed: the `"type": "string"` keys are dropped):

> `"elementName": {"description": "template name", "example": "event_test"}` ·
> `"externalId": {"description": "Meta template id", "example": 1666542899935607}` ·
> `"id": {"description": "Gupshup template id", "example": "312371e9-2771-463b-8cfd-cd8994b810ccf"}` ·
> `"languageCode": {"description": "language code of template", "example": "en"}`

**Inferred**: the send API takes no language field, and each template object carries its own
`languageCode`, so the Gupshup `id` already pins the language. `wa_templates.language` is informational.

**params → `{{1}}…`**: "in the order of occurrence". **Inferred** to mean `params[0]` fills `{{1}}`, and so
on, for templates whose placeholders appear in ascending order. That is Meta's positional rule, and
Meta's error **132000** is *"The number of variable parameter values included in the request did not
match the number of variable parameters defined in the template."*
([M1](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes)).
[G3](https://docs.gupshup.io/reference/postback-text-support) adds: *"All parameters in the main message
bubble and cards must be in the params array in order."* **Not documented**: how a variable in a TEXT
**header** is ordered against body variables. Don't use header variables, or test them first.

### 1.4 Templates with quick-reply buttons. **Confirmed by doc: nothing extra is required**

[G1](https://docs.gupshup.io/docs/template-messages), the "Quick reply" sample:

```curl
curl --location --request POST 'https://api.gupshup.io/wa/api/v1/template/msg' \
--header 'apikey: 2xxc4x4xx2c94xxxc2f9xx9d43xxxx8a' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data-urlencode 'source=917834811114' \
--data-urlencode 'destination=918x98xx21x4' \
--data-urlencode 'template={"id": "c6aecef6-bcb0-4fb1-8100-28c094e3bc6b","params": ["12323XXXX"]}'
```

Quick-reply buttons take no params. `postbackTexts` is **optional**
([G2](https://docs.gupshup.io/reference/sending-text-template)): *"list of objects containing postback text
details; include if postback text support required for quick-reply buttons"*, with `index` described as
*"Button index (0-based)"*. Its shape is `postbackTexts=[{"index":<qr_btn_index>,"text":"<postback_text>"}]`.
When it is sent, the tap comes back with `postbackText` (§6.1). That is an optional exact-attribution
channel (Delta 8).

### 1.5 Media-header templates. **Confirmed by doc**

[G1](https://docs.gupshup.io/docs/template-messages): *"`message` ... Required only if the template is of type
Media - Image, Video, Document(.pdf) or location."* Example: `{"type":"image","image":{"link":""}}`. Media
headers are out of scope for v1 (spec §3). If someone registers one, every send without `message` will
fail (Delta 17).

### 1.6 Success response. **Conflict on the `status` value; `messageId` is Confirmed**

[G1](https://docs.gupshup.io/docs/template-messages):

> Send message API requests received by our platform are processed asynchronously, and hence you will always
> get an HTTP_SUCCESS(200 to 299) response range if the API request made is correct. The API response includes
> an object with a Gupshup unique message identifier and status as submitted. Your callback URL/webhook will
> receive a message event stating the submitted message to the WhatsApp API client(which eventually sends the
> message to the customer) is enqueued or has failed.

```json 2XX
{
   "status":"submitted",
   "messageId":"ee4a68a0-1203-4c85-8dc3-49d0b3226a35"
}
```

> The Gupshup unique message identifier that is the `messageId` in the API response will help you track
> messages through the inbound message events - enqueued, failed, sent, delivered, and read that you obtain on
> your webhook/callback URL.

[G3](https://docs.gupshup.io/reference/postback-text-support) agrees: `202 {"status": "submitted",
"messageId": "3867730a-bb97-4ea5-bad6-e6e34201ce89"}`.

**But** [G2](https://docs.gupshup.io/reference/sending-text-template) says `| 202 | Success response |
{ "messageId": "message id", "status": "success" } |`, and its OpenAPI has `"enum": ["success"]`.

→ **Do not test `status`.** Success means 2xx, `status != "error"`, and a non-empty `messageId`. The plan's
`send_template` already does this. Its test fixtures use `"success"`; add a `"submitted"` case (Delta 9).

The response Content-Type is also inconsistent: [G1](https://docs.gupshup.io/docs/template-messages) lists
`| Content-Type | text/html |`, while [G2](https://docs.gupshup.io/reference/sending-text-template)'s OpenAPI
says `application/json`. → **Parse the body as JSON whatever the header says.** httpx's `r.json()` already
does. The success code documented by G2/G3 is 202.

### 1.7 Error responses. **Confirmed by doc for 400/401 (and 429 on sibling endpoints)**

[G2](https://docs.gupshup.io/reference/sending-text-template):

> | 400 | Error response; in case of a bad request          | `{ "message": "Invalid Destination", "status": "error" }`   |
> | 401 | Error response; in case of authentication failure | `{ "message": "Authentication Failed", "status": "error" }` |

[G14](https://docs.gupshup.io/reference/session-text-message) (`/wa/api/v1/msg`) also documents
`429 Too Many Requests  { "message": "Too Many Requests", "status": "error" }` and
`400 ... { "message": "Invalid App Details", "status": "error" }`. The quick-replies reference documents the
same 429. **Inferred**: the template endpoint can return 429 too, since it is the same platform; its own
page doesn't list it.

**A 2xx carrying `"status":"error"` is Not documented anywhere.** The plan's defensive check (Review Focus
#2) is harmless and should stay.

### 1.8 Per-recipient failures arrive as callbacks, not HTTP errors. **Confirmed by doc**

Per §1.6, the API *"will always get an HTTP_SUCCESS ... if the API request made is correct"*. Failures then
arrive as `message-event` `failed` callbacks. "Sync failed" (Gupshup-side, e.g. code 1002/1008) and "Async
failed" (WhatsApp-side, e.g. Meta 131026/131049/131050) are both callbacks (§3.2). The HTTP response only
rejects malformed requests: bad destination, bad app details, auth, rate.

---

## 2. Opt-in. **Confirmed by doc: Gupshup no longer requires or checks it, and the APIs are sunset**

[S1](https://support.gupshup.io/hc/en-us/articles/35183519921689) ("Prepare for Sunset of Optin Optout service
by Gupshup before 31st Aug 2024", edited 2026-03-02):

> NOTE : Optin Optout and Bulk Upload APIs for partners and self serve customers are now deprecated as of 1st Sep 2024
>
> LATEST : Optin Optout from gupshup.ai interface & APIs will be hidden from 31st March 2026
>
> We advise partners/customers to NOT register opt-in opt-outs via any single/bulk upload APIs or get list of
> optins through any self serve or partner APIs. This is irrespective of cloud API or on-premise hosting.
>
> Gupshup Partners and Businesses must manage optin optout data at their end. [...] As informed in our
> communication since 2023, Gupshup is not doing an optin optout check while sending messages to an end user,
> even if a number is registered as optin or optout for the particular app.
>
> Note : There is no endpoint by Meta to register the optins and this service was built by Gupshup

[S3](https://support.gupshup.io/hc/en-us/articles/42866242419609): *"Note that any new apps created after Aug 01,
2025 will not support Optin Optout and Block user legacy APIs."* The template app is new, so the legacy
`/sm/api/v1/app/opt/in/{appname}` endpoint doesn't exist for it (all of `/sm` is end-of-life,
[S2](https://support.gupshup.io/hc/en-us/articles/34057158742297)).

**What remains is Meta's consent policy, not an API check.**
[M8](https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in): *"Businesses
are required to obtain opt-in before messaging people on WhatsApp."* Older pages still say *"You can send
Template messages to users that you have opted-in"* ([G1](https://docs.gupshup.io/docs/template-messages)).
That is the policy statement, not a gate.

**Legacy residue.** [G13](https://docs.gupshup.io/docs/error-and-status-messages) still lists 1006/1007/1008
(*"Template Opt-in Failure"*, *"Neither Proxied Nor Opted-in"*) and 1012 (*"Number Opted Out"*), and the
[G4](https://docs.gupshup.io/docs/message-events) sync-failed example is `1008 "User is not Opted in and
Inactive"`. **Conflict** with S1. **Inferred**: these come from the retired opt-in service and should not
appear for the new app. Handle them as ordinary `failed` events if they do.

**Plan impact: none.** Never call an opt-in API (Delta 20).

---

## 3. Delivery events (`type: "message-event"`)

### 3.1 The envelope and the id rule. **Confirmed by doc**

[G4](https://docs.gupshup.io/docs/message-events) (the doc's own pseudo-JSON, verbatim):

```json message-event
{
   "app":"DemoAPI",
   "timestamp":1580546677791,
   "version":2,
   "type":"message-event",
   "payload":{
      "id":"59f8db90-c37e-4408-90ab-cc54ef8246ad"(Gupshup Message ID)|"gBEGkYaYVSEEAgnZxQ3JmKK6Wvg" (WhatsApp Message ID)
      "gsId": "ee4a68a0-1203-4c85-8dc3-49d0b3226a35" (Gupshup Message ID - This property is only applicable for DLR events)
      "type":"enqueued"|"failed"|"sent"|"delivered"|"read|"deleted"",
      "destination":"91XX985XX10X",
      "payload": ## This varies according to 'type' property value
   }
}
```

> Events received after a week of sending the message will not have the GSID available in the notification payload.

The field table (same page):

> `id` — This is Gupshup Message Id for message-event types: `enqueued` and `failed`
> In case of `failed` please check the below Sync and Async section.
> For the DLR events `sent`, `delivered`, `read` it is always WhatsApp Message ID.
>
> `gsId` — This is Gupshup Message Id and only present for message-event types: DLR events: `sent`, `delivered`, `read`.
>
> `ts` — Timestamp sent by Meta. This property is received for events `sent`, `delivered`, and `read`.
>
> `timestamp` — The time when Gupshup generated the event.

The partner copy ([G5](https://partner-docs.gupshup.io/docs/message-events)) writes the `sent` example with
explicit placeholders:

```Text sent
	"payload":
	{
		"id": "{{WA_MESSAGE_ID}}",
		"gsId": "{{GS_MESSAGE_ID}}",
		"type": "sent",
```

Ordering and timing:
- *"The order of these notifications in your app may not reflect the actual timing of the message status.
  View the timestamp to determine the timing, if necessary."* ([G4](https://docs.gupshup.io/docs/message-events))
- *"Read notifications will only be available for users who have read receipts enabled. [...] For status to be
  read, it must have been delivered. In some scenarios, such as when a user is on the chat screen and a message
  arrives, the message is delivered and read almost simultaneously. In this or other similar scenarios, the
  given notification will not be sent back, as it is implied that a message has been delivered if it has been
  read."* ([G4](https://docs.gupshup.io/docs/message-events)). So `read` can arrive with no `delivered`, and
  "Read" is a lower bound.
- *"You will receive inbound asynchronous message events on your callback URL with a 5-second delay to ensure
  that users have enough time to persist the original message-id received for an outbound message."*
  ([G6](https://docs.gupshup.io/docs/what-is-an-inbound-message))

### 3.2 Every event type, verbatim ([G4](https://docs.gupshup.io/docs/message-events) unless noted)

**enqueued**: *"This event is received when a message is successfully sent to the WhatsApp Business API client(docker)."*
```json
{
  "app": "DemoAPI",
  "timestamp": 1580546677791,
  "version": 2,
  "type": "message-event",
  "payload": {
    "id": "59f8db90-c37e-4408-90ab-cc54ef8246ad",
    "type": "enqueued",
    "destination": "91XX985XX10X",
    "payload": {
      "whatsappMessageId": "gBEGkYaYVSEEAgkD7bRi9syGnBk",
      "type": "session"
    }
  }
}
```
> `whatsappMessageId` — The WhatsApp message id generated while sending a message to an end-user on WhatsApp ·
> `type` — Indicates the type of message (example: `session`)

(**Not documented**: the `payload.payload.type` value for a template send. **Inferred**: `"template"`. Don't depend on it.)

**failed (sync)**: *"This event is received when the message sending has failed. You will receive the reason for failure on your callback URL"*. The table says *"`id` is Gupshup Message ID"*.
```json
{
    "app": "DemoAPI",
    "timestamp": 1580311136040,
    "version": 2,
    "type": "message-event",
    "payload": {
        "id": "ee4a68a0-1203-4c85-8dc3-49d0b3226a35",
        "type": "failed",
        "destination": "918x98xx21x4",
        "payload": {
            "code": 1008,
            "reason": "User is not Opted in and Inactive"
        }
    }
}
```

**failed (async)**: *"This event is received when messages have been failed by Whatsapp docker."* The table says *"`gsId` is Gupshup Message ID"*.
```json
{
    "app": "DemoAPI",
    "timestamp": 1663138637856,
    "version": 2,
    "type": "message-event",
    "payload": {
        "id": "9163a016-710e-41ee-978b-79a1adbd734e",
        "gsId": "72f61f22-5aa4-4615-a970-943edf6da01c",
        "type": "failed",
        "destination": "918x98xx21x4",
        "payload": {
            "code": 470,
            "reason": "Message failed to send because more than 24 hours have passed since the customer last replied to this number"
        }
    }
}
```

**sent**: *"The `sent` event is received when the message is sent to the end-user."*
```json
{
   "app":"DemoAPI",
   "timestamp":1580546677791,
   "version":2,
   "type":"message-event",
   "payload":{
      "id":"59f8db90-c37e-4408-90ab-cc54ef8246ad",
      "gsId":"ee4a68a0-1203-4c85-8dc3-49d0b3226a35",
      "type":"sent",
      "destination":"91XX985XX10X",
      "payload":{
         "ts":1585344475
      },
      "conversation":{
         "id":"532b57b5f6e63595ccd74c6010e5c5c7",
         "expiresAt":1518780636,
         "type":"marketing/authentication/utility/service/FEP/marketing_lite"
      },
      "pricing":{
         "policy":"CBP/PMP",
         "category":"marketing/authentication/utility/service/FEP/marketing_lite"
      }
   }
}
```
(This example reuses the enqueued sample UUID in `id`, which is a doc artifact. The table and the
[G5](https://partner-docs.gupshup.io/docs/message-events) placeholders settle it: `id` is the WhatsApp id. Since PMP,
the `conversation` object *"may be omitted unless webhook is for a free entry point conversation"*
([G19](https://partner-docs.gupshup.io/docs/pmp-events-1) and support 47379153369113), so don't read it.)

**delivered**: *"This event is received when the message sent by your business was delivered to the user's device."*
```json
{
  "app": "DemoAPI",
  "timestamp": 1585344476683,
  "version": 2,
  "type": "message-event",
  "payload": {
    "id": "gBEGkYaYVSEEAgnZxQ3JmKK6Wvg",
    "gsId": "ee4a68a0-1203-4c85-8dc3-49d0b3226a35",
    "type": "delivered",
    "destination": "918x98xx21x4",
    "payload": {
      "ts": 1585344476
    }
  }
}
```

**read**
```json
{
  "app": "DemoAPI",
  "timestamp": 1585344602933,
  "version": 2,
  "type": "message-event",
  "payload": {
    "id": "gBEGkYaYVSEEAgnZxQ3JmKK6Wvg",
    "gsId": "ee4a68a0-1203-4c85-8dc3-49d0b3226a35",
    "type": "read",
    "destination": "918x98xx21x4",
    "payload": {
      "ts": 1585344602
    }
  }
}
```

**deleted**: *"The `delete` event is received when a user deletes a message for everyone (not 'delete for me') which
they have sent to your WhatsApp Business API."* The partner copy prefixes it with *"[No longer supported by Meta]"*.
This concerns the **user's inbound** message, not ours.
```json
{
  "app": "demoapp",
  "timestamp": 1654703394680,
  "version": 2,
  "type": "message-event",
  "payload": {
    "id": "ABEGkZhngpgo-sJRwQ6dszYhU",
    "type": "deleted",
    "destination": "919867XX9135",
    "payload": {
      "ts": 1654703389
    }
  }
}
```

**MM Lite sent**: *"The DLR event for MM Lite will have a similar payload to the existing non MM Lite DLR payload,
except that the pricing category and conversation type will be "marketing_lite"."* Note: **no `gsId`** in this example.
```json
{
    "app": "AbdDef",
    "timestamp": 1729588576346,
    "version": 2,
    "type": "message-event",
    "payload": {
        "id": "wamid.HBgMOTE5OTg3OTkzMjc0FQIAERgSMTBEQjFDNkQzMUVBRjExRDI1AA==",
        "type": "sent",
        "destination": "919987993274",
        "payload": {
            "ts": 1729588575
        },
        "conversation": {
            "id": "b463ee712d95412611865832987e7a26",
            "expiresAt": 1729599000,
            "type": "marketing_lite"
        },
        "pricing": {
            "policy": "CBP/PMP",
            "category": "marketing_lite"
        }
    }
}
```

**Also listed**: *"Mismatch — This event is only triggered when the destination number provided in the API request does not
match the WhatsApp ID. The mismatch event does not require a subscription"*, with keys `wa_id` and `phone`. The doc
also lists *"`Other` events are miscellaneous events received asynchronously on your callback."* Ignore both.

**Real 2026 traffic shape** ([G20](https://partner-docs.gupshup.io/docs/bsuid), v2 subscription examples). On Cloud
API apps, a DLR's `id` and `gsId` are **two different UUIDs**, while inbound message ids are `wamid.`:
```json
"type": "message-event",
"payload": {
  "id": "cc3651a4-493b-4a38-b867-c547af202259",
  "gsId": "793df8da-2283-4774-a861-c2ffbae83823",
  "type": "sent",
```
So you can't tell the two ids apart by format. Use the field names.

### 3.3 Which field holds the send API's `messageId`, per event

The same sample UUID `ee4a68a0-1203-4c85-8dc3-49d0b3226a35` appears as the send API's `messageId`
([G1](https://docs.gupshup.io/docs/template-messages)), the sync-failed `payload.id`, and the
sent/delivered/read `payload.gsId` ([G4](https://docs.gupshup.io/docs/message-events)). That cross-page
consistency matches the tables.

| Event | `payload.id` is | `payload.gsId` | WhatsApp id lives in | **Send API `messageId` is in** | Confidence |
|---|---|---|---|---|---|
| `enqueued` | Gupshup id | absent | `payload.payload.whatsappMessageId` | **`payload.id`** | Confirmed by doc |
| `failed` (sync, Gupshup-side) | Gupshup id | absent | n/a | **`payload.id`** | Confirmed by doc |
| `failed` (async, WhatsApp-side) | not described; Inferred WhatsApp id | Gupshup id | `payload.id` (Inferred) | **`payload.gsId`** | Confirmed by doc (gsId) |
| `sent` | WhatsApp id | Gupshup id | `payload.id` | **`payload.gsId`** | Confirmed by doc |
| `delivered` | WhatsApp id | Gupshup id | `payload.id` | **`payload.gsId`** | Confirmed by doc |
| `read` | WhatsApp id | Gupshup id | `payload.id` | **`payload.gsId`** | Confirmed by doc |
| any DLR > 1 week after send | WhatsApp id | **absent** | `payload.id` | **not present** | Confirmed by doc |
| MM Lite `sent` (doc example) | `wamid.` | absent in example | `payload.id` | **not present in the example** | **Conflict**: [G23](https://partner-docs.gupshup.io/docs/marketing-messages-lite-mm-lite-api) says *"Webhooks / DLR payload will be the same as existing on V2 and V3, no change."* |
| `deleted` | WhatsApp id of the **user's** message | absent | n/a | n/a | Confirmed by doc |

**Our suspicion is CONFIRMED**: from `sent` onward, `payload.id` is the WhatsApp id and `payload.gsId` holds the
Gupshup id. **The existing `_persist` match `WaMessage.gupshup_id == payload["id"]` only works for `enqueued` and
sync `failed`.** It never matches `sent`, `delivered`, `read` or async `failed`. That is a **live bug**: today the
chat's outbound messages can't progress past `enqueued`/`submitted`, and an async failure (e.g. the 24h-window
code 470/131047) is never recorded (Deltas 1, 15).

**The rule to implement** (single key, then a fallback):
```
key = payload.get("gsId") or payload.get("id")       # Gupshup id whenever Gupshup sends one
match wa_campaign_recipients / wa_messages WHERE gupshup_id = key
if nothing matched and not payload.get("gsId"):      # >1 week late, or an MM Lite-style DLR
    match WHERE whatsapp_id = payload["id"]           # stored from enqueued.payload.payload.whatsappMessageId
```

**Corroboration (non-official, [X1](https://github.com/glific/glific/blob/master/lib/glific_web/providers/gupshup/controllers/message_event_controller.ex),
commit 2026-07-23).** Glific, a production Gupshup v2 consumer, uses exactly this key:
```elixir
bsp_message_id = get_in(params, ["payload", "gsId"]) || get_in(params, ["payload", "id"])
```

### 3.4 Storing the WhatsApp id. **Inferred, but needed**

The fallback above, and `context.id` attribution (§6.4), need the outbound message's **WhatsApp** id on our row.
The documented source is the `enqueued` event's `payload.payload.whatsappMessageId`, and Gupshup v3 shows the same
pairing (`"gs_id": "2baff204-…"`, `"id": "wamid.HBgM…"`, `"status": "enqueued"`,
[G18](https://partner-docs.gupshup.io/docs/events)). A later DLR's `payload.id` is also that id.

**Inferred**: `whatsappMessageId` on `enqueued` equals the `id` on later DLRs. Both are documented as "the WhatsApp
message id", but the doc samples differ (`gBEGkYaYVSEEAgkD7bRi9syGnBk` vs `gBEGkYaYVSEEAgnZxQ3JmKK6Wvg`, sample
artifacts). Verify on first traffic.

### 3.5 The `failed` payload: fields and codes. **Confirmed by doc**

Fields: `payload.payload.code` (number) and `payload.payload.reason` (string)
([G4](https://docs.gupshup.io/docs/message-events): *"`code` — The failure/exception code"*, *"`reason` — Message
failure reason with respect to the error code."*). The plan's `.get("reason")` is right. **Also keep `code`**:
text varies, and the same page spells 1002 both *"Number Does Not Exist On WhatsApp"* and *"Number Does Not Exists
On WhatsApp"*.

Gupshup codes, verbatim from the [G13](https://docs.gupshup.io/docs/error-and-status-messages) table:

| Code | Error Message | Details |
|---|---|---|
| 1002 | Number Not Exist On WhatsApp | Number Does Not Exist On WhatsApp |
| 1003 | Wallet Balance Low | Unable To Send Message / Check your wallet balance. |
| 1004 | Template Disabled Failure | Message sending failed as the user is inactive for session message, and template messaging is disabled. |
| 1005 | Template Match Failed | Message sending failed as the user is inactive for session message, and the template did not match. |
| 1006 / 1007 / 1008 | opt-in failures (legacy, §2) | e.g. 1008 "User is not opted in and inactive." |
| 1009 | Required parameter is missing | Message sending failed because of required parameter missing |
| 1010 / 1011 | Invalid Media Url / Invalid Media Size | |
| 1012 | Number Opted Out | Message Sending failed as the phone number is opted out. |
| 4001 | API Rate Limited | Oops! Something went wrong. Please stop sending messages and contact Gupshup Team with your error code. |
| 4002 | Invalid Response From WhatsApp | Invalid Response From WhatsApp |
| 4003 | No Template Match | Message Sending failed as the template did not match. |
| 4004 | Only CAPI Feature | Message type is only supported on Meta hosted cloud API. |
| 4005 | Paused Template | Message Sending failed as the template is paused. |

> Meta Error Codes — For Meta-related error codes, you can refer to the Cloud API Error Codes and On-Premises Error Codes.

Meta codes a template campaign will meet, verbatim from
[M1](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes)
(the solution column is abridged where marked "…"):

| Code | Meta description | Meta's solution (abridged) | What our app should do |
|---|---|---|---|
| 131026 | Unable to deliver message. Reasons can include: The recipient phone number is not a WhatsApp phone number. Recipient has not accepted the new Terms of Service and Privacy Policy. Recipient using an old WhatsApp version… | ask the user to confirm they can message you, accept ToS, update WhatsApp | §8 |
| 131047 | More than 24 hours have passed since the recipient last replied to the sender number. | Send the recipient a template message instead. | chat replies only (Task 8) |
| 131049 | This message was not delivered to maintain healthy ecosystem engagement. | …wait at least 24 hours before resending the template message. | failed; no retry < 24 h |
| 131050 | Unable to deliver the message. This recipient has chosen to stop receiving marketing messages on WhatsApp from your business. | Do not retry sending messages to this user as they will not be received. … subscribe to the user_preferences webhook. | opt-out (§7) |
| 130472 | Message was not sent as part of an experiment. | See Marketing Message Experiment. | failed, not our fault ([S5](https://support.gupshup.io/hc/en-us/articles/43104565835673): *"Businesses will not be charged if a marketing template is not delivered."*) |
| 130429 | Cloud API message throughput has been reached. | Try again later or reduce the frequency… | transient: back off |
| 131048 | Message failed to send because there are restrictions on how many messages can be sent from this phone number. This may be because too many previous messages were blocked or flagged as spam. | Check your quality status… | campaign-level: pause |
| 131056 | Too many messages sent from the sender phone number to the same recipient phone number in a short period of time. | Wait and retry… | transient |
| 132000 | The number of variable parameter values included in the request did not match the number of variable parameters defined in the template. | | template config: pause |
| 132001 | The template does not exist in the specified language or the template has not been approved. | | template config: pause |
| 132012 | Variable parameter values formatted incorrectly. | | template config: pause |
| 132015 | Template is paused due to low quality so it cannot be sent in a template message. | Edit the template… | pause campaign |
| 132016 | Template has been paused too many times due to low quality and is now permanently disabled. | Create a new template with different content. | pause campaign |
| 131042 | There was an error related to your payment method. | | account-level: pause |
| 131031 | The WhatsApp Business Account associated with the app has been restricted or disabled for violating a platform policy… | | account-level: pause |

**Inferred**: on a Cloud API app, a Gupshup v2 async `failed` carries Meta's numeric code in `payload.payload.code`
and Meta's title in `reason`. Gupshup v3 shows `"errors": [{"code": 131047, ... "title": "Message failed to
send..."}]` ([G18](https://partner-docs.gupshup.io/docs/events)). The v2 doc example shows the old On-Prem code 470.

---

## 4. Do template-app events arrive on the same URL as inbound messages? Per-app settings

**Yes. Callbacks are per Gupshup app (subscription per `appId`), and one subscription can carry both inbound
messages and message events.** **Confirmed by doc**:

- *"Customers' messages sent to your WhatsApp Business Phone Number are routed to your Webhook. [...] the platform
  logs the message and sends a notice (HTTPS POST request) to the Webhook defined in your app's settings."*
  ([G11](https://docs.gupshup.io/docs/what-is-a-webhook))
- *"For each message you send, a notification about the status of the message will be sent to your webhook
  callback."* ([G24](https://partner-docs.gupshup.io/docs/whatsapp-messages))
- The subscription API is `POST https://partner.gupshup.io/partner/app/:appId/subscription`, with per-subscription
  `modes`, `url` and `version` ([G17](https://partner-docs.gupshup.io/reference/setsubscription-api-v3)).
  *"You can now set subscriptions for both V2 and V3 APIs, with the flexibility to configure up to maximum five
  subscriptions per app."* ([S3](https://support.gupshup.io/hc/en-us/articles/42866242419609))

**Inferred**: events for a message sent through the template app (its `src.name`/`source`) go to the **template
app's** subscription, never to the chat app's URL. Our two webhooks share `_persist`, so this needs no code, but
**receipt matching must not filter by app**. It doesn't.

**Per-app setting needed: YES.** **Confirmed by doc**:

- [G10](https://docs.gupshup.io/docs/webhooks-2): *"You have the option to select checkboxes for both **Message
  events** and **System events** to ensure you receive notifications on your webhook."* and *"By default,
  **Enqueued** and **Failed** message events will be turned on, ensuring that you receive notifications for these
  specific events."*
- [G9](https://docs.gupshup.io/docs/subscriptions-and-notifications) table (cells transcribed): the column
  "Events that require subscription" lists **System Events** (Template events; Account events) and **Message Events**
  (Read, Sent, Delivered, Delete, Others). The column "Events that do not require subscription" lists **User Events**
  (Sandbox-start, Opted-in, Opted-out), **Message Events** (Enqueued, Failed, Mismatch), **Message (User messages)**
  and **Billing Events**.
- **Conflict / update** ([S3](https://support.gupshup.io/hc/en-us/articles/42866242419609)): *"FAILED Mode for both
  v2 and V3 APIs: [...] You must subscribe to FAILED mode for subscriptions instead of the old OTHERS mode for new
  subscriptions created after 18th feb 2025 to receive failed message events"*. The same goes for *"BILLING Mode
  [...] You must subscribe to BILLING mode for subscriptions for new subscriptions created after 18th feb 2025"*.
  The new template app's subscription is new, so **tick Failed explicitly**. G10 says it's on by default; check
  that it is.

→ **Template app setup checklist** (dashboard → app → Webhooks tab, or the partner subscription API):

| Mode | Needed for | |
|---|---|---|
| Message (inbound user messages) | replies, button taps, STOP | required |
| Sent, Delivered, Read | the funnel | **required: off by default** |
| Failed | failed rows + reasons | required; verify it is on |
| Enqueued | captures `whatsappMessageId` (§3.4) | recommended (default on) |
| Billing | per-message cost (`references.gsId`) | optional |
| Template (system event) | template paused/disabled/category changes | optional, useful |
| Account (system event) | tier/limit changes | optional |

[G17](https://partner-docs.gupshup.io/reference/setsubscription-api-v3) lists these mode names:
*"NONE, READ, DELIVERED, SENT, DELETED, FLOWS_MESSAGE,PAYMENTS, ALL, OTHERS,COEXISTENCE,TEMPLATE,ACCOUNT"*. The
Modes section adds MESSAGE, BILLING, FAILED and ENQUEUED.

**Webhook contract** ([G11](https://docs.gupshup.io/docs/what-is-a-webhook); identical at partner
[webhook-key-points](https://partner-docs.gupshup.io/docs/webhook-key-points), 2026-09-22). The existing `_accept`
already complies:

> The webhook should return **HTTP_SUCCESS** (code: 2xx) with an empty response.
> Failing to do so within 10 seconds, our platform will consider that the notification has failed and attempt again after a brief interval.
> The webhook should accept user events: **sandbox-start**.

The retries imply **duplicate deliveries**, so handlers must be idempotent (Delta 13).

The partner API also lets you set custom headers per subscription: *"meta json string (meta json key and value will
be passed to the subscription URL as headers , users can set custom headers for the URL which can be used for
authentication)"*, e.g. `meta={"headers":{"X-Gupshup-Webhook-Secret":"xxxxxxxxxxxxxxxxx"}}`
([G17](https://partner-docs.gupshup.io/reference/setsubscription-api-v3)). That would be an alternative to `?token=`;
it is optional.

---

## 5. Callback payload version: v2 (Gupshup format) vs v3 (Meta format)

**How it is chosen: per subscription, `version` = 2 or 3.** **Confirmed by doc**
([G17](https://partner-docs.gupshup.io/reference/setsubscription-api-v3)): *"version | Version | Mandatory | Should be
one of the following : 2,3"*. An app may hold both kinds. If it does, each event goes to both
([G21](https://partner-docs.gupshup.io/docs/whatsapp-passthrough-apis-for-partners)):

> 2. A new v3 callback subscription is mandatory to receive incoming events in Meta format.
>
> All the existing APIs will work with the existing subscriptions and newer APIs will require new v3 subscriptions.
>
> 3. Not available on the UI.
> 4. If a customer has subscribed to both v2 and v3 (passthrough) callback subscriptions for incoming messages and
>    events, they will get such events on both callbacks. Customers have to handle the deduplication logic at their end.

**Inferred**: a webhook added in the self-serve dashboard is **v2**. G21 says the v3/passthrough flow is "Not
available on the UI", and every self-serve page documents v2 payloads. **Not documented**: whether today's
dashboard offers a version picker. **Verify on the first callback**: the body must contain `"version": 2`.

**The two formats are not compatible.** v3 is Meta's envelope plus `gs_id`/`gs_app_id`
([G18](https://partner-docs.gupshup.io/docs/events)):
```json
{ "entry": [ { "changes": [ { "field": "messages", "value": { "messaging_product": "whatsapp",
  "statuses": [ { "gs_id": "7daeb742-f2dc-4c09-90e0-d879d20f7b98", "id": "wamid.HBgMOTE5MTYzODA1ODczFQIAERgSMDQ4Rj...",
  "recipient_id": "91****73", "status": "sent", "timestamp": "1710930461" } ] } } ] } ],
  "gs_app_id": "82ed52f4-30c0-4f12-81b4-e7ad07bd41de", "object": "whatsapp_business_account" }
```
(Condensed from G18's example; field names unchanged.) Our `_accept` reads `body.get("type")`, which is absent in v3,
so `_persist` would silently store nothing.

**What the existing v2 parser requires on the NEW template app**:
1. Subscription **version 2**. v2 is JSON: *"Version v2 content type is application/json; charset=utf-8"*
   ([S8](https://support.gupshup.io/hc/en-us/articles/360014321199)). v1 was form-encoded and only for apps from
   before 28 Jan 2020.
2. The modes in §4.
3. URL `…/v1/gupshup/template-webhook?token=<GUPSHUP_TEMPLATE_WEBHOOK_SECRET>`. The secret must be set in Render
   **before** adding the URL, because the route answers 503 in prod without it and Gupshup expects 2xx.
4. **New apps can't use the legacy "set callback URL" API.** [S3](https://support.gupshup.io/hc/en-us/articles/42866242419609):
   *"Any new apps created after Aug 01, 2025 will not support [...] Callback URL APIs."* Use the dashboard Webhooks
   tab or the subscription API.

---

## 6. Inbound quick-reply button taps

### 6.1 Doc A: `payload.type = "quick_reply"`. **Confirmed by doc**

[G3](https://docs.gupshup.io/reference/postback-text-support), "Expected Response On Callback":
```json
{
    "app": "<APP_NAME>",
    "phone": "<APP_PHONE_NUMBER>",
    "timestamp": 1712230664720,
    "version": 2,
    "type": "message",
    "payload": {
        "id": "<MESSAGE_ID>",
        "source": "<PHONE_NUMBER>",
        "type": "quick_reply",
        "payload": {
            "text": "<BUTTON_TEXT>",
            "type": "button",
            "postbackText": "<POSTBACK_TEXT>"
        },
        "sender": {
            "phone": "<SENDER_PHONE>",
            "name": "<SENDER_NAME>",
            "country_code": "91",
            "dial_code": "<SENDER_PHONE>"
        },
        "context": {
            "id": "<MESSAGE_ID>",
            "forwarded": false,
            "frequently_forwarded": false
        }
    }
}
```

### 6.2 Doc B: `payload.type = "text"`. **Confirmed by doc, so Conflict with 6.1**

[G7](https://docs.gupshup.io/docs/text), "User Clicks The Button On A Quick Reply Template Message":

> When your customer clicks on a quick reply button, a response goes to your Webhook URL.
>
> To understand the context of a message reply, we include the context object. The context object provides the
> Gupshup message-id(property: `gsId`) of the message the user has replied to and the WhatsApp message-id(property:
> `id`) of the original message. In addition to this payload, the object provides the button text that the user clicked.

```json
{
   "app": "docdeck",
  "timestamp": 1718007189549,
  "version": 2,
  "type": "message",
  "payload": {
    "id": "ABEGkZUTIXZ0Ago6jWqOZm-Sz0WD",
    "source": "91XXXXX4",
    "type": "text",
    "payload": {
      "text": "View Account Balance",
      "type": "button"
    },
    "sender": {
      "phone": "91XXXXX4",
      "name": "SJ",
      "country_code": "91",
      "dial_code": "9XXXXX4"
    },
    "context": {
      "id": "gBEGkYaYVSEEAgnPFrOLcjkFjL8",
      "gsId": "9b71295f-f7af-4c1f-b2b4-31b4a4867bad"
    }
  }
}
```

**Corroboration for 6.1 (non-official, [X1](https://github.com/glific/glific/blob/master/lib/glific_web/providers/gupshup/router.ex),
commit 2026-07-23).** Glific routes the v2 `quick_reply` type to its plain-text parser, which reads
`payload.payload.text`, and routes session `button_reply` to its interactive parser, which reads `title`:
```elixir
post("/quick_reply", MessageController, :text)
post("/button_reply", MessageController, :quick_reply)
post("/list_reply", MessageController, :list)
```
**Most likely real value: `"quick_reply"`.** Accept both.

### 6.3 What both docs agree on

| Field | Value | Confidence |
|---|---|---|
| `payload.payload.text` | the button label the user tapped | Confirmed (both pages) |
| `payload.payload.type` | `"button"` | Confirmed (both pages): **the reliable "this is a tap" flag** |
| `payload.payload.postbackText` | the `postbackTexts` text sent with that button index | Confirmed ([G3](https://docs.gupshup.io/reference/postback-text-support)). Not documented when none was sent |
| `payload.id` | the inbound message's own WhatsApp id | Confirmed ([G6](https://docs.gupshup.io/docs/what-is-an-inbound-message)) |
| `payload.type` | `"quick_reply"` or `"text"` | **Conflict** |
| `title` / `id` / `reply` keys | **not part of a template tap** | Not documented for templates. `button_reply` (session interactive reply buttons, which we don't send) is listed as a type in [G6](https://docs.gupshup.io/docs/what-is-an-inbound-message) with no example. Glific reads its `title` |

For reference, Meta's raw tap (what v3 would carry,
[M5](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/button)):
*"A WhatsApp user taps a quick-reply button in a template message."* →
`"type": "button"`, `"button": {"payload": "Unsubscribe", "text": "Unsubscribe"}`, and
`"context": {"from": "15550783881", "id": "wamid.HBgLMTQxMjU1NTA4MjkVAgASGBQzQUNCNjk5RDUwNUZGMUZEM0VBRAA="}`, where
`<CONTEXTUAL_WHATSAPP_MESSAGE_ID>` is *"WhatsApp message ID of the message containing the button the WhatsApp user tapped."*

### 6.4 The `context` object. **Confirmed by doc: it carries BOTH ids**

[G6](https://docs.gupshup.io/docs/what-is-an-inbound-message): *"The context object is **optional**, it will only be
included when someone replies to one of your messages. It contains information about the content of the original
message, such as the Gupshup ID and WhatsApp ID of the message."*

| Key | Meaning | Source |
|---|---|---|
| `context.gsId` | the **Gupshup** message id of the message replied to, which is **our send API `messageId`** for a campaign template | [G7](https://docs.gupshup.io/docs/text) prose (above), [G8](https://docs.gupshup.io/docs/interactive-messages) examples |
| `context.id` | the **WhatsApp** message id of the message replied to | [G7](https://docs.gupshup.io/docs/text) prose, Meta [M5](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/button) |
| `context.forwarded`, `context.frequently_forwarded` | booleans | [G3](https://docs.gupshup.io/reference/postback-text-support), [G8](https://docs.gupshup.io/docs/interactive-messages) |

(The G6/G7 tables label both keys *"…identifier for the inbound message"*. That is a copy-paste slip; the prose on
the same pages is unambiguous.)

**Caveat**: the [G3](https://docs.gupshup.io/reference/postback-text-support) tap example has **no `gsId`** in
`context`. **Inferred**: like DLRs (§3.1), `context.gsId` may be absent for messages older than a week. Glific
([X1](https://github.com/glific/glific/blob/master/lib/glific/providers/gupshup/message.ex)) takes
`context.gsId || context.gs_id || context.id`.

A typed reply made with WhatsApp's swipe-to-reply on the template bubble also carries `context`
([G7](https://docs.gupshup.io/docs/text), "User Replies To Your Message"). That gives exact attribution for those
replies too. This is optional.

### 6.5 Recommended handling (Deltas 6–8)

```
inner = payload["payload"]; kind = payload["type"]
is_tap = inner.get("type") == "button" or kind in ("quick_reply", "button_reply")
text   = inner.get("text") or inner.get("title")     # title only for session button_reply
store msg_type = "quick_reply" when is_tap            # normalise BOTH documented shapes
answered = recipients.gupshup_id = context.gsId       # exact
        or recipients.whatsapp_id = context.id        # exact fallback
        or the time rule in RECIPIENTS_SQL            # last resort
```

---

## 7. Opt-out handling ("STOP")

| Question | Answer | Confidence |
|---|---|---|
| Does Gupshup auto-handle "STOP"? | **No.** Its opt-in/opt-out service is sunset, and *"Gupshup is not doing an optin optout check while sending messages to an end user, even if a number is registered as optin or optout"* ([S1](https://support.gupshup.io/hc/en-us/articles/35183519921689)). | Confirmed by doc |
| Does WhatsApp/Meta process a typed "STOP"? | **Not documented.** Meta's opt-out mechanism is a UI control (next row). [M8](https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in) puts the duty on the business: *"Provide clear instructions for how people can opt out of receiving specific categories of messages, and honor these requests."* A typed STOP is an ordinary inbound `text`. | Inferred |
| Meta's real opt-out | [M6](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/marketing-templates): *"WhatsApp provides a setting, **Offers and announcements**, that allows WhatsApp users to indicate their interest level in marketing messages sent from your business, and to stop or resume delivery of marketing messages from your business entirely."* | Confirmed by doc |
| Does it block further sends? | **Yes, for MARKETING templates only.** [M6](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/marketing-templates): *"If you attempt to send a marketing template to a WhatsApp user who has stopped marketing template messages from your business, the API will process the request but not send the message. Instead, the API will trigger a status messages webhook with: `status` set to `failed`, `code` set to `131050`, `title` set to `Unable to deliver the message. This recipient has chosen to stop receiving marketing messages on WhatsApp from your business`"* | Confirmed by doc (Meta). Gupshup v2 mapping to a `failed` event with code 131050 is Inferred |
| Callback when the user stops/resumes | Meta `user_preferences` ([M4](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/user_preferences)): *"A WhatsApp user stops marketing messages. / A WhatsApp user resumes marketing messages."* *"This webhook triggers only when a user stops or resumes marketing messages. It does not trigger when a user indicates **Interested** or **Not interested** feedback"* | Confirmed by doc |
| How Gupshup v2 delivers it | `type: "preference-event"`. Documented **only** on the partner BSUID page ([G20](https://partner-docs.gupshup.io/docs/bsuid)), headed *"user_preferences (Both v2 and v3 events are supported)"*. JSON below. **Not documented**: which subscription mode carries it on a v2 self-serve app | Confirmed by doc (one page) |
| Legacy Gupshup `user-event` `opted-out` | [G12](https://docs.gupshup.io/docs/user-event): *"This event is received when an end user opt-out from receiving notification from a business"* `{"type":"user-event","payload":{"phone":"918x98xx21x4","type":"opted-out"}}`. Tied to the sunset opt-in service. | Inferred: won't fire for a new app |
| Error when sending to an opted-out user | **131050** (Meta marketing opt-out, async `failed`). Legacy Gupshup **1012** *"Number Opted Out"* ([G13](https://docs.gupshup.io/docs/error-and-status-messages)) | Confirmed by doc |
| User blocked our business number | **Not documented** as an error. [S7](https://support.gupshup.io/hc/en-us/articles/53429741481113): *"Some sent messages may not get delivered (e.g., user blocked the number)"*. Expect `sent` that never becomes `delivered` | Inferred |

[G20](https://partner-docs.gupshup.io/docs/bsuid), *"Example of v2 payload when enableBSUID is true"*. Without BSUID,
`userid`/`parent_user_id` are absent. The `//` comments and the missing comma are in the doc:
```
{
  "app": "<appName>",
  "appId": "<appId>",
  "timestamp": <timestamp>,
  "version": 2,
  "type": "preference-event",
  "payload": {
    "type": "user_preferences",
    "payload": {
      "user_preferences": [
        {
          "wa_id": "919297545638",
          "userid": "user_id",//added
          "parent_user_id" : "parent_user_id"
          "detail": "User requested to stop marketing messages",
          "category": "marketing_messages",
          "value": "stop",
          "timestamp": <timestamp>
        }
      ]
    }
  }
}
```
Meta's values ([M4](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/user_preferences)):
`"category": "marketing_messages"`, `"value": "stop"` or `"resume"`.

**So the plan's typed-STOP rule (Task 12) is our own policy layer.** It is fine to keep: it honours the request
on both numbers, and Meta requires honouring opt-outs. But it **misses every signal Gupshup and Meta actually
send** (Delta 12).

---

## 8. "Not a WhatsApp user"

| Signal | Text | Where | Confidence |
|---|---|---|---|
| Gupshup **1002** (sync `failed`, `payload.id` = our messageId) | *"Number Not Exist On WhatsApp"* / *"Number Does Not Exist On WhatsApp"* (the G4 async table also spells it *"Number Does Not Exists On WhatsApp"*) | [G13](https://docs.gupshup.io/docs/error-and-status-messages), [G4](https://docs.gupshup.io/docs/message-events) | Confirmed by doc |
| Meta **131026** (async `failed`, `payload.gsId` = our messageId) | *"Unable to deliver message. Reasons can include: The recipient phone number is not a WhatsApp phone number. Recipient has not accepted the new Terms of Service… Recipient using an old WhatsApp version"* | [M1](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes) | Confirmed by doc. A **bucket** code, not specific to "no account" |

**Not confirmed**: whether 1002 still occurs on Cloud API apps. 1002 came from Gupshup's pre-send contact check,
and [S9](https://support.gupshup.io/hc/en-us/articles/4413210201625) notes *"the deprecation of the check contact
API"*. **Inferred**: on today's Cloud API apps, a number without WhatsApp mostly surfaces as async **131026**.

**Suggested rule** (the policy is yours to set; the facts above drive it):
- **1002**: permanent "no WhatsApp". Tag the contact and skip it in every future campaign.
- **131026**: "undeliverable". Exclude it from automatic repeats and auto-campaign runs. A manual Retry stays
  allowed but should warn, because the user may update WhatsApp or accept the ToS.
- Match on **`code`**, never on `reason` text (spelling varies, §3.5).

---

## 9. Rate limits

| Limit | Value | Source | Confidence |
|---|---|---|---|
| Gupshup API send rate | *"You can send up to 20 messages/sec."* | [S4](https://support.gupshup.io/hc/en-us/articles/360012076319) (2022) | Confirmed by doc (old article) |
| Gupshup throttle response | `429 Too Many Requests { "message": "Too Many Requests", "status": "error" }` | [G14](https://docs.gupshup.io/reference/session-text-message) (not listed on the template page) | Confirmed for `/msg`; Inferred for `/template/msg` |
| Gupshup code 4001 | *"API Rate Limited — Oops! Something went wrong. Please stop sending messages and contact Gupshup Team with your error code."* | [G13](https://docs.gupshup.io/docs/error-and-status-messages) | Confirmed by doc |
| Partner APIs (`partner.gupshup.io`) | *"For all the rest of the APIs, the rate will be 10 / 1 second."* **Doesn't apply** to `api.gupshup.io/wa/api/v1/*` | [G22](https://partner-docs.gupshup.io/docs/partner-rate-limits) | Confirmed by doc |
| Meta throughput | *"For each registered business phone number, Cloud API supports up to 80 messages per second (mps) by default, and up to 1,000 mps by automatic upgrade."* Exceeding it returns *"error code `130429`"* | [M3](https://developers.facebook.com/documentation/business-messaging/whatsapp/throughput) | Confirmed by doc |
| Meta pair rate limit | 131056 *"Too many messages sent from the sender phone number to the same recipient phone number in a short period of time."* | [M1](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes) | Confirmed by doc |

The plan's 30/min per campaign is far below all of these.

**Meta's messaging limit (the "tier")**, verbatim from [M2](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits):

> Messaging limits are the maximum number of unique WhatsApp user phone numbers your business can deliver messages to,
> outside of a customer service window, within a moving 24-hour period.
>
> Messaging limits are calculated and set at the business portfolio level and are shared by all business phone numbers
> within a portfolio. This means that if a business portfolio has multiple business phone numbers, it's possible for one
> number to consume all of the portfolio's messaging capability within a given period.
>
> Newly created business portfolios have a messaging limit of 250, but this messaging limit can be increased to:
> - 2,000 (by completing a scaling path)
> - 10,000 (via automatic scaling)
> - 100,000 (via automatic scaling)
> - Unlimited (via automatic scaling)
>
> [...] your portfolio's limit increases by one level within 6 hours. [...] Your business phone number's current messaging
> limit is displayed in the WhatsApp Manager > **Account tools** > **Messaging limits** panel

**Conflict**: Gupshup's `tier-event` doc still enumerates
*"TIER_250, TIER_1K, TIER_10K, TIER_100K, and TIER_UNLIMITED"*
([G16](https://docs.gupshup.io/docs/system-events)), and the spec (§10) says *"250 … 1,000 after business
verification"*. Meta's current page says the step after 250 is **2,000**. Meta owns this limit, so Meta's
page wins. **Not documented** (on the pages fetched): which error is returned when the limit is exceeded.

**Per-user marketing cap** ([M7](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/marketing-templates/per-user-limits)):
*"Each marketing template message delivered counts towards the per-user marketing limit. If a WhatsApp user responds to
a marketing message, it starts a 24-hour customer service window. Marketing messages sent within this window do not count
towards the limit."* and *"If your WhatsApp Business account (WABA) attempts to resend marketing messages multiple times
within a 24-hour period to users who have already reached their messaging limit, further delivery attempts to these users
may be unavailable for up to 24 hours and error code 131049 will be returned."*

**Template pacing** ([S6](https://support.gupshup.io/hc/en-us/articles/22857657759769)), marketing templates only:
*"Template Pacing occurs within the initial 30 minutes of a campaign"*; queued messages may be *"sent/dropped"*, and
*"dropped events will have error code 132015"*. Expect a gap between "submitted" and "sent" on large campaigns.

**MM Lite routing** ([G23](https://partner-docs.gupshup.io/docs/marketing-messages-lite-mm-lite-api)): *"As of 16 June
2025, Gupshup switched on the v2 mm lite flag directly, thus routing all marketing messages sent over V2 through MM Lite,
if customer accepts the onboarding intent."* and *"FOR APPS CREATED FROM AUG 2025 : MM Lite onboarding happens while
go-live."* **Inferred**: the template app's MARKETING templates go via MM Lite. Their DLRs say
`"category": "marketing_lite"`, and the only MM Lite DLR example has no `gsId` (§3.3).

---

## 10. Other documented constraints the plan must respect

1. **Template id**: Gupshup UUID (§1.3). The release notes say the dashboard can *"search for templates using their IDs"*
   ([release notes](https://docs.gupshup.io/page/previous-release-notes)).
2. **Phone formats**: digits-only E.164 for `source` and `destination` (§1.2). Inbound `payload.source` and
   `sender.phone` are E.164 without `+` ([G6](https://docs.gupshup.io/docs/what-is-an-inbound-message)).
   The existing `normalize_phone` is correct.
3. **Apikey**: [G1](https://docs.gupshup.io/docs/template-messages) says *"Your Gupshup account API key"*; Settings also
   shows an *"App API Key — API key for accessing the app with API"*
   ([settings](https://docs.gupshup.io/docs/settings)). **Inferred**: if both apps are in one account, one key may serve
   both. A separate `GUPSHUP_TEMPLATE_API_KEY` is still right; it can hold the same value.
4. **`message` is required for media/location templates** (§1.5).
5. **The 24h window is per number.** Session replies outside it fail **asynchronously** (async-failed example code 470:
   *"Message failed to send because more than 24 hours have passed since the customer last replied to this number"*;
   Meta 131047). They are not HTTP errors (§3.2, Delta 15).
6. **Callback delay and retries**: events are delayed about 5 s so you can persist the `messageId` (§3.1). Callbacks are
   retried if not acked in 10 s (§4), so handlers must be idempotent.
7. **Template status events** (optional TEMPLATE mode, [G16](https://docs.gupshup.io/docs/system-events)):
   `{"type":"template-event","payload":{"id":"<gupshup template id>","status":"rejected/approved/deleted/disabled","elementName":"abcd","languageCode":"en_US",...}}`,
   plus `"status": "paused"` with a `description`. These let the app stop a campaign whose template was paused.
8. **New-app restrictions** ([S3](https://support.gupshup.io/hc/en-us/articles/42866242419609)): apps created after
   1 Aug 2025 lose the `/sm` endpoints, the template-matching service, the legacy opt-in/opt-out and block-user APIs,
   and the callback-URL APIs. The plan uses none of them.
9. **`biz_opaque_callback_data`**: the changelog says it *"is returned in sent, delivered, and read message webhooks"*
   ([changelog](https://docs.gupshup.io/changelog/whatsapp-self-serve-platform)), but **how to pass it on
   `/wa/api/v1/template/msg` is Not documented**. Don't use it.
10. **Billing events** (if subscribed) carry `references.gsId` (= our `messageId`) and `deductions.category`
    (`marketing`/`marketing_lite`/…) ([G19](https://partner-docs.gupshup.io/docs/pmp-events-1)). This would give
    per-recipient cost. Optional.

---

## 11. Could not confirm from documentation (verify on first real traffic)

1. Whether the self-serve dashboard's Webhooks tab offers a v2/v3 choice, and its default. **Inferred** v2.
2. The outer `payload.type` of a template quick-reply tap: `"quick_reply"` ([G3](https://docs.gupshup.io/reference/postback-text-support),
   and Glific) or `"text"` ([G7](https://docs.gupshup.io/docs/text)). Handle both.
3. Whether `context.gsId` is always present on a tap. The G3 example omits it.
4. Whether `postbackText` is present (or equals the button text) when no `postbackTexts` were sent.
5. Whether `enqueued.payload.payload.whatsappMessageId` equals the later DLR `payload.id`, and what `payload.payload.type` is for templates.
6. Whether MM Lite DLRs on the v2 subscription carry `gsId`. The G4 example has none, while [G23](https://partner-docs.gupshup.io/docs/marketing-messages-lite-mm-lite-api) says the payload is unchanged.
7. Whether a v2 self-serve app receives `preference-event`, and which mode it needs. It is documented only on the partner BSUID page.
8. Whether v2 async `failed` on Cloud API carries Meta's 131xxx code in `payload.payload.code`. The examples show 470 and 1008.
9. Whether Gupshup 1002 still occurs on Cloud API apps, vs Meta 131026.
10. Which error Meta returns when the portfolio messaging limit is exceeded.
11. Whether `/wa/api/v1/template/msg` returns 429. It is documented only for `/wa/api/v1/msg` and quick-replies.
12. A 2xx with `"status":"error"`. No doc shows one; the plan's defensive handling is fine.
13. What a send to a user who blocked our number produces. [S7](https://support.gupshup.io/hc/en-us/articles/53429741481113) implies "sent but never delivered".

**Fastest read-only way to settle 1–8.** After the template app is configured (Task 10's manual launch to 1–2
internal numbers), read `GET /v1/gupshup/recent` (admin; last 50 raw callbacks) or the Render log lines
`gupshup callback app=template …` for:
- `"version"`;
- an `enqueued` event's `payload.payload`;
- a `sent`/`delivered`/`read` event's `id` vs `gsId`;
- one button tap's `payload.type`, `payload.payload` and `context`.

---

## Deltas vs our plan and existing code

Ordered by severity. Each item gives what it **affects**, what the code or plan does **today**, what **Gupshup**
documents, the change to **do**, and the **source**.

**CRITICAL: data silently never arrives**

1. **LIVE BUG: receipt matching uses the wrong field.**
   - Affects: existing `_persist` (`message-event` branch).
   - Today: `update(WaMessage).where(WaMessage.gupshup_id == payload["id"])`.
   - Gupshup: `payload.id` is the send-API id only for `enqueued` and sync `failed`. For `sent`, `delivered`, `read`
     and async `failed`, the send-API id is in `payload.gsId` and `payload.id` is the WhatsApp id.
   - Effect: today's chat bubbles can never reach sent/delivered/read, and async failures (the 24-hour window) are
     never recorded.
   - Do: `key = payload.get("gsId") or payload.get("id")`.
   - Source: [G4](https://docs.gupshup.io/docs/message-events), [G5](https://partner-docs.gupshup.io/docs/message-events),
     and Glific [X1](https://github.com/glific/glific/blob/master/lib/glific_web/providers/gupshup/controllers/message_event_controller.ex).
   - Read-only check before the fix: Render logs contain `gupshup callback app=chat type=message-event body=…`
     (`_accept` logs 2000 chars), which shows `gsId` next to `id`.

2. **The same bug, copied into Task 9.**
   - Affects: Task 9's `apply_receipt` call in `_persist`.
   - Today: `apply_receipt(conn, payload["id"], …)`.
   - Gupshup: same as Delta 1.
   - Effect: every campaign recipient would stop at `sent`. Delivered, read and async failures (131026/131049/131050)
     would never be counted.
   - Do: pass `payload.get("gsId") or payload.get("id")`. Add a test with a `delivered` event whose `id ≠ gsId`.
   - Source: [G4](https://docs.gupshup.io/docs/message-events).

3. **The template app must subscribe to Sent, Delivered and Read.**
   - Affects: Task 15 (setup notes) and the Task 10 manual verification.
   - Today: not mentioned anywhere.
   - Gupshup: only Enqueued and Failed are on by default. Read, Sent and Delivered "require subscription". For
     subscriptions created after 18 Feb 2025, FAILED (and BILLING) must be chosen explicitly.
   - Do: add a setup checklist (§4 table) to the notes, and verify on the first campaign.
   - Source: [G10](https://docs.gupshup.io/docs/webhooks-2), [G9](https://docs.gupshup.io/docs/subscriptions-and-notifications),
     [S3](https://support.gupshup.io/hc/en-us/articles/42866242419609).

4. **The template app's webhook must be payload version 2.**
   - Affects: Task 15 setup and `_accept`/`_persist`.
   - Today: assumes v2 implicitly.
   - Gupshup: version is chosen per subscription (2 or 3), and v3 is Meta's envelope, which `body.get("type")` can't read.
   - Do: in the setup notes, require v2 and check `"version": 2` in `/gupshup/recent` after setup. Optionally log a
     warning when a body has `entry`/`object` (v3) instead of `type`.
   - Source: [G17](https://partner-docs.gupshup.io/reference/setsubscription-api-v3), [G21](https://partner-docs.gupshup.io/docs/whatsapp-passthrough-apis-for-partners).

**HIGH: wrong or lost signals**

5. **`gsId` is not always present.**
   - Affects: Task 1 (models) and Task 9.
   - Today: matches only on the Gupshup id.
   - Gupshup: *"Events received after a week of sending the message will not have the GSID available"*. The MM Lite
     DLR example has no `gsId`, and MM Lite is the default route for v2 marketing templates on apps created from Aug 2025.
   - Do: add a nullable `whatsapp_id` column to `wa_campaign_recipients` (and `wa_messages`). Fill it from
     `enqueued.payload.payload.whatsappMessageId`, or from the first DLR's `payload.id` when the row matched by
     `gsId`. When `gsId` is absent, also match `payload.id` against `whatsapp_id`. The same column serves `context.id`
     in Delta 8.
   - Source: [G4](https://docs.gupshup.io/docs/message-events), [G23](https://partner-docs.gupshup.io/docs/marketing-messages-lite-mm-lite-api).

6. **The button-tap shape the plan tests is not the documented one.**
   - Affects: Task 9's `_text_of` and its tests.
   - Today: the tests use `{"title": "Yes", "id": "b1"}` for `quick_reply` and `{"text": "No"}` for `button_reply`.
   - Gupshup: a template tap is `payload.type ∈ {"quick_reply" (G3), "text" (G7)}` with
     `payload.payload = {"text": "<BUTTON_TEXT>", "type": "button", "postbackText": …}`. `title` belongs to session
     `button_reply`, which is undocumented and which we don't send.
   - Do: fixtures `{"text": "Yes", "type": "button", "postbackText": "x"}` with kind `"quick_reply"`, **and** the same
     inner payload with kind `"text"`. Keep the `title` fallback.
   - Source: [G3](https://docs.gupshup.io/reference/postback-text-support), [G7](https://docs.gupshup.io/docs/text).

7. **Button detection by `msg_type` misses the documented `"text"` variant.**
   - Affects: Task 9's `_persist` insert and the `RECIPIENTS_SQL` `button` filter.
   - Today: `FILTER (WHERE m.msg_type IN ('quick_reply','button_reply','button'))`, with `msg_type` stored as
     `payload.type`.
   - Gupshup: G7's tap arrives with `payload.type = "text"`, so it would be stored as `msg_type='text'` and never
     counted as a button.
   - Do: in `_persist`, when `inner.get("type") == "button"`, store `msg_type = "quick_reply"`. SQL and UI then see one value.
   - Source: [G7](https://docs.gupshup.io/docs/text).

8. **Exact button attribution is documented and can ship now.**
   - Affects: Task 9's `RECIPIENTS_SQL` and its ponytail note.
   - Today: time-based attribution, with a note to "replace … when the first real tap lands".
   - Gupshup: `context.gsId` is *"the Gupshup message-id … of the message the user has replied to"*, which is our
     `messageId`. `context.id` is that message's WhatsApp id.
   - Do: attribute a tap by `raw->'payload'->'context'->>'gsId' = r.gupshup_id`, else `->>'id' = r.whatsapp_id`, else
     the time rule. Optionally send `postbackTexts` (e.g. `"<campaign_id>:<index>"`) for an id that survives even
     without `context`.
   - Source: [G7](https://docs.gupshup.io/docs/text), [G6](https://docs.gupshup.io/docs/what-is-an-inbound-message),
     [G2](https://docs.gupshup.io/reference/sending-text-template).

9. **A 2xx is "submitted", not "sent".**
   - Affects: Task 7's `_send_one`, `send_template` tests, and the Task 9/10 funnel.
   - Today: the recipient becomes `status='sent'` on HTTP 2xx, the tests use `{"status": "success"}`, and the global
     constraint says `"status": "success"`.
   - Gupshup: the response is *"status as submitted"* (G1, G3) or `"success"` (G2). Real delivery is the later `sent`
     DLR, and per-recipient failures arrive afterwards as `failed` callbacks.
   - Do: keep the status-agnostic success check and add a `"submitted"` test. Either label the 2xx bucket "Accepted" in
     the UI, or add an `accepted` state below `sent` in `STATUS_RANK`/`RECEIPT_SQL` and let the DLR move it to `sent`.
     The plan's own `submitted` already means "claimed, outcome unknown", so don't reuse that word.
   - Source: [G1](https://docs.gupshup.io/docs/template-messages), [G2](https://docs.gupshup.io/reference/sending-text-template),
     [G3](https://docs.gupshup.io/reference/postback-text-support).

10. **Rate-limit and server errors are treated as permanent.**
    - Affects: Task 7's `send_template` and `_send_one`.
    - Today: every non-2xx except a network error returns `{"ok": False}` without `transient`, so the row becomes `failed`.
    - Gupshup: `429 {"message":"Too Many Requests","status":"error"}` is documented on `/wa/api/v1/msg`. Code 4001 says
      *"Please stop sending messages"*. Meta 130429 and 131056 say retry later.
    - Do: treat HTTP 429 and 5xx as transient. Put the claimed row back to `queued` (Gupshup refused it, so nothing was
      sent) and back the loop off. On a 4001 failed event, pause the campaign.
    - Source: [G14](https://docs.gupshup.io/reference/session-text-message), [G13](https://docs.gupshup.io/docs/error-and-status-messages),
      [M1](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes).

11. **Keep the failure code, and stop the campaign on campaign-level codes.**
    - Affects: Task 9's `apply_receipt`, and Task 7/9 campaign state.
    - Today: stores only `reason`, and each recipient fails on its own.
    - Gupshup: `failed` carries `payload.payload.code` and `reason`. Template- and account-level codes (132000, 132001,
      132012, 132015, 132016, 4003, 4005, 1003, 131042, 131031, 131048) mean every later recipient will fail too.
    - Do: store `error = f"{code}: {reason}"`; no schema change is needed. When such a code arrives, pause the campaign
      with that reason, so a paused template or an empty wallet doesn't burn the whole list.
    - Source: [G4](https://docs.gupshup.io/docs/message-events), [G13](https://docs.gupshup.io/docs/error-and-status-messages),
      [M1](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes).

12. **The opt-out signals Gupshup and Meta actually send are ignored.**
    - Affects: Task 12's `_persist`, `OPT_OUT_SQL` and `is_stop`.
    - Today: only a typed `STOP` text opts a number out.
    - Gupshup/Meta: neither processes a typed STOP. Meta's opt-out is the "Offers and announcements" stop control. It
      arrives on Gupshup v2 as `type: "preference-event"` with `payload.payload.user_preferences[].value == "stop"`
      (or `"resume"`) and `wa_id`. Afterwards, marketing sends fail with **131050**, which Meta says never to retry.
    - Do: (a) add a `preference-event` branch: `stop` runs `OPT_OUT_SQL` on `wa_id[-10:]`, and `resume` is a product
      decision (suggest clearing `opted_out` only if it came from a preference event); (b) treat a `failed` with code
      131050 as opted out; (c) keep typed STOP as our own policy. Optionally treat a tap on a template's designated
      opt-out button as STOP (`is_stop("Stop promotions")` is false today).
    - Source: [M6](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/marketing-templates),
      [M4](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/user_preferences),
      [G20](https://partner-docs.gupshup.io/docs/bsuid), [S1](https://support.gupshup.io/hc/en-us/articles/35183519921689).

**MEDIUM: robustness**

13. **Duplicate deliveries are not idempotent.**
    - Affects: existing `_persist` (`message` branch), Task 9's reply counts and Task 12.
    - Today: every inbound callback inserts a row, and `gupshup_id` is indexed but not unique.
    - Gupshup: a callback not acked 2xx within 10 s is retried.
    - Do: skip the insert when a row with the same inbound `payload.id` already exists. A partial unique index on
      `gupshup_id WHERE direction='in'` works, or an existence check. Receipts are already idempotent through the
      forward-only rank.
    - Source: [G11](https://docs.gupshup.io/docs/what-is-a-webhook).

14. **`wa_messages.status` is not forward-only.**
    - Affects: existing `_persist`.
    - Today: an unconditional `status = payload.type`.
    - Gupshup: *"The order of these notifications in your app may not reflect the actual timing"*, and `read` may come
      without `delivered`.
    - Do: once Delta 1 makes DLRs match, apply the same rank guard to `wa_messages.status`, so a late `delivered`
      never overwrites `read`.
    - Source: [G4](https://docs.gupshup.io/docs/message-events).

15. **The existing comment misstates where 24-hour-window failures appear.**
    - Affects: existing `gupshup_send`, and Task 8 (reply from the right app).
    - Today: the comment says *"the usual cause is the 24-hour window having closed — Gupshup says so here"*, meaning
      in the HTTP response.
    - Gupshup: the HTTP response is 2xx "submitted". The 24 h failure is an async `failed` event (code 470 on-prem /
      131047 Cloud) keyed by `gsId`.
    - Do: fix the comment. Task 8's "sending from the wrong number" failures only become visible once Delta 1 is done.
    - Source: [G4](https://docs.gupshup.io/docs/message-events), [M1](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes).

16. **The daily cap uses an IST calendar day; Meta's limit is a moving 24 h across the whole portfolio.**
    - Affects: Task 7's `SENT_TODAY_SQL` and the spec's §10 tier numbers.
    - Today: counts distinct `phone10` with `(sent_at AT TIME ZONE 'Asia/Kolkata')::date = today`. The spec says 250 → 1,000 → 10k.
    - Gupshup/Meta: *"unique WhatsApp user phone numbers … outside of a customer service window, within a moving 24-hour
      period"*, *"shared by all business phone numbers within a portfolio"*, with tiers 250 / **2,000** / 10,000 /
      100,000 / unlimited.
    - Do: count `sent_at > now() - interval '24 hours'`. With a calendar-day cap, sending N at 18:00 and N again at
      10:00 the next day passes our cap but puts 2N inside Meta's moving 24 h. Set `WA_DAILY_SEND_LIMIT` from WhatsApp
      Manager → Account tools → Messaging limits, and update the spec's tier list.
    - Source: [M2](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits).

17. **Template registration needs the right id, and refuses media headers.**
    - Affects: Task 2's `wa_templates` form and its help text.
    - Today: the form asks for "the id Gupshup's template send API takes".
    - Gupshup: it is the Gupshup template **UUID** (`id` in Get-all-templates). It is not `elementName` and not Meta's
      numeric `externalId`. The language is fixed by that id, and media/location-header templates need a `message`
      field we don't send.
    - Do: show a hint and validate UUID shape. Refuse, or warn on, media-header templates. Warn that header-variable
      ordering is undocumented.
    - Source: [G15](https://docs.gupshup.io/reference/get-all-templates-for-an-app), [G1](https://docs.gupshup.io/docs/template-messages).

18. **Retry should depend on the failure code.**
    - Affects: Task 7's `retry_recipient`.
    - Today: any `failed` or `submitted` row can be re-queued.
    - Gupshup/Meta: 131050 means *"Do not retry"*. For 131049, *"wait at least 24 hours"*, and retries inside 24 h can
      extend the block. 1002 means no WhatsApp.
    - Do: refuse a retry for 131050 and 1002, and refuse or warn for 131049 inside 24 h (409 with the reason).
    - Source: [M1](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes),
      [M7](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/marketing-templates/per-user-limits).

19. **A sync `failed` may arrive before the row is written.**
    - Affects: Task 7's `_send_one` and Task 9's receipts.
    - Today: `gupshup_id` is written in a transaction after the HTTP call returns.
    - Gupshup: events are delayed about 5 s *"to ensure that users have enough time to persist the original message-id"*.
    - Do: keep that write fast, since it already happens right after the call. If `apply_receipt` matches 0 rows for a
      `failed`/`enqueued`, retry once after about 10 s in the background task, otherwise the row stays `sent` forever.
      Low risk, cheap fix.
    - Source: [G6](https://docs.gupshup.io/docs/what-is-an-inbound-message).

**LOW: hygiene and config**

20. **Opt-in.** Affects: none (spec/plan). Today: nothing calls an opt-in API, which is correct. Gupshup: the opt-in
    service is sunset and doesn't exist for apps created after Aug 2025. Do: nothing; keep it that way. Source:
    [S1](https://support.gupshup.io/hc/en-us/articles/35183519921689), [S3](https://support.gupshup.io/hc/en-us/articles/42866242419609).

21. **Configuration values.** Affects: Task 1 config and the Task 7 test fixtures.
    - `GUPSHUP_TEMPLATE_SOURCE_NUMBER` must be digits-only E.164 (`91…`, no `+`).
    - `GUPSHUP_TEMPLATE_APP_NAME` is the Gupshup app name, which can't contain spaces. The fixture `"OH Templates"` is
      unrealistic but harmless.
    - Set `GUPSHUP_TEMPLATE_WEBHOOK_SECRET` before adding the URL.
    - Source: [G1](https://docs.gupshup.io/docs/template-messages), [quickstart](https://docs.gupshup.io/docs/quickstart-create-and-configure-access-api).

22. **"Read" is a lower bound.** Affects: Task 10 UI. Gupshup: *"Read notifications will only be available for users
    who have read receipts enabled."* Do: add a tooltip on the Read box. Source: [G4](https://docs.gupshup.io/docs/message-events).

---

## Addendum (1 Oct, controller): template parameter text

Meta refuses a template parameter that contains a **newline, a tab, or more than four consecutive spaces**, with
error **132018** ("There was an issue with the parameters in your template" — *"Param text cannot have
new-line/tab characters or more than 4 consecutive spaces"*). The send API still answers 2xx; the refusal is a
per-recipient `failed` callback. Flatten every value to one line before it is stored or sent (Task 4's `build`).
**Field-confirmed**, not on a Gupshup page: [Pabbly forum](https://forum.pabbly.com/threads/erro-cannot-have-new-line-tab-characters-or-more-than-4-consecutive-space-whatsapp-clound-api.6449/),
[opencouncil PR #780](https://github.com/schemalabz/opencouncil/pull/780).
