# Service account for the pipeline

Everything in `scripts/` authenticates as a dedicated non-human account, not
a personal login. Ask whoever manages your Atlassian org (or Rovo, if it has
admin-side actions available) to do this:

1. **Provision the identity** via your IdP (Okta/Azure AD) -- e.g.
   `svc-qa-automation@<company>.com`. Not a personal account.
2. **Grant product access** in `admin.atlassian.com`: Jira + Confluence,
   added to the QA/automation project role in the relevant project(s).
3. **Generate credentials:**
   - Atlassian API token: `id.atlassian.com/manage-profile/security/api-tokens`
     -- this is `JIRA_API_TOKEN` in GitHub Secrets, paired with the service
     account's email as `JIRA_EMAIL`.
   - Xray API Key (Client ID + Secret): **Jira Settings → Apps → Xray →
     API Keys** -- these are `XRAY_CLIENT_ID` / `XRAY_CLIENT_SECRET`.
4. **Store + rotate:** both go straight into GitHub Environment Secrets (see
   main README for the full list) -- never into a file in this repo. Set a
   rotation reminder; classic tokens like these don't expire on their own.
