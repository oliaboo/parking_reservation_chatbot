# Testing Guardrails with the Chatbot

Guardrails block **sensitive data** in user messages (and redact it in bot responses). Use the examples below while chatting to see them in action.

## 1. Ensure guardrails are on

Default is on. To confirm or turn on:

- In `.env`: `ENABLE_GUARD_RAILS=true`
- Or leave unset (default is true).

---

## 2. Test in the chat (general questions)

Run the chatbot, log in with a nickname (e.g. `alice`), then try these as **general questions** (not during reservation).

### Blocked patterns (bot should refuse or ask you to rephrase)

| What you type | Why it's blocked |
|---------------|------------------|
| `What are your prices? My SSN is 123-45-6789` | SSN pattern (XXX-XX-XXXX) |
| `I need to pay. Card 4532-1234-5678-9012` | Credit card (4 groups of 4 digits) |
| `Contact me at john.doe@email.com for the receipt` | Email address |
| `Call me at 555-123-4567 to confirm` | US phone (XXX-XXX-XXXX) |

**Expected:** The bot replies with something like: *"Query contains potentially sensitive information. Please rephrase."* and does **not** answer using that message.

### Allowed (no sensitive data)

- `What are your prices?`
- `How many parking spaces do you have?`
- `Where are you located?`

---

## 3. Test during reservation

During the reservation flow the bot **allows** name, surname, car plate, and dates, but still blocks:

- **SSN** (e.g. `123-45-6789`)
- **Credit card** (e.g. `4532 1234 5678 9012`)

So you can try:

1. Say: `I want to reserve`
2. When asked for date, reply with something that includes a card number, e.g. `Charge my card 4532-1234-5678-9012 for 2025-03-15`

**Expected:** Message about sensitive information; you’re asked to provide only the date (no card).

---

## 4. Test response filtering (optional)

If the **model’s answer** accidentally contained an email or phone, the guardrails would **redact** it (replace with `[REDACTED]`) before showing it to you. That’s harder to trigger by normal questions; the unit tests cover it.

---

## 5. Quick checklist

- [ ] General query with SSN → blocked
- [ ] General query with credit card → blocked  
- [ ] General query with email → blocked
- [ ] General query with phone → blocked
- [ ] Normal question without sensitive data → answered
- [ ] Reservation date only (e.g. `2025-03-15`) → accepted
- [ ] Reservation reply with card/SSN → blocked, asked to give only date

To **disable** guardrails for debugging: set `ENABLE_GUARD_RAILS=false` in `.env` and restart the chatbot.
