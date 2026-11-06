# Reviewer sign-in

Reviewers sign in with an approved email address. Supabase handles email
verification and password resets. The reviewer server checks access before
returning documents, saved records, or downloads. Approved users share the same
workspace; this change does not move the existing SQLite database.

## Set up a local test

1. In a team-owned Supabase test project, enable email sign-in and **Confirm
   email**. Set the **Site URL** to `http://127.0.0.1:8000`. Use the team's SMTP
   sender to deliver emails to pilot users.
2. Set these links in the Supabase email templates. Keep the `#` so the token
   stays out of server access logs.

   **Confirm sign up**
   ```html
   <p><a href="{{ .SiteURL }}/#auth=confirm&amp;type=email&amp;token_hash={{ .TokenHash }}">Verify your email</a></p>
   ```

   **Reset password**
   ```html
   <p><a href="{{ .SiteURL }}/#auth=confirm&amp;type=recovery&amp;token_hash={{ .TokenHash }}">Reset your password</a></p>
   ```

3. In the terminal that will start the app, set these variables. Replace the
   example values with your test project's URL and **publishable** key, and
   the email addresses allowed to use the app. Keep configuration out of Git.

   ```bash
   export WARREN_SUPABASE_URL='https://your-project.supabase.co'
   export WARREN_SUPABASE_PUBLISHABLE_KEY='sb_publishable_your_key'
   export WARREN_PUBLIC_URL='http://127.0.0.1:8000'
   export WARREN_ALLOWED_EMAILS='reviewer@example.com,second-reviewer@example.com'
   ```

4. Start the app using the [reviewer setup commands](README.md#setup-and-launch).
   At **http://127.0.0.1:8000**, sign up with an approved address, open the
   verification link, choose **Continue**, and sign in. Try **Forgot password?**
   and check that you can sign in with the new password. Check that an unlisted
   email cannot open the workspace.

Without these variables, the local reviewer opens without a sign-in screen.
The automated tests use a fake provider. Test real email delivery with a
configured project and sample files before using client documents.

## Railway

Set the same four variables in Railway. Use the hosted HTTPS address for both
`WARREN_PUBLIC_URL` and the Supabase **Site URL**. The app requires auth settings
on Railway. Serve the built UI and API from the same address and point
`WARREN_DATA_DIR` at the service's persistent volume.
