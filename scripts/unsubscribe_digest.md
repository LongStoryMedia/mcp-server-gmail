# Scheduled Task: Unsubscribe from Marketing/Newsletter Emails and Clean Up

## Purpose
Automatically find and unsubscribe from marketing, promotional, and newsletter emails that contain unsubscribe links, then delete those emails. Exclude school-related messages (ParentSquare/education senders).

## Workflow

### Phase 1: Discover emails with unsubscribe links
1. Use `grep_email` tool to search email bodies for unsubscribe patterns across multiple query batches:
   - Query: `"unsubscribe"` with pattern `"unsubscribe|opt out|manage preferences|email preferences|notification preferences|stop receiving"` (max 500 results)
   - Query: `"from:linkedin.com"` with pattern `"unsubscribe"` (max 500)
   - Query: `"from:substack.com OR from:techcrunch.com OR from:theverge.com OR from:reddit.com OR from:venmo.com OR from:stripe.com OR from:aws.amazon.com OR from:github.com OR from:producthunt.com OR from:medium.com OR from:hubspot.com OR from:turbo.scribe OR from:loops.so OR from:google.com"` with pattern `"unsubscribe"` (max 500)
   - Query: `"from:reddit.com OR from:news.ycombinator.com OR from:techcrunch.com OR from:theverge.com OR from:wired.com OR from:arstechnica.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:hubspot.com OR from:zoho.com OR from:salesforce.com OR from:pipedrive.com OR from:intercom.com OR from:drift.com OR from:zapier.com OR from:ifttt.com OR from:notion.so OR from:figma.com OR from:canva.com OR from:adobe.com OR from:dribbble.com OR from:behance.net OR from:pocket.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:zoom.us OR from:slack.com OR from:trello.com OR from:asana.com OR from:dropbox.com OR from:evernote.com OR from:spotify.com OR from:netflix.com OR from:venmo.com OR from:stripe.com OR from:github.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:zillow.com OR from:redfin.com OR from:realtor.com OR from:century21.com OR from:remax.com OR from:compass.com OR from:trulia.com OR from:homes.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:ubereats.com OR from:doordash.com OR from:grubhub.com OR from:postmates.com OR from:seamless.com OR from:panera.com OR from:chipotle.com OR from:starbucks.com OR from:dominos.com OR from:pizzahut.com OR from:papajohns.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:chase.com OR from:bankofamerica.com OR from:usbank.com OR from:wellsfargo.com OR from:citi.com OR from:capitalone.com OR from:amex.com OR from:discover.com OR from:paypal.com OR from:venmo.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:target.com OR from:walmart.com OR from:bestbuy.com OR from:macy.com OR from:nordstrom.com OR from:kohls.com OR from:costco.com OR from:ikea.com OR from:wayfair.com OR from:overstock.com OR from:homedepot.com OR from:lowes.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:booking.com OR from:expedia.com OR from:hotels.com OR from:kayak.com OR from:trivago.com OR from:airbnb.com OR from:vrbo.com OR from:opentable.com OR from:yelp.com OR from:thefork.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:nytimes.com OR from:wsj.com OR from:reuters.com OR from:apnews.com OR from:cnn.com OR from:foxnews.com OR from:npr.org OR from:bbc.com OR from:politico.com OR from:theatlantic.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:uber.com OR from:lyft.com OR from:ford.com OR from:tesla.com OR from:nissan.com OR from:hyundai.com OR from:honda.com OR from:toyota.com OR from:bmw.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:spotify.com OR from:netflix.com OR from:hulu.com OR from:disney.com OR from:hbo.com OR from:peacocktv.com OR from:paramount.com OR from:apple.com OR from:itunes.com OR from:music.apple.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:exploreschools.com OR from:collegeboard.org OR from:fafsa.ed.gov OR from:fastweb.com OR from:chegg.com OR from:quizlet.com OR from:coursehero.com OR from:coursera.org OR from:udemy.com OR from:edx.org OR from:khanacademy.org OR from:linkedin.com/learning"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:spring.io OR from:bitbucket.org OR from:npmjs.com OR from:pypi.org OR from:dev.to OR from:digitalocean.com OR from:cloud.google.com OR from:azure.microsoft.com OR from:oracle.com OR from:mongodb.com OR from:elastic.co OR from:redis.io OR from:postgresql.org OR from:confluent.io OR from:databricks.com OR from:snowflake.com OR from:hashicorp.com OR from:kubernetes.io OR from:docker.com"` with pattern `"unsubscribe"` (max 200)
   - Query: `"from:aws.amazon.com OR from:amazon.com OR from:shopify.com OR from:mailchimp.com OR from:constantcontact.com OR from:sendgrid.com OR from:circleci.com OR from:circle.com OR from:travis-ci.org OR from:circle-staging.com"` with pattern `"unsubscribe"` (max 200)

2. Deduplicate results by email ID. Build a list of unique senders with their unsubscribe URLs.

### Phase 2: Filter out excluded senders
Exclude any emails from:
- ParentSquare (`@parentsquare.com`) - school communications
- Any sender containing "school", "education", "university", "college", "academy" in the domain or sender name
- Any sender explicitly marked as educational

### Phase 3: Unsubscribe via Playwright
For each unique sender (not excluded):

1. **Direct unsubscribe links** (URLs found in email body):
   - Navigate to the unsubscribe URL using `browser_navigate`
   - Take a snapshot to check the page state
   - If a button like "Unsubscribe" or "Unsubscribe from all" is visible, click it
   - Verify the page shows a confirmation (e.g., "Resubscribe" button or success message)
   - Log success/failure for each sender

2. **Senders requiring login** (LinkedIn, RedCareers, etc.):
   - Navigate to the provider's email preferences page (e.g., `https://www.linkedin.com/comm/psettings/email`)
   - If a login page appears, skip and log as "requires manual login"
   - If already logged in or preferences page is accessible, navigate to unsubscribe options

3. **Track results**:
   - Successfully unsubscribed: list of senders
   - Requires manual login: list of senders + URLs
   - Failed/error: list of senders + error details
   - Skipped (excluded): list of senders

### Phase 4: Delete the emails
After unsubscribing, use `delete_emails` tool to trash all emails from the successfully unsubscribed senders:
- Query: `"from:sender1@example.com OR from:sender2@example.com OR from:sender3@example.com"`
- Set `dry_run: false`, `max_results: 500`
- Report how many were deleted

### Phase 5: Report
Output a summary:
```
=== Unsubscribe Digest ===
Successfully unsubscribed: [list of senders]
Requires manual login: [list of senders with URLs]
Failed: [list of senders with errors]
Emails deleted: [count]
School/education emails skipped: [count]
```

## Notes
- Run this on a schedule (e.g., weekly) to catch new marketing emails
- The `grep_email` tool may timeout on very large queries - use smaller batch queries if needed
- Some unsubscribe links expire after use - if a link returns 404, try the provider's main email preferences page
- Always verify unsubscribe confirmation before moving to the next sender
- Never unsubscribe from or delete school/educational communications
