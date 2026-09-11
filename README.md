# Daily LinkedIn brief

Every weekday morning this reads the last 72 hours of enterprise AI news,
scores it against a written definition of your audience, drafts three LinkedIn
posts in your writing style, and emails them to you.

It publishes nothing. You read the email, pick one, edit it, and post it
yourself.

---

## Contents

1. [The one thing to understand first](#1-the-one-thing-to-understand-first)
2. [What you need before starting](#2-what-you-need-before-starting)
3. [Get your two API keys](#3-get-your-two-api-keys)
4. [Set it up on your computer](#4-set-it-up-on-your-computer)
5. [Test it in three stages](#5-test-it-in-three-stages)
6. [Put it on a daily schedule](#6-put-it-on-a-daily-schedule)
7. [Using it day to day](#7-using-it-day-to-day)
8. [Every file, explained](#8-every-file-explained)
9. [Every setting, explained](#9-every-setting-explained)
10. [When something breaks](#10-when-something-breaks)

---

## 1. The one thing to understand first

**Your API keys go in two separate places, and neither one copies to the other.**

This is the single most common source of confusion, so it is worth being
completely clear about it.

| Where | What it is | Used when |
|---|---|---|
| A file called `.env` on your computer | A plain text file you create in step 4 | You run the tool manually from your terminal |
| GitHub repository secrets | Boxes in the GitHub website, not a file | The scheduled 6:30am run happens |

The `.env` file is deliberately never uploaded to GitHub. It is listed in
`.gitignore`, which tells git to ignore it. That is intentional and correct:
API keys must never be committed to a repository, even a private one.

So you will enter the same keys twice. Once in `.env` for local runs, once in
GitHub secrets for scheduled runs. If the scheduled run fails while your local
run works, this is almost always why.

---

## 2. What you need before starting

**Python 3.10 or newer.** Check with:

```bash
python3 --version
```

If that errors or shows something below 3.10, install Python from python.org.

**Git.** Check with:

```bash
git --version
```

**About 20 minutes**, mostly waiting for a DNS record to verify.

**A credit card for Anthropic.** The API is pay as you go and this costs a few
dollars a month, but you do need a card on file. Resend needs no card.

---

## 3. Get your two API keys

### 3a. Anthropic API key

This is what writes the posts.

1. Go to **console.anthropic.com** and sign in or create an account
2. This is a separate account from claude.ai. A Claude Pro subscription does
   not give you API credit, and API credit does not give you Claude Pro
3. Click **Billing** in the left sidebar, add a payment method, and add credit.
   Ten dollars will run this for a couple of months
4. Click **API keys** in the left sidebar, then **Create Key**
5. Name it something like `linkedin-brief`
6. Copy the key. It starts with `sk-ant-`

**Copy it now and paste it somewhere safe.** Anthropic shows the key exactly
once. If you lose it, delete that key and make a new one.

### 3b. Resend API key

This is what sends the email.

1. Go to **resend.com** and click Get Started. Signing in with GitHub is fastest
2. In the left sidebar click **API Keys**, then **Create API Key**
3. Name it `linkedin-brief`
4. For Permission choose **Sending access**, not Full access. This key only
   ever needs to send email, so do not give it more than that
5. Copy the key. It starts with `re_`

Resend's free tier is 3,000 emails a month capped at 100 a day. This sends about
22 a month, so you will never pay for it.

### 3c. Decide your sender address

You have two options and you can start with the first and move to the second
later.

**Option A, works immediately, zero setup.** Use `onboarding@resend.dev` as
your sender. Resend allows this without any verification, but it will *only*
deliver to the email address you signed up to Resend with. Perfectly fine for
getting started.

**Option B, proper sender, about 10 minutes.** Send from your own domain.

1. In Resend click **Domains**, then **Add Domain**
2. Enter your domain, for example `latentit.com`
3. Resend shows you two or three DNS records to add, of type TXT and CNAME
4. Go to wherever your domain's DNS is managed, which is your registrar or
   Cloudflare, and add each record exactly as shown
5. Back in Resend, click **Verify**. This usually takes a few minutes, sometimes
   up to an hour
6. Once verified, your sender can be anything on that domain, such as
   `brief@latentit.com`

Option B is worth doing if the domain is the same one your business email uses,
because a verified domain protects your sending reputation.

---

## 4. Set it up on your computer

### 4a. Get the code

If you have not cloned the repository yet:

```bash
git clone https://github.com/YOUR-USERNAME/linkedin-brief.git
cd linkedin-brief
```

If you already have it, make sure it is current:

```bash
cd linkedin-brief
git pull
```

### 4b. Install the dependencies

```bash
pip install -r requirements.txt
```

If `pip` is not found, try `pip3` instead. If you get a permissions error or an
"externally managed environment" message, use a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate       # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

If you use a virtual environment, you must run `source venv/bin/activate` in
each new terminal window before running the tool.

### 4c. Create your .env file

**This is the file where your API keys go for local runs.**

The repository includes a template called `.env.example`. Copy it:

```bash
cp .env.example .env
```

Now open `.env` in any text editor. Notice the name starts with a dot, which
makes it hidden in Finder and in most file browsers. Open it from your editor
directly, or use `nano .env` in the terminal.

Fill in these four lines. Everything else in the file can stay as it is.

```
ANTHROPIC_API_KEY=sk-ant-paste-your-real-key-here
RESEND_API_KEY=re_paste-your-real-key-here
EMAIL_FROM=onboarding@resend.dev
EMAIL_TO=your-email@example.com
```

Rules for editing this file:

- No spaces around the `=` sign. `KEY=value` is right, `KEY = value` is wrong
- No quotes around the values
- `EMAIL_FROM` is `onboarding@resend.dev` unless you completed Option B above,
  in which case use your verified address such as `brief@latentit.com`
- `EMAIL_TO` is where the brief lands. If you chose Option A, this **must** be
  the address you signed up to Resend with, or nothing will arrive
- For more than one recipient, separate with commas and no spaces

Save the file.

### 4d. Confirm .env is being ignored by git

```bash
git status
```

`.env` must **not** appear anywhere in that output. If it does, something is
wrong with `.gitignore` and you should fix it before committing anything.

---

## 5. Test it in three stages

Run these in order. Each one tests more than the last.

### Stage 1: the news sources. Free, no API calls.

```bash
python src/main.py --sources-only
```

Takes about five seconds and costs nothing. It fetches Hacker News and your RSS
feeds and prints everything it found.

**Expect some feeds to fail.** The starter list in `config/feeds.txt` includes
publications whose RSS URLs may have moved. A failure looks like:

```
  Feed 'Insurance Times' failed: HTTP Error 404: Not Found
```

Open `config/feeds.txt`, delete the lines that failed, and add feeds you
actually read. The format is `Label | URL`, one per line.

You should end up seeing 20 to 45 items. If you see zero, check your internet
connection and that `USE_SOURCE_FEEDS=true` in `.env`.

### Stage 2: a dry run. Costs a few cents, sends no email.

```bash
python src/main.py --dry-run
```

Takes 60 to 120 seconds because it runs about a dozen web searches. You will see
the candidate stories print with their scores:

```
Excluding 0 recently offered topics.
Collected 31 unique items from HN and RSS.
Research returned 5 candidates.
  [9] Accenture and Google Cloud launch 1,000-engineer agentic AI group
  [7] Deloitte data shows 89% of agent pilots never reach production
  [4] Mistral raises 3B euro
```

Then open the preview:

```bash
open data/preview.html          # on Windows: start data/preview.html
```

That HTML file is exactly what the email will look like. Read the drafts
properly. If they are wrong, this is the moment to fix it, by editing
`config/icp.md` if the wrong topics were chosen, or `config/style_guide.md` if
the writing is off. Then run the dry run again.

**Do this loop two or three times before going further.** Tuning these two
files is where the value is.

### Stage 3: send it for real.

```bash
python src/main.py
```

Same as the dry run, then actually sends. You should see:

```
Resend accepted the message. id=3f1b-...
Sent to your-email@example.com.
History updated.
```

Check your inbox. Also check spam on the first send, and mark it as not spam if
it landed there.

---

## 6. Put it on a daily schedule

Everything so far runs only when you type a command. This step makes it run by
itself at 6:30am on weekdays, using GitHub Actions, which is free.

### 6a. Push your code

```bash
git add .
git commit -m "Configure daily brief"
git push
```

Run `git status` first and confirm `.env` is not in the list.

If you have not created the repository yet:

```bash
git init
git add .
git commit -m "Daily LinkedIn brief"
gh repo create linkedin-brief --private --source=. --push
```

**Keep the repository private.** Your audience definition and writing style
guide are commercially useful to a competitor.

### 6b. Add your secrets to GitHub

**This is the second place your keys go. It is a website form, not a file.**

1. Open your repository on github.com
2. Click **Settings**, the tab along the top of the repository, not your account
   settings
3. In the left sidebar click **Secrets and variables**, then **Actions**
4. Click **New repository secret**
5. Add each of these four, one at a time. The Name must match exactly,
   including capitals

| Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your `sk-ant-...` key |
| `RESEND_API_KEY` | your `re_...` key |
| `EMAIL_FROM` | the same sender as in your `.env` |
| `EMAIL_TO` | the same recipient as in your `.env` |

You cannot view a secret after saving it, only replace it. That is normal.

### 6c. Test the scheduled run

1. Click the **Actions** tab
2. If prompted to enable workflows, click to enable them
3. Click **Daily LinkedIn brief** in the left sidebar
4. Click **Run workflow** on the right
5. **Tick the dry run box**, then click the green Run workflow button
6. Wait about two minutes, then click into the run to read the log

If it is green, your secrets are correct. Now run it again without ticking dry
run, and check your inbox.

From then on it runs itself at 01:00 UTC, which is 06:30 India time, Monday to
Friday. GitHub's scheduler sometimes fires up to 20 minutes late under load,
which is why it is set early.

### 6d. Turn on failure notifications

The realistic failure is not a crash you notice, it is the job dying quietly and
you not noticing for three weeks.

Go to github.com/settings/notifications and confirm **Actions** notifications
are on for failed workflows. This is on by default. Leave it on.

---

## 7. Using it day to day

The brief arrives each weekday morning with up to three options. Each one shows:

- The draft post, ready to copy
- A relevance score out of 10
- Why that angle is different from what others will post
- A suggested first comment holding the source link
- The sources, labelled primary, trade press or vendor blog
- A link to the Hacker News discussion when there is one
- Any warnings, such as a statistic that came from a vendor with an incentive

**How to post one.** Copy the draft text exactly, line breaks included. Paste it
into LinkedIn. Post the source link as the first comment, not in the post body,
because links in the body cut reach substantially.

**Some mornings you will get "nothing worth posting today."** That is the tool
working correctly. If no story scores 6 or above it refuses to pad. Skipping a
day costs you nothing. Posting filler under your own name does.

**Before posting anything with a number in it,** click through to the source.
The tool labels source quality but cannot judge whether a statistic is sound.
Your name goes on the post.

### Tuning it

Two files, both plain English, no code:

**`config/icp.md`** controls which stories get chosen. If briefs keep surfacing
funding rounds and chip news, add those to the "score low" section. If it is too
narrow, widen the list of verticals.

**`config/style_guide.md`** controls how the posts read. Every hard rule in here
is enforced twice, once in the instructions to the model and once by a checker
in the code. If a phrase keeps slipping through, add it to `BANNED_PATTERNS`
near the top of `src/draft.py`.

Two more, also plain text:

**`config/feeds.txt`** is your RSS list. **`config/hn_queries.txt`** is what
gets searched on Hacker News.

**`config/blocklist.txt`** drops RSS items by title even when they matched a
keyword. Webinar listings, podcast episodes and award roundups mention AI
constantly while containing no story to post about. Only titles are checked, so
an article that mentions a webinar in passing still gets through.

**`config/keywords.txt`** filters RSS items. An item must match one of these
terms in its title or summary to enter the pool. This matters most for vertical
trade press: an insurance feed publishes far more about catastrophes and market
movements than about technology, and without the filter that noise crowds out
the story you wanted. Terms of four characters or fewer match as whole words,
so "AI" does not match "Airlines". Longer terms match as prefixes, so "agent"
catches "agents" and "agentic". Delete every line to turn filtering off.

After editing any of these, run `python src/main.py --sources-only` or
`--dry-run` to see the effect before the next scheduled send.

### Watch the scores for the first fortnight

If almost everything comes back scored 8 or 9, the model is being agreeable
rather than honest. Sharpen the "score low" section of `config/icp.md` until the
scores spread out. Honest scoring is what makes the "nothing today" answer
trustworthy.

---

## 8. Every file, explained

### Files you will edit

| File | What it does |
|---|---|
| `.env` | **Your API keys for local runs.** You create this in step 4c. Never committed to git |
| `config/icp.md` | Defines your audience and how stories are scored |
| `config/style_guide.md` | Defines how the posts are written |
| `config/feeds.txt` | Your RSS feed list, `Label \| URL` per line |
| `config/hn_queries.txt` | Hacker News search terms, one per line |

### Files you will not normally touch

| File | What it does |
|---|---|
| `src/main.py` | Runs everything in order, handles the command line flags |
| `src/sources.py` | Fetches Hacker News and RSS, concurrently, deduplicated |
| `src/research.py` | Sends the pool to Claude with web search, gets scored candidates |
| `src/draft.py` | Writes the posts, then checks them against the style rules |
| `src/mailer.py` | Builds the HTML email and sends it through Resend |
| `src/history.py` | Remembers past topics so the brief does not repeat itself |
| `src/config.py` | Reads settings from `.env` or from GitHub secrets |
| `src/claude_client.py` | Talks to the Anthropic API, retries on failure |
| `.github/workflows/daily-brief.yml` | The 6:30am schedule |
| `data/history.json` | Topics offered recently. Managed automatically |
| `requirements.txt` | The two Python packages needed |
| `.env.example` | The template you copy to make `.env` |
| `.gitignore` | Stops `.env` being committed |

---

## 9. Every setting, explained

All of these live in `.env`. The four in bold are required.

| Setting | Default | What it does |
|---|---|---|
| **`ANTHROPIC_API_KEY`** | none | Your `sk-ant-...` key |
| **`RESEND_API_KEY`** | none | Your `re_...` key |
| **`EMAIL_FROM`** | `onboarding@resend.dev` | Sender address |
| **`EMAIL_TO`** | none | Recipient. Comma separated for several |
| `EMAIL_PROVIDER` | `resend` | Set to `smtp` to use Gmail instead |
| `RESEARCH_MODEL` | `claude-sonnet-5` | Model that finds and scores stories |
| `DRAFT_MODEL` | `claude-opus-5` | Model that writes the posts |
| `MAX_SEARCHES` | `12` | Web searches per run. Lower is cheaper |
| `NUM_OPTIONS` | `3` | Drafts per email |
| `DEDUPE_WINDOW_DAYS` | `21` | Days before a topic can be offered again |
| `MAX_STORY_AGE_HOURS` | `72` | Ignore anything older than this |
| `USE_SOURCE_FEEDS` | `true` | Set `false` to skip HN and RSS entirely |
| `HN_MIN_POINTS` | `15` | Ignore Hacker News stories below this |
| `MAX_ITEMS_PER_SOURCE` | `5` | Items kept per query or feed |
| `MAX_POOL_ITEMS` | `60` | Hard cap on items sent to the model |

### Using Gmail instead of Resend

Set `EMAIL_PROVIDER=smtp` and add these four. Gmail requires an App Password,
generated at Google Account, Security, App passwords, which needs 2-Step
Verification enabled first. Your normal password will not work.

```
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-16-character-app-password
```

---

## 10. When something breaks

| What you see | What it means |
|---|---|
| `Missing required environment variables: ANTHROPIC_API_KEY` | `.env` does not exist, or the key line has a typo. Check there are no spaces around `=` |
| `Resend returned 403: The domain is not verified` | `EMAIL_FROM` uses a domain you have not verified. Use `onboarding@resend.dev` or finish domain verification |
| `Resend returned 401` | The Resend key is wrong. It should start with `re_` |
| Email sends but never arrives | If using `onboarding@resend.dev`, `EMAIL_TO` must be the address you signed up to Resend with. Otherwise check spam |
| `anthropic.AuthenticationError` | The Anthropic key is wrong or has no credit. Check Billing at console.anthropic.com |
| `Feed 'X' failed: HTTP Error 404` | That RSS URL has moved. Delete the line from `config/feeds.txt` |
| `Nothing scored 6 or above` | Working as designed. Some days have no story worth posting |
| Local run works, scheduled run fails | Your GitHub secrets are missing or misspelled. They are separate from `.env`, see section 1 |
| `SSL: CERTIFICATE_VERIFY_FAILED` on macOS | Your Python has no root certificates. Run `pip install -r requirements.txt` to get `certifi`, which the code uses directly. If it persists, run `/Applications/Python 3.12/Install Certificates.command`, matching your version |
| `ModuleNotFoundError: No module named 'anthropic'` | Run `pip install -r requirements.txt`. If using a virtual environment, activate it first |
| No email for several days and no error | Check the Actions tab for red runs. Confirm GitHub failure notifications are on |
| `! [rejected] main -> main (fetch first)` | The scheduled job committed history since your last pull. Run `git pull` then push again |

### What it costs

Two Anthropic API calls per weekday. The research call is the expensive one
because web search pulls a lot of text. Roughly a few cents per run, so under
about 10 US dollars a month at 22 weekdays.

If that drifts higher, lower `MAX_SEARCHES` to 8, or set
`DRAFT_MODEL=claude-sonnet-5` and compare the writing quality for a week.

GitHub Actions is free for public repositories and gives 2,000 minutes a month
on private ones. This uses roughly two minutes a day, so about 44 a month.

Resend stays free at this volume.
