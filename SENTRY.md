# Sentry — Reddit Sub Analyzer

Project: `rosenberg-digital/reddit-sub-analyzer` · platform `python`

## Activation

Set `REDDIT_ANALYZER_SENTRY_DSN` in the app's environment (e.g. `.env`):

```
REDDIT_ANALYZER_SENTRY_DSN=https://...
```

Django integration auto-captures unhandled exceptions and slow requests.
Sentry is a no-op if the var is unset.
