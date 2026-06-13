# Job-search-assistant

## Vercel environment variables

Configure these variables for the Vercel project:

- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY`: server-only service role key from the Supabase
  project API settings
- `GEMINI_API_KEY`: Gemini API key used to parse and score resumes

Do not expose `SUPABASE_SERVICE_ROLE_KEY` in browser code or commit it to Git.
After changing an environment variable in Vercel, redeploy the project.
