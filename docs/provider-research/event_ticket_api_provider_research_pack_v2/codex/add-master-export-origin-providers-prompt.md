# Codex prompt: Add master-export provider/origin references

We added a v2 provider research pack based on a scan of the Music Roadtrip master export.

Important:
- Do not import or bundle the master export itself.
- Do not make live API calls.
- Do not hardcode API keys.
- CitySpark is a paid licensed vendor API feed; keep live calls off until
  credentials and configuration are added, and keep provider records behind
  API Feed Review before app use.
- Concert records remain events and must never become POIs.

Use these new files:

- `MASTER_EXPORT_ORIGIN_SCAN.md`
- `data/master_export_provider_candidates.csv`
- `data/master_export_concert_domain_summary.csv`
- `provider_references/opendate.md`
- `provider_references/eventvesta.md`
- `provider_references/universe.md`
- `provider_references/outhouse_tickets.md`
- `provider_references/skiddle.md`
- `provider_references/venuepilot.md`
- `provider_references/biletix.md`
- `provider_references/ticketnetwork_mercury.md`
- `provider_references/tockify.md`
- `provider_references/humanitix.md`
- `provider_references/simpletix.md`
- `provider_references/ticketleap.md`
- `provider_references/showpass.md`
- `provider_references/holdmyticket.md`
- `provider_references/eventnoire.md`
- `provider_references/my805tix.md`
- `provider_references/tix_24.md`
- `provider_references/prekindle.md`
- `provider_references/speakeasygo.md`
- `provider_references/ovationtix_audienceview.md`
- `provider_references/timely.md`
- `provider_references/afton_tickets.md`

Goal:
Update the API feed review workbench and ticket-link classifier with source/domain recognition for these providers.

Implementation scope:
1. Add these provider/domain keys to the source taxonomy.
2. Add domain detection patterns for each provider.
3. Show these providers in API feed provenance/source-chain UI where detected.
4. Add ticket-link QA classifications:
   - event-specific platform page
   - affiliate redirect
   - calendar/source platform
   - ticketing platform with no public API docs
   - API candidate with official docs
   - no public API docs found
5. Do not build live connectors for providers with no public API docs.
6. For providers with docs, still keep connectors disabled unless credentials/config are supplied.
7. Add tests that the detected domains map to the correct provider keys.
8. Add tests that generic affiliate/redirect domains are flagged, not blindly trusted.
9. Update README/provider reference documentation.

Done when:
- The system recognizes all newly observed provider domains.
- API review and preview provenance can show these upstream/ticketing providers.
- Ticket-link classifier uses the new source/domain knowledge.
- No live API calls are added.
- No API keys are hardcoded.
- Tests pass, Ruff passes, Mypy passes.
