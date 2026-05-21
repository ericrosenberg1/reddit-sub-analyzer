# Sentry — Reddit Sub Analyzer

Project: `rosenberg-digital/reddit-sub-analyzer` · platform `python`

## Activation

Set `REDDIT_ANALYZER_SENTRY_DSN` in the app's environment (e.g. `.env`):

```
REDDIT_ANALYZER_SENTRY_DSN=https://a30709f9f1462639a11432faa2f47759@o4507525754060800.ingest.us.sentry.io/4511429854822400
```

Django integration auto-captures unhandled exceptions and slow requests.
Sentry is a no-op if the var is unset.
