# Outreach Templates

Outreach templates are drafts for human review. They should not be sent automatically.

## Template Rules

- Reference a real signal.
- Keep the message short.
- Avoid exaggerated claims.
- Avoid fake familiarity.
- Use clear next steps.
- Do not invent facts.

## Initial Outreach

```text
Hi, I found {{company_name}} while reviewing {{source_context}}.

The main opportunity I noticed is {{marketing_gap}}.

A useful first step could be {{recommended_offer}}.

Worth a quick look?
```

## Follow-Up

```text
Hi, following up on my note about {{recommended_offer}}.

The reason I thought it might be relevant: {{priority_reason}}.

Should I send over the short version?
```

## Reply Handling

Positive reply:

- Confirm interest.
- Ask one clarifying question.
- Offer a next step.

Negative reply:

- Acknowledge.
- Close politely.
- Update status to `closed_lost` or `skip`.

## Personalization Fields

- `company_name`
- `business_type`
- `location`
- `priority_reason`
- `marketing_gap`
- `recommended_offer`
- `source`
- `signal`
